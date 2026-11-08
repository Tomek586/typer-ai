"""Narzędzia chatbota (docs/08, sekcja 8.3) – wersja PoC.

Każde narzędzie czyta prawdziwe dane z bazy i zwraca słownik. LLM nie liczy sam prawdopodobieństw
ani EV – wszystkie liczby w odpowiedzi muszą pochodzić z wyników tych funkcji.
Docstringi i typy argumentów trafiają do modelu jako opis narzędzia, dlatego są po polsku i precyzyjne.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from typerai import config, db, teams
from typerai.betting import odds_math, value
from typerai.model import predict as model_predict
from typerai.model.score_matrix import market_probs, matrix

TZ = ZoneInfo("Europe/Warsaw")
_model_cache: dict[str, object] = {}


def _conn():
    return db.connect()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d.%m %H:%M")


def _team_name(conn, team_id: str) -> str:
    return conn.execute("SELECT name FROM team WHERE id = ?", (team_id,)).fetchone()[0]


def _model(conn, as_of: str):
    key = as_of[:13]  # jedno dopasowanie na godzinę
    if key not in _model_cache:
        _model_cache[key] = model_predict.fit_model(conn, as_of)
    return _model_cache[key]


def terminarz(dni: int = 7) -> dict:
    """Zwraca nadchodzące mecze Ekstraklasy z najbliższych dni.

    Args:
        dni: ile dni do przodu (domyślnie 7)
    """
    conn = _conn()
    now = _now()
    rows = conn.execute(
        """SELECT kickoff_utc, home_id, away_id FROM match WHERE status = 'scheduled'
           AND kickoff_utc BETWEEN ? AND ? ORDER BY kickoff_utc""",
        (now.isoformat(timespec="minutes"), (now + timedelta(days=dni)).isoformat(timespec="minutes"))).fetchall()
    return {"mecze": [{"termin": _local(r["kickoff_utc"]), "gospodarz": _team_name(conn, r["home_id"]),
                       "gosc": _team_name(conn, r["away_id"])} for r in rows]}


def forma_druzyny(druzyna: str, ostatnie: int = 5) -> dict:
    """Zwraca ostatnie wyniki ligowe drużyny, bilans bramek i najlepszych strzelców w bieżącym sezonie.

    Args:
        druzyna: nazwa drużyny, np. "Lech Poznań", "Legia", "Kolejorz"
        ostatnie: liczba ostatnich meczów (domyślnie 5)
    """
    conn = _conn()
    try:
        team_id = teams.resolve(druzyna)
    except KeyError:
        return {"blad": f"Nie znam drużyny '{druzyna}'", "podobne": teams.suggest(druzyna)}
    rows = conn.execute(
        """SELECT kickoff_utc, home_id, away_id, hg, ag FROM match WHERE status = 'finished'
           AND (home_id = ? OR away_id = ?) ORDER BY kickoff_utc DESC LIMIT ?""", (team_id, team_id, ostatnie)).fetchall()
    mecze, punkty, strzelone, stracone = [], 0, 0, 0
    for r in rows:
        home = r["home_id"] == team_id
        gf, ga = (r["hg"], r["ag"]) if home else (r["ag"], r["hg"])
        rywal = _team_name(conn, r["away_id"] if home else r["home_id"])
        wynik = "W" if gf > ga else "R" if gf == ga else "P"
        punkty += {"W": 3, "R": 1, "P": 0}[wynik]
        strzelone, stracone = strzelone + gf, stracone + ga
        mecze.append({"data": _local(r["kickoff_utc"]), "rywal": rywal, "dom": home, "wynik": f"{gf}:{ga}", "rezultat": wynik})
    season = conn.execute("SELECT MAX(season) FROM match").fetchone()[0]
    strzelcy = conn.execute(
        """SELECT p.name, SUM(l.goals) g, SUM(l.minutes) m FROM lineup l JOIN player p ON p.id = l.player_id
           JOIN match m ON m.id = l.match_id WHERE l.team_id = ? AND m.season = ? AND l.source = 'official'
           GROUP BY p.id HAVING g > 0 ORDER BY g DESC LIMIT 3""", (team_id, season)).fetchall()
    return {"druzyna": _team_name(conn, team_id), "mecze": mecze, "punkty": punkty,
            "bramki": f"{strzelone}:{stracone}",
            "najlepsi_strzelcy_sezonu": [{"zawodnik": s["name"], "gole": s["g"], "minuty": s["m"]} for s in strzelcy]}


def analiza_meczu(gospodarz: str, gosc: str) -> dict:
    """Analiza nadchodzącego meczu: prawdopodobieństwa modelu i rynku, najlepsze kursy, EV i czy jest typ.

    Args:
        gospodarz: drużyna grająca u siebie, np. "Legia Warszawa"
        gosc: drużyna na wyjeździe, np. "Raków"
    """
    conn = _conn()
    try:
        home_id, away_id = teams.resolve(gospodarz), teams.resolve(gosc)
    except KeyError as e:
        return {"blad": str(e)}
    match = conn.execute(
        """SELECT * FROM match WHERE home_id = ? AND away_id = ? AND status = 'scheduled'
           ORDER BY kickoff_utc LIMIT 1""", (home_id, away_id)).fetchone()
    if match is None:
        return {"blad": "Nie znalazłem nadchodzącego meczu tych drużyn (sprawdź, kto jest gospodarzem – użyj terminarz)."}
    as_of = _now().isoformat(timespec="minutes")
    model = _model(conn, as_of)
    lh, la = model.lambdas(home_id, away_id)
    mat = matrix(lh, la, model.rho)
    quotes = value.latest_quotes(conn, match["id"], as_of, 24 * 60)

    rynki = {}
    for code, label in (("1X2:1", "wygrana gospodarza"), ("1X2:X", "remis"), ("1X2:2", "wygrana gościa"),
                        ("OU:2.5:over", "powyżej 2,5 gola"), ("OU:2.5:under", "poniżej 2,5 gola")):
        best = value.best_price(quotes.get(code, []))
        probs = value._final_probability(code, mat, quotes, config.MODEL["blend_w"]) if quotes.get(code) else None
        entry = {"zdarzenie": label, "p_model": round(market_probs(mat, code).win, 3)}
        if probs and best:
            p, _, p_market = probs
            entry.update({"p_rynek_pinnacle": round(p_market, 3), "p_koncowe": round(p, 3),
                          "najlepszy_kurs": best.odds, "bukmacher": best.bookmaker,
                          "ev": round(odds_math.expected_value(p, best.odds), 3)})
        rynki[code] = entry
    cands = value.candidates(mat, quotes)
    best_pick = value.choose(cands)
    return {
        "mecz": f"{_team_name(conn, home_id)} – {_team_name(conn, away_id)}",
        "termin": _local(match["kickoff_utc"]),
        "oczekiwane_gole": {"gospodarz": round(lh, 2), "gosc": round(la, 2)},
        "rynki": rynki,
        "typ": None if best_pick is None else {
            "zdarzenie": best_pick.market, "kurs": best_pick.odds, "bukmacher": best_pick.bookmaker,
            "p": round(best_pick.p, 3), "ev": round(best_pick.ev, 3)},
        "reguly": f"typ tylko gdy p ≥ {config.RULES['p_min']}, EV ≥ {config.RULES['ev_min']:.0%}, "
                  f"kurs {config.RULES['odds_min']}–{config.RULES['odds_max']}",
    }


def przelicz_kurs(kursy: list[float]) -> dict:
    """Przelicza kursy jednego rynku (np. 1, X, 2) na prawdopodobieństwa i marżę bukmachera.

    Args:
        kursy: kursy wszystkich wyników rynku, np. [2.10, 3.40, 3.60]; dla jednego kursu tylko prawdopodobieństwo implikowane
    """
    if len(kursy) == 1:
        return {"prawdopodobienstwo_implikowane": round(1 / kursy[0], 4)}
    return {
        "marza": round(odds_math.margin(kursy), 4),
        "bez_marzy_proporcjonalnie": [round(p, 4) for p in odds_math.proportional(kursy)],
        "bez_marzy_shin": [round(p, 4) for p in odds_math.shin(kursy)],
    }


def typy() -> dict:
    """Zwraca typy wydane przez typera (wstępne, potwierdzone, anulowane) i wynik oficjalny."""
    conn = _conn()
    rows = conn.execute(
        """SELECT p.*, m.kickoff_utc, m.home_id, m.away_id FROM pick p JOIN match m ON m.id = p.match_id
           ORDER BY m.kickoff_utc DESC LIMIT 20""").fetchall()
    lista = [{"mecz": f"{_team_name(conn, r['home_id'])} – {_team_name(conn, r['away_id'])}",
              "termin": _local(r["kickoff_utc"]), "zdarzenie": r["market"], "status": r["status"],
              "kurs": r["odds_stage2"] or r["odds_stage1"], "wynik": r["outcome"]} for r in rows]
    return {"typy": lista, "liczba": len(lista)}


TOOLS = [terminarz, forma_druzyny, analiza_meczu, przelicz_kurs, typy]
