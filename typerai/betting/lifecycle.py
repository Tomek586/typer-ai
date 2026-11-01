"""Dwuetapowy cykl życia typu (docs/07, sekcja 7.4).

Etap 1 (dzień wcześniej / rano): kandydat spełniający reguły -> typ WSTEPNY.
Etap 2 (ok. 60 min przed meczem): ponowne sprawdzenie reguł na świeżych kursach
    -> POTWIERDZONY albo ANULOWANY; nowy kandydat bez typu wstępnego -> POTWIERDZONY_POZNO.
Model v1 nie ma jeszcze bramki Jev – każdy kandydat jest wydawany (rozdz. 6 dochodzi w etapie 5).
"""

import sqlite3
from datetime import datetime, timedelta

from typerai import config
from typerai.betting import value
from typerai.model import predict as model_predict

OFFICIAL = ("POTWIERDZONY", "POTWIERDZONY_POZNO")


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def team_has_history(conn: sqlite3.Connection, team_id: str, as_of: str) -> bool:
    """Reguła R5: co najmniej N meczów ligowych drużyny w ostatnich 365 dniach."""
    since = _iso(datetime.fromisoformat(as_of) - timedelta(days=365))
    n = conn.execute(
        """SELECT COUNT(*) FROM match WHERE status = 'finished' AND kickoff_utc BETWEEN ? AND ?
           AND (home_id = ? OR away_id = ?)""", (since, as_of, team_id, team_id)).fetchone()[0]
    return n >= config.RULES["min_team_matches"]


def _match_ok(conn, match, as_of) -> bool:
    return team_has_history(conn, match["home_id"], as_of) and team_has_history(conn, match["away_id"], as_of)


def stage1(conn: sqlite3.Connection, now: datetime) -> list[dict]:
    """Typy wstępne dla meczów w ciągu stage1_horizon_h, które nie mają jeszcze predykcji etapu 1."""
    as_of = _iso(now)
    horizon = _iso(now + timedelta(hours=config.STAGES["stage1_horizon_h"]))
    stage2_start = _iso(now + timedelta(minutes=config.STAGES["stage2_window_min"][1]))
    matches = conn.execute(
        """SELECT * FROM match m WHERE status = 'scheduled' AND kickoff_utc > ? AND kickoff_utc <= ?
           AND NOT EXISTS (SELECT 1 FROM prediction p WHERE p.match_id = m.id AND p.stage = '1')
           ORDER BY kickoff_utc""", (stage2_start, horizon)).fetchall()
    if not matches:
        return []
    model = model_predict.fit_model(conn, as_of)
    issued = []
    for m in matches:
        pred_id, matrix = model_predict.predict(conn, model, m["id"], "1", as_of)
        if not _match_ok(conn, m, as_of):
            continue
        quotes = value.latest_quotes(conn, m["id"], as_of, config.ODDS["max_age_stage1_min"])
        best = value.choose(value.candidates(matrix, quotes))
        if best is None:
            continue
        conn.execute(
            """INSERT INTO pick (prediction_id, match_id, market, bookmaker, p_model, ev, status, odds_stage1, stage1_at)
               VALUES (?, ?, ?, ?, ?, ?, 'WSTEPNY', ?, ?)""",
            (pred_id, m["id"], best.market, best.bookmaker, best.p, best.ev, best.odds, as_of))
        issued.append({"match_id": m["id"], "market": best.market, "odds": best.odds,
                       "bookmaker": best.bookmaker, "p": best.p, "ev": best.ev})
    conn.commit()
    return issued


def matches_for_stage2(conn: sqlite3.Connection, now: datetime) -> list[sqlite3.Row]:
    lo, hi = config.STAGES["stage2_window_min"]
    return conn.execute(
        """SELECT * FROM match m WHERE status = 'scheduled' AND kickoff_utc BETWEEN ? AND ?
           AND NOT EXISTS (SELECT 1 FROM prediction p WHERE p.match_id = m.id AND p.stage = '2')
           ORDER BY kickoff_utc""",
        (_iso(now + timedelta(minutes=lo)), _iso(now + timedelta(minutes=hi)))).fetchall()


def stage2(conn: sqlite3.Connection, now: datetime) -> list[dict]:
    """Potwierdzenie lub anulowanie typów dla meczów zaczynających się za 45–75 min."""
    as_of = _iso(now)
    matches = matches_for_stage2(conn, now)
    if not matches:
        return []
    model = model_predict.fit_model(conn, as_of)
    decisions = []
    for m in matches:
        pred_id, matrix = model_predict.predict(conn, model, m["id"], "2", as_of)
        quotes = value.latest_quotes(conn, m["id"], as_of, config.ODDS["max_age_stage2_min"])
        cands = value.candidates(matrix, quotes) if _match_ok(conn, m, as_of) else []
        prelim = conn.execute(
            "SELECT * FROM pick WHERE match_id = ? AND status IN ('WSTEPNY', 'WSTRZYMANY')", (m["id"],)).fetchone()
        if prelim:
            same = next((c for c in cands if c.market == prelim["market"]), None)
            status = "POTWIERDZONY" if same else "ANULOWANY"
            conn.execute(
                """UPDATE pick SET status = ?, odds_stage2 = ?, bookmaker_stage2 = ?, p_stage2 = ?, ev_stage2 = ?,
                       stage2_at = ? WHERE id = ?""",
                (status, same.odds if same else None, same.bookmaker if same else None,
                 same.p if same else None, same.ev if same else None, as_of, prelim["id"]))
            decisions.append({"match_id": m["id"], "market": prelim["market"], "status": status,
                              "odds": same.odds if same else None})
            continue
        best = value.choose(cands)
        if best:
            conn.execute(
                """INSERT INTO pick (prediction_id, match_id, market, bookmaker, p_model, ev, status,
                       odds_stage2, bookmaker_stage2, p_stage2, ev_stage2, stage2_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'POTWIERDZONY_POZNO', ?, ?, ?, ?, ?)""",
                (pred_id, m["id"], best.market, best.bookmaker, best.p, best.ev,
                 best.odds, best.bookmaker, best.p, best.ev, as_of))
            decisions.append({"match_id": m["id"], "market": best.market, "status": "POTWIERDZONY_POZNO",
                              "odds": best.odds})
    conn.commit()
    return decisions
