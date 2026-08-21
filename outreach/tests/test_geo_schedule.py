"""Unit tests for geo_schedule (no SMTP / DB required)."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from geo_schedule import (
    iana_from_utc_offset,
    in_send_window,
    next_send_datetime,
    snap_followup_utc,
    split_russian_fio,
    window_rank,
)


def test_split_fio_full():
    fio = split_russian_fio("Марушкин Игорь Юрьевич")
    assert fio.surname == "Марушкин"
    assert fio.first == "Игорь"
    assert fio.patronymic == "Юрьевич"
    assert fio.greeting == "Игорь Юрьевич"


def test_split_fio_name_patronymic():
    fio = split_russian_fio("Игорь Юрьевич")
    assert fio.first == "Игорь"
    assert fio.patronymic == "Юрьевич"
    assert fio.greeting == "Игорь Юрьевич"


def test_iana_from_dadata():
    assert iana_from_utc_offset("UTC+3") == "Europe/Moscow"
    assert iana_from_utc_offset("UTC+7") == "Asia/Krasnoyarsk"
    assert iana_from_utc_offset("UTC+12") == "Asia/Kamchatka"


def test_window_tue_morning_moscow():
    # Tuesday 10:15 Moscow
    local = datetime(2026, 8, 18, 10, 15, tzinfo=ZoneInfo("Europe/Moscow"))
    assert in_send_window(local) is True
    assert window_rank(local) > 0


def test_window_blocks_weekend_and_night():
    sat = datetime(2026, 8, 22, 10, 15, tzinfo=ZoneInfo("Europe/Moscow"))
    night = datetime(2026, 8, 18, 21, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    assert in_send_window(sat) is False
    assert in_send_window(night) is False


def test_snap_followup_absolute_from_anchor():
    # Friday 09:00 UTC (= 12:00 Moscow) — first letter
    anchor = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    # +3 days → Monday; prefer Tue–Thu → should land Tuesday 10:00 Moscow
    nxt = snap_followup_utc(anchor, delay_days=3, tz_name="Europe/Moscow")
    local = nxt.astimezone(ZoneInfo("Europe/Moscow"))
    assert local.weekday() in (1, 2, 3)  # Tue–Thu
    assert local.hour == 10 and local.minute == 0


def test_next_send_from_evening_goes_next_slot_or_day():
    evening = datetime(2026, 8, 18, 18, 0, tzinfo=timezone.utc)  # Tue 21:00 MSK
    nxt = next_send_datetime(evening, "Europe/Moscow")
    local = nxt.astimezone(ZoneInfo("Europe/Moscow"))
    assert local.weekday() in (1, 2, 3)
    assert (local.hour, local.minute) == (10, 0)
