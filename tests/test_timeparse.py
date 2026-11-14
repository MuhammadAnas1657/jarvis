"""Unit tests for mixed Roman-Urdu and English time parsing."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from jarvis.timeparse import parse_relative_time, parse_time_with_analysis, DEFAULT_TIMEZONE


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


def test_midnight_12_baje_raat_and_aadhi_raat(fixed_now):
    # "12 baje raat" and "aadhi raat" -> 00:00:00
    dt1 = parse_relative_time("kal 12 baje raat server backup", base_dt=fixed_now)
    assert dt1 is not None
    assert dt1.hour == 0
    assert dt1.minute == 0
    assert dt1.second == 0

    dt2 = parse_relative_time("kal aadhi raat deploy", base_dt=fixed_now)
    assert dt2 is not None
    assert dt2.hour == 0
    assert dt2.minute == 0
    assert dt2.second == 0


def test_agle_hafte_named_weekday_precedence(fixed_now):
    # Base is Wednesday 2026-10-28.
    # "agle hafte mangal" -> Next week's Tuesday = 2026-11-03 (not generic +7 days Wednesday)
    dt_tue = parse_relative_time("agle hafte mangal 11 baje client call", base_dt=fixed_now)
    assert dt_tue is not None
    assert dt_tue.weekday() == 1  # Tuesday
    assert (dt_tue.date() - fixed_now.date()).days == 6

    # "agle hafte jumma" -> Next week's Friday = 2026-11-06
    dt_fri = parse_relative_time("agle hafte jumma shaam 5 baje", base_dt=fixed_now)
    assert dt_fri is not None
    assert dt_fri.weekday() == 4  # Friday
    assert dt_fri.hour == 17


def test_compound_and_fractional_urdu_durations(fixed_now):
    # "1 ghanta 30 minute baad" -> +90 min (11:30 PKT)
    dt_comp = parse_relative_time("1 ghanta 30 minute baad reminder", base_dt=fixed_now)
    assert dt_comp is not None
    assert dt_comp == fixed_now + timedelta(minutes=90)

    # "derh ghanta baad" -> +90 min (11:30 PKT)
    dt_derh = parse_relative_time("derh ghanta baad call client", base_dt=fixed_now)
    assert dt_derh is not None
    assert dt_derh == fixed_now + timedelta(minutes=90)

    # "dhai ghante baad" -> +150 min (12:30 PKT)
    dt_dhai = parse_relative_time("dhai ghante baad lunch break", base_dt=fixed_now)
    assert dt_dhai is not None
    assert dt_dhai == fixed_now + timedelta(minutes=150)


def test_isha_and_maghrib_pm_hints(fixed_now):
    # "isha 9 baje" -> 21:00:00
    dt_isha = parse_relative_time("aaj isha 9 baje study session", base_dt=fixed_now)
    assert dt_isha is not None
    assert dt_isha.hour == 21
    assert dt_isha.minute == 0
    assert dt_isha.second == 0

    # "maghrib 7 baje" -> 19:00:00
    dt_maghrib = parse_relative_time("kal maghrib 7 baje gym", base_dt=fixed_now)
    assert dt_maghrib is not None
    assert dt_maghrib.hour == 19
    assert dt_maghrib.minute == 0
