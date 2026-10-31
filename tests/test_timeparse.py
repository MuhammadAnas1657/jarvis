"""Unit tests for mixed Roman-Urdu and English time parsing."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from jarvis.timeparse import parse_relative_time, DEFAULT_TIMEZONE


@pytest.fixture
def fixed_now():
    # Fixed base: Wednesday, 2026-10-28 10:00:00 PKT
    return datetime(2026, 10, 28, 10, 0, 0, tzinfo=DEFAULT_TIMEZONE)


def test_kal_subah(fixed_now):
    # kal subah 9 baje -> Thursday Oct 29, 09:00 PKT
    dt = parse_relative_time("kal subah 9 baje meeting hai", base_dt=fixed_now)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 10
    assert dt.day == 29
    assert dt.hour == 9
    assert dt.minute == 0


def test_parson_shaam(fixed_now):
    # parson shaam 6:30 baje -> Friday Oct 30, 18:30 PKT
    dt = parse_relative_time("parson shaam 6:30 baje dinner with team", base_dt=fixed_now)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 10
    assert dt.day == 30
    assert dt.hour == 18
    assert dt.minute == 30


def test_aaj_raat(fixed_now):
    # aaj raat 10 baje -> Wednesday Oct 28, 22:00 PKT
    dt = parse_relative_time("aaj raat 10 baje review budget", base_dt=fixed_now)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 10
    assert dt.day == 28
    assert dt.hour == 22
    assert dt.minute == 0


def test_dopahar_two_pm(fixed_now):
    # kal dopahar 2 baje -> Thursday Oct 29, 14:00 PKT
    dt = parse_relative_time("kal dopahar 2 baje submit report", base_dt=fixed_now)
    assert dt is not None
    assert dt.day == 29
    assert dt.hour == 14
    assert dt.minute == 0


def test_saadhe_nau(fixed_now):
    # kal saadhe nau baje subah -> Thursday Oct 29, 09:30 PKT
    dt = parse_relative_time("kal saadhe nau baje call", base_dt=fixed_now)
    assert dt is not None
    assert dt.day == 29
    assert dt.hour == 9
    assert dt.minute == 30


def test_duration_aadha_ghanta(fixed_now):
    # aadhe ghantay baad -> 10:30 PKT
    dt = parse_relative_time("aadhe ghantay baad check oven", base_dt=fixed_now)
    assert dt is not None
    assert dt.hour == 10
    assert dt.minute == 30


def test_english_standard(fixed_now):
    # tomorrow at 3pm -> Thursday Oct 29, 15:00 PKT
    dt = parse_relative_time("tomorrow at 3pm team sync", base_dt=fixed_now)
    assert dt is not None
    assert dt.day == 29
    assert dt.hour == 15

