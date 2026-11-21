"""Cechy meczu dla modelu v2 (docs/04, sekcja 4.4) – liczone wyłącznie z meczów rozegranych wcześniej.

Jedno przejście po meczach ligowych w kolejności chronologicznej: cechy meczu powstają ze stanu
sprzed meczu, a dopiero potem stan jest uzupełniany o ten mecz (zasada anty-wyciekowa, docs/03 3.7).

Siła składu (4.4.1) w dwóch wariantach:
  - `*_off`  – skład wyjściowy z meczu (90minut.pl, znany dopiero tuż przed meczem): górna granica
               wartości informacji o składzie, do treningu i ablacji,
  - `*_prev` – skład wyjściowy z poprzedniego meczu drużyny: przybliżenie składu dostępne w etapie 1
               bez newsów (realistyczny wariant do typów, dopóki nie ma składu przewidywanego).
"""

import math
import sqlite3
from collections import defaultdict, deque
from datetime import datetime

from typerai.model.ratings import elo, pi

WINDOW = 10              # mecze drużyny w oknie siły składu
MAX_GAP_DAYS = 300       # starsze mecze (np. przed spadkiem z ligi) nie opisują obecnego składu
MIN_HISTORY = 3          # mniej meczów w oknie = brak cechy (wartości neutralne)
SHRINK_90 = 2.0          # ściąganie goli/90 do średniej pozycji: (gole + 2·śr) / (minuty/90 + 2)
FORM_HALF_LIFE = 8       # półokres formy w meczach
LINEUP_HALF_LIFE = None  # półokres wag meczów w oknie składu (None = równe wagi); świeże mecze szybciej
                         # „przestawiają” skład referencyjny po transferach i zmianie bramkarza
REST_CAP = 10            # dni odpoczynku obcinane do 10
ELO_PARAMS = {"k": elo.K, "hfa": elo.HFA}

# Motywacja z tabeli (docs/04, 4.4.3). Format Ekstraklasy: 2013/14–2019/20 system ESA-37 (16 drużyn,
# 30 kolejek, podział tabeli i połowienie punktów, razem 37 kolejek), 2020/21 – 30 kolejek, od 2021/22
# 18 drużyn i 34 kolejki. Podział na grupy po 30. kolejce przybliżamy jedną tabelą.
ESA_SEASONS = {"2013/14", "2014/15", "2015/16", "2016/17", "2017/18", "2018/19", "2019/20"}
RELEGATED = {"2019/20": 3, "2020/21": 1}       # pozostałe sezony: 16 drużyn – 2 spadki, 18 drużyn – 3
EURO_PLACES = 3                                 # miejsca premiowane grą w pucharach (bez zdobywcy Pucharu Polski)
PRESSURE_ROUNDS = 12                            # presja liczona w ostatnich 12 kolejkach, wcześniej 0
NOTHING_ROUNDS = 5
PI_PARAMS = {"lam": pi.LAMBDA, "gamma": pi.GAMMA}

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


def lineup_strength(history: list[list], starters: set[int], pos_rate: dict[str, float],
                    half_life: float | None = None) -> dict[str, float]:
    """Siła składu `starters` względem składu referencyjnego z historii drużyny (docs/04, 4.4.1).

    history: składy od najstarszego do najnowszego; half_life – półokres wag meczów (None = równe wagi).
    """
    if len(history) < MIN_HISTORY:
        return dict(NEUTRAL_LINEUP)
    minutes: dict[int, float] = defaultdict(float)
    goals: dict[int, float] = defaultdict(float)
    position: dict[int, str] = {}
    n = len(history)
    weights = [1.0 if half_life is None else 0.5 ** ((n - 1 - k) / half_life) for k in range(n)]
    for w, match in zip(weights, history):
        for player, _, m, g, pos in match:
            minutes[player] += w * m
            goals[player] += w * g
            position[player] = pos
    total = sum(weights)
    share = {p: m / (90 * total) for p, m in minutes.items()}
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


def season_rounds(season: str, n_teams: int) -> int:
    if n_teams >= 18:
        return 34
    return 37 if season in ESA_SEASONS else 30


def motivation(points: dict[str, float], team: str, rounds_left: int, n_relegated: int) -> dict[str, float]:
    """Presja spadkowa i pucharowa oraz „nic do grania” z tabeli przed meczem (docs/04, 4.4.3)."""
    if rounds_left <= 0 or rounds_left > PRESSURE_ROUNDS or len(points) <= n_relegated + EURO_PLACES:
        return {"releg_pressure": 0.0, "euro_pressure": 0.0, "nothing_to_play": 0.0}
    table = sorted(points.values(), reverse=True)
    reachable = 3 * rounds_left
    above_drop = points[team] - table[len(table) - n_relegated]      # punkty nad najwyższą drużyną w strefie spadkowej
    to_euro = table[EURO_PLACES - 1] - points[team]                  # strata do ostatniego miejsca pucharowego
    releg = min(1.0, max(0.0, 1 - above_drop / reachable))
    euro = min(1.0, max(0.0, 1 - to_euro / reachable))
    nothing = float(rounds_left <= NOTHING_ROUNDS and above_drop > reachable and to_euro > reachable)
    return {"releg_pressure": releg, "euro_pressure": euro, "nothing_to_play": nothing}


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
    elo_r = elo.pre_match(matches, **ELO_PARAMS)
    pi_r = pi.pre_match(matches, **PI_PARAMS)
    teams_in: dict[str, set] = defaultdict(set)
    for _, season, _, h, a, *_ in matches:
        teams_in[season] |= {h, a}
    for (season,) in conn.execute("SELECT DISTINCT season FROM match"):   # bieżący sezon: także mecze zaplanowane
        teams_in[season] |= {t for row in conn.execute(
            "SELECT home_id, away_id FROM match WHERE season = ?", (season,)) for t in row}
    points: dict[str, dict[str, float]] = defaultdict(dict)
    played: dict[str, dict[str, int]] = defaultdict(dict)
    out = {}

    for match_id, season, kickoff, home, away, hg, ag in matches:
        n_teams = len(teams_in[season])
        total = season_rounds(season, n_teams)
        n_relegated = RELEGATED.get(season, 3 if n_teams >= 18 else 2)
        table = {t: points[season].get(t, 0.0) for t in teams_in[season]}
        pos_rate = {p: pos_goals[p] / (pos_minutes[p] / 90) for p in pos_minutes if pos_minutes[p] > 0}
        feats = {}
        for side, team, opp in (("home", home, away), ("away", away, home)):
            recent = [lu for ko, lu in history[team] if _days(ko, kickoff) <= MAX_GAP_DAYS]
            starters = {p for p, start, *_ in lineups.get((match_id, team), []) if start}
            off = lineup_strength(recent, starters, pos_rate, LINEUP_HALF_LIFE) if starters else dict(NEUTRAL_LINEUP)
            prev = (lineup_strength(recent, last_starters[team], pos_rate, LINEUP_HALF_LIFE)
                    if team in last_starters and recent else dict(NEUTRAL_LINEUP))
            rest = min(_days(last_kickoff[team], kickoff), REST_CAP) if team in last_kickoff else REST_CAP
            feats[side] = {
                "att_off": off["att"], "reg_off": off["reg"], "gk_backup_off": off["gk_backup"],
                "att_prev": prev["att"], "reg_prev": prev["reg"], "gk_backup_prev": prev["gk_backup"],
                "form_gf": form_gf.get(team, 1.3), "form_ga": form_ga.get(team, 1.3),
                "rest_days": rest, "n_history": len(recent),
                **motivation(table, team, total - played[season].get(team, 0), n_relegated),
            }
        hh, ha, ah, aa = pi_r[match_id]
        feats["home"].update(elo=elo_r[match_id][0], pi_g=pi.expected_goal_diff(hh))   # gospodarz: rating u siebie
        feats["away"].update(elo=elo_r[match_id][1], pi_g=pi.expected_goal_diff(aa))   # gość: rating na wyjeździe
        out[match_id] = feats

        # stan po meczu
        for team, gf, ga in ((home, hg, ag), (away, ag, hg)):
            pts = points[season].get(team, 0.0) + (3 if gf > ga else 1 if gf == ga else 0)
            played[season][team] = played[season].get(team, 0) + 1
            if season in ESA_SEASONS and played[season][team] == 30:
                pts = math.ceil(pts / 2)                 # ESA-37: połowienie punktów po rundzie zasadniczej
            points[season][team] = pts
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
