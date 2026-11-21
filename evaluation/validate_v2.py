"""Walidacja modelu v2 (λ-GLM na cechach meczu) – docs/04 4.5 i 4.10, docs/10 A.

Krok 1: Dixon-Coles walk-forward (dopasowanie co tydzień) daje λ „spoza próby” dla każdego meczu
        sezonów 2016/17–2024/25; wynik trafia do evaluation/cache (liczony raz, ok. 4 min).
Krok 2: dla sezonu walidacyjnego S λ-GLM uczymy na sezonach od 2016/17 do S−1, a oceniamy na S.
Krok 3: porównanie wariantów cech (ablacja) po log-loss 1X2 i OU 2.5 oraz po mieszaniu z rynkiem.

Sezon testowy 2025/26 nie jest tu używany (docs/10, A.1).

    .venv/Scripts/python -m evaluation.validate_v2
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from evaluation import validate_v1 as v1
from typerai import config
from typerai.betting import odds_math
from typerai.model import dixon_coles, features, glm, score_matrix

FIRST_TRAIN = "2016/17"      # pierwszy sezon z pełnym oknem składów (90minut.pl od 2015/16)
VALIDATION = ["2023/24", "2024/25"]
SEASONS = ["2016/17", "2017/18", "2018/19", "2019/20", "2020/21", "2021/22", "2022/23", "2023/24", "2024/25"]
ALPHAS = [1.0, 10.0, 100.0, 1000.0]
CACHE = Path(__file__).parent / "cache"
REPORT_DIR = Path(__file__).parent / "reports"

# Grupy cech (docs/04, 4.5). Każda cecha opisuje drużynę „atakującą” (own) i jej rywala (opp).
GROUPS = {
    "forma": ["form_gf_own", "form_ga_opp"],
    "odpoczynek": ["rest_diff"],
    "sklad_prev": ["att_prev_own", "reg_prev_own", "reg_prev_opp", "gk_backup_prev_opp"],
    "sklad_off": ["att_off_own", "reg_off_own", "reg_off_opp", "gk_backup_off_opp"],
}
VARIANTS = {
    "v1 (Dixon-Coles)": [],
    "+ forma": ["forma"],
    "+ odpoczynek": ["odpoczynek"],
    "+ skład z poprzedniego meczu": ["sklad_prev"],
    "+ forma, odpoczynek, skład poprzedni (realny v2)": ["forma", "odpoczynek", "sklad_prev"],
    "+ skład oficjalny (górna granica)": ["sklad_off"],
    "+ forma, odpoczynek, skład oficjalny": ["forma", "odpoczynek", "sklad_off"],
}


def dc_lambdas(conn: sqlite3.Connection, xi: float) -> dict[int, tuple[float, float, float]]:
    """λ_gosp, λ_gość, ρ z Dixona-Colesa dopasowanego co tydzień tylko na wcześniejszych meczach."""
    path = CACHE / f"dc_lambdas_xi{xi:g}.json"
    if path.exists():
        return {int(k): tuple(v) for k, v in json.loads(path.read_text()).items()}
    history = conn.execute(
        "SELECT home_id, away_id, hg, ag, kickoff_utc FROM match WHERE status = 'finished'").fetchall()
    out = {}
    for season in SEASONS:
        target = conn.execute(
            """SELECT id, home_id, away_id, kickoff_utc FROM match
               WHERE season = ? AND status = 'finished' ORDER BY kickoff_utc""", (season,)).fetchall()
        model, week_start = None, None
        for match_id, h, a, ko in target:
            kick = datetime.fromisoformat(ko)
            if week_start is None or kick - week_start >= timedelta(days=7):
                week_start = kick
                model = dixon_coles.fit(history, (kick - timedelta(hours=1)).isoformat(timespec="minutes"), xi=xi)
            lh, la = model.lambdas(h, a)
            out[match_id] = (lh, la, model.rho)
        print(f"  Dixon-Coles walk-forward {season}: {len(target)} meczów", flush=True)
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def team_rows(match_feats: dict, side: str) -> dict[str, float]:
    own, opp = match_feats[side], match_feats["away" if side == "home" else "home"]
    return {
        "form_gf_own": own["form_gf"], "form_ga_opp": opp["form_ga"],
        "rest_diff": own["rest_days"] - opp["rest_days"],
        **{f"{k}_{v}_own": own[f"{k}_{v}"] for k in ("att", "reg") for v in ("prev", "off")},
        **{f"reg_{v}_opp": opp[f"reg_{v}"] for v in ("prev", "off")},
        **{f"gk_backup_{v}_opp": opp[f"gk_backup_{v}"] for v in ("prev", "off")},
    }


def build_rows(conn, lambdas, feats):
    """Dwa wiersze na mecz (gospodarz i gość jako drużyna „atakująca”)."""
    rows = []
    for match_id, season, hg, ag in conn.execute(
            "SELECT id, season, hg, ag FROM match WHERE status = 'finished' AND hg IS NOT NULL"):
        if match_id not in lambdas or match_id not in feats:
            continue
        lh, la, rho = lambdas[match_id]
        for side, goals, lam in (("home", hg, lh), ("away", ag, la)):
            rows.append({"match_id": match_id, "season": season, "side": side, "goals": goals,
                         "lambda_dc": lam, "rho": rho, **team_rows(feats[match_id], side)})
    return rows


def probabilities(lh: float, la: float, rho: float) -> tuple[np.ndarray, float]:
    """1X2 oraz P(powyżej 2,5 gola) z macierzy wyników."""
    p = score_matrix.matrix(lh, la, rho)
    one_x_two = np.array([np.tril(p, -1).sum(), np.trace(p), np.triu(p, 1).sum()])
    total = np.add.outer(np.arange(p.shape[0]), np.arange(p.shape[1]))
    return one_x_two, float(p[total >= 3].sum())


def evaluate(rows, season: str, names: list[str], alpha: float):
    """Uczy λ-GLM na sezonach < season i zwraca prognozy {mecz: (1X2, P(over 2,5))} dla sezonu."""
    train = [r for r in rows if FIRST_TRAIN <= r["season"] < season]
    test = [r for r in rows if r["season"] == season]
    model = None
    if names:
        model = glm.fit(np.array([[r[n] for n in names] for r in train]),
                        np.array([r["goals"] for r in train]),
                        np.log([r["lambda_dc"] for r in train]), names, alpha)
    by_match: dict[int, dict] = {}
    for r in test:
        ratio = float(model.ratio(np.array([r[n] for n in names]))[0]) if model else 1.0
        by_match.setdefault(r["match_id"], {"rho": r["rho"]})[r["side"]] = r["lambda_dc"] * ratio
    preds = {mid: probabilities(d["home"], d["away"], d["rho"]) for mid, d in by_match.items()}
    return preds, model


def log_loss_ou(preds, totals):
    ll = [-np.log(max(p if totals[mid] >= 3 else 1 - p, 1e-12)) for mid, (_, p) in preds.items()]
    return float(np.mean(ll))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xi", type=float, default=config.MODEL["xi"])
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{Path(config.DB_PATH).as_posix()}?mode=ro", uri=True)
    lambdas = dc_lambdas(conn, args.xi)
    rows = build_rows(conn, lambdas, features.build(conn))
    print(f"Wierszy (drużyna-mecz): {len(rows)}; sezony treningowe od {FIRST_TRAIN}")

    report = {}
    for season in VALIDATION:
        _, target, odds = v1.load(conn, season)
        results = {m[0]: v1.result_index(m[3], m[4]) for m in target}
        totals = {m[0]: m[3] + m[4] for m in target}
        market = {}
        for mid in results:
            q = odds.get((mid, "pinnacle")) or odds.get((mid, "market_avg"))
            if q and all(o in q for o in v1.OUTCOMES):
                market[mid] = np.array(odds_math.shin([q[o] for o in v1.OUTCOMES]))
        results = {k: r for k, r in results.items() if k in market}
        season_report = {"market_1x2": v1.metrics(market, results)["log_loss"], "n": len(results), "variants": {}}
        print(f"\nSezon {season} ({len(results)} meczów); rynek 1X2: {season_report['market_1x2']:.4f}")
        print(f"  {'wariant':52} {'alpha':>6} {'1X2':>7} {'OU2.5':>7} {'mieszanka':>9} {'best w':>6}")
        for label, groups in VARIANTS.items():
            names = [n for g in groups for n in GROUPS[g]]
            best = None
            for alpha in (ALPHAS if names else [0.0]):
                preds, model = evaluate(rows, season, names, alpha)
                preds = {k: v for k, v in preds.items() if k in results}
                ll = v1.metrics({k: p for k, (p, _) in preds.items()}, results)["log_loss"]
                if best is None or ll < best["log_loss_1x2"]:
                    blends = {w: v1.metrics({k: v1.blend(preds[k][0], market[k], w) for k in preds}, results)["log_loss"]
                              for w in v1.W_GRID}
                    best = {"alpha": alpha, "log_loss_1x2": ll, "log_loss_ou25": log_loss_ou(preds, totals),
                            "blend_prod_w": blends[config.MODEL["blend_w"]], "best_w": min(blends, key=blends.get),
                            "blend_best": min(blends.values()),
                            "beta": dict(zip(model.names, map(float, model.beta))) if model else {}}
            season_report["variants"][label] = best
            print(f"  {label:52} {best['alpha']:>6g} {best['log_loss_1x2']:>7.4f} {best['log_loss_ou25']:>7.4f} "
                  f"{best['blend_prod_w']:>9.4f} {best['best_w']:>6g}")
        report[season] = season_report

    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / "validate_v2.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRaport: {path}")


if __name__ == "__main__":
    main()
