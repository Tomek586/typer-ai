import pytest

from typerai.model.ratings import elo, pi


def m(mid, season, h, a, hg, ag):
    return (mid, season, f"2020-01-{mid:02d}T18:00+00:00", h, a, hg, ag)


def test_elo_uses_ratings_before_the_match_and_conserves_points():
    out = elo.pre_match([m(1, "s1", "lech", "legia", 2, 0), m(2, "s1", "legia", "lech", 0, 0)])
    assert out[1] == (elo.START, elo.START)
    rh, ra = out[2]                            # po wygranej Lecha
    assert ra > elo.START > rh                 # legia (gospodarz meczu 2) straciła, lech zyskał
    assert rh + ra == pytest.approx(2 * elo.START)


def test_elo_bigger_win_moves_rating_more():
    small = elo.pre_match([m(1, "s1", "a", "b", 1, 0), m(2, "s1", "a", "b", 0, 0)])[2][0]
    big = elo.pre_match([m(1, "s1", "a", "b", 4, 0), m(2, "s1", "a", "b", 0, 0)])[2][0]
    assert big > small > elo.START


def test_elo_season_regression_and_promoted_team():
    matches = [m(1, "s1", "a", "b", 3, 0), m(2, "s1", "c", "b", 3, 0),     # b przegrywa i spada
               m(3, "s2", "a", "c", 0, 0), m(4, "s2", "d", "a", 0, 0)]     # d to beniaminek
    out = elo.pre_match(matches)
    b_after_s1 = elo.pre_match(matches[:2] + [m(5, "s1", "b", "a", 0, 0)])[5][0]
    expected_newcomer = b_after_s1 - (b_after_s1 - elo.START) * elo.SEASON_REGRESSION
    assert out[4][0] == pytest.approx(expected_newcomer)                   # d startuje jak drużyna, która spadła
    assert out[4][0] < elo.START


def test_pi_expected_goal_diff_is_symmetric():
    assert pi.expected_goal_diff(0.0) == 0.0
    assert pi.expected_goal_diff(1.5) == pytest.approx(-pi.expected_goal_diff(-1.5))
    assert pi.expected_goal_diff(3.0) == pytest.approx(9.0)


def test_pi_home_win_updates_home_and_away_ratings():
    out = pi.pre_match([m(1, "s1", "lech", "legia", 3, 0), m(2, "s1", "lech", "legia", 0, 0)])
    assert out[1] == (0.0, 0.0, 0.0, 0.0)
    hh, ha, ah, aa = out[2]
    assert hh > 0 and ha == pytest.approx(pi.GAMMA * hh)     # rating wyjazdowy Lecha rośnie o γ·zmianę
    assert aa == pytest.approx(-hh) and ah == pytest.approx(-ha)
