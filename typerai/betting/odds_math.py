"""Kursy, marża i usuwanie marży (docs/07, sekcja 7.1)."""


def margin(odds: list[float]) -> float:
    """Marża bukmachera na rynku: Σ(1/kurs) − 1."""
    return sum(1 / o for o in odds) - 1


def proportional(odds: list[float]) -> list[float]:
    """Prawdopodobieństwa bez marży, metoda proporcjonalna."""
    raw = [1 / o for o in odds]
    total = sum(raw)
    return [r / total for r in raw]


def shin(odds: list[float], tol: float = 1e-10) -> list[float]:
    """Prawdopodobieństwa bez marży metodą Shina.

    Uwzględnia, że bukmacher zawyża marżę głównie na outsiderach (favourite-longshot bias).
    Szukamy z, dla którego suma p_k(z) = 1 (bisekcja; suma maleje wraz z z).
    """
    raw = [1 / o for o in odds]
    booksum = sum(raw)
    if booksum <= 1:
        return [r / booksum for r in raw]

    def probs(z: float) -> list[float]:
        return [((z * z + 4 * (1 - z) * r * r / booksum) ** 0.5 - z) / (2 * (1 - z)) for r in raw]

    lo, hi = 0.0, 0.4
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if sum(probs(mid)) > 1:
            lo = mid
        else:
            hi = mid
    p = probs((lo + hi) / 2)
    total = sum(p)
    return [x / total for x in p]


def expected_value(p: float, odds: float) -> float:
    """EV przy stawce 1 dla zakładu bez zwrotów: p·kurs − 1."""
    return p * odds - 1
