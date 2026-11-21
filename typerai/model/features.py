"""Cechy meczu dla modelu v2 (docs/04, sekcja 4.4) – liczone wyłącznie z meczów rozegranych wcześniej.

Jedno przejście po meczach ligowych w kolejności chronologicznej: cechy meczu powstają ze stanu
sprzed meczu, a dopiero potem stan jest uzupełniany o ten mecz (zasada anty-wyciekowa, docs/03 3.7).

Siła składu (4.4.1) w dwóch wariantach:
  - `*_off`  – skład wyjściowy z meczu (90minut.pl, znany dopiero tuż przed meczem): górna granica
               wartości informacji o składzie, do treningu i ablacji,
  - `*_prev` – skład wyjściowy z poprzedniego meczu drużyny: przybliżenie składu dostępne w etapie 1
               bez newsów (realistyczny wariant do typów, dopóki nie ma składu przewidywanego).
"""

import sqlite3
from collections import defaultdict, deque
from datetime import datetime

WINDOW = 10              # mecze drużyny w oknie siły składu
MAX_GAP_DAYS = 300       # starsze mecze (np. przed spadkiem z ligi) nie opisują obecnego składu
MIN_HISTORY = 3          # mniej meczów w oknie = brak cechy (wartości neutralne)
SHRINK_90 = 2.0          # ściąganie goli/90 do średniej pozycji: (gole + 2·śr) / (minuty/90 + 2)
FORM_HALF_LIFE = 8       # półokres formy w meczach
REST_CAP = 10            # dni odpoczynku obcinane do 10

NEUTRAL_LINEUP = {"att": 1.0, "reg": 1.0, "gk_backup": 0.0}


def _days(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 86400


def load(conn: sqlite3.Connection):
    """Mecze ligowe rozegrane (chronologicznie) i oficjalne składy: {(mecz, drużyna): [(zawodnik, start, min, gole, poz)]}."""
    matches = conn.execute(
        """SELECT id, season, kickoff_utc, home_id, away_id, hg, ag FROM match
           WHERE status = 'finished' AND hg IS NOT NULL ORDER BY kickoff_utc, id""").fetchall()
    lineups: dict[tuple[int, str], list] = defaultdict(list)
    for match_id, team, player, starter, minutes, goals, position in conn.execute(
            """SELECT l.match_id, l.team_id, l.player_id, l.is_starter, l.minutes, l.goals, p.position
               FROM lineup l JOIN player p ON p.id = l.player_id WHERE l.source = 'official'"""):
        lineups[(match_id, team)].append((player, bool(starter), minutes or 0, goals or 0, position or "M"))
    return matches, lineups


def lineup_strength(history: list[list], starters: set[int], pos_rate: dict[str, float]) -> dict[str, float]:
    """Siła składu `starters` względem składu referencyjnego z historii drużyny (docs/04, 4.4.1)."""
    if len(history) < MIN_HISTORY:
        return dict(NEUTRAL_LINEUP)
    minutes: dict[int, int] = defaultdict(int)
    goals: dict[int, int] = defaultdict(int)
    position: dict[int, str] = {}
    for match in history:
        for player, _, m, g, pos in match:
            minutes[player] += m
            goals[player] += g
            position[player] = pos
    n = len(history)
    share = {p: m / (90 * n) for p, m in minutes.items()}
    attack = {p: (goals[p] + SHRINK_90 * pos_rate.get(position[p], 0.0)) / (minutes[p] / 90 + SHRINK_90)
              for p in minutes}
    keepers = [p for p in minutes if position[p] == "G"]
    ref_gk = max(keepers, key=minutes.get) if keepers else None
    outfield = sorted((p for p in minutes if position[p] != "G"), key=minutes.get, reverse=True)[:10]
    reference = outfield + ([ref_gk] if ref_gk is not None else [])

    def value(players):
        return sum(attack.get(p, 0.0) * share.get(p, 0.0) for p in players)

    def regular(players):
        return sum(share.get(p, 0.0) for p in players)

    ref_value, ref_regular = value(reference), regular(reference)
    return {
        "att": value(starters) / ref_value if ref_value > 0 else 1.0,
        "reg": regular(starters) / ref_regular if ref_regular > 0 else 1.0,
        "gk_backup": float(ref_gk is not None and ref_gk not in starters),
    }


def build(conn: sqlite3.Connection) -> dict[int, dict[str, dict[str, float]]]:
    """Cechy wszystkich rozegranych meczów: {mecz: {'home': {...}, 'away': {...}}}."""
    matches, lineups = load(conn)
    history: dict[str, deque] = defaultdict(lambda: deque(maxlen=WINDOW))   # (kickoff, skład) ostatnich meczów
    form_gf: dict[str, float] = {}
    form_ga: dict[str, float] = {}
    last_kickoff: dict[str, str] = {}
    last_starters: dict[str, set[int]] = {}
    pos_goals: dict[str, float] = defaultdict(float)
    pos_minutes: dict[str, float] = defaultdict(float)
    decay = 0.5 ** (1 / FORM_HALF_LIFE)
    out = {}

    for match_id, _, kickoff, home, away, hg, ag in matches:
        pos_rate = {p: pos_goals[p] / (pos_minutes[p] / 90) for p in pos_minutes if pos_minutes[p] > 0}
        feats = {}
        for side, team, opp in (("home", home, away), ("away", away, home)):
            recent = [lu for ko, lu in history[team] if _days(ko, kickoff) <= MAX_GAP_DAYS]
            starters = {p for p, start, *_ in lineups.get((match_id, team), []) if start}
            off = lineup_strength(recent, starters, pos_rate) if starters else dict(NEUTRAL_LINEUP)
            prev = (lineup_strength(recent, last_starters[team], pos_rate)
                    if team in last_starters and recent else dict(NEUTRAL_LINEUP))
            rest = min(_days(last_kickoff[team], kickoff), REST_CAP) if team in last_kickoff else REST_CAP
            feats[side] = {
                "att_off": off["att"], "reg_off": off["reg"], "gk_backup_off": off["gk_backup"],
                "att_prev": prev["att"], "reg_prev": prev["reg"], "gk_backup_prev": prev["gk_backup"],
                "form_gf": form_gf.get(team, 1.3), "form_ga": form_ga.get(team, 1.3),
                "rest_days": rest, "n_history": len(recent),
            }
        out[match_id] = feats

        # stan po meczu
        for team, gf, ga in ((home, hg, ag), (away, ag, hg)):
            form_gf[team] = decay * form_gf.get(team, gf) + (1 - decay) * gf
            form_ga[team] = decay * form_ga.get(team, ga) + (1 - decay) * ga
            last_kickoff[team] = kickoff
            players = lineups.get((match_id, team), [])
            if players:
                history[team].append((kickoff, players))
                last_starters[team] = {p for p, start, *_ in players if start}
                for _, _, m, g, pos in players:
                    pos_goals[pos] += g
                    pos_minutes[pos] += m
    return out
