import numpy as np
import pytest

from typerai import db
from typerai.model import features, glm

POS_RATE = {"G": 0.0, "D": 0.05, "M": 0.15, "F": 0.45}


def squad():
    """Bramkarz 1, obrońcy 2–5, pomocnicy 6–9, napastnicy 10–11 (11 = najlepszy strzelec), rezerwowy bramkarz 12."""
    pos = {1: "G", **{i: "D" for i in range(2, 6)}, **{i: "M" for i in range(6, 10)}, 10: "F", 11: "F", 12: "G"}
    return pos


def history(n=10, scorer_goals=1):
    pos = squad()
    match = [(p, True, 90, scorer_goals if p == 11 else 0, pos[p]) for p in range(1, 12)]
    return [list(match) for _ in range(n)]


def test_full_reference_lineup_is_neutral():
    s = features.lineup_strength(history(), set(range(1, 12)), POS_RATE)
    assert s["att"] == pytest.approx(1.0) and s["reg"] == pytest.approx(1.0) and s["gk_backup"] == 0.0


def test_missing_top_scorer_lowers_attack():
    s = features.lineup_strength(history(), set(range(1, 11)), POS_RATE)
    assert s["att"] < 0.7          # najlepszy strzelec dawał większość wkładu w atak
    assert s["reg"] == pytest.approx(10 / 11)
    assert s["gk_backup"] == 0.0


def test_backup_goalkeeper_is_flagged():
    s = features.lineup_strength(history(), set(range(2, 13)), POS_RATE)   # zamiast bramkarza 1 gra 12
    assert s["gk_backup"] == 1.0
    assert s["att"] == pytest.approx(1.0)


def test_short_history_gives_neutral_values():
    assert features.lineup_strength(history(n=2), {1, 2}, POS_RATE) == features.NEUTRAL_LINEUP


def test_build_uses_only_earlier_matches(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    ids = []
    for day, (h, a, hg, ag) in enumerate([("lech", "legia", 3, 0), ("legia", "lech", 1, 1), ("lech", "legia", 0, 5)]):
        ids.append(conn.execute(
            """INSERT INTO match (season, kickoff_utc, home_id, away_id, hg, ag, status)
               VALUES ('2025/26', ?, ?, ?, ?, ?, 'finished')""",
            (f"2025-08-{day * 4 + 1:02d}T18:00+00:00", h, a, hg, ag)).lastrowid)
    conn.commit()
    f = features.build(conn)
    # przed pierwszym meczem brak historii: wartości domyślne
    assert f[ids[0]]["home"]["form_gf"] == 1.3 and f[ids[0]]["home"]["rest_days"] == features.REST_CAP
    # forma przed meczem 3 zależy tylko od meczów 1 i 2, nie od wyniku 0:5
    before = f[ids[2]]["home"]["form_gf"]
    conn.execute("UPDATE match SET ag = 0 WHERE id = ?", (ids[2],))
    assert features.build(conn)[ids[2]]["home"]["form_gf"] == before
    assert f[ids[2]]["home"]["rest_days"] == pytest.approx(4.0)


def test_glm_recovers_known_effect():
    rng = np.random.default_rng(1)
    n = 6000
    x = rng.normal(size=(n, 2))
    offset = np.log(rng.uniform(0.8, 2.0, size=n))
    goals = rng.poisson(np.exp(offset + 0.2 * x[:, 0]))       # druga cecha bez wpływu
    model = glm.fit(x, goals, offset, ["a", "b"], alpha=1.0)
    assert model.beta[0] == pytest.approx(0.2, abs=0.04)
    assert abs(model.beta[1]) < 0.04
    assert abs(model.b0) < 0.04


def test_glm_ratio_is_clipped():
    model = glm.LambdaGLM(["a"], np.array([0.0]), np.array([1.0]), 0.0, np.array([5.0]))
    assert model.ratio(np.array([[10.0]]))[0] == glm.RATIO_MAX
    assert model.ratio(np.array([[-10.0]]))[0] == glm.RATIO_MIN
    assert model.contributions([1.0]) == {"a": 5.0}


def test_season_rounds_follow_league_format():
    assert features.season_rounds("2017/18", 16) == 37      # ESA-37
    assert features.season_rounds("2020/21", 16) == 30
    assert features.season_rounds("2026/27", 18) == 34


def test_motivation_from_table():
    # 18 drużyn, 3 spadają, 3 miejsca pucharowe; punkty: t0 = 60, t1 = 59, …, t17 = 43
    points = {f"t{i}": 60.0 - i for i in range(18)}
    early = features.motivation(points, "t16", rounds_left=20, n_relegated=3)
    assert early == {"releg_pressure": 0.0, "euro_pressure": 0.0, "nothing_to_play": 0.0}
    late = features.motivation(points, "t14", rounds_left=4, n_relegated=3)  # 1 pkt nad strefą (t15 = 45)
    assert late["releg_pressure"] == pytest.approx(1 - 1 / 12)
    assert features.motivation(points, "t16", 4, 3)["releg_pressure"] == 1.0    # w strefie spadkowej
    assert features.motivation(points, "t0", 4, 3)["euro_pressure"] == 1.0      # lider
    spread = {f"t{i}": 100.0 - 5 * i for i in range(18)}                       # duże różnice punktowe
    assert features.motivation(spread, "t8", 2, 3)["nothing_to_play"] == 1.0
