"""Rozliczanie typów po meczu (docs/07, sekcja 7.7).

Typ jest rozliczony, gdy ma wypełnione `outcome`. Zysk oficjalny (`profit`) liczymy tylko dla typów
potwierdzonych, po kursie z etapu 2; pozostałe strategie (np. wszystkie typy wstępne po kursie
z etapu 1) liczy raport z `outcome` i zapisanych kursów.
"""

import sqlite3

from typerai import config
from typerai.markets import profit, settle

OFFICIAL = ("POTWIERDZONY", "POTWIERDZONY_POZNO")


def closing_reference_odds(conn: sqlite3.Connection, match_id: int, market: str, kickoff: str) -> float | None:
    """Ostatni kurs Pinnacle przed meczem – podstawa metryki CLV."""
    row = conn.execute(
        """SELECT odds FROM odds_snapshot WHERE match_id = ? AND market = ? AND bookmaker = ?
           AND is_closing = 0 AND taken_at <= ? ORDER BY taken_at DESC LIMIT 1""",
        (match_id, market, config.ODDS["reference_bookmaker"], kickoff)).fetchone()
    return row[0] if row else None


def settle_picks(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """SELECT p.id, p.market, p.status, p.odds_stage2, m.id AS match_id, m.hg, m.ag, m.kickoff_utc
           FROM pick p JOIN match m ON m.id = p.match_id
           WHERE p.outcome IS NULL AND m.status = 'finished' AND m.hg IS NOT NULL""").fetchall()
    for r in rows:
        outcome = settle(r["market"], r["hg"], r["ag"])
        official_profit = profit(outcome, r["odds_stage2"]) if r["status"] in OFFICIAL else None
        conn.execute(
            "UPDATE pick SET outcome = ?, profit = ?, odds_closing = ? WHERE id = ?",
            (outcome.value, official_profit,
             closing_reference_odds(conn, r["match_id"], r["market"], r["kickoff_utc"]), r["id"]))
    conn.commit()
    return len(rows)
