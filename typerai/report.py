"""Zestawienia typów i wyników dla aplikacji Streamlit i notebooka (docs/09, docs/10).

Wyłącznie odczyt: baza otwierana w trybie read-only, więc aplikację i notebook można uruchomić
także na kopii bazy (laptop, komputer kolegi) bez ryzyka zapisu.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from typerai import config
from typerai.betting import value
from typerai.betting.settle import OFFICIAL, SHADOW_CONFIRMED

REPORT_DIR = Path(config.ROOT) / "evaluation" / "reports"
TZ = ZoneInfo("Europe/Warsaw")
ONE_X_TWO = ["1X2:1", "1X2:X", "1X2:2"]

STATUS_LABELS = {
    "WSTEPNY": "wstępny", "WSTRZYMANY": "wstrzymany", "POTWIERDZONY": "potwierdzony",
    "POTWIERDZONY_POZNO": "potwierdzony (późno)", "ANULOWANY": "anulowany", "ODRZUCONY": "odrzucony",
    "CIEN": "wstępny", "CIEN_POTWIERDZONY": "potwierdzony", "CIEN_ANULOWANY": "anulowany",
}
OUTCOME_LABELS = {"WIN": "wygrany", "HALF_WIN": "pół wygranej", "PUSH": "zwrot",
                  "HALF_LOSS": "pół przegranej", "LOSS": "przegrany"}


def connect_ro(path: Path | str | None = None) -> sqlite3.Connection:
    """Połączenie tylko do odczytu – aplikacja nie może zmienić bazy harmonogramu."""
    path = Path(path or config.DB_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Brak bazy {path}. Skopiuj kopię z komputera domowego (CONTRIBUTING.md, krok 5).")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _num(value: str) -> str:
    return value.replace(".", ",")


def market_label(code: str) -> str:
    """Kod rynku -> opis po polsku, np. 'OU:2.5:under' -> 'poniżej 2,5 gola'."""
    parts = code.split(":")
    kind = parts[0]
    if kind == "1X2":
        return {"1": "wygrana gospodarza (1)", "X": "remis (X)", "2": "wygrana gościa (2)"}[parts[1]]
    if kind == "DC":
        return f"podwójna szansa {parts[1]}"
    if kind == "BTTS":
        return "obie drużyny strzelą" if parts[1] == "yes" else "nie strzelą obie drużyny"
    if kind == "OU":
        return f"{'powyżej' if parts[2] == 'over' else 'poniżej'} {_num(parts[1])} gola"
    if kind == "AH":
        line = float(parts[1])
        side = "gospodarz" if parts[2] == "home" else "gość"
        return f"handicap {side} {'+' if line > 0 else ''}{_num(f'{line:g}')}"
    return code


def strategy(status: str) -> str:
    return "cień" if status.startswith("CIEN") else "oficjalna"


def local_time(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d.%m.%Y %H:%M")


def picks(conn: sqlite3.Connection) -> list[dict]:
    """Wszystkie typy (obie strategie) z meczem, kursami etapów, CLV i wynikiem – najnowsze na górze."""
    rows = conn.execute(
        """SELECT p.*, m.kickoff_utc, m.hg, m.ag, h.name AS home, a.name AS away FROM pick p
           JOIN match m ON m.id = p.match_id JOIN team h ON h.id = m.home_id JOIN team a ON a.id = m.away_id
           ORDER BY m.kickoff_utc DESC, p.id""").fetchall()
    out = []
    for r in rows:
        taken = r["odds_stage2"] or r["odds_stage1"]
        out.append({
            "termin": local_time(r["kickoff_utc"]),
            "mecz": f"{r['home']} – {r['away']}",
            "zdarzenie": market_label(r["market"]),
            "strategia": strategy(r["status"]),
            "status": STATUS_LABELS.get(r["status"], r["status"]),
            "p_model": round(r["p_model"], 3),
            "ev": round(r["ev"], 3),
            "kurs_etap1": r["odds_stage1"],
            "kurs_etap2": r["odds_stage2"],
            "bukmacher": r["bookmaker"],
            # CLV: nasz kurs względem ostatniego kursu Pinnacle przed meczem (docs/10)
            "clv": round(taken / r["odds_closing"] - 1, 3) if taken and r["odds_closing"] else None,
            "wynik_meczu": f"{r['hg']}:{r['ag']}" if r["hg"] is not None else None,
            "rozliczenie": OUTCOME_LABELS.get(r["outcome"]) if r["outcome"] else None,
            "zysk": r["profit"],
            "_status": r["status"],
            "_outcome": r["outcome"],
        })
    return out


def summary(rows: list[dict], statuses: tuple[str, ...]) -> dict:
    """Wynik strategii na typach rozliczonych (zysk przy stawce 1 j.)."""
    done = [r for r in rows if r["_status"] in statuses and r["zysk"] is not None]
    wins = sum(r["_outcome"] in ("WIN", "HALF_WIN") for r in done)
    clv = [r["clv"] for r in done if r["clv"] is not None]
    return {
        "typy": len(done),
        "trafne": wins,
        "trafnosc": wins / len(done) if done else None,
        "zysk": round(sum(r["zysk"] for r in done), 2),
        "roi": sum(r["zysk"] for r in done) / len(done) if done else None,
        "clv_srednie": sum(clv) / len(clv) if clv else None,
    }


def live_summary(conn: sqlite3.Connection) -> dict:
    rows = picks(conn)
    return {"oficjalna": summary(rows, OFFICIAL), "cień": summary(rows, SHADOW_CONFIRMED),
            "wszystkie_typy": len(rows)}


def cumulative_profit(rows: list[dict], statuses: tuple[str, ...]) -> list[dict]:
    """Skumulowany zysk w kolejności meczów – do wykresu."""
    done = sorted((r for r in rows if r["_status"] in statuses and r["zysk"] is not None),
                  key=lambda r: datetime.strptime(r["termin"], "%d.%m.%Y %H:%M"))
    total, out = 0.0, []
    for i, r in enumerate(done, 1):
        total += r["zysk"]
        out.append({"typ": i, "termin": r["termin"], "zysk_narastajaco": round(total, 2)})
    return out


def upcoming(conn: sqlite3.Connection, days: int = 7, now: datetime | None = None) -> list[dict]:
    """Najbliższe mecze, wynik 1X2 po wyniku: model, rynek bez marży, mieszanka, najlepszy kurs i EV.

    Liczone tak samo jak w etapie 1 (betting.value): mieszanka z wagą config.MODEL["blend_w"],
    kurs bez odstających ofert, kursy z ostatnich 36 h. Pokazuje, dlaczego mecz dostał typ albo nie.
    """
    now = now or datetime.now(timezone.utc)
    as_of = now.isoformat(timespec="minutes")
    until = (now + timedelta(days=days)).isoformat(timespec="minutes")
    matches = conn.execute(
        """SELECT m.id, m.kickoff_utc, h.name AS home, a.name AS away FROM match m
           JOIN team h ON h.id = m.home_id JOIN team a ON a.id = m.away_id
           WHERE m.status != 'finished' AND m.kickoff_utc BETWEEN ? AND ?
           ORDER BY m.kickoff_utc""", (as_of, until)).fetchall()
    rules, w = config.RULES, config.MODEL["blend_w"]
    out = []
    for m in matches:
        pred = conn.execute("SELECT probabilities FROM prediction WHERE match_id = ? ORDER BY id DESC LIMIT 1",
                            (m["id"],)).fetchone()
        model = json.loads(pred[0]) if pred else {}
        quotes = value.latest_quotes(conn, m["id"], as_of, 36 * 60)
        fair = value.fair_probs(quotes, ONE_X_TWO) if quotes else None
        p_model = [model.get(k) for k in ONE_X_TWO]
        mixed = value.blend(p_model, fair, w) if fair and all(p_model) else None
        for i, market in enumerate(ONE_X_TWO):
            best = value.best_price(quotes.get(market, [])) if quotes else None
            p = float(mixed[i]) if mixed else None
            ev = p * best.odds - 1 if p and best else None
            ok = bool(p and best and p >= rules["p_min"] and rules["ev_min"] <= ev <= rules["ev_max"]
                      and rules["odds_min"] <= best.odds <= rules["odds_max"])
            out.append({"termin": local_time(m["kickoff_utc"]), "mecz": f"{m['home']} – {m['away']}",
                        "zdarzenie": market_label(market), "p_model": p_model[i],
                        "p_rynek": float(fair[i]) if fair else None, "p_mieszanka": p,
                        "kurs": best.odds if best else None, "bukmacher": best.bookmaker if best else None,
                        "ev": ev, "spelnia_reguly": ok})
    return out


def job_runs(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT job, started_at, finished_at, status, error FROM job_run ORDER BY id DESC LIMIT ?", (limit,))]


def validation_reports() -> dict[str, dict]:
    """Raporty walidacji walk-forward modelu v1 (evaluation/validate_v1.py) – po sezonach."""
    out = {}
    for path in sorted(REPORT_DIR.glob("validate_v1_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out[data["season"]] = data
    return out


def validation_table(reports: dict[str, dict]) -> list[dict]:
    """Log-loss 1X2: rynek vs model (najlepsze ξ) vs mieszanka z wagą produkcyjną."""
    w = f"{config.MODEL['blend_w']:g}"
    rows = []
    for season, d in reports.items():
        model = d["xi"][str(d["best_xi"])] if str(d["best_xi"]) in d["xi"] else d["xi"][f"{d['best_xi']:g}"]
        blend = d["blend_log_loss"].get(w) or d["blend_log_loss"].get(f"{config.MODEL['blend_w']}")
        rows.append({"sezon": season, "mecze": d["market"]["n"],
                     "rynek": round(d["market"]["log_loss"], 4),
                     "model": round(model["log_loss"], 4),
                     f"mieszanka w={w}": round(blend, 4) if blend else None})
    return rows


CATEGORY_LABELS = {"injury": "kontuzja", "suspension": "zawieszenie", "return": "powrót", "coach_change": "zmiana trenera",
                   "club_crisis": "kryzys w klubie", "fatigue_schedule": "zmęczenie, terminarz",
                   "motivation_context": "stawka meczu", "match_conditions": "warunki meczu"}
FACT_STATUS = {"out": "nie zagra", "doubtful": "niepewny", "available": "dostępny"}
CERTAINTY_LABELS = {"official": "oficjalne", "reported": "media", "speculation": "spekulacja"}
DECISION_LABELS = {"duplicate": "duplikat", "no_team": "bez drużyny"}


def news_articles(conn: sqlite3.Connection, days: int = 7, now: datetime | None = None) -> list[dict]:
    """Artykuły z ostatnich dni z wynikiem klasyfikacji (docs/09, strona „Newsy”)."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat(timespec="minutes")
    rows = conn.execute(
        """SELECT a.id, a.published_at, a.source, a.title, a.url, a.duplicate_of,
                  (SELECT d.decision FROM decision_log d WHERE d.purpose = 'news_classify' AND d.ref_id = a.id
                   ORDER BY d.id DESC LIMIT 1) AS decision,
                  (SELECT d.model FROM decision_log d WHERE d.purpose = 'news_classify' AND d.ref_id = a.id
                   ORDER BY d.id DESC LIMIT 1) AS model,
                  (SELECT COUNT(*) FROM news_fact f WHERE f.article_id = a.id) AS facts,
                  (SELECT GROUP_CONCAT(DISTINCT f.team_id) FROM news_fact f WHERE f.article_id = a.id) AS teams
           FROM news_article a WHERE a.published_at >= ? ORDER BY a.published_at DESC""", (since,)).fetchall()
    out = []
    for r in rows:
        if r["model"] is None:
            status = "czeka na klasyfikację"
        elif r["decision"] in DECISION_LABELS:
            status = DECISION_LABELS[r["decision"]]
        else:
            status = f"sklasyfikowany ({r['model']})"
        out.append({"data": local_time(r["published_at"]), "źródło": r["source"], "tytuł": r["title"], "url": r["url"],
                    "status": status, "fakty": r["facts"], "drużyny": r["teams"] or ""})
    return out


def news_facts(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    """Aktywne fakty wszystkich drużyn (niezastąpione i ważne), od największego wpływu."""
    as_of = (now or datetime.now(timezone.utc)).isoformat(timespec="minutes")
    rows = conn.execute(
        """SELECT t.name AS team, f.team_id, f.category, p.name AS player, f.status, f.impact, f.certainty,
                  f.valid_until, a.title, a.url FROM news_fact f
           JOIN team t ON t.id = f.team_id LEFT JOIN player p ON p.id = f.player_id
           LEFT JOIN news_article a ON a.id = f.article_id
           WHERE f.superseded_by IS NULL AND f.valid_from <= ? AND (f.valid_until IS NULL OR f.valid_until > ?)
           ORDER BY f.impact DESC""", (as_of, as_of)).fetchall()
    return [{"drużyna": r["team"], "team_id": r["team_id"],
             "kategoria": CATEGORY_LABELS.get(r["category"], r["category"]), "zawodnik": r["player"] or "–",
             "status": FACT_STATUS.get(r["status"], "–"), "wpływ (0–4)": r["impact"],
             "pewność": CERTAINTY_LABELS.get(r["certainty"], r["certainty"]),
             "ważny do": local_time(r["valid_until"]) if r["valid_until"] else "–", "źródło": r["title"], "url": r["url"]}
            for r in rows]
