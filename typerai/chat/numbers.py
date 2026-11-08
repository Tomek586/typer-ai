"""Guardrail G5 (docs/08, 8.6): liczby w odpowiedzi muszą pochodzić z wyników narzędzi.

Sprawdzamy liczby dziesiętne i procenty z odpowiedzi modelu: każda musi odpowiadać jakiejś liczbie
z wyników narzędzi wywołanych w tej turze (z tolerancją na zaokrąglenia i zapis procentowy: 0.649 ↔ 64,9%).
Liczby całkowite bez % (np. „3 z 4”, „5 meczów”, godziny) pomijamy – dają za dużo fałszywych alarmów.
"""

import json
import re

NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(\s?%)?")


def answer_numbers(text: str) -> list[float]:
    """Liczby do sprawdzenia: dziesiętne albo z procentem."""
    out = []
    for value, percent in NUMBER.findall(text):
        if percent or "." in value or "," in value:
            out.append(float(value.replace(",", ".")))
    return out


def tool_numbers(results: list) -> list[float]:
    """Wszystkie liczby z wyników narzędzi – także te zapisane w tekstach (np. daty, reguły)."""
    found: list[float] = []

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            found.append(float(x))
        elif isinstance(x, str):
            found.extend(float(v.replace(",", ".")) for v, _ in NUMBER.findall(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(json.loads(json.dumps(results, default=str)))
    return found


def _matches(x: float, t: float) -> bool:
    t = abs(t)
    return (abs(x - t) <= 0.006 * max(1.0, t)          # ten sam zapis, po zaokrągleniu
            or abs(x - 100 * t) <= 0.06                  # 0.649 -> 64,9%
            or abs(x - round(100 * t)) <= 0.5 and t < 1)  # 0.649 -> 65%


def unverified(answer: str, results: list) -> list[float]:
    """Liczby z odpowiedzi, których nie ma w wynikach narzędzi."""
    known = tool_numbers(results)
    return [x for x in answer_numbers(answer) if not any(_matches(x, t) for t in known)]
