"""ESPN scoreboard fetching: single-date requests, the fallback, the small-hours merge.

ESPN started rejecting date ranges with HTTP 400 on 2026-09-16, which blanked
the whole board. These cases pin the behaviour that replaced it.

Run from the repo root: python tests/espn_scoreboard_check.py
No network (ESPN is stubbed). Exits non-zero on any failure.
"""
import sys
from datetime import datetime

sys.path.insert(0, ".")

import requests  # noqa: E402

from adapters import espn  # noqa: E402

E = espn.EASTERN
ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(("  PASS " if good else "  FAIL ") + label + ": " + repr(got))


class FrozenNow(datetime):
    moment = None

    @classmethod
    def now(cls, tz=None):
        return cls.moment.astimezone(tz) if tz else cls.moment


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


def run(moment, responder):
    """Call _scoreboard_events at a fixed time with ESPN replaced by responder."""
    calls = []
    real_fetch, real_datetime = espn._fetch_json, espn.datetime

    def fake_fetch(url, params=None):
        calls.append(dict(params or {}))
        return responder(params or {})

    FrozenNow.moment = moment
    espn._fetch_json, espn.datetime = fake_fetch, FrozenNow
    try:
        events = espn._scoreboard_events({"path": "baseball/mlb", "params": {}})
    finally:
        espn._fetch_json, espn.datetime = real_fetch, real_datetime
    return [e["id"] for e in events], [c.get("dates") for c in calls]


afternoon = datetime(2026, 9, 16, 16, 4, tzinfo=E)
small_hours = datetime(2026, 9, 16, 1, 15, tzinfo=E)

# 1. normal afternoon: one single-date request for today
ids, dates = run(afternoon, lambda p: {"events": [{"id": "today-game"}]})
check("afternoon asks for today only", dates, ["20260916"])
check("afternoon returns those events", ids, ["today-game"])


# 2. ESPN rejects the dated request: fall back to the undated slate
def rejects_dates(params):
    if params.get("dates"):
        raise http_error(400)
    return {"events": [{"id": "slate-game"}]}


ids, dates = run(afternoon, rejects_dates)
check("rejected date falls back to the undated request", dates, ["20260916", None])
check("fallback events are used", ids, ["slate-game"])


# 3. before 5am: yesterday and today, merged without duplicates
def by_day(params):
    return {"20260915": {"events": [{"id": "late-game"}]},
            "20260916": {"events": [{"id": "late-game"}, {"id": "early-game"}]}}[params["dates"]]


ids, dates = run(small_hours, by_day)
check("small hours fetch yesterday then today", dates, ["20260915", "20260916"])
check("a game on both days appears once", ids, ["late-game", "early-game"])


# 4. a server error is not swallowed by the fallback
def server_down(params):
    raise http_error(503)


try:
    run(afternoon, server_down)
    check("5xx raises", "no exception", "HTTPError")
except requests.HTTPError:
    check("5xx raises", "HTTPError", "HTTPError")

# 5. aggregator: says so when every league failed, stays quiet otherwise
real_fetch_games = espn.fetch_games
try:
    def all_fail(league):
        raise http_error(400)

    espn.fetch_games = all_fail
    down = espn.build_all_today(leagues=("mlb", "nfl"))
    check("every league failing sets error", bool(down.get("error")), True)
    check("every league failing has no games", down["games"], [])

    def one_fails(league):
        if league == "nfl":
            raise http_error(400)
        return []

    espn.fetch_games = one_fails
    check("one league failing leaves error unset", espn.build_all_today(leagues=("mlb", "nfl")).get("error"), None)
finally:
    espn.fetch_games = real_fetch_games

print("  ALL PASS" if ok else "  SOME FAIL")
sys.exit(0 if ok else 1)
