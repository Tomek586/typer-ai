from typerai import db


def test_backup_copies_data_including_wal(tmp_path):
    src = tmp_path / "typer.db"
    conn = db.connect(src)                 # tryb WAL: świeże zmiany siedzą w pliku -wal
    db.init_db(conn)
    conn.execute("""INSERT INTO match (season, kickoff_utc, home_id, away_id, hg, ag, status)
                    VALUES ('2026/27', '2026-11-08T16:30+00:00', 'lech', 'legia', 2, 1, 'finished')""")
    conn.commit()

    copy = db.backup(tmp_path / "kopia" / "typer_kopia.db", src=src)
    conn.close()

    c2 = db.connect(copy)
    assert tuple(c2.execute("SELECT hg, ag FROM match").fetchone()) == (2, 1)
    assert c2.execute("SELECT COUNT(*) FROM team").fetchone()[0] > 30
