"""Elo z mnożnikiem za różnicę goli (docs/04, sekcja 4.2.1).

Ratingi liczone chronologicznie; wynik dla meczu to ratingi SPRZED meczu (bez wycieku).
Między sezonami częściowy powrót do średniej, a beniaminek startuje ze średnią drużyn, które spadły.
"""

import math
from collections import defaultdict

START = 1500.0
K = 20.0
HFA = 60.0
SEASON_REGRESSION = 1 / 3


def pre_match(matches, k: float = K, hfa: float = HFA) -> dict[int, tuple[float, float]]:
    """matches: (id, sezon, kickoff, gospodarz, gość, gole_g, gole_a) chronologicznie -> {id: (R_gosp, R_gość)}."""
    teams_in = defaultdict(set)
    for _, season, _, h, a, *_ in matches:
        teams_in[season] |= {h, a}
    seasons = sorted(teams_in)
    previous = {s: seasons[i - 1] for i, s in enumerate(seasons) if i > 0}

    rating: dict[str, float] = {}
    current_season = None
    out = {}
    for match_id, season, _, home, away, hg, ag in matches:
        if season != current_season:
            current_season = season
            for t in rating:
                rating[t] -= (rating[t] - START) * SEASON_REGRESSION
            prev = previous.get(season)
            relegated = [rating[t] for t in teams_in.get(prev, set()) - teams_in[season] if t in rating]
            newcomer = sum(relegated) / len(relegated) if relegated else START
            for t in teams_in[season]:
                if prev is not None and t not in teams_in[prev]:
                    rating[t] = newcomer          # beniaminek (także powracający po latach)
        rh, ra = rating.setdefault(home, START), rating.setdefault(away, START)
        out[match_id] = (rh, ra)
        expected = 1 / (1 + 10 ** ((ra - rh - hfa) / 400))
        actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        change = k * (math.log(abs(hg - ag) + 1) + 1) * (actual - expected)
        rating[home] = rh + change
        rating[away] = ra - change
    return out
