from pathlib import Path

from typerai import db
from typerai.collectors import ninetymin

FIXTURE = Path(__file__).parent / "fixtures" / "90minut_mecz_2113301.html"


def report():
    return ninetymin.parse_match(FIXTURE.read_text(encoding="utf-8"), 2113301)


def test_header():
    r = report()
    assert (r.season, r.round, r.home, r.away, r.hg, r.ag) == ("2026/27", 3, "Lech Poznań", "Piast Gliwice", 3, 0)
    assert r.kickoff_utc == "2026-08-09T15:30+00:00"  # 17:30 czasu polskiego latem
    assert r.referee == "Patryk Gryckiewicz"


def test_lineups_minutes_and_substitutions():
    r = report()
    for side in ("home", "away"):
        players = [p for p in r.players if p.side == side]
        assert sum(p.is_starter for p in players) == 11
        assert sum(p.minutes for p in players) == 11 * 90
    ishak = next(p for p in r.players if p.name == "Mikael Ishak")
    assert (ishak.is_starter, ishak.minute_in, ishak.minutes, ishak.row_index) == (False, 61, 29, 10)
    agnero = next(p for p in r.players if p.name == "Yannick Agnero")
    assert (agnero.is_starter, agnero.minute_out) == (True, 61)


def test_cards_and_goals():
    r = report()
    assert {p.name for p in r.players if p.yellow} == {"Mikael Ishak", "Emmanuel Twumasi", "Leandro Sanca"}
    assert {p.name: p.goals for p in r.players if p.goals} == {
        "Mikael Ishak": 1, "Karol Delikat": 1, "Allahyar Sayyadmanesh": 1}


def test_parse_season_takes_only_played_matches():
    html = ('<a href="/mecz.php?id_mecz=11" title="A 1-0 B">1-0</a>'
            '<a href="/mecz.php?id_mecz=12">-</a>'
            '<a href="/mecz.php?id_mecz=11">1-0</a>')
    assert ninetymin.parse_season(html) == [11]


def test_save_report_links_existing_match(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    # mecz z football-data: godzina brytyjska przeliczona na UTC
    conn.execute("""INSERT INTO match (season, kickoff_utc, home_id, away_id, hg, ag, status)
                    VALUES ('2026/27', '2026-08-09T15:30+00:00', 'lech', 'piast', 3, 0, 'finished')""")
    match_id = ninetymin.save_report(conn, report())
    ninetymin.update_positions(conn)

    m = conn.execute("SELECT * FROM match").fetchall()
    assert len(m) == 1 and m[0]["id"] == match_id and m[0]["ninetymin_id"] == 2113301 and m[0]["round"] == 3
    assert conn.execute("SELECT COUNT(*) FROM lineup WHERE match_id = ?", (match_id,)).fetchone()[0] == 32
    assert conn.execute("SELECT position FROM player WHERE name = 'Mateusz Lis'").fetchone()[0] == "G"
    assert tuple(conn.execute("SELECT yellow_h, yellow_a FROM match_stats").fetchone()) == (1, 2)
