"""Import wyników i kursów 1X2 Ekstraklasy z football-data.co.uk (docs/03, sekcje 3.1 i 3.7).

Użycie:
    python -m typerai.collectors.football_data            # pobierz świeży plik i zaimportuj
    python -m typerai.collectors.football_data --offline  # zaimportuj ostatni pobrany plik
"""

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from typerai import config, db, teams
from typerai.matches import find_match

RAW_DIR = config.RAW_DIR / "football_data"
LATEST = RAW_DIR / "POL.csv"

# Kolumny z kursami zamknięcia -> nazwa bukmachera w bazie
BOOKMAKERS = {
    "PSC": "pinnacle",
    "B365C": "bet365",
    "BFEC": "betfair_ex",
    "AvgC": "market_avg",
    "MaxC": "market_max",
}
OUTCOMES = {"H": "1X2:1", "D": "1X2:X", "A": "1X2:2"}


@dataclass
class FdMatch:
    season: str          # '2025/26'
    kickoff_utc: str     # ISO 8601
    home_id: str
    away_id: str
    hg: int | None
    ag: int | None
    odds: dict[str, dict[str, float]]  # bookmaker -> {kod_rynku: kurs}


def download() -> Path:
    """Pobiera aktualny plik i zapisuje kopię z datą (surowe dane, docs/03 3.7)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    resp = httpx.get(config.FOOTBALL_DATA_URL, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    stamp = datetime.now().strftime("%Y%m%d")
    (RAW_DIR / f"POL_{stamp}.csv").write_bytes(resp.content)
    LATEST.write_bytes(resp.content)
    return LATEST


def _season(raw: str) -> str:
    """'2025/2026' -> '2025/26'."""
    start, end = raw.split("/")
    return f"{start}/{end[-2:]}"


def _kickoff_utc(date: str, time: str) -> str:
    """Data 'dd/mm/yyyy' i godzina 'HH:MM' w czasie brytyjskim -> ISO w UTC."""
    local = datetime.strptime(f"{date} {time or '00:00'}", "%d/%m/%Y %H:%M")
    local = local.replace(tzinfo=ZoneInfo(config.FOOTBALL_DATA_TZ))
    return local.astimezone(timezone.utc).isoformat(timespec="minutes")


def _float(value: str) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x > 1.0 else None


def parse(path: Path) -> list[FdMatch]:
    matches = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("Home"):
                continue
            odds: dict[str, dict[str, float]] = {}
            for prefix, bookmaker in BOOKMAKERS.items():
                quotes = {market: _float(row.get(prefix + res)) for res, market in OUTCOMES.items()}
                if all(quotes.values()):  # bierzemy tylko kompletne rynki
                    odds[bookmaker] = quotes
            matches.append(
                FdMatch(
                    season=_season(row["Season"]),
                    kickoff_utc=_kickoff_utc(row["Date"], row.get("Time", "")),
                    home_id=teams.resolve(row["Home"]),
                    away_id=teams.resolve(row["Away"]),
                    hg=int(row["HG"]) if row.get("HG") not in (None, "") else None,
                    ag=int(row["AG"]) if row.get("AG") not in (None, "") else None,
                    odds=odds,
                )
            )
    return matches


def import_matches(conn: sqlite3.Connection, matches: list[FdMatch]) -> dict[str, int]:
    """Wstawia lub uzupełnia mecze (dopasowanie: para drużyn ±48 h) i kursy zamknięcia (tylko nowe)."""
    stats = {"matches": 0, "odds": 0}
    for m in matches:
        status = "finished" if m.hg is not None else "scheduled"
        match_id = find_match(conn, m.home_id, m.away_id, m.kickoff_utc)
        if match_id is None:
            match_id = conn.execute(
                """INSERT INTO match (season, competition, kickoff_utc, home_id, away_id, hg, ag, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (m.season, config.LEAGUE, m.kickoff_utc, m.home_id, m.away_id, m.hg, m.ag, status),
            ).lastrowid
        else:
            # Mecz mógł już przyjść z innego źródła (np. jako zaplanowany) – uzupełniamy wynik
            conn.execute(
                "UPDATE match SET season = ?, hg = ?, ag = ?, status = ? WHERE id = ?",
                (m.season, m.hg, m.ag, status, match_id),
            )
        stats["matches"] += 1
        for bookmaker, quotes in m.odds.items():
            for market, price in quotes.items():
                cur = conn.execute(
                    """INSERT OR IGNORE INTO odds_snapshot (match_id, market, odds, bookmaker, taken_at, is_closing)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (match_id, market, price, bookmaker, m.kickoff_utc),
                )
                stats["odds"] += cur.rowcount
    conn.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="nie pobieraj, użyj ostatniego pliku")
    args = parser.parse_args()

    path = LATEST if args.offline else download()
    matches = parse(path)
    with db.connect() as conn:
        db.init_db(conn)
        stats = import_matches(conn, matches)
    print(f"Zaimportowano {stats['matches']} meczów, nowych kursów: {stats['odds']} ({path.name})")


if __name__ == "__main__":
    main()
