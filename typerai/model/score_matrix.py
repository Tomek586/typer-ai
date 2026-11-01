"""Macierz wyników i prawdopodobieństwa rynków (docs/04, sekcja 4.6).

Każdy rynek liczymy tak samo: dla każdego wyniku i:j z macierzy rozliczamy zakład funkcją
markets.settle i sumujemy prawdopodobieństwa wyników WIN / HALF_WIN / PUSH / HALF_LOSS / LOSS.
Dzięki temu linie ćwiartkowe i zwroty są obsłużone bez osobnych wzorów.
"""

from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson

from typerai.markets import Outcome, settle

MAX_GOALS = 10


def matrix(lambda_home: float, lambda_away: float, rho: float) -> np.ndarray:
    """P[i, j] = P(gospodarze i goli, goście j goli) z poprawką Dixona-Colesa, znormalizowana."""
    goals = np.arange(MAX_GOALS + 1)
    p = np.outer(poisson.pmf(goals, lambda_home), poisson.pmf(goals, lambda_away))
    p[0, 0] *= 1 - lambda_home * lambda_away * rho
    p[0, 1] *= 1 + lambda_home * rho
    p[1, 0] *= 1 + lambda_away * rho
    p[1, 1] *= 1 - rho
    return p / p.sum()


@dataclass
class MarketProbs:
    win: float
    half_win: float
    push: float
    half_loss: float
    loss: float

    @property
    def p(self) -> float:
        """Prawdopodobieństwo „nieprzegrania” w sensie reguły p ≥ próg (docs/07, 7.2)."""
        return self.win + self.half_win + 0.5 * self.push

    def ev(self, odds: float) -> float:
        """Wartość oczekiwana zakładu przy stawce 1."""
        return (self.win * (odds - 1) + self.half_win * (odds - 1) / 2
                - self.half_loss * 0.5 - self.loss)


def market_probs(p: np.ndarray, market: str) -> MarketProbs:
    totals = {o: 0.0 for o in Outcome}
    n = p.shape[0]
    for i in range(n):
        for j in range(n):
            totals[settle(market, i, j)] += p[i, j]
    return MarketProbs(totals[Outcome.WIN], totals[Outcome.HALF_WIN], totals[Outcome.PUSH],
                       totals[Outcome.HALF_LOSS], totals[Outcome.LOSS])


STANDARD_MARKETS = (
    ["1X2:1", "1X2:X", "1X2:2", "DC:1X", "DC:X2", "DC:12", "BTTS:yes", "BTTS:no"]
    + [f"OU:{line}:{side}" for line in ("1.5", "2.5", "3.5") for side in ("over", "under")]
    + [f"AH:{line}:home" for line in ("-1.5", "-1", "-0.5", "0", "0.5")]
)


def standard_probabilities(p: np.ndarray) -> dict[str, float]:
    """Prawdopodobieństwa wygranej najczęstszych rynków (do zapisu w PREDICTION i do czatu)."""
    return {m: round(market_probs(p, m).p, 4) for m in STANDARD_MARKETS}
