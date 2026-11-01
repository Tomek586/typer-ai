"""Drużyny i rozpoznawanie ich nazw ze wszystkich źródeł (docs/03, sekcja 3.5).

Każda drużyna ma stałe ID (slug), nazwę kanoniczną i listę aliasów.
Nowy wariant nazwy z kolejnego źródła dopisujemy do listy aliasów.
"""

import json
import sqlite3
import unicodedata

from rapidfuzz import fuzz, process

# id: (nazwa kanoniczna, [aliasy])
TEAMS: dict[str, tuple[str, list[str]]] = {
    "arka-gdynia": ("Arka Gdynia", []),
    "cracovia": ("Cracovia", ["KS Cracovia", "Cracovia Kraków"]),
    "gks-belchatow": ("GKS Bełchatów", []),
    "gks-katowice": ("GKS Katowice", []),
    "gornik-zabrze": ("Górnik Zabrze", ["Gornik Z."]),
    "gornik-leczna": ("Górnik Łęczna", ["Leczna"]),
    "jagiellonia": ("Jagiellonia Białystok", ["Jagiellonia", "Jaga"]),
    "korona": ("Korona Kielce", []),
    "lks-lodz": ("ŁKS Łódź", []),
    "lech": ("Lech Poznań", ["Kolejorz"]),
    "lechia": ("Lechia Gdańsk", []),
    "legia": ("Legia Warszawa", ["Legia", "Wojskowi"]),
    "miedz-legnica": ("Miedź Legnica", ["Legnica"]),
    "motor": ("Motor Lublin", []),
    "piast": ("Piast Gliwice", []),
    "podbeskidzie": ("Podbeskidzie Bielsko-Biała", ["Podbeskidzie"]),
    "pogon": ("Pogoń Szczecin", ["Portowcy"]),
    "polonia-warszawa": ("Polonia Warszawa", []),
    "puszcza": ("Puszcza Niepołomice", ["Puszcza"]),
    "radomiak": ("Radomiak Radom", ["Radomiak"]),
    "rakow": ("Raków Częstochowa", ["Raków"]),
    "ruch": ("Ruch Chorzów", ["Ruch"]),
    "sandecja": ("Sandecja Nowy Sącz", ["Sandecja Nowy S."]),
    "slask": ("Śląsk Wrocław", ["Śląsk"]),
    "stal-mielec": ("Stal Mielec", []),
    "termalica": ("Bruk-Bet Termalica Nieciecza", ["Termalica B-B.", "Termalica Nieciecza", "Bruk-Bet Termalica", "Termalica Bruk-Bet Nieciecza"]),
    "warta": ("Warta Poznań", []),
    "widzew": ("Widzew Łódź", ["Widzew"]),
    "wieczysta": ("Wieczysta Kraków", []),
    "wisla-krakow": ("Wisła Kraków", ["Wisla", "Biała Gwiazda"]),
    "wisla-plock": ("Wisła Płock", []),
    "zaglebie-lubin": ("Zagłębie Lubin", ["Zaglebie"]),
    "zaglebie-sosnowiec": ("Zagłębie Sosnowiec", []),
    "zawisza": ("Zawisza Bydgoszcz", ["Zawisza"]),
}


def normalize(name: str) -> str:
    """Małe litery, bez polskich znaków i interpunkcji: 'Śląsk Wrocław' -> 'slask wroclaw'."""
    name = name.replace("ł", "l").replace("Ł", "L")
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = "".join(c if c.isalnum() else " " for c in name.lower())
    return " ".join(name.split())


def _build_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for team_id, (canonical, aliases) in TEAMS.items():
        for variant in [canonical, *aliases]:
            key = normalize(variant)
            if key in index and index[key] != team_id:
                raise ValueError(f"Alias '{variant}' wskazuje na dwie drużyny: {index[key]}, {team_id}")
            index[key] = team_id
    return index


_INDEX = _build_index()


def resolve(name: str) -> str:
    """Zwraca ID drużyny dla dowolnego znanego wariantu nazwy. Nieznana nazwa -> KeyError."""
    key = normalize(name)
    if key in _INDEX:
        return _INDEX[key]
    raise KeyError(f"Nieznana drużyna: '{name}'. Podobne: {suggest(name)}")


def suggest(name: str, limit: int = 3) -> list[str]:
    """Podpowiedzi dla nieznanej nazwy (do raportu unmatched i do czatu)."""
    matches = process.extract(normalize(name), list(_INDEX), scorer=fuzz.WRatio, limit=limit)
    return [f"{TEAMS[_INDEX[m]][0]} ({score:.0f})" for m, score, _ in matches]


def seed_teams(conn: sqlite3.Connection) -> None:
    """Wstawia lub aktualizuje drużyny w bazie (bez nadpisywania współrzędnych stadionów)."""
    conn.executemany(
        """INSERT INTO team (id, name, aliases) VALUES (?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET name = excluded.name, aliases = excluded.aliases""",
        [(tid, canonical, json.dumps(aliases, ensure_ascii=False)) for tid, (canonical, aliases) in TEAMS.items()],
    )
