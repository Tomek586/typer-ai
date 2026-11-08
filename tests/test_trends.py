from typerai import db
from typerai.analysis import trends
from typerai.betting import value


def setup(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    games = [  # (data, gospodarz, gość, hg, ag)
        ("2026-01-10", "lech", "legia", 3, 1), ("2026-03-10", "legia", "lech", 2, 2),
        ("2026-05-10", "lech", "legia", 1, 0), ("2026-08-10", "legia", "lech", 0, 2),
        ("2026-09-01", "lech", "rakow", 2, 1), ("2026-09-08", "piast", "lech", 1, 3),
        ("2026-09-15", "legia", "motor", 0, 0), ("2026-09-22", "pogon", "legia", 2, 1),
        ("2026-12-01", "lech", "legia", 5, 0),  # po dacie analizy – nie może być uwzględniony
    ]
    for d, h, a, hg, ag in games:
        conn.execute("""INSERT INTO match (season, kickoff_utc, home_id, away_id, hg, ag, status)
                        VALUES ('x', ?, ?, ?, ?, ?, 'finished')""", (d + "T18:00+00:00", h, a, hg, ag))
    return conn


def test_h2h_and_form_respect_date(tmp_path):
    conn = setup(tmp_path)
    t = trends.match_trends(conn, "lech", "legia", "2026-10-01T18:00+00:00")
    assert len(t["h2h"]) == 4 and t["h2h"][0]["wynik"].startswith("Legia Warszawa 0:2")
    assert t["h2h_bilans_gospodarza"] == "W W R W"   # z perspektywy Lecha, najnowszy pierwszy
    assert t["forma_gospodarza"] == "W W W"
    assert t["forma_goscia"] == "P R P"
    assert t["zdarzenia"]["powyżej 1,5 gola"]["h2h"] == "3 z 4"


def test_recurring_needs_two_groups(tmp_path):
    conn = setup(tmp_path)
    t = trends.match_trends(conn, "lech", "legia", "2026-10-01T18:00+00:00")
    names = [r["zdarzenie"] for r in t["powtarza_sie"]]
    assert "powyżej 1,5 gola" in names  # 3/4 w H2H i 3/3 w formie Lecha


def test_minimum_odds():
    assert value.minimum_odds(0.5) == 2.06   # (1 + 0,03) / 0,5
    assert value.minimum_odds(0.5, ev_min=0.0) == 2.0
