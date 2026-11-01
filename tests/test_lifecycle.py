from datetime import datetime, timedelta, timezone

import numpy as np

from typerai import db
from typerai.betting import lifecycle, settle

TEAMS = ["lech", "legia", "rakow", "pogon", "piast", "motor"]
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=10)


def iso(dt):
    return dt.isoformat(timespec="minutes")


def strong(team):
    """Lech wyraźnie najsilniejszy, Motor najsłabszy – model ma się zgadzać z rynkiem co do faworyta."""
    return {"lech": 0.35, "motor": -0.25}.get(team, 0.0)


def setup_db(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    rng = np.random.default_rng(0)
    day = NOW - timedelta(days=360)
    for _ in range(4):
        for h in TEAMS:
            for a in TEAMS:
                if h != a:
                    conn.execute("""INSERT INTO match (season, kickoff_utc, home_id, away_id, hg, ag, status)
                                    VALUES ('2025/26', ?, ?, ?, ?, ?, 'finished')""",
                                 (iso(day), h, a, int(rng.poisson(1.5 + strong(h) - strong(a) / 2)),
                                  int(rng.poisson(1.1 + strong(a) - strong(h) / 2))))
                    day += timedelta(days=2)
    match_id = conn.execute("""INSERT INTO match (season, kickoff_utc, home_id, away_id, status)
                               VALUES ('2026/27', ?, 'lech', 'motor', 'scheduled')""", (iso(KICKOFF),)).lastrowid
    return conn, match_id


def add_odds(conn, match_id, taken, home_best, others=1.70):
    # Pinnacle wycenia gospodarza na ok. 59%; najlepszy kurs u 'betclic'
    books = {"pinnacle": (1.62, 4.0, 5.5), "unibet": (1.65, 3.9, 5.2), "betclic": (home_best, 3.8, 5.0),
             "leovegas": (others, 3.9, 5.3)}
    for book, (o1, ox, o2) in books.items():
        for market, o in (("1X2:1", o1), ("1X2:X", ox), ("1X2:2", o2)):
            conn.execute("INSERT INTO odds_snapshot (match_id, market, odds, bookmaker, taken_at) VALUES (?, ?, ?, ?, ?)",
                         (match_id, market, o, book, iso(taken)))
    conn.commit()


def test_full_cycle_confirmed_then_settled(tmp_path):
    conn, match_id = setup_db(tmp_path)
    add_odds(conn, match_id, NOW - timedelta(minutes=5), home_best=1.78)

    issued = lifecycle.stage1(conn, NOW)
    assert [i["market"] for i in issued] == ["1X2:1"]
    assert lifecycle.stage1(conn, NOW) == []  # drugi przebieg nie dubluje typu

    stage2_time = KICKOFF - timedelta(minutes=60)
    add_odds(conn, match_id, stage2_time - timedelta(minutes=2), home_best=1.76)
    decisions = lifecycle.stage2(conn, stage2_time)
    assert decisions == [{"match_id": match_id, "market": "1X2:1", "status": "POTWIERDZONY", "odds": 1.76}]

    conn.execute("UPDATE match SET hg = 2, ag = 0, status = 'finished' WHERE id = ?", (match_id,))
    assert settle.settle_picks(conn) == 1
    pick = conn.execute("SELECT * FROM pick").fetchone()
    assert (pick["outcome"], round(pick["profit"], 2), pick["odds_closing"]) == ("WIN", 0.76, 1.62)


def test_stage2_cancels_when_value_disappears(tmp_path):
    conn, match_id = setup_db(tmp_path)
    add_odds(conn, match_id, NOW - timedelta(minutes=5), home_best=1.78)
    lifecycle.stage1(conn, NOW)

    stage2_time = KICKOFF - timedelta(minutes=60)
    add_odds(conn, match_id, stage2_time - timedelta(minutes=2), home_best=1.64, others=1.63)  # kursy spadły u wszystkich
    assert lifecycle.stage2(conn, stage2_time)[0]["status"] == "ANULOWANY"

    conn.execute("UPDATE match SET hg = 0, ag = 1, status = 'finished' WHERE id = ?", (match_id,))
    settle.settle_picks(conn)
    pick = conn.execute("SELECT outcome, profit FROM pick").fetchone()
    assert (pick["outcome"], pick["profit"]) == ("LOSS", None)  # anulowany nie wchodzi do wyniku oficjalnego
