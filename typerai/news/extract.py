"""Fakty z newsów (docs/05, kroki 3–5 i sekcje 5.3–5.5; polityka progów: docs/06, 6.4.1).

Dla każdego nowego artykułu (bez duplikatów) jedno zapytanie do silnika decyzyjnego z pytaniami:
  - about_<drużyna> (Noul)      – czy artykuł dotyczy drużyny (tylko drużyny wspomniane w tekście),
  - <drużyna>__category/impact/direction/certainty – zdarzenie z punktu widzenia tej drużyny,
  - p_<zawodnik>, status_<zawodnik> – tylko zawodnicy z kadry drużyny (bez „zmyślania” nazwisk).
Odpowiedzi zamieniane są na fakty w kodzie, według jawnych progów.

    .venv/Scripts/python -m typerai.news.extract
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from typerai import config, db
from typerai.collectors.news import TEAM_PATTERNS, current_teams, team_mentions
from typerai.decision.engine import DecisionEngine, LLMEngine, Question

ABOUT_MIN = 0.6
CATEGORY_CONFIDENCE_MIN = 0.4
PLAYER_MIN = 0.7
STATUS_CONFIDENCE_MIN = 0.3
SQUAD_SIZE = 35
TEXT_CHARS = 6000
MAX_TEAMS = 3
PLAYER_CATEGORIES = ("injury", "suspension", "return")
CERTAINTY_RANK = {"speculation": 0, "reported": 1, "official": 2}
# ważność faktu (docs/05, 5.3): liczba dni albo „do następnego meczu ligowego”; None = brak faktu (tylko RAG)
VALIDITY = {"injury": 14, "suspension": "next_match", "return": "next_match", "coach_change": 21, "club_crisis": 14,
            "fatigue_schedule": "next_match", "motivation_context": "next_match", "match_conditions": "next_match",
            "transfer": None, "other": None}

CATEGORY = {
    "injury": "A player is injured or recovering from injury",
    "suspension": "A player is suspended (cards, disciplinary decision)",
    "return": "A player returns from injury or suspension and is available",
    "coach_change": "Coach dismissed, appointed, or coach position under threat",
    "club_crisis": "Financial problems, unpaid wages, internal conflict, ownership turmoil",
    "fatigue_schedule": "Congested schedule, travel, cup matches, squad rotation",
    "motivation_context": "Stakes of the match: derby, relegation fight, title race, nothing to play for",
    "match_conditions": "Weather, pitch condition, stadium closure, match without fans",
    "transfer": "Transfer in or out, contract news",
    "other": "Anything else (preview without new facts, interviews, history)",
}
IMPACT = ["No effect on the next match", "Marginal effect (fringe player, minor issue)",
          "Small effect (rotation player, minor disruption)", "Moderate effect (regular starter, noticeable disruption)",
          "Large effect (key player or major disruption of the whole team)"]
DIRECTION = {"weakens": "Makes the team weaker", "strengthens": "Makes the team stronger", "neutral": "No clear effect"}
CERTAINTY = {"official": "Confirmed by the club, coach or league",
             "reported": "Reported by media as fact, not officially confirmed",
             "speculation": "Rumour, possibility or speculation"}
STATUS = {"out": "Will not play", "doubtful": "Uncertain whether he will play", "available": "Will be available"}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="minutes")


def squad(conn: sqlite3.Connection, team: str, as_of: str) -> list[tuple[int, str]]:
    """Aktualna kadra: zawodnicy ze składów drużyny z ostatnich 365 dni, od największej liczby minut."""
    since = _iso(datetime.fromisoformat(as_of) - timedelta(days=365))
    return [(pid, name) for pid, name, _ in conn.execute(
        """SELECT p.id, p.name, SUM(l.minutes) m FROM lineup l JOIN player p ON p.id = l.player_id
           JOIN match ma ON ma.id = l.match_id
           WHERE l.team_id = ? AND l.source = 'official' AND ma.kickoff_utc BETWEEN ? AND ?
           GROUP BY p.id ORDER BY m DESC LIMIT ?""", (team, since, as_of, SQUAD_SIZE))]


def build_questions(team_names: dict[str, str], squads: dict[str, list[tuple[int, str]]]) -> dict[str, Question]:
    q: dict[str, Question] = {}
    for team, name in team_names.items():
        q[f"about_{team}"] = Question("noul", f"Does this article report news about the football club {name} (players, "
                                      "coach, club situation or an upcoming match)? Mentions only in passing do not count.")
        q[f"{team}__category"] = Question("choice", f"What is the main event reported about {name}?", CATEGORY)
        q[f"{team}__impact"] = Question("score", f"How much could this event affect {name} in its next league match?", IMPACT)
        q[f"{team}__direction"] = Question("choice", f"For {name}'s next match, does this event weaken or strengthen the team?", DIRECTION)
        q[f"{team}__certainty"] = Question("choice", "How certain is the reported information?", CERTAINTY)
        for pid, player in squads.get(team, []):
            q[f"p_{pid}"] = Question("noul", f"Does the article state that {player} ({name}) will miss, may miss or "
                                     "returns for the next match because of injury or suspension?")
            q[f"status_{pid}"] = Question("choice", f"What is the availability status of {player} for the next match?", STATUS)
    return q


def next_match(conn: sqlite3.Connection, team: str, after: str) -> str | None:
    row = conn.execute(
        """SELECT kickoff_utc FROM match WHERE (home_id = ? OR away_id = ?) AND status = 'scheduled' AND kickoff_utc > ?
           ORDER BY kickoff_utc LIMIT 1""", (team, team, after)).fetchone()
    return row[0] if row else None


def valid_until(conn, team: str, category: str, valid_from: str) -> str | None:
    rule = VALIDITY.get(category)
    if rule is None:
        return None
    start = datetime.fromisoformat(valid_from)
    if rule == "next_match":
        kickoff = next_match(conn, team, valid_from)
        return _iso(datetime.fromisoformat(kickoff) + timedelta(hours=3)) if kickoff else _iso(start + timedelta(days=7))
    return _iso(start + timedelta(days=rule))


def interpret(answers, team_names, squads) -> list[dict]:
    """Odpowiedzi silnika → fakty (bez zapisu). Fakt drużynowy ma player_id = None."""
    facts = []
    for team in team_names:
        if answers[f"about_{team}"].value < ABOUT_MIN:
            continue
        cat = answers[f"{team}__category"]
        category = cat.value if cat.confidence >= CATEGORY_CONFIDENCE_MIN else "other"
        if VALIDITY.get(category) is None:
            continue
        base = {"team_id": team, "category": category, "impact": round(answers[f"{team}__impact"].value, 2),
                "direction": answers[f"{team}__direction"].value, "certainty": answers[f"{team}__certainty"].value}
        players = []
        if category in PLAYER_CATEGORIES:
            for pid, _ in squads.get(team, []):
                if answers[f"p_{pid}"].value >= PLAYER_MIN:
                    status = answers[f"status_{pid}"]
                    players.append((pid, status.value if status.confidence >= STATUS_CONFIDENCE_MIN else "doubtful"))
        if players:
            facts += [{**base, "player_id": pid, "status": status} for pid, status in players]
        else:
            facts.append({**base, "player_id": None, "status": None})
    return facts


def save_fact(conn, fact: dict, article_id: int, valid_from: str) -> int:
    """Zapis z zasadami scalania (docs/05, 5.5): nowszy fakt zastępuje starszy, chyba że starszy jest pewniejszy i sprzeczny."""
    until = valid_until(conn, fact["team_id"], fact["category"], valid_from)
    fact_id = conn.execute(
        """INSERT INTO news_fact (article_id, source, team_id, player_id, category, status, impact, direction, certainty,
           valid_from, valid_until) VALUES (?, 'news', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (article_id, fact["team_id"], fact["player_id"], fact["category"], fact["status"], fact["impact"],
         fact["direction"], fact["certainty"], valid_from, until)).lastrowid
    older = conn.execute(
        """SELECT id, status, certainty FROM news_fact WHERE id != ? AND team_id = ? AND category = ?
           AND player_id IS ? AND superseded_by IS NULL""",
        (fact_id, fact["team_id"], fact["category"], fact["player_id"])).fetchall()
    for old_id, old_status, old_certainty in older:
        stronger_old = (old_status != fact["status"]
                        and CERTAINTY_RANK.get(old_certainty, 0) > CERTAINTY_RANK.get(fact["certainty"], 0))
        if stronger_old:
            conn.execute("UPDATE news_fact SET superseded_by = ? WHERE id = ?", (old_id, fact_id))
        else:
            conn.execute("UPDATE news_fact SET superseded_by = ? WHERE id = ?", (fact_id, old_id))
    return fact_id


def confirm_duplicate(conn, article_id: int, original_id: int, reliability: str) -> None:
    """Duplikat z innego źródła podnosi pewność faktów oryginału; źródło oficjalne – do „official”."""
    new = "official" if reliability == "oficjalne" else "reported"
    conn.execute("""UPDATE news_fact SET certainty = ? WHERE article_id = ? AND
                    CASE certainty WHEN 'speculation' THEN 0 WHEN 'reported' THEN 1 ELSE 2 END < ?""",
                 (new, original_id, CERTAINTY_RANK[new]))


def pending(conn: sqlite3.Connection, limit: int):
    return conn.execute(
        """SELECT a.id, a.title, a.text, a.published_at, a.source, a.reliability, a.duplicate_of FROM news_article a
           WHERE NOT EXISTS (SELECT 1 FROM decision_log d WHERE d.purpose = 'news_classify' AND d.ref_type = 'article'
                             AND d.ref_id = a.id)
           ORDER BY a.published_at LIMIT ?""", (limit,)).fetchall()


def _mark(conn, article_id: int, decision: str) -> None:
    conn.execute("""INSERT INTO decision_log (purpose, engine, model, ref_type, ref_id, state, questions, answers, decision,
                    created_at) VALUES ('news_classify', 'none', '-', 'article', ?, '{}', '{}', '{}', ?, ?)""",
                 (article_id, decision, _iso(datetime.now(timezone.utc))))


def process(conn: sqlite3.Connection, engine: DecisionEngine, limit: int = 10) -> dict:
    """Klasyfikuje do `limit` nowych artykułów (limit chroni darmowe limity LLM). Zwraca liczniki."""
    names = dict(conn.execute("SELECT id, name FROM team").fetchall())
    teams = current_teams(conn)
    stats = {"artykulow": 0, "duplikatow": 0, "bez_druzyny": 0, "faktow": 0}
    for article_id, title, text, published, source, reliability, duplicate_of in pending(conn, limit):
        stats["artykulow"] += 1
        if duplicate_of:
            confirm_duplicate(conn, article_id, duplicate_of, reliability)
            _mark(conn, article_id, "duplicate")
            stats["duplikatow"] += 1
            continue
        content = f"{title} {text[:TEXT_CHARS]}"
        # najwyżej MAX_TEAMS drużyn wspominanych najczęściej – każda dodaje ok. 70 pytań (kadra × 2)
        mentioned = sorted(team_mentions(content, teams), key=lambda t: -len(TEAM_PATTERNS[t].findall(content)))[:MAX_TEAMS]
        if not mentioned:
            _mark(conn, article_id, "no_team")
            stats["bez_druzyny"] += 1
            continue
        team_names = {t: names.get(t, t) for t in mentioned}
        squads = {t: squad(conn, t, published) for t in mentioned}
        state = {"title": title, "text": text[:TEXT_CHARS], "source": source, "published_at": published}
        try:
            answers = engine.ask("news_classify", state, build_questions(team_names, squads), ref=("article", article_id))
        except Exception as e:   # np. wszystkie modele przeciążone (503): kończymy przebieg, artykuł wróci w następnym
            stats["artykulow"] -= 1
            stats["przerwano"] = f"{type(e).__name__}: {str(e)[:80]}"
            break
        if getattr(engine, "log", None) is None:     # silnik bez DECISION_LOG – oznaczamy artykuł sami
            _mark(conn, article_id, "classified")
        for fact in interpret(answers, team_names, squads):
            save_fact(conn, fact, article_id, published)
            stats["faktow"] += 1
        conn.commit()
    conn.commit()
    return stats


def active_facts(conn: sqlite3.Connection, team: str, as_of: str) -> list[dict]:
    """Aktualne fakty drużyny (kontekst dla bramki i czatu, docs/05 5.6), od największego wpływu."""
    rows = conn.execute(
        """SELECT f.category, f.status, f.impact, f.certainty, f.valid_from, p.name AS player, a.title, a.url
           FROM news_fact f LEFT JOIN player p ON p.id = f.player_id LEFT JOIN news_article a ON a.id = f.article_id
           WHERE f.team_id = ? AND f.superseded_by IS NULL AND f.valid_from <= ? AND (f.valid_until IS NULL OR f.valid_until > ?)
           ORDER BY f.impact DESC""", (team, as_of, as_of)).fetchall()
    return [dict(zip(("category", "status", "impact", "certainty", "valid_from", "player", "title", "url"), r)) for r in rows]


def main() -> None:
    conn = db.connect()
    db.init_db(conn)
    print(process(conn, LLMEngine(log=conn), limit=config.NEWS.get("max_classify_per_run", 10)))
    conn.close()


if __name__ == "__main__":
    main()
