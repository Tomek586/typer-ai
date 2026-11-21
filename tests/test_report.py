import sqlite3

import pytest

from typerai import config, report
from typerai.betting import lifecycle

from test_lifecycle import NOW, add_odds, setup_db


def build(tmp_path):
    conn, match_id = setup_db(tmp_path)
    add_odds(conn, match_id, NOW, home_best=1.78)
    conn.commit()
    return conn, match_id


@pytest.mark.parametrize("code, label", [
    ("1X2:1", "wygrana gospodarza (1)"),
    ("OU:2.5:under", "poniżej 2,5 gola"),
    ("AH:-0.5:home", "handicap gospodarz -0,5"),
    ("AH:1.5:away", "handicap gość +1,5"),
    ("BTTS:no", "nie strzelą obie drużyny"),
    ("DC:1X", "podwójna szansa 1X"),
])
def test_market_label(code, label):
    assert report.market_label(code) == label


def test_connect_ro_rejects_writes(tmp_path):
    conn, _ = build(tmp_path)
    conn.close()
    ro = report.connect_ro(tmp_path / "t.db")
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM pick")


def test_connect_ro_missing_db(tmp_path):
    with pytest.raises(FileNotFoundError):
        report.connect_ro(tmp_path / "brak.db")


def test_picks_and_summary_after_settlement(tmp_path):
    conn, match_id = build(tmp_path)
    issued = lifecycle.stage1(conn, NOW)
    assert issued, "scenariusz z test_lifecycle powinien dać typ"
    # potwierdzony i wygrany typ oficjalny po kursie 1,78; zamknięcie Pinnacle 1,62 -> CLV +9,9%
    conn.execute("""UPDATE pick SET status = CASE WHEN status = 'WSTEPNY' THEN 'POTWIERDZONY' ELSE status END,
                    odds_stage2 = odds_stage1, odds_closing = 1.62, outcome = 'WIN', profit = odds_stage1 - 1""")
    conn.commit()

    rows = report.picks(conn)
    official = [r for r in rows if r["strategia"] == "oficjalna"]
    names = dict(conn.execute("SELECT id, name FROM team WHERE id IN ('lech', 'motor')").fetchall())
    assert official[0]["mecz"] == f"{names['lech']} – {names['motor']}"
    assert official[0]["status"] == "potwierdzony"
    assert official[0]["clv"] == pytest.approx(1.78 / 1.62 - 1, abs=1e-3)

    s = report.live_summary(conn)["oficjalna"]
    assert (s["typy"], s["trafne"]) == (1, 1)
    assert s["roi"] == pytest.approx(0.78)
    assert report.cumulative_profit(rows, ("POTWIERDZONY",))[-1]["zysk_narastajaco"] == pytest.approx(0.78)


def test_summary_without_settled_picks(tmp_path):
    conn, _ = build(tmp_path)
    s = report.live_summary(conn)["oficjalna"]
    assert s["typy"] == 0 and s["trafnosc"] is None and s["roi"] is None


def test_upcoming_uses_blend_and_rules(tmp_path):
    conn, _ = build(tmp_path)
    lifecycle.stage1(conn, NOW)          # zapisuje predykcję meczu
    rows = report.upcoming(conn, now=NOW)
    assert [r["zdarzenie"] for r in rows] == ["wygrana gospodarza (1)", "remis (X)", "wygrana gościa (2)"]
    home = rows[0]
    w = config.MODEL["blend_w"]
    # mieszanka leży między modelem a rynkiem, bliżej rynku (w < 0,5)
    lo, hi = sorted([home["p_model"], home["p_rynek"]])
    assert lo <= home["p_mieszanka"] <= hi
    assert abs(home["p_mieszanka"] - home["p_rynek"]) <= abs(home["p_mieszanka"] - home["p_model"]) or w >= 0.5
    assert home["kurs"] == 1.78 and home["ev"] == pytest.approx(home["p_mieszanka"] * 1.78 - 1)
    assert sum(r["p_rynek"] for r in rows) == pytest.approx(1.0, abs=1e-6)
