import pytest

from typerai.betting import odds_math


def test_margin():
    assert odds_math.margin([2.0, 2.0]) == pytest.approx(0.0)
    assert odds_math.margin([1.9, 1.9]) == pytest.approx(0.0526, abs=1e-4)


def test_proportional_sums_to_one():
    p = odds_math.proportional([2.2, 3.5, 3.3])
    assert sum(p) == pytest.approx(1.0)
    assert p[0] == pytest.approx(0.4357, abs=1e-4)


def test_shin_sums_to_one_and_shifts_margin_to_longshot():
    odds = [1.30, 5.0, 11.0]
    shin, prop = odds_math.shin(odds), odds_math.proportional(odds)
    assert sum(shin) == pytest.approx(1.0)
    # Faworyt dostaje więcej prawdopodobieństwa niż w metodzie proporcjonalnej, outsider mniej
    assert shin[0] > prop[0]
    assert shin[2] < prop[2]


def test_shin_without_margin_returns_implied():
    assert odds_math.shin([2.0, 2.0]) == pytest.approx([0.5, 0.5])


def test_expected_value():
    assert odds_math.expected_value(0.5, 2.2) == pytest.approx(0.1)
