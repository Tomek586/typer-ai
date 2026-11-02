"""Harmonogram zadań (docs/02, sekcja 2.4). Uruchomienie: python -m typerai.scheduler

Proces działa w tle i co minutę sprawdza, czy któreś zadanie powinno się wykonać.
Godziny podane są w czasie polskim. Każde uruchomienie zapisuje się w tabeli JOB_RUN.
"""

import sys
import time
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from typerai import config, db
from typerai.pipeline import cmd_settle, cmd_stage1, cmd_stage2

TZ = ZoneInfo("Europe/Warsaw")

# nazwa: (godziny "HH:MM" albo co ile minut)
JOBS = {
    "stage1": {"at": ["09:00", "18:00"]},
    "stage2": {"every_min": 10},
    "settle": {"at": ["10:30", "23:45"]},
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
                if due(name, local):
                    print(f"[{local:%Y-%m-%d %H:%M}] {name}", flush=True)
                    _run(name)
        time.sleep(15)


if __name__ == "__main__":
    main()
