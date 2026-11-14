"""Deterministic time parser for mixed Roman-Urdu and English speech with precompiled regexes."""

from datetime import datetime, timedelta, time
import re
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

try:
    import dateparser
    HAS_DATEPARSER = True
except ImportError:
    dateparser = None
    HAS_DATEPARSER = False

DEFAULT_TIMEZONE = ZoneInfo("Asia/Karachi")

URDU_NUMBERS = {
    "ek": 1, "aik": 1, "one": 1,
    "do": 2, "two": 2,
    "teen": 3, "three": 3,
    "char": 4, "chaar": 4, "four": 4,
    "paanch": 5, "panch": 5, "five": 5,
    "chhey": 6, "che": 6, "chhe": 6, "six": 6,
    "saat": 7, "seven": 7,
    "aath": 8, "ath": 8, "eight": 8,
    "nau": 9, "no": 9, "nine": 9,
    "dus": 10, "das": 10, "ten": 10,
    "gyarah": 11, "eleven": 11,
    "barah": 12, "twelve": 12,
}

URDU_WEEKDAYS = {
    "somwar": 0, "peer": 0, "monday": 0,
    "mangal": 1, "tuesday": 1,
    "budh": 2, "wednesday": 2,
    "jumerat": 3, "jumeraat": 3, "thursday": 3,
    "jumma": 4, "juma": 4, "friday": 4,
    "sanichar": 5, "saturday": 5,
    "itwar": 6, "etwar": 6, "sunday": 6,
}

TIME_OF_DAY_DEFAULTS = {
    "subah": (9, 0),      # Morning: 9:00 AM
    "fajar": (6, 0),      # Early morning: 6:00 AM
    "dopahar": (14, 0),   # Afternoon: 2:00 PM
    "sehpahar": (16, 0),  # Late afternoon: 4:00 PM
    "shaam": (18, 0),     # Evening: 6:00 PM
    "maghrib": (18, 30),  # Dusk: 6:30 PM
    "raat": (21, 0),      # Night: 9:00 PM
    "isha": (21, 30),     # Night: 9:30 PM
}

# Precompiled regex patterns for optimal performance
RE_COMPOUND_DURATION = re.compile(
    r'(\d+|[a-zA-Z]+)\s*(?:ghanta|ghante|ghantay|hour|hours|hr|hrs)\s*(?:aur|and)?\s*(\d+|[a-zA-Z]+)\s*(?:minute|minutes|min|mins|m)\s*(?:baad|after|later)?',
    re.I
)
RE_MINUTES = re.compile(r'(\d+)\s*(?:minute|minutes|min|mins|m)\s*(?:baad|after|later)', re.I)
RE_HOURS = re.compile(r'(\d+)\s*(?:ghanta|ghante|ghantay|hour|hours|hr|hrs)\s*(?:baad|after|later)', re.I)
RE_DAYS = re.compile(r'(\d+)\s*(?:din|days|day)\s*(?:baad|after|later)', re.I)
RE_COLON_TIME = re.compile(r'(\d{1,2}):(\d{2})(?:\s*(?:baje|am|pm))?', re.I)
RE_MODIFIER_TIME = re.compile(r'\b(saadhe|sawa|paunay|pone)\s+([a-zA-Z0-9]+)\s*(?:baje)?', re.I)
RE_DIGIT_BAJE = re.compile(r'(\d{1,2})\s*(?:baje|am|pm)', re.I)
RE_FRAC_DURATION = re.compile(r'\b(derh|dedh|dhai|dhaai)\s*(?:ghanta|ghante|ghantay|hour|hours|hr|hrs)(?:\s*(?:baad|after|later))?', re.I)


def parse_relative_time(
    text: str,
    base_dt: Optional[datetime] = None,
    tz: Optional[ZoneInfo] = None
) -> Optional[datetime]:
    """
    Parse Roman-Urdu and English temporal phrases into a timezone-aware datetime.
    """
    res, _ = parse_time_with_analysis(text, base_dt, tz)
    return res


def parse_time_with_analysis(
    text: str,
    base_dt: Optional[datetime] = None,
    tz: Optional[ZoneInfo] = None
) -> Tuple[Optional[datetime], Dict[str, Optional[str]]]:
    """
    Parse time and provide clarification question or recommendation if ambiguous.
    Returns: (parsed_datetime, {"clarification": str, "recommendation": str})
    """
    analysis: Dict[str, Optional[str]] = {"clarification": None, "recommendation": None}
    if not text or not text.strip():
        return None, analysis

    tz = tz or DEFAULT_TIMEZONE
    now = base_dt.astimezone(tz) if base_dt else datetime.now(tz)
    cleaned = text.lower().strip()

    # 1. Quick duration matches
    duration_dt = _parse_durations(cleaned, now)
    if duration_dt:
        return duration_dt, analysis

    # 2. Date offset extraction
    target_date, date_matched = _parse_target_date(cleaned, now)

    # 3. Time of day extraction
    target_time = _parse_target_time(cleaned)

    if date_matched and target_time:
        res_dt = datetime.combine(target_date, target_time, tzinfo=tz)
        analysis["recommendation"] = f"Scheduled for {res_dt.strftime('%A, %b %d at %I:%M %p PKT')}."
        return res_dt, analysis

    if date_matched and not target_time:
        # User specified a day like 'kal' or 'parson' but omitted specific time
        default_t = time(9, 0)
        res_dt = datetime.combine(target_date, default_t, tzinfo=tz)
        analysis["clarification"] = "No specific time was mentioned. Recommended time: 09:00 AM."
        analysis["recommendation"] = f"Defaulting to morning: {res_dt.strftime('%b %d at 09:00 AM PKT')}."
        return res_dt, analysis

    if not date_matched and target_time:
        candidate = datetime.combine(now.date(), target_time, tzinfo=tz)
        if candidate <= now:
            candidate += timedelta(days=1)
        analysis["recommendation"] = f"Scheduled for {candidate.strftime('%A at %I:%M %p PKT')}."
        return candidate, analysis

    # 4. Fallback for standard English expressions
    if HAS_DATEPARSER and dateparser:
        parsed = dateparser.parse(
            cleaned,
            settings={
                "RELATIVE_BASE": now.replace(tzinfo=None),
                "TIMEZONE": str(tz),
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            }
        )
        if parsed:
            dt_aware = parsed.astimezone(tz)
            analysis["recommendation"] = f"Parsed date: {dt_aware.strftime('%b %d at %I:%M %p PKT')}."
            return dt_aware, analysis
    else:
        if "tomorrow" in cleaned:
            dt_base = now + timedelta(days=1)
            t_obj = _parse_target_time(cleaned) or time(9, 0)
            res_dt = datetime.combine(dt_base.date(), t_obj, tzinfo=tz)
            return res_dt, analysis
        if "today" in cleaned:
            t_obj = _parse_target_time(cleaned) or time(9, 0)
            res_dt = datetime.combine(now.date(), t_obj, tzinfo=tz)
            return res_dt, analysis

    return None, analysis


def _parse_durations(text: str, now: datetime) -> Optional[datetime]:
    # 1. Compound duration: e.g., "1 ghanta 30 minute baad", "do ghante 15 minute baad"
    comp_match = RE_COMPOUND_DURATION.search(text)
    if comp_match:
        h_val = _resolve_hour_number(comp_match.group(1))
        m_str = comp_match.group(2)
        m_val = int(m_str) if m_str.isdigit() else URDU_NUMBERS.get(m_str.lower())
        if h_val is not None and m_val is not None:
            return now + timedelta(hours=h_val, minutes=m_val)

    # 2. Fractional Urdu duration: "derh ghanta baad" (+90 min), "dhai ghante baad" (+150 min)
    frac_match = RE_FRAC_DURATION.search(text)
    if frac_match:
        word = frac_match.group(1).lower()
        if word in ("derh", "dedh"):
            return now + timedelta(minutes=90)
        if word in ("dhai", "dhaai"):
            return now + timedelta(minutes=150)

    if "aadha ghanta" in text or "aadhe ghantay" in text or "aadhe ghante" in text or "half an hour" in text:
        return now + timedelta(minutes=30)

    hr_match = RE_HOURS.search(text)
    if hr_match:
        return now + timedelta(hours=int(hr_match.group(1)))

    for word, num in URDU_NUMBERS.items():
        if re.search(rf'\b{word}\s+(?:ghanta|ghante|ghantay)\b', text):
            return now + timedelta(hours=num)

    min_match = RE_MINUTES.search(text)
    if min_match:
        return now + timedelta(minutes=int(min_match.group(1)))

    for word, num in URDU_NUMBERS.items():
        if re.search(rf'\b{word}\s+(?:minute|minutes|min|mins)\s*(?:baad|after|later)\b', text):
            return now + timedelta(minutes=num)

    days_match = RE_DAYS.search(text)
    if days_match:
        return now + timedelta(days=int(days_match.group(1)))

    return None


def _parse_target_date(text: str, now: datetime) -> Tuple[datetime.date, bool]:
    current_date = now.date()

    # Check named weekdays first so "agle hafte <weekday>" resolves to that weekday next week
    for day_name, target_weekday in URDU_WEEKDAYS.items():
        pattern = rf'\b{day_name}\b'
        if re.search(pattern, text):
            days_ahead = target_weekday - current_date.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            if "agle hafte" in text or "aglay hafte" in text or "next week" in text:
                # Named weekday in next week
                days_to_next_monday = 7 - current_date.weekday()
                days_ahead = days_to_next_monday + target_weekday
            elif "agle" in text or "aglay" in text or "next" in text:
                if days_ahead < 7:
                    days_ahead += 7
            return current_date + timedelta(days=days_ahead), True

    if "tarson" in text:
        return current_date + timedelta(days=3), True
    if "parson" in text:
        return current_date + timedelta(days=2), True
    if "kal" in text or "tomorrow" in text:
        return current_date + timedelta(days=1), True
    if "aaj" in text or "today" in text:
        return current_date, True
    if "agle hafte" in text or "aglay hafte" in text or "next week" in text:
        return current_date + timedelta(days=7), True

    return current_date, False


def _parse_target_time(text: str) -> Optional[time]:
    # Check explicit midnight phrases first
    if "aadhi raat" in text or "adhi raat" in text or "midnight" in text:
        return time(0, 0)
    if re.search(r'\b(?:12|barah)\s*baje\s*raat\b', text) or re.search(r'\braat\s*(?:ke\s*)?(?:12|barah)\s*baje\b', text):
        return time(0, 0)

    is_pm_hint = any(w in text for w in [
        "dopahar", "sehpahar", "shaam", "maghrib", "raat", "isha",
        "pm", "afternoon", "evening", "night"
    ])
    is_am_hint = any(w in text for w in ["subah", "fajar", "am", "morning"])

    if ("derh baje" in text or "dedh baje" in text or re.search(r'\b(?:derh|dedh)\b', text)) and not RE_FRAC_DURATION.search(text):
        hour = 13 if is_pm_hint else 1
        return time(hour, 30)
    if ("dhai baje" in text or "dhaai baje" in text or re.search(r'\b(?:dhai|dhaai)\b', text)) and not RE_FRAC_DURATION.search(text):
        hour = 14 if (is_pm_hint or not is_am_hint) else 2
        return time(hour, 30)

    colon_match = RE_COLON_TIME.search(text)
    if colon_match:
        h = int(colon_match.group(1))
        m = int(colon_match.group(2))
        h = _adjust_ampm(h, text, is_pm_hint, is_am_hint)
        return time(h, m)

    modifier_match = RE_MODIFIER_TIME.search(text)
    if modifier_match:
        mod = modifier_match.group(1).lower()
        num_str = modifier_match.group(2)
        base_h = _resolve_hour_number(num_str)
        if base_h is not None:
            m = 0
            if mod == "saadhe":
                m = 30
            elif mod == "sawa":
                m = 15
            elif mod in ("paunay", "pone"):
                m = 45
                base_h = (base_h - 1) if base_h > 1 else 12

            base_h = _adjust_ampm(base_h, text, is_pm_hint, is_am_hint)
            return time(base_h, m)

    digit_baje = RE_DIGIT_BAJE.search(text)
    if digit_baje:
        h = int(digit_baje.group(1))
        h = _adjust_ampm(h, text, is_pm_hint, is_am_hint)
        return time(h, 0)

    for word, val in URDU_NUMBERS.items():
        if re.search(rf'\b{word}\s*baje\b', text):
            h = _adjust_ampm(val, text, is_pm_hint, is_am_hint)
            return time(h, 0)

    for tod, (def_h, def_m) in TIME_OF_DAY_DEFAULTS.items():
        if re.search(rf'\b{tod}\b', text):
            return time(def_h, def_m)

    return None


def _resolve_hour_number(s: str) -> Optional[int]:
    if s.isdigit():
        return int(s)
    return URDU_NUMBERS.get(s.lower())


def _adjust_ampm(hour: int, text: str, is_pm_hint: bool, is_am_hint: bool) -> int:
    if hour > 12:
        return hour
    if "raat" in text and hour == 12:
        return 0
    if "pm" in text and hour < 12:
        return hour + 12
    if "am" in text and hour == 12:
        return 0
    if is_pm_hint and hour < 12:
        return hour + 12
    if is_am_hint and hour == 12:
        return 0
    return hour
