"""λ-GLM: korekta oczekiwanych goli Dixona-Colesa o cechy meczu (docs/04, sekcja 4.5).

    gole_own ~ Poisson(λ),   log λ = log λ_DC_own + b0 + β·x

Offset log λ_DC sprawia, że model uczy się tylko tego, czego Dixon-Coles nie widzi. Cechy są
standaryzowane na zbiorze treningowym, β ma regularyzację L2 (b0 bez kary), a korekta
λ / λ_DC jest obcinana do [0,75; 1,33].
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

RATIO_MIN, RATIO_MAX = 0.75, 1.33


@dataclass
class LambdaGLM:
    names: list[str]
    mean: np.ndarray
    std: np.ndarray
    b0: float
    beta: np.ndarray

    def ratio(self, x: np.ndarray) -> np.ndarray:
        """Mnożnik λ_DC dla wierszy cech x (kształt n × k)."""
        z = (np.atleast_2d(x) - self.mean) / self.std
        return np.clip(np.exp(self.b0 + z @ self.beta), RATIO_MIN, RATIO_MAX)

    def contributions(self, x: np.ndarray) -> dict[str, float]:
        """Składniki β_k·z_k jednego wiersza – do wyjaśnień w PREDICTION.features."""
        z = (np.asarray(x, dtype=float) - self.mean) / self.std
        return {n: float(b * v) for n, b, v in zip(self.names, self.beta, z)}


def fit(x: np.ndarray, goals: np.ndarray, offset: np.ndarray, names: list[str], alpha: float = 1.0) -> LambdaGLM:
    """Regresja Poissona z offsetem i karą L2: minimalizuje Σ(λ − y·log λ) + alpha·‖β‖²."""
    x = np.asarray(x, dtype=float)
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std == 0] = 1.0
    z = (x - mean) / std
    y = np.asarray(goals, dtype=float)
    off = np.asarray(offset, dtype=float)

    def loss(theta):
        eta = off + theta[0] + z @ theta[1:]
        lam = np.exp(eta)
        value = (lam - y * eta).sum() + alpha * np.square(theta[1:]).sum()
        resid = lam - y
        grad = np.concatenate([[resid.sum()], z.T @ resid + 2 * alpha * theta[1:]])
        return value, grad

    res = minimize(loss, np.zeros(z.shape[1] + 1), jac=True, method="L-BFGS-B")
    if not res.success:
        raise RuntimeError(f"λ-GLM nie zbiegł: {res.message}")
    return LambdaGLM(names, mean, std, float(res.x[0]), res.x[1:])
