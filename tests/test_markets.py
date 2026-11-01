import pytest

from typerai.markets import Outcome, profit, settle

W, HW, P, HL, L = Outcome.WIN, Outcome.HALF_WIN, Outcome.PUSH, Outcome.HALF_LOSS, Outcome.LOSS


@pytest.mark.parametrize("market, hg, ag, expected", [
    ("1X2:1", 2, 1, W), ("1X2:X", 2, 1, L), ("1X2:X", 1, 1, W), ("1X2:2", 0, 3, W),
    ("DC:1X", 1, 1, W), ("DC:1X", 0, 1, L), ("DC:12", 0, 0, L), ("DC:X2", 0, 2, W),
    ("BTTS:yes", 1, 1, W), ("BTTS:yes", 2, 0, L), ("BTTS:no", 2, 0, W),
    # gole: linie połówkowe, całkowite i ćwiartkowe
    ("OU:2.5:over", 2, 1, W), ("OU:2.5:over", 1, 1, L), ("OU:2.5:under", 1, 1, W),
    ("OU:3:over", 2, 1, P), ("OU:3:over", 3, 1, W), ("OU:3:under", 1, 1, W),
    ("OU:2.25:over", 1, 1, HL), ("OU:2.25:over", 2, 1, W), ("OU:2.25:under", 1, 1, HW),
    ("OU:2.75:over", 2, 1, HW), ("OU:2.75:under", 2, 1, HL), ("OU:2.75:over", 1, 1, L),
    # handicap azjatycki z perspektywy typowanej drużyny
    ("AH:0:home", 1, 1, P), ("AH:-0.5:home", 1, 0, W), ("AH:-0.5:home", 1, 1, L),
    ("AH:-0.25:home", 1, 1, HL), ("AH:0.25:away", 1, 1, HW), ("AH:-0.75:home", 1, 0, HW),
    ("AH:-0.75:home", 2, 0, W), ("AH:0.75:away", 1, 0, HL), ("AH:-1:home", 1, 0, P),
    ("AH:1.5:away", 2, 1, W), ("AH:-1.5:home", 2, 1, L),
])
def test_settle(market, hg, ag, expected):
    assert settle(market, hg, ag) == expected


def test_profit():
    assert profit(W, 2.0) == 1.0
    assert profit(HW, 2.0) == 0.5
    assert profit(P, 2.0) == 0.0
    assert profit(HL, 2.0) == -0.5
    assert profit(L, 2.0) == -1.0


def test_unknown_market():
    with pytest.raises(ValueError):
        settle("CRN:9.5:over", 1, 0)
