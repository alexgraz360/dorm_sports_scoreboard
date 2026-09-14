import sys
sys.path.insert(0, ".")
from datetime import datetime
from adapters import weekday as W

E = W.EASTERN
CRLF = chr(13) + chr(10)
TZ = "DTSTART;TZID=America/New_York:"


def cal(*events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for ev in events:
        lines += ["BEGIN:VEVENT"] + list(ev) + ["END:VEVENT"]
    lines.append("END:VCALENDAR")
    return CRLF.join(lines) + CRLF


def day(text, y, m, d):
    now = datetime(y, m, d, 6, 0, tzinfo=E)
    return [(e["time"], e["title"]) for e in W._parse_ical_today(text, now)]


ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(("  PASS " if good else "  FAIL ") + label + ": " + repr(got))


# 1. single occurrence moved to a new time (Gym, Fri Sep 11: 5:00p -> 7:30a)
gym = cal(
    ["UID:gym-fri", TZ + "20260904T170000", "DTEND;TZID=America/New_York:20260904T180000",
     "RRULE:FREQ=WEEKLY;UNTIL=20261218T045959Z;BYDAY=FR", "SUMMARY:Gym"],
    ["UID:gym-fri", "RECURRENCE-ID;TZID=America/New_York:20260911T170000",
     TZ + "20260911T073000", "DTEND;TZID=America/New_York:20260911T083000", "SUMMARY:Gym"])
check("moved occurrence shows once, at the new time", day(gym, 2026, 9, 11), [("7:30a", "Gym")])
check("other weeks keep the series time", day(gym, 2026, 9, 18), [("5:00p", "Gym")])

# 2. single occurrence edited without moving (Work, Mon Sep 7 stays 9:00a)
work = cal(
    ["UID:work-mon", TZ + "20260831T090000", "RRULE:FREQ=WEEKLY;BYDAY=MO", "SUMMARY:Work"],
    ["UID:work-mon", "RECURRENCE-ID;TZID=America/New_York:20260907T090000",
     TZ + "20260907T090000", "SUMMARY:Work"])
check("edited-in-place occurrence shows once", day(work, 2026, 9, 7), [("9:00a", "Work")])

# 3. 'this and following' split (Dinner: 6:30p series ends, 5:00p series starts Sep 14)
dinner = cal(
    ["UID:dinner-old", TZ + "20260907T183000",
     "RRULE:FREQ=WEEKLY;UNTIL=20260914T035959Z;BYDAY=MO", "SUMMARY:Dinner"],
    ["UID:dinner-new", TZ + "20260914T170000",
     "RRULE:FREQ=WEEKLY;UNTIL=20261214T045959Z;BYDAY=MO", "SUMMARY:Dinner"])
check("split series: old time before the split", day(dinner, 2026, 9, 7), [("6:30p", "Dinner")])
check("split series: only the new time after", day(dinner, 2026, 9, 14), [("5:00p", "Dinner")])

# 4. single occurrence cancelled
cancelled = cal(
    ["UID:lunch-wed", TZ + "20260902T120000", "RRULE:FREQ=WEEKLY;BYDAY=WE", "SUMMARY:Lunch"],
    ["UID:lunch-wed", "RECURRENCE-ID;TZID=America/New_York:20260916T120000", "STATUS:CANCELLED",
     TZ + "20260916T120000", "SUMMARY:Lunch"])
check("cancelled occurrence disappears", day(cancelled, 2026, 9, 16), [])
check("cancellation only affects that day", day(cancelled, 2026, 9, 23), [("12:00p", "Lunch")])

# guards that must keep working
daily = cal(["UID:camp", TZ + "20260915T080000", "RRULE:FREQ=DAILY;UNTIL=20260920", "SUMMARY:Camp"])
check("date-only UNTIL is inclusive", day(daily, 2026, 9, 20), [("8:00a", "Camp")])
check("date-only UNTIL stops after", day(daily, 2026, 9, 21), [])
counted = cal(["UID:series", TZ + "20260914T190000", "RRULE:FREQ=WEEKLY;COUNT=2;BYDAY=MO", "SUMMARY:Class"])
check("COUNT: second occurrence", day(counted, 2026, 9, 21), [("7:00p", "Class")])
check("COUNT: no third", day(counted, 2026, 9, 28), [])
late = cal(["UID:late", TZ + "20260914T223000",
            "RRULE:FREQ=WEEKLY;UNTIL=20260922T035959Z;BYDAY=MO", "SUMMARY:Late"])
check("late-evening series: last occurrence before a UTC UNTIL still shows", day(late, 2026, 9, 21), [("10:30p", "Late")])

print("  ALL PASS" if ok else "  SOME FAIL")
sys.exit(0 if ok else 1)
