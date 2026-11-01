"""Predykcja meczu (docs/04, sekcja 4.11). Model v1: Dixon-Coles na wynikach."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import numpy as np

from typerai import config
from typerai.model import dixon_coles, score_matrix


def config_hash() -> str:
    """Skrót aktualnej konfiguracji modelu i reguł – zapisywany przy każdej predykcji i typie."""
    payload = json.dumps([config.MODEL, config.RULES, config.ODDS], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def fit_model(conn: sqlite3.Connection, as_of: str) -> dixon_coles.DixonColesModel:
    """Dopasowanie wyłącznie na meczach rozegranych przed as_of (zasada anty-wyciekowa, docs/03 3.7)."""
    history = conn.execute(
        """SELECT home_id, away_id, hg, ag, kickoff_utc FROM match
           WHERE status = 'finished' AND hg IS NOT NULL AND kickoff_utc < ?""", (as_of,)).fetchall()
    return dixon_coles.fit([tuple(r) for r in history], as_of, xi=config.MODEL["xi"])


def predict(conn: sqlite3.Connection, model: dixon_coles.DixonColesModel, match_id: int,
            stage: str, as_of: str) -> tuple[int, np.ndarray]:
    """Zapisuje predykcję w tabeli PREDICTION i zwraca (id predykcji, macierz wyników)."""
    home_id, away_id = conn.execute("SELECT home_id, away_id FROM match WHERE id = ?", (match_id,)).fetchone()
    lh, la = model.lambdas(home_id, away_id)
    matrix = score_matrix.matrix(lh, la, model.rho)
    features = {"lambda_home": round(lh, 4), "lambda_away": round(la, 4), "rho": round(model.rho, 4),
                "home_advantage": round(model.home, 4), "xi": config.MODEL["xi"]}
    cur = conn.execute(
        """INSERT INTO prediction (match_id, stage, model_version, config_hash, as_of, created_at, features, probabilities)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (match_id, stage, config.MODEL["version"], config_hash(), as_of,
         datetime.now(timezone.utc).isoformat(timespec="seconds"),
         json.dumps(features), json.dumps(score_matrix.standard_probabilities(matrix))),
    )
    return cur.lastrowid, matrix
