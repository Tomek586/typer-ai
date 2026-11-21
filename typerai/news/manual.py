"""Ręczne potwierdzenia (docs/05, 5.5; docs/03: NEWS_FACT.source = manual).

Informacje sprawdzone przez użytkownika (np. wpis dziennikarza na X, komunikat klubu, skład ogłoszony przed meczem)
wpisywane w aplikacji. Trafiają do tej samej tabeli co fakty z newsów i podlegają tym samym zasadom scalania.
Zapis tylko na komputerze z bazą główną – na kopii bazy (laptop) wpis zniknie przy następnej kopii.
"""

import sqlite3
from datetime import datetime, timezone

from typerai.news import extract

CATEGORIES = [c for c, v in extract.VALIDITY.items() if v is not None]
DIRECTION = {"injury": "weakens", "suspension": "weakens", "return": "strengthens", "coach_change": "neutral",
             "club_crisis": "weakens", "fatigue_schedule": "weakens", "motivation_context": "neutral",
             "match_conditions": "neutral"}


def add(conn: sqlite3.Connection, team_id: str, category: str, note: str, player_id: int | None = None,
        status: str | None = None, certainty: str = "official", impact: float = 3.0,
        source_url: str | None = None, now: datetime | None = None) -> int:
    if category not in CATEGORIES:
        raise ValueError(f"Nieznana kategoria: {category}")
    if status not in (None, *extract.STATUS):
        raise ValueError(f"Nieznany status: {status}")
    if certainty not in extract.CERTAINTY:
        raise ValueError(f"Nieznana pewność: {certainty}")
    if not note.strip():
        raise ValueError("Opis jest wymagany (skąd wiadomo, np. treść wpisu)")
    if category in extract.PLAYER_CATEGORIES and player_id is not None and status is None:
        status = "available" if category == "return" else "out"
    valid_from = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="minutes")
    fact = {"team_id": team_id, "player_id": player_id, "category": category, "status": status,
            "impact": max(0.0, min(4.0, float(impact))), "direction": DIRECTION[category], "certainty": certainty}
    fact_id = extract.save_fact(conn, fact, None, valid_from, source="manual", note=note.strip(),
                                source_url=(source_url or "").strip() or None)
    conn.commit()
    return fact_id


def withdraw(conn: sqlite3.Connection, fact_id: int, now: datetime | None = None) -> None:
    """Wycofanie ręcznego faktu (np. pomyłka): kończy jego ważność teraz."""
    until = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="minutes")
    conn.execute("UPDATE news_fact SET valid_until = ? WHERE id = ? AND source = 'manual'", (until, fact_id))
    conn.commit()
