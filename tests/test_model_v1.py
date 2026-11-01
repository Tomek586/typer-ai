from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from typerai.model import dixon_coles, score_matrix


def test_matrix_sums_to_one_and_1x2_consistent():
    p = score_matrix.matrix(1.6, 1.1, -0.05)
    assert p.sum() == pytest.approx(1.0)
    probs = [score_matrix.market_probs(p, m).p for m in ("1X2:1", "1X2:X", "1X2:2")]
    assert sum(probs) == pytest.approx(1.0)
    assert probs[0] > probs[2]  # gospodarz z wyższą λ jest faworytem


def test_over_under_complementary_and_quarter_line_ev():
    p = score_matrix.matrix(1.4, 1.2, 0.0)
    over, under = (score_matrix.market_probs(p, f"OU:2.5:{s}") for s in ("over", "under"))
    assert over.win + under.win == pytest.approx(1.0)
    # linia 2.25 = pół stawki na 2.0 i pół na 2.5
    q = score_matrix.market_probs(p, "OU:2.25:over")
    o2, o25 = score_matrix.market_probs(p, "OU:2:over"), score_matrix.market_probs(p, "OU:2.5:over")
    assert q.ev(1.9) == pytest.approx((o2.ev(1.9) + o25.ev(1.9)) / 2)


def test_ah_zero_equals_draw_no_bet():
    p = score_matrix.matrix(1.5, 1.0, -0.05)
    ah = score_matrix.market_probs(p, "AH:0:home")
    x = score_matrix.market_probs(p, "1X2:X").win
    assert ah.push == pytest.approx(x)
    assert ah.ev(2.0) == pytest.approx(ah.win * 1.0 - ah.loss)


def _synthetic_league(seed=1, seasons=3):
    """Liga z drużyną wyraźnie mocniejszą i wyraźnie słabszą; model powinien to odtworzyć."""
    rng = np.random.default_rng(seed)
    strength = {"a": 0.4, "b": 0.1, "c": 0.0, "d": -0.1, "e": -0.4, "f": 0.0}
    start = datetime(2023, 8, 1, tzinfo=timezone.utc)
    matches, day = [], 0
    for _ in range(seasons * 2):
        for h in strength:
            for a in strength:
                if h == a:
                    continue
                lh = np.exp(0.25 + 0.25 + strength[h] - strength[a] * 0.5)
                la = np.exp(0.25 + strength[a] - strength[h] * 0.5)
                ko = (start + timedelta(days=day)).isoformat(timespec="minutes")
                matches.append((h, a, int(rng.poisson(lh)), int(rng.poisson(la)), ko))
                day += 1
    return matches, (start + timedelta(days=day + 1)).isoformat(timespec="minutes")


def test_dixon_coles_recovers_team_order():
    matches, as_of = _synthetic_league()
    model = dixon_coles.fit(matches, as_of, xi=0.0)
    lh_strong, la_weak = model.lambdas("a", "e")
    assert lh_strong > la_weak
    assert model.home > 0
    att = dict(zip(model.teams, model.attack))
    assert att["a"] == max(att.values()) and att["e"] == min(att.values())


def test_unknown_team_gets_league_average():
    matches, as_of = _synthetic_league()
    model = dixon_coles.fit(matches, as_of)
    lh, la = model.lambdas("nowa", "nowa2")
    assert lh > la  # różnią się tylko przewagą własnego boiska


def test_too_few_matches():
    with pytest.raises(ValueError):
        dixon_coles.fit([("a", "b", 1, 0, "2026-01-01T12:00+00:00")], "2026-02-01T12:00+00:00")
