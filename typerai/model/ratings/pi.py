"""Pi-ratings (Constantinou i Fenton, 2013; docs/04, sekcja 4.2.2).

Każda drużyna ma rating u siebie (H) i na wyjeździe (A). Wynik dla meczu to ratingi SPRZED meczu.
"""

import math

LAMBDA = 0.035
GAMMA = 0.7


def expected_goal_diff(rating: float) -> float:
    """ĝ(R) = sign(R)·(10^{|R|/3} − 1)."""
    return math.copysign(10 ** (abs(rating) / 3) - 1, rating)


def pre_match(matches, lam: float = LAMBDA, gamma: float = GAMMA) -> dict[int, tuple[float, float, float, float]]:
    """-> {id: (R_gosp^H, R_gosp^A, R_gość^H, R_gość^A)} sprzed meczu."""
    home_r: dict[str, float] = {}
    away_r: dict[str, float] = {}
    out = {}
    for match_id, _, _, home, away, hg, ag in matches:
        hh, ha = home_r.get(home, 0.0), away_r.get(home, 0.0)
        ah, aa = home_r.get(away, 0.0), away_r.get(away, 0.0)
        out[match_id] = (hh, ha, ah, aa)
        error = (hg - ag) - (expected_goal_diff(hh) - expected_goal_diff(aa))
        psi = math.copysign(3 * math.log10(1 + abs(error)), error)
        home_r[home] = hh + lam * psi
        away_r[home] = ha + gamma * lam * psi
        away_r[away] = aa - lam * psi
        home_r[away] = ah - gamma * lam * psi
    return out
