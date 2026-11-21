"""Ustawienia projektu. Progi i parametry trzymamy w jednym miejscu (docs/02, sekcja 2.7)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = Path(os.getenv("TYPERAI_DB", DATA_DIR / "typer.db"))

# football-data.co.uk
FOOTBALL_DATA_URL = "https://www.football-data.co.uk/new/POL.csv"
# Godziny w plikach football-data są podawane w czasie brytyjskim
FOOTBALL_DATA_TZ = "Europe/London"

LEAGUE = "Ekstraklasa"

# ---------------------------------------------------------------- model v1
# Parametry z walidacji walk-forward 2023/24 + 2024/25 (evaluation/validate_v1.py):
# ξ – ważenie czasem; w – waga modelu przy mieszaniu z rynkiem (1 = sam model, 0 = sam rynek)
MODEL = {
    "version": "dc1-blend1",
    "xi": 0.0005,
    "blend_w": 0.15,
}

# Reguły wyboru typów (docs/07, sekcja 7.3) – wartości startowe, zamrożone na czas testu na żywo
# 21.11.2026: EV z 3% na 1% – przy w = 0,15 próg 3% dawał ok. 8 typów na sezon (za mało do oceny celu);
# waga modelu bez zmian, bo wynika z log-loss (docs/DZIENNIK.md)
RULES = {
    "ev_min": 0.01,
    "ev_max": 0.25,
    "p_min": 0.52,
    "odds_min": 1.50,
    "odds_max": 2.30,
    "min_team_matches": 5,          # mecze ligowe drużyny w ostatnich 365 dniach
    "families": ["1X2", "DC", "OU", "BTTS", "AH"],
}

# Strategia „cień” (docs/07, 7.4): typy z łagodniejszymi regułami zapisywane WYŁĄCZNIE do pomiaru modelu.
# Nie wchodzą do oficjalnego wyniku; dają większą próbkę do oceny trafności, ROI i CLV.
SHADOW_RULES = {**RULES, "ev_min": 0.0, "p_min": 0.45, "odds_max": 3.00}

# Wybór kursu (docs/03, sekcja 3.3.4)
ODDS = {
    "outlier_pct": 0.08,            # kurs wyższy o >8% od mediany = prawdopodobny błąd oferty
    "max_age_stage1_min": 120,
    "max_age_stage2_min": 15,
    "reference_bookmaker": "pinnacle",
    # giełdy pobierają prowizję, której kurs nie uwzględnia
    "excluded_bookmakers": ["betfair_ex_eu", "betfair_ex_uk", "matchbook", "smarkets"],
}

# Okna czasowe etapów (docs/07, sekcja 7.4)
STAGES = {
    "stage1_horizon_h": 36,
    "stage2_window_min": (45, 75),
}

# ---------------------------------------------------------------- newsy (docs/05)
# Kanały RSS sprawdzone 21.11.2026: robots.txt nie blokuje zwykłych botów. Regulaminy serwisów (zastrzeżenia
# eksploracji tekstu i danych) sprawdza zespół – źródło z zakazem usuwamy z listy.
NEWS_SOURCES = [
    {"name": "sportowefakty", "feed": "https://sportowefakty.wp.pl/pilka-nozna/ekstraklasa/rss.xml", "reliability": "medialne"},
    {"name": "interia", "feed": "https://sport.interia.pl/pilka-nozna/ekstraklasa/feed", "reliability": "medialne"},
    {"name": "tvp-sport", "feed": "https://sport.tvp.pl/rss", "reliability": "medialne"},
    {"name": "sport-pl", "feed": "https://www.sport.pl/pub/rss/sport.htm", "reliability": "medialne"},
    {"name": "weszlo", "feed": "https://weszlo.com/feed/", "reliability": "medialne"},
]
NEWS = {
    "max_age_days": 7,          # starsze artykuły pomijamy
    "min_chars": 300,           # krótszy tekst = sam tytuł lub zajawka
    "request_delay_s": 2.0,     # przerwa między pobraniami artykułów z jednego serwisu
    "simhash_max_distance": 3,  # odległość Hamminga ≤ 3 = duplikat
    "dedup_hours": 48,          # z iloma godzinami wstecz porównujemy duplikaty
    "max_classify_per_run": 10, # artykułów klasyfikowanych przez LLM w jednym przebiegu (darmowe limity Gemini)
}
# Wstępny filtr: rdzenie nazw drużyn w polskiej odmianie („Legii”, „Lechem”, „Rakowa”). Pułapki: Lechia to nie Lech,
# „Wisła” bez miasta może oznaczać obie Wisły (rozstrzyga klasyfikacja LLM).
NEWS_TEAM_PATTERNS = {
    "cracovia": r"\bCracovi", "gks-katowice": r"\bGKS(?:-u|-ie)? Katowice|\bGieKS", "gornik-zabrze": r"\bG[óo]rnik",
    "jagiellonia": r"\bJagielloni|\bJag[aięą]\b", "korona": r"\bKoron[aiyęą]\b|\bKorona Kielce", "lech": r"\bLech(?!i)\w*|\bKolejorz",
    "legia": r"\bLegi[aięąo]|\bWojskow", "motor": r"\bMotor(?:a|em|u|ze)?\s+Lublin|\bMotor(?:u|em)?\b",
    "piast": r"\bPiast", "pogon": r"\bPogo[nń]|\bPortowc", "radomiak": r"\bRadomiak", "rakow": r"\bRak[oó]w",
    "slask": r"\b[ŚS]l[ąa]sk(?:a|iem|u)?\b", "widzew": r"\bWidzew",
    "wieczysta": r"\bWieczyst", "wisla-krakow": r"\bWis[łl]\w* Krak|\bBia[łl]\w* Gwiazd|\bWis[łl][aąyę]\b(?! P[łl]ock)",
    "wisla-plock": r"\bWis[łl]\w* P[łl]ock|\bNafciarz", "zaglebie-lubin": r"\bZag[łl][ęe]bi",
}
