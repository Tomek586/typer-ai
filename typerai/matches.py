"""Wspólne dopasowywanie meczów z różnych źródeł do jednego rekordu w tabeli `match`.

Źródła podają godzinę meczu z różną dokładnością, a mecze bywają przekładane,
dlatego mecz szukamy po parze drużyn i godzinie rozpoczęcia z tolerancją.
"""

import sqlite3
from datetime import datetime, timedelta

from typerai import config

WINDOW = timedelta(hours=48)


def season_of(kickoff_utc: str) -> str:
    """Sezon Ekstraklasy dla daty meczu (sezon zaczyna się w lipcu): '2026-11-08…' -> '2026/27'."""
    dt = datetime.fromisoformat(kickoff_utc)
    start = dt.year if dt.month >= 7 else dt.year - 1
    return f"{start}/{(start + 1) % 100:02d}"


def find_match(conn: sqlite3.Connection, home_id: str, away_id: str, kickoff_utc: str) -> int | None:
    """ID meczu tej samej pary drużyn rozgrywanego w oknie ±48 h, najbliższego podanej godzinie."""
    kickoff = datetime.fromisoformat(kickoff_utc)
    rows = conn.execute(
        """SELECT id, kickoff_utc FROM match
           WHERE competition = ? AND home_id = ? AND away_id = ? AND kickoff_utc BETWEEN ? AND ?""",
        (config.LEAGUE, home_id, away_id, (kickoff - WINDOW).isoformat(timespec="minutes"),
         (kickoff + WINDOW).isoformat(timespec="minutes")),
    ).fetchall()
    if not rows:
        return None
    return min(rows, key=lambda r: abs(datetime.fromisoformat(r["kickoff_utc"]) - kickoff))["id"]


def upsert_scheduled(conn: sqlite3.Connection, home_id: str, away_id: str, kickoff_utc: str) -> int:
    """Zwraca ID meczu; nowy mecz zapisuje jako zaplanowany, istniejącemu niezakończonemu aktualizuje godzinę."""
    match_id = find_match(conn, home_id, away_id, kickoff_utc)
    if match_id is None:
        cur = conn.execute(
            """INSERT INTO match (season, competition, kickoff_utc, home_id, away_id, status)
               VALUES (?, ?, ?, ?, ?, 'scheduled')""",
            (season_of(kickoff_utc), config.LEAGUE, kickoff_utc, home_id, away_id),
        )
        return cur.lastrowid
    conn.execute(
        "UPDATE match SET kickoff_utc = ? WHERE id = ? AND status = 'scheduled'",
        (kickoff_utc, match_id),
    )
    return match_id
