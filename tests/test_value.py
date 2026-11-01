import pytest

from typerai.betting import value
from typerai.betting.value import Quote
from typerai.model import score_matrix

T = "2026-11-08T10:00+00:00"


def q(book, odds):
    return Quote(book, odds, T)


def test_best_price_drops_outliers_and_exchanges():
    quotes = [q("pinnacle", 2.00), q("unibet", 2.05), q("betclic", 2.10), q("1xbet", 2.60), q("betfair_ex_eu", 2.30)]
    best = value.best_price(quotes)
    assert (best.bookmaker, best.odds) == ("betclic", 2.10)  # 2.60 to błąd oferty, giełda wykluczona


def test_groups():
    assert value.group_of("DC:1X") == ["1X2:1", "1X2:X", "1X2:2"]
    assert value.group_of("AH:0.5:away") == ["AH:-0.5:home", "AH:0.5:away"]
    assert value.group_of("OU:2.5:under") == ["OU:2.5:over", "OU:2.5:under"]
    assert value.is_half_line("AH:-1.5:home") and not value.is_half_line("OU:2.25:over")


def test_fair_probs_prefers_pinnacle_then_median():
    group = ["BTTS:yes", "BTTS:no"]
    with_ref = {"BTTS:yes": [q("pinnacle", 1.9), q("a", 1.8)], "BTTS:no": [q("pinnacle", 1.95), q("a", 1.9)]}
    assert value.fair_probs(with_ref, group) == pytest.approx([1.95 / 3.85, 1.9 / 3.85], abs=2e-3)
    too_few = {"BTTS:yes": [q("a", 1.8)], "BTTS:no": [q("a", 1.9)]}
    assert value.fair_probs(too_few, group) is None


def test_blend_extremes():
    assert value.blend([0.6, 0.4], [0.5, 0.5], 1.0) == pytest.approx([0.6, 0.4])
    assert value.blend([0.6, 0.4], [0.5, 0.5], 0.0) == pytest.approx([0.5, 0.5])


def test_candidates_find_line_shopping_value():
    # Uczciwa cena (Pinnacle bez marży) ok. 60% na gospodarza; ktoś płaci 1,78 -> EV ok. +6%
    # (1,78 mieści się w limicie 8% ponad medianą 1,675; wyższy kurs zostałby odrzucony jako błąd oferty)
    matrix = score_matrix.matrix(1.9, 0.9, -0.05)
    quotes = {
        "1X2:1": [q("pinnacle", 1.62), q("unibet", 1.65), q("betclic", 1.78), q("leovegas", 1.70)],
        "1X2:X": [q("pinnacle", 4.0), q("unibet", 3.9), q("betclic", 3.8), q("leovegas", 3.9)],
        "1X2:2": [q("pinnacle", 5.5), q("unibet", 5.2), q("betclic", 5.0), q("leovegas", 5.3)],
    }
    found = value.candidates(matrix, quotes, w=0.15)
    best = value.choose(found)
    assert best.market == "1X2:1" and best.bookmaker == "betclic" and best.odds == 1.78
    assert best.ev > 0.03 and best.p > 0.52 and best.ref_odds == 1.62


def test_no_candidates_when_price_is_fair():
    matrix = score_matrix.matrix(1.9, 0.9, -0.05)
    quotes = {m: [q("pinnacle", o), q("a", o * 0.98), q("b", o * 0.97)]
              for m, o in (("1X2:1", 1.62), ("1X2:X", 4.0), ("1X2:2", 5.5))}
    assert value.candidates(matrix, quotes, w=0.15) == []
