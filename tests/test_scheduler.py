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


def test_last_slot_today_and_yesterday():
    assert scheduler.last_slot("stage1", at(12, 0)) == at(9, 0)
    assert scheduler.last_slot("stage1", at(18, 0)) == at(18, 0)
    early = scheduler.last_slot("stage1", at(7, 0))            # przed 9:00 -> wczorajsze 18:00
    assert (early.day, early.hour) == (5, 18)
    assert scheduler.last_slot("stage2", at(12, 0)) is None     # zadania „co N minut” nie są nadrabiane


def test_missed_slot_is_caught_up_once():
    # komputer spał o 9:00, ostatnie uruchomienie wczoraj o 18:00 -> nadrabiamy po wybudzeniu
    yesterday_18 = scheduler.last_slot("stage1", at(7, 0))
    assert scheduler.missed("stage1", at(11, 40), yesterday_18)
    # po nadrobieniu (uruchomienie o 11:40) nic więcej do 18:00
    assert not scheduler.missed("stage1", at(15, 0), at(11, 40))
    assert scheduler.missed("stage1", at(18, 30), at(11, 40))   # 18:00 też przespane
    assert scheduler.missed("stage1", at(10, 0), None)          # pierwsze uruchomienie w ogóle
