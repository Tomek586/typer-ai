"""Kody rynków i rozliczanie zakładów (docs/03, sekcja 3.4).

Kody: 1X2:{1|X|2}, DC:{1X|X2|12}, OU:{linia}:{over|under}, BTTS:{yes|no}, AH:{linia}:{home|away}.
Linie gole/handicap mogą być całkowite (zwrot przy równości), połówkowe i ćwiartkowe
(np. 2.25 – stawka dzielona po połowie na linie 2.0 i 2.5).
"""

from enum import Enum


class Outcome(str, Enum):
    WIN = "WIN"
    HALF_WIN = "HALF_WIN"
    PUSH = "PUSH"
    HALF_LOSS = "HALF_LOSS"
    LOSS = "LOSS"


# Zysk przy stawce 1 jako funkcja kursu
def profit(outcome: Outcome, odds: float) -> float:
    return {
        Outcome.WIN: odds - 1,
        Outcome.HALF_WIN: (odds - 1) / 2,
        Outcome.PUSH: 0.0,
        Outcome.HALF_LOSS: -0.5,
        Outcome.LOSS: -1.0,
    }[outcome]


def family(market: str) -> str:
    """Rodzina rynku do kalibracji i raportów: '1X2', 'DC', 'OU', 'BTTS', 'AH'."""
    return market.split(":")[0]


def _single_line(margin: float) -> Outcome:
    if margin > 0:
        return Outcome.WIN
    if margin < 0:
        return Outcome.LOSS
    return Outcome.PUSH


def _line_outcome(margin_without_line: float, line: float) -> Outcome:
    """Wynik zakładu z linią: wynik + linia > 0 wygrywa; linia ćwiartkowa = dwie połówki stawki."""
    if (line * 4) % 2 == 0:  # linia całkowita lub połówkowa
        return _single_line(margin_without_line + line)
    a = _single_line(margin_without_line + line - 0.25)
    b = _single_line(margin_without_line + line + 0.25)
    pair = {a, b}
    if pair == {Outcome.WIN}:
        return Outcome.WIN
    if pair == {Outcome.LOSS}:
        return Outcome.LOSS
    if pair == {Outcome.WIN, Outcome.PUSH}:
        return Outcome.HALF_WIN
    if pair == {Outcome.LOSS, Outcome.PUSH}:
        return Outcome.HALF_LOSS
    raise ValueError(f"Nieoczekiwana kombinacja połówek: {pair}")


def settle(market: str, hg: int, ag: int) -> Outcome:
    parts = market.split(":")
    kind = parts[0]
    if kind == "1X2":
        actual = "1" if hg > ag else "X" if hg == ag else "2"
        return Outcome.WIN if parts[1] == actual else Outcome.LOSS
    if kind == "DC":
        actual = "1" if hg > ag else "X" if hg == ag else "2"
        return Outcome.WIN if actual in parts[1] else Outcome.LOSS
    if kind == "BTTS":
        both = hg > 0 and ag > 0
        return Outcome.WIN if both == (parts[1] == "yes") else Outcome.LOSS
    if kind == "OU":
        line, side = float(parts[1]), parts[2]
        total = hg + ag
        # over: wygrywa, gdy suma > linia; zapis jako „margines + linia > 0” z linią ujemną
        return _line_outcome(total if side == "over" else -total, -line if side == "over" else line)
    if kind == "AH":
        line, side = float(parts[1]), parts[2]
        diff = hg - ag if side == "home" else ag - hg
        return _line_outcome(diff, line)
    raise ValueError(f"Nieznany rynek: {market}")
