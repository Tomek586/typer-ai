"""Model Dixona-Colesa z ważeniem czasem (docs/04, sekcja 4.3).

    λ_gosp = exp(μ + h + atak_gosp − obrona_gość)
    λ_gość = exp(μ + atak_gość − obrona_gosp)
    P(x, y) = τ(x, y; λ_gosp, λ_gość, ρ) · Pois(x; λ_gosp) · Pois(y; λ_gość)

Parametry szacujemy metodą największej wiarygodności; mecz sprzed t dni ma wagę exp(−ξ·t).
Lekka regularyzacja L2 ściąga parametry drużyn z małą liczbą meczów do średniej ligowej.
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

DEFAULT_XI = 0.0025     # ważenie czasem na dzień (strojone na walidacji)
DEFAULT_L2 = 0.05       # siła regularyzacji parametrów drużyn
HISTORY_DAYS = 1500     # starsze mecze mają wagę < exp(−3,75) ≈ 0,02 – pomijamy je dla szybkości


@dataclass
class DixonColesModel:
    teams: list[str]
    attack: np.ndarray
    defence: np.ndarray
    home: float
    mu: float
    rho: float

    def lambdas(self, home_id: str, away_id: str) -> tuple[float, float]:
        i = self._index(home_id)
        j = self._index(away_id)
        a_h, d_h = (self.attack[i], self.defence[i]) if i is not None else (0.0, 0.0)
        a_a, d_a = (self.attack[j], self.defence[j]) if j is not None else (0.0, 0.0)
        return float(np.exp(self.mu + self.home + a_h - d_a)), float(np.exp(self.mu + a_a - d_h))

    def _index(self, team_id: str) -> int | None:
        # drużyna bez meczów w historii (np. beniaminek przed pierwszym meczem) = średnia ligowa
        return self.teams.index(team_id) if team_id in self.teams else None


def _tau(x: np.ndarray, y: np.ndarray, lh: np.ndarray, la: np.ndarray, rho: float) -> np.ndarray:
    tau = np.ones_like(lh)
    tau = np.where((x == 0) & (y == 0), 1 - lh * la * rho, tau)
    tau = np.where((x == 0) & (y == 1), 1 + lh * rho, tau)
    tau = np.where((x == 1) & (y == 0), 1 + la * rho, tau)
    tau = np.where((x == 1) & (y == 1), 1 - rho, tau)
    return tau


def fit(matches: list[tuple[str, str, int, int, str]], as_of: str, xi: float = DEFAULT_XI,
        l2: float = DEFAULT_L2) -> DixonColesModel:
    """matches: (home_id, away_id, hg, ag, kickoff_utc) – tylko mecze rozegrane przed as_of."""
    ref = datetime.fromisoformat(as_of)
    rows = []
    for h, a, hg, ag, ko in matches:
        days = (ref - datetime.fromisoformat(ko)).total_seconds() / 86400
        if 0 < days <= HISTORY_DAYS:
            rows.append((h, a, hg, ag, days))
    if len(rows) < 50:
        raise ValueError(f"Za mało meczów do dopasowania modelu ({len(rows)})")

    teams = sorted({r[0] for r in rows} | {r[1] for r in rows})
    idx = {t: k for k, t in enumerate(teams)}
    n = len(teams)
    hi = np.array([idx[r[0]] for r in rows])
    ai = np.array([idx[r[1]] for r in rows])
    x = np.array([r[2] for r in rows], dtype=float)
    y = np.array([r[3] for r in rows], dtype=float)
    w = np.exp(-xi * np.array([r[4] for r in rows]))
    const = gammaln(x + 1) + gammaln(y + 1)

    def unpack(theta):
        attack = np.append(theta[: n - 1], -theta[: n - 1].sum())   # Σ atak = 0
        defence = theta[n - 1: 2 * n - 1]
        mu, home, rho = theta[2 * n - 1:]
        return attack, defence, mu, home, rho

    def nll(theta):
        attack, defence, mu, home, rho = unpack(theta)
        lh = np.exp(mu + home + attack[hi] - defence[ai])
        la = np.exp(mu + attack[ai] - defence[hi])
        tau = np.clip(_tau(x, y, lh, la, rho), 1e-10, None)
        loglik = np.log(tau) + x * np.log(lh) - lh + y * np.log(la) - la - const
        return -(w * loglik).sum() + l2 * (np.square(attack).sum() + np.square(defence).sum())

    theta0 = np.concatenate([np.zeros(n - 1), np.zeros(n), [np.log(1.3), 0.25, -0.05]])
    bounds = [(None, None)] * (2 * n - 1) + [(None, None), (None, None), (-0.25, 0.25)]
    res = minimize(nll, theta0, method="L-BFGS-B", bounds=bounds)
    if not res.success:
        raise RuntimeError(f"Dopasowanie Dixona-Colesa nie zbiegło: {res.message}")
    attack, defence, mu, home, rho = unpack(res.x)
    return DixonColesModel(teams, attack, defence, float(home), float(mu), float(rho))
