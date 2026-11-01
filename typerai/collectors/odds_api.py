"""Kursy Ekstraklasy z The Odds API (docs/03, sekcje 3.2 i 3.3).

Jedno pobranie rynków głównych (1X2, gole, handicap) kosztuje 3 kredyty i obejmuje wszystkie
nadchodzące mecze. Rynki dodatkowe (BTTS, podwójna szansa) pobieramy tylko dla wybranych meczów.

Użycie:
    python -m typerai.collectors.odds_api --events     # terminarz nadchodzących meczów (bez kosztu)
    python -m typerai.collectors.odds_api              # terminarz + snapshot kursów głównych (3 kredyty)
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

import httpx

from typerai import config, db, teams
from typerai.matches import upsert_scheduled

BASE_URL = "https://api.the-odds-api.com/v4/sports/soccer_poland_ekstraklasa"
RAW_DIR = config.RAW_DIR / "odds_api"
MAIN_MARKETS = "h2h,totals,spreads"
EXTRA_MARKETS = "btts,double_chance"


def iso_utc(value: str) -> str:
    """'2026-11-07T14:30:00Z' -> '2026-11-07T14:30+00:00' (format używany w bazie)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).isoformat(timespec="minutes")


def _line(point: float) -> str:
    """Linia w kodzie rynku: 2.5 -> '2.5', -0.75 -> '-0.75', 0.0 -> '0'."""
    return f"{point:g}"


def market_codes(market_key: str, outcomes: list[dict], home: str, away: str) -> list[tuple[str, float]]:
    """Zamienia rynek z The Odds API na listę (kod rynku, kurs). Nieobsługiwane rynki -> []."""
    codes = []
    for o in outcomes:
        name, price, point = o["name"], float(o["price"]), o.get("point")
        side = "home" if name == home else "away" if name == away else None
        if market_key == "h2h":
            code = {"home": "1X2:1", "away": "1X2:2"}.get(side) or ("1X2:X" if name == "Draw" else None)
        elif market_key == "totals" and point is not None:
            code = f"OU:{_line(point)}:{name.lower()}" if name in ("Over", "Under") else None
        elif market_key == "spreads" and point is not None and side:
            # Linia z perspektywy typowanej drużyny, jak u bukmachera: AH:-0.75:home
            code = f"AH:{_line(point)}:{side}"
        elif market_key == "btts":
            code = {"Yes": "BTTS:yes", "No": "BTTS:no"}.get(name)
        elif market_key == "double_chance":
            code = _double_chance_code(name, home, away)
        else:
            code = None
        if code:
            codes.append((code, price))
    return codes


def _double_chance_code(name: str, home: str, away: str) -> str | None:
    """Nazwy w podwójnej szansie bywają postaci 'Lech Poznań/Draw' albo 'Draw/Legia Warszawa'."""
    parts = {p.strip() for p in name.replace(" or ", "/").split("/")}
    if parts == {home, "Draw"}:
        return "DC:1X"
    if parts == {away, "Draw"}:
        return "DC:X2"
    if parts == {home, away}:
        return "DC:12"
    return None


class OddsApi:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("ODDS_API_KEY")
        if not key:
            raise RuntimeError("Brak ODDS_API_KEY w .env")
        self._client = httpx.Client(base_url=BASE_URL, params={"apiKey": key}, timeout=30)
        self.remaining: str | None = None

    def _get(self, path: str, **params) -> list | dict:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        self.remaining = resp.headers.get("x-requests-remaining", self.remaining)
        data = resp.json()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        name = path.strip("/").replace("/", "_") or "root"
        (RAW_DIR / f"{stamp}_{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def events(self) -> list[dict]:
        return self._get("/events")

    def odds(self, markets: str = MAIN_MARKETS) -> list[dict]:
        return self._get("/odds", regions="eu", markets=markets, oddsFormat="decimal")

    def event_odds(self, event_id: str, markets: str = EXTRA_MARKETS) -> dict:
        return self._get(f"/events/{event_id}/odds", regions="eu", markets=markets, oddsFormat="decimal")


def save_events(conn: sqlite3.Connection, events: list[dict]) -> dict[str, int]:
    """Zapisuje nadchodzące mecze; zwraca mapę id wydarzenia w The Odds API -> id meczu."""
    mapping = {}
    for ev in events:
        home, away = teams.resolve(ev["home_team"]), teams.resolve(ev["away_team"])
        mapping[ev["id"]] = upsert_scheduled(conn, home, away, iso_utc(ev["commence_time"]))
    conn.commit()
    return mapping


def save_odds(conn: sqlite3.Connection, events: list[dict], taken_at: str | None = None) -> int:
    """Dopisuje snapshot kursów wszystkich bukmacherów. Zwraca liczbę zapisanych kursów."""
    taken_at = taken_at or datetime.now(timezone.utc).isoformat(timespec="minutes")
    mapping = save_events(conn, events)
    saved = 0
    for ev in events:
        match_id = mapping[ev["id"]]
        for book in ev.get("bookmakers", []):
            for market in book["markets"]:
                for code, price in market_codes(market["key"], market["outcomes"], ev["home_team"], ev["away_team"]):
                    cur = conn.execute(
                        """INSERT OR IGNORE INTO odds_snapshot (match_id, market, odds, bookmaker, taken_at, is_closing)
                           VALUES (?, ?, ?, ?, ?, 0)""",
                        (match_id, code, price, book["key"], taken_at),
                    )
                    saved += cur.rowcount
    conn.commit()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--events", action="store_true", help="tylko terminarz (bez kosztu)")
    args = parser.parse_args()

    api = OddsApi()
    with db.connect() as conn:
        db.init_db(conn)
        if args.events:
            n = len(save_events(conn, api.events()))
            print(f"Zapisano {n} nadchodzących meczów")
        else:
            saved = save_odds(conn, api.odds())
            print(f"Zapisano {saved} kursów")
    print(f"Pozostało kredytów The Odds API: {api.remaining}")


if __name__ == "__main__":
    main()
