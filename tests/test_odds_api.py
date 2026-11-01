from typerai import db
from typerai.collectors import odds_api
from typerai.collectors.football_data import FdMatch, import_matches

HOME, AWAY = "Lech Poznań", "Legia Warszawa"

EVENT = {
    "id": "abc123",
    "commence_time": "2026-11-08T16:30:00Z",
    "home_team": HOME,
    "away_team": AWAY,
    "bookmakers": [
        {
            "key": "pinnacle",
            "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": HOME, "price": 2.15}, {"name": AWAY, "price": 3.4}, {"name": "Draw", "price": 3.5}]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": 1.9, "point": 2.5}, {"name": "Under", "price": 1.95, "point": 2.5}]},
                {"key": "spreads", "outcomes": [
                    {"name": HOME, "price": 1.98, "point": -0.25}, {"name": AWAY, "price": 1.9, "point": 0.25}]},
            ],
        }
    ],
}


def test_market_codes():
    book = EVENT["bookmakers"][0]["markets"]
    codes = [c for m in book for c in odds_api.market_codes(m["key"], m["outcomes"], HOME, AWAY)]
    assert codes == [
        ("1X2:1", 2.15), ("1X2:2", 3.4), ("1X2:X", 3.5),
        ("OU:2.5:over", 1.9), ("OU:2.5:under", 1.95),
        ("AH:-0.25:home", 1.98), ("AH:0.25:away", 1.9),
    ]


def test_extra_markets():
    btts = [{"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.0}]
    dc = [{"name": f"{HOME}/Draw", "price": 1.3}, {"name": f"Draw/{AWAY}", "price": 1.7}, {"name": f"{HOME}/{AWAY}", "price": 1.3}]
    assert odds_api.market_codes("btts", btts, HOME, AWAY) == [("BTTS:yes", 1.8), ("BTTS:no", 2.0)]
    assert [c for c, _ in odds_api.market_codes("double_chance", dc, HOME, AWAY)] == ["DC:1X", "DC:X2", "DC:12"]


def test_unknown_market_is_ignored():
    assert odds_api.market_codes("player_goals", [{"name": "X", "price": 2.0}], HOME, AWAY) == []


def test_save_odds_then_result_from_football_data_links_same_match(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)

    assert odds_api.save_odds(conn, [EVENT], taken_at="2026-11-07T10:00+00:00") == 7
    match = conn.execute("SELECT id, season, status FROM match").fetchone()
    assert (match["season"], match["status"]) == ("2026/27", "scheduled")

    # football-data podaje godzinę zaokrągloną inaczej – mecz ma zostać ten sam
    result = FdMatch("2026/27", "2026-11-08T16:45+00:00", "lech", "legia", 2, 1, {})
    import_matches(conn, [result])

    rows = conn.execute("SELECT id, hg, ag, status FROM match").fetchall()
    assert len(rows) == 1
    assert (rows[0]["id"], rows[0]["hg"], rows[0]["ag"], rows[0]["status"]) == (match["id"], 2, 1, "finished")
