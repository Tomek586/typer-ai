"""Baza SQLite: schemat i połączenie (docs/03, sekcja 3.4).

Zasady:
- ODDS_SNAPSHOT, PREDICTION i DECISION_LOG są tylko dopisywane, nigdy nadpisywane.
- Czasy zapisujemy jako tekst ISO 8601 w UTC.
"""

import sqlite3
from pathlib import Path

from typerai import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS team (
    id            TEXT PRIMARY KEY,          -- slug, np. 'lech'
    name          TEXT NOT NULL,             -- nazwa kanoniczna z polskimi znakami
    aliases       TEXT NOT NULL DEFAULT '[]',-- JSON: warianty nazw ze wszystkich źródeł
    stadium_lat   REAL,
    stadium_lon   REAL
);

CREATE TABLE IF NOT EXISTS match (
    id            INTEGER PRIMARY KEY,
    season        TEXT NOT NULL,             -- '2025/26'
    round         INTEGER,
    competition   TEXT NOT NULL DEFAULT 'Ekstraklasa',
    kickoff_utc   TEXT NOT NULL,
    home_id       TEXT NOT NULL REFERENCES team(id),
    away_id       TEXT NOT NULL REFERENCES team(id),
    hg            INTEGER,
    ag            INTEGER,
    status        TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled | finished | postponed | abandoned
    referee       TEXT,
    ninetymin_id  INTEGER UNIQUE,            -- id meczu w 90minut.pl
    UNIQUE (competition, home_id, away_id, kickoff_utc)  -- w formacie 37 kolejek para mogła grać 2x u tego samego gospodarza
);

CREATE TABLE IF NOT EXISTS match_stats (
    match_id      INTEGER PRIMARY KEY REFERENCES match(id),
    yellow_h INTEGER, yellow_a INTEGER,
    red_h INTEGER, red_a INTEGER
);

CREATE TABLE IF NOT EXISTS player (
    id            INTEGER PRIMARY KEY,       -- id zawodnika w 90minut.pl
    team_id       TEXT REFERENCES team(id),  -- ostatni klub, w którym wystąpił
    name          TEXT NOT NULL,
    aliases       TEXT NOT NULL DEFAULT '[]',
    position      TEXT                       -- G | D | M | F (z kolejności w składach)
);

CREATE TABLE IF NOT EXISTS lineup (
    match_id      INTEGER REFERENCES match(id),
    player_id     INTEGER REFERENCES player(id),
    team_id       TEXT REFERENCES team(id),
    source        TEXT NOT NULL,             -- official (90minut.pl) | expected (newsy) | manual
    is_starter    INTEGER NOT NULL,
    row_index     INTEGER,                   -- pozycja w składzie 1–11 (wiersz w relacji); do wyznaczenia pozycji
    weight        REAL NOT NULL DEFAULT 1.0, -- 0.5 dla 'doubtful' w składzie przewidywanym
    minutes       INTEGER,
    goals         INTEGER NOT NULL DEFAULT 0,
    yellow        INTEGER NOT NULL DEFAULT 0,
    red           INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (match_id, player_id, source, created_at)
);

CREATE TABLE IF NOT EXISTS odds_snapshot (
    id            INTEGER PRIMARY KEY,
    match_id      INTEGER NOT NULL REFERENCES match(id),
    market        TEXT NOT NULL,             -- kod rynku, np. '1X2:1' (docs/03, 3.3)
    odds          REAL NOT NULL,
    bookmaker     TEXT NOT NULL,             -- klucz bukmachera z The Odds API lub football-data (pinnacle, bet365, betfair_ex, market_avg, market_max)
    taken_at      TEXT NOT NULL,
    is_closing    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (match_id, market, bookmaker, taken_at)
);

CREATE TABLE IF NOT EXISTS prediction (
    id            INTEGER PRIMARY KEY,
    match_id      INTEGER NOT NULL REFERENCES match(id),
    stage         TEXT NOT NULL,             -- 1 | 2 | backtest
    model_version TEXT NOT NULL,
    config_hash   TEXT NOT NULL,
    as_of         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    features      TEXT NOT NULL,             -- JSON
    probabilities TEXT NOT NULL              -- JSON {kod_rynku: p}
);

CREATE TABLE IF NOT EXISTS pick (
    id            INTEGER PRIMARY KEY,
    prediction_id INTEGER NOT NULL REFERENCES prediction(id),
    match_id      INTEGER NOT NULL REFERENCES match(id),
    market        TEXT NOT NULL,
    bookmaker     TEXT NOT NULL,
    p_model       REAL NOT NULL,
    ev            REAL NOT NULL,
    status        TEXT NOT NULL,             -- KANDYDAT | WSTEPNY | WSTRZYMANY | ODRZUCONY | POTWIERDZONY | POTWIERDZONY_POZNO | ANULOWANY | ROZLICZONY
    odds_stage1   REAL,
    odds_stage2   REAL,
    odds_closing  REAL,
    stage1_at     TEXT,
    stage2_at     TEXT,
    outcome       TEXT,                      -- WIN | HALF_WIN | PUSH | HALF_LOSS | LOSS
    profit        REAL
);

CREATE TABLE IF NOT EXISTS coupon (
    id            INTEGER PRIMARY KEY,
    created_at    TEXT NOT NULL,
    pick_ids      TEXT NOT NULL,             -- JSON
    total_odds    REAL NOT NULL,
    p_total       REAL NOT NULL,
    ev            REAL NOT NULL,
    outcome       TEXT
);

CREATE TABLE IF NOT EXISTS decision_log (
    id            INTEGER PRIMARY KEY,
    purpose       TEXT NOT NULL,             -- news_classify | gate | router | guard_in | guard_out
    engine        TEXT NOT NULL,             -- jev | llm-gemini ...
    model         TEXT NOT NULL,
    ref_type      TEXT,                      -- pick | article | message
    ref_id        INTEGER,
    state         TEXT NOT NULL,             -- JSON
    questions     TEXT NOT NULL,             -- JSON
    answers       TEXT NOT NULL,             -- JSON
    decision      TEXT,
    latency_ms    INTEGER,
    input_tokens  INTEGER,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_article (
    id            INTEGER PRIMARY KEY,
    url           TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL,
    reliability   TEXT NOT NULL,             -- oficjalne | medialne
    published_at  TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    title         TEXT NOT NULL,
    text          TEXT NOT NULL,
    simhash       TEXT,
    duplicate_of  INTEGER REFERENCES news_article(id)
);

CREATE TABLE IF NOT EXISTS news_fact (
    id            INTEGER PRIMARY KEY,
    article_id    INTEGER REFERENCES news_article(id),  -- NULL dla ręcznych potwierdzeń
    source        TEXT NOT NULL DEFAULT 'news',         -- news | manual
    team_id       TEXT NOT NULL REFERENCES team(id),
    player_id     INTEGER REFERENCES player(id),
    category      TEXT NOT NULL,
    status        TEXT,                      -- out | doubtful | available
    impact        REAL,
    direction     TEXT,
    certainty     TEXT,
    valid_from    TEXT NOT NULL,
    valid_until   TEXT,
    superseded_by INTEGER REFERENCES news_fact(id)
);

CREATE TABLE IF NOT EXISTS job_run (
    id            INTEGER PRIMARY KEY,
    job           TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,             -- running | ok | error
    error         TEXT
);

CREATE INDEX IF NOT EXISTS ix_match_kickoff ON match(kickoff_utc);
CREATE INDEX IF NOT EXISTS ix_odds_match ON odds_snapshot(match_id, market);
CREATE INDEX IF NOT EXISTS ix_pick_status ON pick(status);
CREATE INDEX IF NOT EXISTS ix_fact_team ON news_fact(team_id, valid_until);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    # timeout: przy równoległej pracy kolektorów czekamy na zwolnienie blokady zapisu zamiast przerywać
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # odczyty nie blokują zapisu i odwrotnie
    return conn


# Kolumny dodane po utworzeniu pierwszych baz: (tabela, kolumna, typ)
MIGRATIONS = [
    ("pick", "p_stage2", "REAL"),
    ("pick", "ev_stage2", "REAL"),
    ("pick", "bookmaker_stage2", "TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, sql_type in MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    from typerai.teams import seed_teams  # import lokalny – teams korzysta z db

    seed_teams(conn)
    conn.commit()


if __name__ == "__main__":
    with connect() as c:
        init_db(c)
    print(f"Baza gotowa: {config.DB_PATH}")
