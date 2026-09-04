"""Torey J. Sabatini Elementary (Madison NJ) calendar -> Glenwild traffic advice.

Why this exists: the back entrance to campus runs past TJS on Glenwild, and
arrival/dismissal traffic makes that route a bad idea for a ~30 minute window.
Normal dismissal (3:15pm) rarely clashes with a midday drive back, but EARLY
DISMISSAL days let out at 12:45pm - right when you'd typically be heading back -
and that is the case that actually catches you out.

Source of truth is the district's published PDF calendar:
  https://www.madisonpublicschools.org/page/annual-school-calendars
  -> "2026-2027" (School-Calendar_2026-27_REVISED-06.16.26.pdf)

The dates below were parsed from that PDF. They are stored rather than fetched
because the calendar changes about once a year, a 7am board should not depend on
a district web server being up, and scraping a PDF layout live would fail
silently. Re-check each August; CALENDAR_SOURCE_REVISION tracks which revision
these dates came from.

NOT encoded (deliberately - they are conditional):
  * 3 emergency closure make-up days, used only if snow days happen
    (they would be added back as school days: Apr 16, then 15, then 14)
  * "give back" days if emergencies go unused (Mar 29, Jun 1, May 28)
Both only matter late in the year, and the district announces them.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

CALENDAR_SOURCE_REVISION = "2026-27, revised 6/16/26"
SCHOOL_NAME = "Torey J. Sabatini"
SCHOOL_YEAR_START = date(2026, 9, 2)
SCHOOL_YEAR_END = date(2027, 6, 17)

# Elementary bell times (the PDF lists junior/high separately; TJS is elementary)
NORMAL_ARRIVAL, NORMAL_DISMISSAL = time(8, 30), time(15, 15)
EARLY_DISMISSAL = time(12, 45)
DELAYED_ARRIVAL = time(10, 30)

# How long Glenwild is worth avoiding either side of a bell.
TRAFFIC_WINDOW_MIN = 30


def _days(start: date, end: date) -> set[date]:
    out, cur = set(), start
    while cur <= end:
        out.add(cur)
        cur += timedelta(days=1)
    return out


# District closed - no school traffic at all.
CLOSED: set[date] = (
    _days(date(2026, 9, 4), date(2026, 9, 7))      # Labor Day
    | {date(2026, 9, 21)}                          # Yom Kippur
    | _days(date(2026, 11, 5), date(2026, 11, 6))  # NJEA Convention
    | _days(date(2026, 11, 26), date(2026, 11, 27))  # Thanksgiving
    | _days(date(2026, 12, 24), date(2027, 1, 1))  # Winter Recess
    | {date(2027, 1, 18)}                          # MLK Day
    | {date(2027, 2, 15)}                          # Presidents' Day
    | {date(2027, 3, 10)}                          # Eid
    | {date(2027, 3, 26)}                          # Good Friday
    | _days(date(2027, 4, 12), date(2027, 4, 16))  # Spring Recess
    | {date(2027, 5, 31)}                          # Memorial Day
)

# Early dismissal - out at 12:45pm instead of 3:15pm. These are the dangerous
# ones for a midday drive back.
EARLY: dict[date, str] = {
    date(2026, 9, 2): "First day - early dismissal",
    date(2026, 9, 3): "Early dismissal: staff PD",
    date(2026, 10, 12): "Early dismissal: staff PD",
    date(2026, 11, 2): "Early dismissal: conferences",
    date(2026, 11, 3): "Early dismissal: conferences",
    date(2026, 11, 4): "Early dismissal: conferences",
    date(2026, 11, 25): "Early dismissal: Thanksgiving eve",
    date(2026, 12, 23): "Early dismissal: winter recess eve",
    date(2027, 1, 15): "Early dismissal: staff PD",
    date(2027, 2, 12): "Early dismissal: staff PD",
    date(2027, 3, 22): "Early dismissal: conferences",
    date(2027, 3, 23): "Early dismissal: conferences",
    date(2027, 3, 24): "Early dismissal: conferences",
    date(2027, 5, 28): "Early dismissal: staff PD",
    date(2027, 6, 17): "Last day - early dismissal",
}

# Delayed opening - in at 10:30am, normal 3:15pm dismissal.
DELAYED: dict[date, str] = {
    date(2027, 3, 11): "Delayed opening: staff PD",
}


def school_day(day: date | None = None) -> dict:
    """What kind of school day is this, and when are the bells?

    Returns status one of: closed | normal | early | delayed, plus arrival and
    dismissal times (None when closed) and a short human note.
    """
    day = day or datetime.now(EASTERN).date()

    if day < SCHOOL_YEAR_START or day > SCHOOL_YEAR_END:
        return {"status": "closed", "arrival": None, "dismissal": None,
                "note": "Summer break", "inSession": False}
    if day.weekday() >= 5:
        return {"status": "closed", "arrival": None, "dismissal": None,
                "note": "Weekend", "inSession": False}
    if day in CLOSED:
        return {"status": "closed", "arrival": None, "dismissal": None,
                "note": "School closed", "inSession": False}
    if day in EARLY:
        return {"status": "early", "arrival": NORMAL_ARRIVAL,
                "dismissal": EARLY_DISMISSAL, "note": EARLY[day], "inSession": True}
    if day in DELAYED:
        return {"status": "delayed", "arrival": DELAYED_ARRIVAL,
                "dismissal": NORMAL_DISMISSAL, "note": DELAYED[day], "inSession": True}
    return {"status": "normal", "arrival": NORMAL_ARRIVAL,
            "dismissal": NORMAL_DISMISSAL, "note": "Regular schedule", "inSession": True}


def _fmt(t: time | None) -> str:
    if not t:
        return ""
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'a' if t.hour < 12 else 'p'}"


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def traffic_windows(day: date | None = None) -> list[tuple[int, int, str]]:
    """Minute-of-day ranges where Glenwild is worth avoiding, with a label."""
    info = school_day(day)
    if not info["inSession"]:
        return []
    w = TRAFFIC_WINDOW_MIN
    out = []
    if info["arrival"]:
        a = _minutes(info["arrival"])
        out.append((a - w, a + w, "drop-off"))
    if info["dismissal"]:
        d = _minutes(info["dismissal"])
        out.append((d - w, d + w, "dismissal"))
    return out
