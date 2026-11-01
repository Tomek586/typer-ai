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
RULES = {
    "ev_min": 0.03,
    "ev_max": 0.25,
    "p_min": 0.52,
    "odds_min": 1.50,
    "odds_max": 2.30,
    "min_team_matches": 5,          # mecze ligowe drużyny w ostatnich 365 dniach
    "families": ["1X2", "DC", "OU", "BTTS", "AH"],
}

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
