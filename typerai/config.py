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
