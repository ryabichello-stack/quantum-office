"""Layer C: holidays, TZ fairness, OOO pause classification."""

from __future__ import annotations

from datetime import date, datetime, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from geo_schedule import (
    in_send_window,
    is_russian_public_holiday,
    next_send_datetime,
    window_rank,
)
from modules.replies.classify import classify_reply


def test_ru_new_year_is_holiday():
    assert is_russian_public_holiday(date(2026, 1, 1)) is True
    assert is_russian_public_holiday(date(2026, 1, 8)) is True
    assert is_russian_public_holiday(date(2026, 2, 23)) is True
    assert is_russian_public_holiday(date(2026, 8, 18)) is False


def test_holiday_blocks_send_window():
    # Thursday 10:15 Moscow but New Year holiday
    local = datetime(2026, 1, 1, 10, 15, tzinfo=ZoneInfo("Europe/Moscow"))
    assert in_send_window(local) is False
    assert in_send_window(local, settings={"SCHEDULE_SKIP_RU_HOLIDAYS": "false"}) is True


def test_next_send_skips_new_year_block():
    # Dec 31 2025 evening → should land after Jan 8 holidays on a preferred weekday slot
    after = datetime(2025, 12, 31, 18, 0, tzinfo=timezone.utc)
    nxt = next_send_datetime(after, "Europe/Moscow")
    local = nxt.astimezone(ZoneInfo("Europe/Moscow"))
    assert local.date() >= date(2026, 1, 9)
    assert is_russian_public_holiday(local.date()) is False
    assert local.weekday() in (0, 1, 2, 3, 4)


def test_tz_fairness_rotates():
    # Same preferred Tue morning slot; Moscow vs Vladivostok
    msk = datetime(2026, 8, 18, 10, 15, tzinfo=ZoneInfo("Europe/Moscow"))
    vvo = datetime(2026, 8, 18, 10, 15, tzinfo=ZoneInfo("Asia/Vladivostok"))
    east = {"SCHEDULE_TZ_FAIRNESS": "east_first"}
    west = {"SCHEDULE_TZ_FAIRNESS": "west_first"}
    assert window_rank(vvo, settings=east) > window_rank(msk, settings=east)
    assert window_rank(msk, settings=west) > window_rank(vvo, settings=west)

    # rotate_daily: odd UTC ordinal prefers east, even prefers west
    odd_day = datetime(2026, 8, 19, 7, 15, tzinfo=timezone.utc)  # Wed
    even_day = datetime(2026, 8, 18, 7, 15, tzinfo=timezone.utc)  # Tue
    odd_msk = odd_day.astimezone(ZoneInfo("Europe/Moscow")).replace(
        hour=10, minute=15, second=0, microsecond=0
    )
    odd_vvo = odd_day.astimezone(ZoneInfo("Asia/Vladivostok")).replace(
        hour=10, minute=15, second=0, microsecond=0
    )
    even_msk = even_day.astimezone(ZoneInfo("Europe/Moscow")).replace(
        hour=10, minute=15, second=0, microsecond=0
    )
    even_vvo = even_day.astimezone(ZoneInfo("Asia/Vladivostok")).replace(
        hour=10, minute=15, second=0, microsecond=0
    )
    rot = {"SCHEDULE_TZ_FAIRNESS": "rotate_daily"}
    assert odd_day.date().toordinal() % 2 == 1
    assert even_day.date().toordinal() % 2 == 0
    assert window_rank(odd_vvo, settings=rot) > window_rank(odd_msk, settings=rot)
    assert window_rank(even_msk, settings=rot) > window_rank(even_vvo, settings=rot)


def test_ooo_and_automatic_pause_not_stop():
    ooo = classify_reply(subject="Out of office", body="Я в отпуске, вернусь через неделю")
    assert ooo.classification == "out_of_office"
    assert ooo.should_stop_sequence is False
    assert ooo.should_pause_sequence is True

    msg = EmailMessage()
    msg["Auto-Submitted"] = "auto-replied"
    msg["Subject"] = "Автоответ"
    auto = classify_reply(subject="Автоответ", body="", msg=msg)
    assert auto.classification == "automatic"
    assert auto.should_stop_sequence is False
    assert auto.should_pause_sequence is True

    unsub = classify_reply(subject="stop", body="отпишитесь пожалуйста")
    assert unsub.should_stop_sequence is True
    assert unsub.should_pause_sequence is False
