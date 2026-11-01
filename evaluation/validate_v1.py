"""Walidacja modelu v1 (Dixon-Coles) na sezonie walidacyjnym – docs/10, sekcje A.1–A.5.

Walk-forward: model dopasowywany co tydzień wyłącznie na meczach sprzed tego tygodnia.
Porównujemy rynek 1X2 z kursami zamknięcia (Pinnacle, a gdy brak – średnia rynkowa) i dobieramy:
  - ξ (ważenie czasem) po log-loss modelu,
  - w (waga modelu przy mieszaniu z rynkiem) po log-loss mieszanki.
Na końcu symulacja reguł wyboru typów na kursach zamknięcia (informacyjnie).

    .venv/Scripts/python -m evaluation.validate_v1 --season 2024/25
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from typerai import config
from typerai.betting import odds_math
from typerai.model import dixon_coles, score_matrix

XI_GRID = [0.0005, 0.001, 0.0015, 0.0025]
W_GRID = [round(x, 2) for x in np.arange(0, 1.01, 0.05)]
OUTCOMES = ["1X2:1", "1X2:X", "1X2:2"]
REPORT_DIR = Path(__file__).parent / "reports"


def load(conn: sqlite3.Connection, season: str):
    history = conn.execute(
        "SELECT home_id, away_id, hg, ag, kickoff_utc FROM match WHERE status = 'finished'").fetchall()
    target = conn.execute(
        """SELECT id, home_id, away_id, hg, ag, kickoff_utc FROM match
           WHERE season = ? AND status = 'finished' ORDER BY kickoff_utc""", (season,)).fetchall()
    odds = defaultdict(dict)
    for match_id, market, price, book in conn.execute(
            """SELECT match_id, market, odds, bookmaker FROM odds_snapshot
               WHERE is_closing = 1 AND bookmaker IN ('pinnacle', 'market_avg', 'market_max')"""):
        odds[(match_id, book)][market] = price
    return history, target, odds


def result_index(hg: int, ag: int) -> int:
    return 0 if hg > ag else 1 if hg == ag else 2


def walk_forward(history, target, xi: float) -> dict[int, np.ndarray]:
    """Prawdopodobieństwa 1X2 dla każdego meczu sezonu, z ponownym dopasowaniem co tydzień."""
    preds, model, week_start = {}, None, None
    for match_id, h, a, _, _, ko in target:
        kick = datetime.fromisoformat(ko)
        if week_start is None or kick - week_start >= timedelta(days=7):
            week_start = kick
            as_of = (kick - timedelta(hours=1)).isoformat(timespec="minutes")
            model = dixon_coles.fit(history, as_of, xi=xi)
        lh, la = model.lambdas(h, a)
        p = score_matrix.matrix(lh, la, model.rho)
        preds[match_id] = np.array([np.tril(p, -1).sum(), np.trace(p), np.triu(p, 1).sum()])
    return preds


def metrics(probs: dict[int, np.ndarray], results: dict[int, int]) -> dict[str, float]:
    ll, brier, rps = [], [], []
    for mid, p in probs.items():
        y = np.zeros(3)
        y[results[mid]] = 1
        ll.append(-np.log(max(p[results[mid]], 1e-12)))
        brier.append(np.square(p - y).sum())
        rps.append(np.square(np.cumsum(p)[:2] - np.cumsum(y)[:2]).sum() / 2)
    return {"log_loss": float(np.mean(ll)), "brier": float(np.mean(brier)), "rps": float(np.mean(rps)), "n": len(ll)}


def blend(p_model: np.ndarray, p_market: np.ndarray, w: float) -> np.ndarray:
    """Łączenie log-liniowe: p ∝ p_model^w · p_rynek^(1−w) (dla dwóch wyników to mieszanie w logitach)."""
    q = np.power(p_model, w) * np.power(p_market, 1 - w)
    return q / q.sum()


def simulate_rules(probs, market_probs, results, odds, best_book: str, p_min=0.52, ev_min=0.03,
                   o_min=1.5, o_max=2.3) -> dict:
    stakes = wins = 0
    profit = 0.0
    for mid, p in probs.items():
        quotes = odds.get((mid, best_book))
        if not quotes:
            continue
        best = None
        for k, market in enumerate(OUTCOMES):
            price = quotes.get(market)
            if price is None or not (o_min <= price <= o_max) or p[k] < p_min:
                continue
            ev = p[k] * price - 1
            if ev >= ev_min and (best is None or ev * p[k] > best[0]):
                best = (ev * p[k], k, price)
        if best:
            _, k, price = best
            stakes += 1
            won = results[mid] == k
            wins += won
            profit += price - 1 if won else -1
    return {"typy": stakes, "trafnosc": wins / stakes if stakes else None, "roi": profit / stakes if stakes else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2024/25")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    history, target, odds = load(conn, args.season)
    results = {m[0]: result_index(m[3], m[4]) for m in target}

    market = {}
    for mid in results:
        quotes = odds.get((mid, "pinnacle")) or odds.get((mid, "market_avg"))
        if quotes and all(o in quotes for o in OUTCOMES):
            market[mid] = np.array(odds_math.shin([quotes[o] for o in OUTCOMES]))
    results = {mid: r for mid, r in results.items() if mid in market}
    print(f"Sezon {args.season}: meczów z kursami zamknięcia {len(results)}")

    report = {"season": args.season, "market": metrics(market, results), "xi": {}}
    print(f"Rynek (Pinnacle/średnia, Shin): {report['market']}")

    best = None
    for xi in XI_GRID:
        preds = {k: v for k, v in walk_forward(history, target, xi).items() if k in results}
        m = metrics(preds, results)
        report["xi"][xi] = m
        print(f"ξ={xi}: model {m}")
        if best is None or m["log_loss"] < best[1]["log_loss"]:
            best = (xi, m, preds)

    xi, _, preds = best
    blends = {w: metrics({mid: blend(preds[mid], market[mid], w) for mid in preds}, results)["log_loss"] for w in W_GRID}
    w_best = min(blends, key=blends.get)
    report.update({"best_xi": xi, "blend_log_loss": blends, "best_w": w_best})
    print(f"Najlepsze ξ = {xi}; mieszanie z rynkiem: najlepsze w = {w_best} (log-loss {blends[w_best]:.4f}, "
          f"model {blends[1.0]:.4f}, rynek {blends[0.0]:.4f})")

    report["rules"] = {}
    for label, w in (("model", 1.0), (f"mieszanka_w{w_best}", w_best)):
        probs = {mid: blend(preds[mid], market[mid], w) for mid in preds}
        for book in ("market_avg", "market_max"):
            r = simulate_rules(probs, market, results, odds, book)
            report["rules"][f"{label}@{book}"] = r
            print(f"Reguły {label}, kursy {book}: {r}")

    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"validate_v1_{args.season.replace('/', '-')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Raport: {out}")


if __name__ == "__main__":
    main()
