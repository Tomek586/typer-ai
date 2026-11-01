"""Polecenia procesu typowania (docs/02, sekcja 2.4; docs/07, sekcja 7.4).

    python -m typerai.pipeline stage1     # kursy + typy wstępne dla meczów w ciągu 36 h
    python -m typerai.pipeline stage2     # świeże kursy + potwierdzenie/anulowanie (mecze za 45–75 min)
    python -m typerai.pipeline settle     # wyniki (football-data, 90minut.pl) + rozliczenie typów
    python -m typerai.pipeline picks      # lista typów i wynik oficjalny

Opcja --no-fetch pomija pobieranie danych (np. do testów na danych już zapisanych).
"""

import argparse
from datetime import datetime, timezone

from typerai import db
from typerai.betting import lifecycle, settle
from typerai.collectors import football_data, ninetymin, odds_api


def _now(value: str | None) -> datetime:
    return datetime.fromisoformat(value) if value else datetime.now(timezone.utc).replace(second=0, microsecond=0)


def fetch_odds(conn) -> None:
    api = odds_api.OddsApi()
    saved = odds_api.save_odds(conn, api.odds())
    print(f"Kursy: zapisano {saved}, pozostało kredytów: {api.remaining}")


def cmd_stage1(conn, now, fetch: bool) -> None:
    if fetch:
        fetch_odds(conn)
    issued = lifecycle.stage1(conn, now)
    print(f"Etap 1 ({now:%Y-%m-%d %H:%M} UTC): typów wstępnych {len(issued)}")
    for p in issued:
        print(f"  mecz {p['match_id']}: {p['market']} @ {p['odds']} ({p['bookmaker']}), p={p['p']:.3f}, EV={p['ev']:+.3f}")


def cmd_stage2(conn, now, fetch: bool) -> None:
    if not lifecycle.matches_for_stage2(conn, now):
        print("Etap 2: brak meczów w oknie 45–75 min")
        return
    if fetch:
        fetch_odds(conn)
    for d in lifecycle.stage2(conn, now):
        print(f"  mecz {d['match_id']}: {d['market']} -> {d['status']} {d['odds'] or ''}")


def cmd_settle(conn, fetch: bool) -> None:
    if fetch:
        football_data.import_matches(conn, football_data.parse(football_data.download()))
        conn.commit()
    if fetch:
        conn.close()                   # kolektor 90minut.pl otwiera własne połączenie
        ninetymin.collect([ninetymin.CURRENT_SEASON], refresh_season_pages=True)
        conn = db.connect()
    print(f"Rozliczono typów: {settle.settle_picks(conn)}")
    conn.close()


def cmd_picks(conn) -> None:
    rows = conn.execute(
        """SELECT p.*, m.kickoff_utc, h.name AS home, a.name AS away FROM pick p
           JOIN match m ON m.id = p.match_id JOIN team h ON h.id = m.home_id JOIN team a ON a.id = m.away_id
           ORDER BY m.kickoff_utc""").fetchall()
    for r in rows:
        odds = r["odds_stage2"] or r["odds_stage1"]
        profit = "" if r["profit"] is None else f"{r['profit']:+.2f}"
        print(f"{r['kickoff_utc'][:16]} {r['home']} – {r['away']}: {r['market']} @ {odds} "
              f"[{r['status']}] {r['outcome'] or ''} {profit}")
    official = [r for r in rows if r["profit"] is not None]
    if official:
        wins = sum(r["outcome"] in ("WIN", "HALF_WIN") for r in official)
        print(f"\nWynik oficjalny: typów {len(official)}, trafnych {wins} ({wins / len(official):.0%}), "
              f"ROI {sum(r['profit'] for r in official) / len(official):+.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["stage1", "stage2", "settle", "picks"])
    parser.add_argument("--no-fetch", action="store_true", help="bez pobierania danych")
    parser.add_argument("--now", help="czas w ISO (do testów), domyślnie teraz")
    args = parser.parse_args()

    conn = db.connect()
    db.init_db(conn)
    now, fetch = _now(args.now), not args.no_fetch
    if args.command == "stage1":
        cmd_stage1(conn, now, fetch)
    elif args.command == "stage2":
        cmd_stage2(conn, now, fetch)
    elif args.command == "settle":
        cmd_settle(conn, fetch)
        return
    else:
        cmd_picks(conn)
    conn.close()


if __name__ == "__main__":
    main()
