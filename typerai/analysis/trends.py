"""Trendy meczu: H2H, ostatnia forma i zdarzenia, które się powtarzają.

To KONTEKST dla użytkownika, a nie podstawa typu. Na danych 2015–2026 „najczęstszy wynik z 4 ostatnich
H2H” trafiał 37,9% wyników, a faworyt bukmachera 46,5% – mała próbka to głównie szum. Dlatego każdy trend
podajemy z liczbą meczów („3 z 4”), a o wpływie H2H i formy na prawdopodobieństwo decyduje backtest (model v2).
"""

import sqlite3
from dataclasses import dataclass


@dataclass
class Game:
    kickoff_utc: str
    home_id: str
    away_id: str
    hg: int
    ag: int
    cards: int | None   # żółte + czerwone obu drużyn (z 90minut.pl), jeśli znane

    def goals_for(self, team: str) -> int:
        return self.hg if self.home_id == team else self.ag

    def goals_against(self, team: str) -> int:
        return self.ag if self.home_id == team else self.hg


def _games(conn: sqlite3.Connection, where: str, params: tuple, limit: int) -> list[Game]:
    rows = conn.execute(
        f"""SELECT m.kickoff_utc, m.home_id, m.away_id, m.hg, m.ag,
                   s.yellow_h + s.yellow_a + s.red_h + s.red_a AS cards
            FROM match m LEFT JOIN match_stats s ON s.match_id = m.id
            WHERE m.status = 'finished' AND m.hg IS NOT NULL AND {where}
            ORDER BY m.kickoff_utc DESC LIMIT ?""", (*params, limit)).fetchall()
    return [Game(*r) for r in rows]


def head_to_head(conn, home_id: str, away_id: str, before: str, n: int = 4) -> list[Game]:
    """Ostatnie n bezpośrednich meczów (na obu boiskach), rozegranych przed `before`."""
    return _games(conn, "m.kickoff_utc < ? AND ((m.home_id = ? AND m.away_id = ?) OR (m.home_id = ? AND m.away_id = ?))",
                  (before, home_id, away_id, away_id, home_id), n)


def recent_form(conn, team_id: str, before: str, n: int = 3) -> list[Game]:
    """Ostatnie n meczów ligowych drużyny przed `before`."""
    return _games(conn, "m.kickoff_utc < ? AND (m.home_id = ? OR m.away_id = ?)", (before, team_id, team_id), n)


# Zdarzenia liczone w każdej grupie meczów: nazwa -> warunek
EVENTS = {
    "powyżej 1,5 gola": lambda g: g.hg + g.ag > 1.5,
    "powyżej 2,5 gola": lambda g: g.hg + g.ag > 2.5,
    "poniżej 2,5 gola": lambda g: g.hg + g.ag < 2.5,
    "obie drużyny strzelą": lambda g: g.hg > 0 and g.ag > 0,
    "powyżej 4,5 kartki": lambda g: g.cards is not None and g.cards > 4.5,
}


def _count(games: list[Game], test) -> str | None:
    return f"{sum(test(g) for g in games)} z {len(games)}" if games else None


def _result_line(games: list[Game], team: str) -> str:
    """Np. 'W W R' z perspektywy drużyny (najnowszy mecz pierwszy)."""
    def r(g):
        gf, ga = g.goals_for(team), g.goals_against(team)
        return "W" if gf > ga else "R" if gf == ga else "P"
    return " ".join(r(g) for g in games)


def match_trends(conn: sqlite3.Connection, home_id: str, away_id: str, before: str) -> dict:
    h2h = head_to_head(conn, home_id, away_id, before)
    form_home = recent_form(conn, home_id, before)
    form_away = recent_form(conn, away_id, before)
    groups = {"h2h": h2h, "forma_gospodarza": form_home, "forma_goscia": form_away}

    events = {}
    for name, test in EVENTS.items():
        events[name] = {g: _count(games, test) for g, games in groups.items()}

    # „Powtarza się”: zdarzenie wystąpiło w co najmniej 3/4 meczów w każdej grupie, w której są dane
    recurring = []
    for name, counts in events.items():
        ok = [g for g, games in groups.items()
              if games and sum(EVENTS[name](x) for x in games) / len(games) >= 0.75]
        if len(ok) >= 2:
            recurring.append({"zdarzenie": name, "grupy": {g: events[name][g] for g in ok}})

    names = dict(conn.execute("SELECT id, name FROM team").fetchall())
    return {
        "h2h": [{"wynik": f"{names[g.home_id]} {g.hg}:{g.ag} {names[g.away_id]}", "data": g.kickoff_utc[:10],
                 "rezultat_dla_gospodarza": _result_line([g], home_id)} for g in h2h],
        "h2h_bilans_gospodarza": _result_line(h2h, home_id),
        "forma_gospodarza": _result_line(form_home, home_id),
        "forma_goscia": _result_line(form_away, away_id),
        "zdarzenia": events,
        "powtarza_sie": recurring,
        "uwaga": "Trendy z 3–4 meczów to mała próbka – kontekst, nie podstawa typu.",
    }
