"""Sprawdza, jakie dane dla Ekstraklasy dają API-Football i The Odds API.

Wymaga kluczy w .env: API_FOOTBALL_KEY, ODDS_API_KEY.
Koszt: ok. 6 zapytań API-Football (z dziennego limitu) i 3 kredyty The Odds API.

    .venv/Scripts/python scripts/check_api_coverage.py
"""

import os
import sys
from collections import Counter

import httpx

from typerai import config  # noqa: F401  (ładuje .env)

AF_URL = "https://v3.football.api-sports.io"
ODDS_URL = "https://api.the-odds-api.com/v4"
EKSTRAKLASA = 106


def check_api_football(key: str) -> None:
    print("=== API-Football ===")
    client = httpx.Client(base_url=AF_URL, headers={"x-apisports-key": key}, timeout=30)

    def get(path: str, **params) -> dict:
        data = client.get(path, params=params).json()
        if data.get("errors"):
            print(f"  {path} błędy: {data['errors']}")
        return data

    status = get("/status")["response"]
    if status:
        sub, req = status.get("subscription", {}), status.get("requests", {})
        print(f"  plan: {sub.get('plan')}, zapytania dziś: {req.get('current')}/{req.get('limit_day')}")

    leagues = get("/leagues", id=EKSTRAKLASA)["response"]
    if not leagues:
        print("  brak ligi 106")
        return
    print(f"  liga: {leagues[0]['league']['name']} ({leagues[0]['country']['name']})")
    print("  sezon | events lineups fix_stats player_stats injuries odds")
    for s in leagues[0]["seasons"][-6:]:
        c, f = s["coverage"], s["coverage"]["fixtures"]
        flags = [f["events"], f["lineups"], f["statistics_fixtures"], f["statistics_players"], c["injuries"], c["odds"]]
        print(f"  {s['year']}  | " + "  ".join("T" if x else "-" for x in flags))

    season = leagues[0]["seasons"][-1]["year"]
    fixtures = get("/fixtures", league=EKSTRAKLASA, season=season)["response"]
    done = [fx for fx in fixtures if fx["fixture"]["status"]["short"] == "FT"]
    print(f"  sezon {season}: meczów {len(fixtures)}, zakończonych {len(done)}")
    if not done:
        return
    fx = done[-1]
    fid = fx["fixture"]["id"]
    print(f"  przykład: {fx['teams']['home']['name']} – {fx['teams']['away']['name']}, sędzia: {fx['fixture'].get('referee')}")

    stats = get("/fixtures/statistics", fixture=fid)["response"]
    if stats:
        names = [s["type"] for s in stats[0]["statistics"]]
        print(f"  statystyki: {names}")
    players = get("/fixtures/players", fixture=fid)["response"]
    if players:
        p = players[0]["players"][0]["statistics"][0]
        print(f"  statystyki zawodnika (klucze): {list(p)}")
    injuries = get("/injuries", league=EKSTRAKLASA, season=season)["response"]
    print(f"  kontuzje/nieobecności w sezonie: {len(injuries)}; typy: {Counter(i['player']['type'] for i in injuries).most_common(3)}")


def check_odds_api(key: str) -> None:
    print("=== The Odds API ===")
    resp = httpx.get(
        f"{ODDS_URL}/sports/soccer_poland_ekstraklasa/odds",
        params={"apiKey": key, "regions": "eu", "markets": "h2h,totals,spreads", "oddsFormat": "decimal"},
        timeout=30,
    )
    print(f"  status {resp.status_code}, pozostało kredytów: {resp.headers.get('x-requests-remaining')}, koszt: {resp.headers.get('x-requests-last')}")
    if resp.status_code != 200:
        print(f"  {resp.text[:300]}")
        return
    events = resp.json()
    print(f"  nadchodzących meczów: {len(events)}")
    books, markets = Counter(), Counter()
    for ev in events:
        for b in ev["bookmakers"]:
            books[b["title"]] += 1
            for m in b["markets"]:
                markets[m["key"]] += 1
    print(f"  bukmacherzy: {dict(books.most_common())}")
    print(f"  rynki: {dict(markets)}")


def main() -> None:
    af, odds = os.getenv("API_FOOTBALL_KEY"), os.getenv("ODDS_API_KEY")
    if not af and not odds:
        sys.exit("Brak kluczy API_FOOTBALL_KEY i ODDS_API_KEY w .env")
    if af:
        check_api_football(af)
    if odds:
        check_odds_api(odds)


if __name__ == "__main__":
    main()
