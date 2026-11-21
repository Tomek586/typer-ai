"""Harmonogram zadań (docs/02, sekcja 2.4). Uruchomienie: python -m typerai.scheduler

Proces działa w tle i co minutę sprawdza, czy któreś zadanie powinno się wykonać.
Godziny podane są w czasie polskim. Każde uruchomienie zapisuje się w tabeli JOB_RUN.
Zadania o stałych godzinach są NADRABIANE: jeśli komputer spał o 9:00, etap 1 wykona się po wybudzeniu.
"""

import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from typerai import config, db
from typerai.pipeline import cmd_settle, cmd_stage1, cmd_stage2

TZ = ZoneInfo("Europe/Warsaw")

# nazwa: (godziny "HH:MM" albo co ile minut)
JOBS = {
    "stage1": {"at": ["09:00", "18:00"]},
    "stage2": {"every_min": 10},
    "settle": {"at": ["10:30", "23:45"]},
    # newsy co 2 godziny w ciągu dnia (docs/05, 5.2): pobranie RSS + klasyfikacja do 10 artykułów przez LLM
    "news": {"at": ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]},
}


def _run(name: str) -> None:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn = db.connect()
    db.init_db(conn)
    run_id = conn.execute("INSERT INTO job_run (job, started_at, status) VALUES (?, ?, 'running')",
                          (name, now.isoformat())).lastrowid
    conn.commit()
    status, error = "ok", None
    try:
        if name == "stage1":
            cmd_stage1(conn, now, fetch=True)
        elif name == "stage2":
            cmd_stage2(conn, now, fetch=True)
        elif name == "settle":
            cmd_settle(conn, fetch=True)   # zamyka własne połączenie
            conn = db.connect()
        elif name == "news":
            from typerai.collectors import news
            from typerai.decision.engine import LLMEngine
            from typerai.news import extract
            print(f"Newsy: {news.collect(conn, now)}", flush=True)
            print(f"Fakty: {extract.process(conn, LLMEngine(log=conn), config.NEWS['max_classify_per_run'])}", flush=True)
    except Exception:                      # błąd jednego zadania nie zatrzymuje harmonogramu
        status, error = "error", traceback.format_exc()
        print(error)
    conn.execute("UPDATE job_run SET finished_at = ?, status = ?, error = ? WHERE id = ?",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"), status, error, run_id))
    conn.commit()
    conn.close()


def due(name: str, local: datetime) -> bool:
    job = JOBS[name]
    if "at" in job:
        return local.strftime("%H:%M") in job["at"]
    return local.minute % job["every_min"] == 0


def last_slot(name: str, local: datetime) -> datetime | None:
    """Ostatni zaplanowany termin zadania o stałych godzinach, nie późniejszy niż `local` (dziś albo wczoraj)."""
    job = JOBS[name]
    if "at" not in job:
        return None
    slots = []
    for day in (local.date(), local.date() - timedelta(days=1)):
        for hhmm in job["at"]:
            h, m = map(int, hhmm.split(":"))
            slot = datetime(day.year, day.month, day.day, h, m, tzinfo=local.tzinfo)
            if slot <= local:
                slots.append(slot)
    return max(slots) if slots else None


def missed(name: str, local: datetime, last_run: datetime | None) -> bool:
    """Czy ostatni termin zadania przepadł (np. komputer był uśpiony) i trzeba go nadrobić.

    Liczy się każda próba, także zakończona błędem – inaczej przy awarii API zadanie ponawiałoby się co minutę
    i zużywało limity. Po błędzie czekamy do następnego terminu.
    """
    slot = last_slot(name, local)
    return slot is not None and (last_run is None or last_run < slot)


def _last_run(name: str) -> datetime | None:
    conn = db.connect()
    db.init_db(conn)
    row = conn.execute("SELECT MAX(started_at) FROM job_run WHERE job = ?", (name,)).fetchone()
    conn.close()
    return datetime.fromisoformat(row[0]) if row and row[0] else None


def _log_to_file_without_console() -> None:
    """Uruchomiony przez pythonw.exe (Harmonogram zadań Windows) nie ma konsoli – piszemy do pliku."""
    if sys.stdout is None or sys.stderr is None:
        log = open(config.DATA_DIR / "scheduler.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log


def main() -> None:
    _log_to_file_without_console()
    print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M}] Harmonogram Typer AI uruchomiony: {JOBS}", flush=True)
    last_minute = None
    while True:
        local = datetime.now(TZ).replace(second=0, microsecond=0)
        if local != last_minute:
            last_minute = local
            for name in JOBS:
                catch_up = not due(name, local) and missed(name, local, _last_run(name))
                if due(name, local) or catch_up:
                    print(f"[{local:%Y-%m-%d %H:%M}] {name}{' (nadrabianie pominiętego terminu)' if catch_up else ''}",
                          flush=True)
                    _run(name)
        time.sleep(15)


if __name__ == "__main__":
    main()
