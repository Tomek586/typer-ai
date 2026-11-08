"""Wybór kursu, mieszanie z rynkiem i reguły value (docs/03 3.3.4, docs/04 4.9, docs/07 7.2–7.3).

Model v1 typuje tylko rynki bez możliwości zwrotu (1X2, podwójna szansa, BTTS, linie połówkowe goli
i handicapu). Dla linii całkowitych i ćwiartkowych potrzebne byłoby mieszanie rozkładów z uwzględnieniem
zwrotów – to rozszerzenie na później.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

import numpy as np

from typerai import config
from typerai.betting import odds_math
from typerai.markets import family
from typerai.model.score_matrix import market_probs


@dataclass
class Quote:
    bookmaker: str
    odds: float
    taken_at: str


@dataclass
class Candidate:
    market: str
    odds: float
    bookmaker: str
    p: float            # prawdopodobieństwo po zmieszaniu z rynkiem – na nim liczymy EV i reguły
    p_model: float
    p_market: float
    ev: float
    n_books: int
    ref_odds: float | None  # kurs Pinnacle na to samo zdarzenie (do CLV i porównań)


def latest_quotes(conn: sqlite3.Connection, match_id: int, as_of: str, max_age_min: int) -> dict[str, list[Quote]]:
    """Najświeższy kurs każdego bukmachera dla każdego rynku z okna [as_of − max_age, as_of]."""
    start = (datetime.fromisoformat(as_of) - timedelta(minutes=max_age_min)).isoformat(timespec="minutes")
    latest: dict[tuple[str, str], Quote] = {}
    for market, book, odds, taken in conn.execute(
            """SELECT market, bookmaker, odds, taken_at FROM odds_snapshot
               WHERE match_id = ? AND is_closing = 0 AND taken_at BETWEEN ? AND ? ORDER BY taken_at""",
            (match_id, start, as_of)):
        latest[(market, book)] = Quote(book, odds, taken)
    out: dict[str, list[Quote]] = {}
    for (market, _), q in latest.items():
        out.setdefault(market, []).append(q)
    return out


def _usable(quotes: list[Quote]) -> list[Quote]:
    return [q for q in quotes if q.bookmaker not in config.ODDS["excluded_bookmakers"]]


def best_price(quotes: list[Quote]) -> Quote | None:
    """Najlepszy kurs po odrzuceniu kursów odstających o więcej niż outlier_pct od mediany."""
    usable = _usable(quotes)
    if not usable:
        return None
    limit = median(q.odds for q in usable) * (1 + config.ODDS["outlier_pct"])
    return max((q for q in usable if q.odds <= limit), key=lambda q: q.odds)


def is_half_line(market: str) -> bool:
    parts = market.split(":")
    if parts[0] not in ("OU", "AH"):
        return True
    return (float(parts[1]) * 2) % 2 == 1


def group_of(market: str) -> list[str] | None:
    """Rynki tworzące pełny podział wyników – potrzebny do usunięcia marży."""
    parts = market.split(":")
    kind = parts[0]
    if kind in ("1X2", "DC"):
        return ["1X2:1", "1X2:X", "1X2:2"]
    if kind == "BTTS":
        return ["BTTS:yes", "BTTS:no"]
    if kind == "OU":
        return [f"OU:{parts[1]}:over", f"OU:{parts[1]}:under"]
    if kind == "AH":
        line = float(parts[1])
        home_line = line if parts[2] == "home" else -line
        return [f"AH:{home_line:g}:home", f"AH:{-home_line:g}:away"]
    return None


def fair_probs(quotes: dict[str, list[Quote]], group: list[str]) -> list[float] | None:
    """Prawdopodobieństwa rynku bez marży (Shin): z Pinnacle, a gdy brak – z median kursów."""
    ref = config.ODDS["reference_bookmaker"]
    ref_odds = []
    for m in group:
        q = next((q for q in quotes.get(m, []) if q.bookmaker == ref), None)
        ref_odds.append(q.odds if q else None)
    if all(ref_odds):
        return odds_math.shin(ref_odds)
    medians = []
    for m in group:
        usable = _usable(quotes.get(m, []))
        if len(usable) < 3:
            return None
        medians.append(median(q.odds for q in usable))
    return odds_math.shin(medians)


def blend(p_model: list[float], p_market: list[float], w: float) -> list[float]:
    """Łączenie log-liniowe: p ∝ p_model^w · p_rynek^(1−w) (docs/04, 4.9)."""
    q = np.power(np.clip(p_model, 1e-9, 1), w) * np.power(np.clip(p_market, 1e-9, 1), 1 - w)
    return list(q / q.sum())


def _final_probability(market: str, matrix: np.ndarray, quotes, w: float) -> tuple[float, float, float] | None:
    group = group_of(market)
    fair = fair_probs(quotes, group) if group else None
    if fair is None:
        return None
    model = [market_probs(matrix, m).win for m in group]
    mixed = blend(model, fair, w)
    if family(market) == "DC":   # podwójna szansa = suma dwóch wyników 1X2
        idx = {"1X": (0, 1), "X2": (1, 2), "12": (0, 2)}[market.split(":")[1]]
        return sum(mixed[i] for i in idx), sum(model[i] for i in idx), sum(fair[i] for i in idx)
    k = group.index(market)
    return mixed[k], model[k], fair[k]


def candidates(matrix: np.ndarray, quotes: dict[str, list[Quote]], w: float | None = None) -> list[Candidate]:
    """Wszystkie zdarzenia meczu spełniające reguły R1–R4 i R6 (docs/07, 7.3)."""
    w = config.MODEL["blend_w"] if w is None else w
    rules = config.RULES
    out = []
    for market, market_quotes in quotes.items():
        if family(market) not in rules["families"] or not is_half_line(market):
            continue
        best = best_price(market_quotes)
        if best is None or not (rules["odds_min"] <= best.odds <= rules["odds_max"]):
            continue
        probs = _final_probability(market, matrix, quotes, w)
        if probs is None:
            continue
        p, p_model, p_market = probs
        ev = odds_math.expected_value(p, best.odds)
        if p >= rules["p_min"] and rules["ev_min"] <= ev <= rules["ev_max"]:
            ref = next((q.odds for q in market_quotes if q.bookmaker == config.ODDS["reference_bookmaker"]), None)
            out.append(Candidate(market, best.odds, best.bookmaker, p, p_model, p_market, ev,
                                 len(_usable(market_quotes)), ref))
    return out


def choose(cands: list[Candidate]) -> Candidate | None:
    """Jeden typ na mecz: najwyższe EV·p, przy remisie wyższe p (docs/07, 7.3)."""
    return max(cands, key=lambda c: (c.ev * c.p, c.p), default=None)


def minimum_odds(p: float, ev_min: float | None = None) -> float:
    """Najniższy kurs, przy którym zakład ma EV ≥ ev_min: (1 + ev_min) / p.

    Pozwala ocenić zakład, na który nie mamy kursu – użytkownik porównuje go z ofertą swojego bukmachera.
    """
    ev_min = config.RULES["ev_min"] if ev_min is None else ev_min
    return round((1 + ev_min) / p, 2)
