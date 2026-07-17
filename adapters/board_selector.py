"""Mode-switcher: pick which board shows based on the local day and time.

Mechanism A from the build spec. Pure logic (no I/O) so it is easy to test;
the route layer supplies the "is an NFL game on tonight" flag and the current
time. Times are local.

Schedule:
  | Window        | Mon-Fri            | Sat-Sun          |
  | 06:00-16:00   | Weekday dashboard  | Sports board     |
  | 16:00-01:00   | Sports board       | Sports board     |
  | 01:00-06:00   | Display asleep     | Display asleep   |

Sports board choice during sports hours:
  - Sunday in NFL season                    -> NFL
  - Mon/Thu night in NFL season             -> NFL if a game is scheduled, else all-sports
  - Saturday in CFB season                  -> CFB
  - otherwise                               -> all-sports (the default)
"""

from __future__ import annotations

from datetime import datetime

# Board identifiers the rest of the app maps to templates/URLs.
ASLEEP = "asleep"
WEEKDAY = "weekday"
NFL = "nfl"
CFB = "cfb"
ALL = "all"


def is_nfl_season(now: datetime) -> bool:
    """Roughly September through early February."""
    m, d = now.month, now.day
    if m in (9, 10, 11, 12, 1):
        return True
    return m == 2 and d <= 15


def is_cfb_season(now: datetime) -> bool:
    """Roughly late August through early January."""
    m, d = now.month, now.day
    if m in (9, 10, 11, 12):
        return True
    if m == 8 and d >= 24:
        return True
    return m == 1 and d <= 15


def _in_sleep_window(now: datetime) -> bool:
    # 01:00 (inclusive) to 06:00 (exclusive).
    return 1 <= now.hour < 6


def _in_daytime_window(now: datetime) -> bool:
    # 06:00 (inclusive) to 16:00 (exclusive).
    return 6 <= now.hour < 16


def _sports_board(now: datetime, has_nfl_game: bool) -> str:
    weekday = now.weekday()  # Mon=0 .. Sun=6
    if weekday == 6 and is_nfl_season(now):        # Sunday
        return NFL
    if weekday in (0, 3) and is_nfl_season(now):   # Monday / Thursday night
        return NFL if has_nfl_game else ALL
    if weekday == 5 and is_cfb_season(now):        # Saturday
        return CFB
    return ALL


def select_board(now: datetime, has_nfl_game: bool = False) -> str:
    """Return the board id to display for `now`."""
    if _in_sleep_window(now):
        return ASLEEP
    is_weekend = now.weekday() >= 5
    if _in_daytime_window(now) and not is_weekend:
        return WEEKDAY
    return _sports_board(now, has_nfl_game)
