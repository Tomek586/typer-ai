from datetime import datetime

from typerai import scheduler


def at(hh, mm):
    return datetime(2026, 11, 6, hh, mm, tzinfo=scheduler.TZ)


def test_fixed_time_jobs():
    assert scheduler.due("stage1", at(9, 0)) and scheduler.due("stage1", at(18, 0))
    assert not scheduler.due("stage1", at(9, 1))
    assert scheduler.due("settle", at(23, 45))


def test_interval_job():
    assert scheduler.due("stage2", at(17, 30)) and scheduler.due("stage2", at(17, 40))
    assert not scheduler.due("stage2", at(17, 35))
