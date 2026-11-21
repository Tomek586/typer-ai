import json
from types import SimpleNamespace

import pytest

from typerai import db
from typerai.decision import engine
from typerai.decision.engine import Answer, Question
from typerai.news import extract

PUBLISHED = "2026-11-20T10:00+00:00"


# ------------------------------------------------------------------ silnik decyzyjny

def test_to_answer_normalizes_and_computes_confidence():
    choice = Question("choice", "?", {"a": "A", "b": "B", "c": "C"})
    a = engine.to_answer(choice, {"a": 2, "b": 1, "c": 1, "x": 5})          # nieznana opcja pominięta
    assert a.value == "a" and a.probabilities["a"] == pytest.approx(0.5)
    assert a.confidence == pytest.approx((0.5 - 1 / 3) / (1 - 1 / 3))
    noul = engine.to_answer(Question("noul", "?"), {"yes": 0.8, "no": 0.2})
    assert noul.value == pytest.approx(0.8)
    score = engine.to_answer(Question("score", "?", ["0", "1", "2"]), {"1": 0.5, "2": 0.5})
    assert score.value == pytest.approx(1.5)
    empty = engine.to_answer(choice, None)                                  # brak odpowiedzi = rozkład równomierny
    assert empty.confidence == pytest.approx(0.0)


def test_llm_engine_parses_json_and_logs(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    reply = json.dumps({"q1": {"yes": 0.9, "no": 0.1}})
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=reply)))
    e = engine.LLMEngine(client=client, models=["m1"], log=conn)
    answers = e.ask("test", {"x": 1}, {"q1": Question("noul", "?")}, ref=("article", 7))
    assert answers["q1"].value == pytest.approx(0.9)
    row = conn.execute("SELECT purpose, engine, model, ref_id FROM decision_log").fetchone()
    assert tuple(row) == ("test", "llm-gemini", "m1", 7)


# ------------------------------------------------------------------ fakty z newsów

def ans(value, confidence=1.0, type_="choice"):
    return Answer(type_, value, {}, confidence)


def answers_for(team, category, players=(), about=0.9, cat_conf=0.9, certainty="reported"):
    a = {f"about_{team}": ans(about, type_="noul"), f"{team}__category": ans(category, cat_conf),
         f"{team}__impact": ans(3.0, type_="score"), f"{team}__direction": ans("weakens"),
         f"{team}__certainty": ans(certainty)}
    squad = [(11, "Mikael Ishak"), (12, "Bramkarz")]
    for pid, _ in squad:
        hit = dict(players).get(pid)
        a[f"p_{pid}"] = ans(0.9 if hit else 0.1, type_="noul")
        a[f"status_{pid}"] = ans(hit or "available", 0.8)
    return a, {team: squad}


def test_interpret_applies_thresholds():
    a, squads = answers_for("lech", "injury", players=[(11, "out")])
    facts = extract.interpret(a, {"lech": "Lech Poznań"}, squads)
    assert [(f["player_id"], f["status"], f["category"]) for f in facts] == [(11, "out", "injury")]
    a, squads = answers_for("lech", "injury", about=0.4)                        # artykuł nie dotyczy drużyny
    assert extract.interpret(a, {"lech": "Lech"}, squads) == []
    a, squads = answers_for("lech", "injury", cat_conf=0.2)                     # niepewna kategoria → other → brak faktu
    assert extract.interpret(a, {"lech": "Lech"}, squads) == []
    a, squads = answers_for("lech", "coach_change")
    facts = extract.interpret(a, {"lech": "Lech"}, squads)
    assert facts[0]["player_id"] is None and facts[0]["category"] == "coach_change"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    c.execute("INSERT INTO player (id, team_id, name, position) VALUES (11, 'lech', 'Mikael Ishak', 'F')")
    c.execute("""INSERT INTO match (season, kickoff_utc, home_id, away_id, status)
                 VALUES ('2026/27', '2026-11-23T17:30+00:00', 'lech', 'legia', 'scheduled')""")
    for i, title in enumerate(["Ishak kontuzjowany", "Ishak jednak zagra"], 1):
        c.execute("""INSERT INTO news_article (id, url, source, reliability, published_at, fetched_at, title, text)
                     VALUES (?, ?, 'a', 'medialne', ?, ?, ?, 'tekst')""", (i, f"https://a.pl/{i}", PUBLISHED, PUBLISHED, title))
    return c


def fact(category="injury", status="out", certainty="reported", player=11):
    return {"team_id": "lech", "player_id": player, "category": category, "status": status, "impact": 3.0,
            "direction": "weakens", "certainty": certainty}


def test_validity_by_category(conn):
    assert extract.valid_until(conn, "lech", "injury", PUBLISHED) == "2026-12-04T10:00+00:00"        # 14 dni
    assert extract.valid_until(conn, "lech", "suspension", PUBLISHED) == "2026-11-23T20:30+00:00"    # do meczu + 3 h
    assert extract.valid_until(conn, "lech", "transfer", PUBLISHED) is None


def test_newer_fact_supersedes_older_unless_older_is_more_certain(conn):
    first = extract.save_fact(conn, fact(), 1, PUBLISHED)
    second = extract.save_fact(conn, fact(status="doubtful"), 2, "2026-11-21T10:00+00:00")
    rows = dict(conn.execute("SELECT id, superseded_by FROM news_fact").fetchall())
    assert rows == {first: second, second: None}
    official = extract.save_fact(conn, fact(status="out", certainty="official"), 1, "2026-11-21T11:00+00:00")
    rumour = extract.save_fact(conn, fact(status="available", certainty="speculation"), 2, "2026-11-21T12:00+00:00")
    rows = dict(conn.execute("SELECT id, superseded_by FROM news_fact").fetchall())
    assert rows[rumour] == official and rows[official] is None          # plotka nie zastępuje oficjalnej informacji
    active = extract.active_facts(conn, "lech", "2026-11-22T00:00+00:00")
    assert [(f["player"], f["status"]) for f in active] == [("Mikael Ishak", "out")]


class FakeEngine:
    def __init__(self):
        self.calls = []

    def ask(self, purpose, state, questions, ref=None):
        self.calls.append(ref)
        out = {k: Answer(q.type, q.options()[0] if q.type == "choice" else 0.1, {}, 1.0) for k, q in questions.items()}
        out["about_lech"] = Answer("noul", 0.95, {}, 1.0)
        out["lech__category"] = Answer("choice", "coach_change", {}, 1.0)
        out["lech__certainty"] = Answer("choice", "speculation", {}, 1.0)
        return out


def test_process_classifies_once_and_confirms_duplicates(conn):
    conn.execute("UPDATE news_article SET title = 'Lech: trener do zwolnienia?' WHERE id = 1")
    conn.execute("""INSERT INTO news_article (id, url, source, reliability, published_at, fetched_at, title, text, duplicate_of)
                    VALUES (3, 'https://b.pl/3', 'b', 'medialne', ?, ?, 'Lech: trener do zwolnienia', 'tekst', 1)""",
                 (PUBLISHED, PUBLISHED))
    conn.execute("UPDATE news_article SET title = 'Tenis: finał' WHERE id = 2")
    e = FakeEngine()
    stats = extract.process(conn, e, limit=10)
    assert stats == {"artykulow": 3, "duplikatow": 1, "bez_druzyny": 1, "faktow": 1}
    assert e.calls == [("article", 1)]                                  # duplikat i artykuł bez drużyny bez zapytania
    assert conn.execute("SELECT certainty FROM news_fact").fetchone()[0] == "reported"   # podniesione przez duplikat
    assert extract.process(conn, e, limit=10)["artykulow"] == 0          # każdy artykuł tylko raz
