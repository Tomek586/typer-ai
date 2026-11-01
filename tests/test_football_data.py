from pathlib import Path

from typerai import db
from typerai.collectors import football_data

SAMPLE = Path(__file__).parent / "fixtures" / "pol_sample.csv"


def test_parse_sample():
    matches = football_data.parse(SAMPLE)
    assert len(matches) == 3

    first = matches[0]
    assert first.season == "2012/13"
    assert (first.home_id, first.away_id, first.hg, first.ag) == ("pogon", "zaglebie-lubin", 4, 0)
    # 17:00 czasu brytyjskiego latem (BST) = 16:00 UTC
    assert first.kickoff_utc == "2012-08-17T16:00+00:00"
    # Brak Betfair i Bet365 w tym wierszu -> tylko kompletne rynki
    assert set(first.odds) == {"pinnacle", "market_avg", "market_max"}
    assert first.odds["pinnacle"] == {"1X2:1": 3.23, "1X2:X": 3.21, "1X2:2": 2.47}


def test_winter_kickoff_and_missing_pinnacle():
    last = football_data.parse(SAMPLE)[-1]
    assert last.kickoff_utc == "2026-10-25T16:30+00:00"  # po zmianie czasu: GMT = UTC
    assert "pinnacle" not in last.odds
    assert last.odds["betfair_ex"]["1X2:2"] == 2.62


def test_import_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_db(conn)
    matches = football_data.parse(SAMPLE)

    first = football_data.import_matches(conn, matches)
    second = football_data.import_matches(conn, matches)

    assert first == {"matches": 3, "odds": 3 * 3 + 5 * 3 + 4 * 3}
    assert second["odds"] == 0
    assert conn.execute("SELECT COUNT(*) FROM match").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM team").fetchone()[0] == len(football_data.teams.TEAMS)
