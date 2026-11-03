"""College basketball is filtered down to games worth one of the board's tiles.

Division I plays ~180 games a night and the board shows nine tiles for every
sport put together, so the whole slate cannot go in. Only men's college
basketball is filtered; every other league ships whole.

Run from the repo root: python tests/cbb_filter_check.py
No network (ESPN is stubbed). Exits non-zero on any failure.
"""
import sys

sys.path.insert(0, ".")

from adapters import espn  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(("  PASS " if good else "  FAIL ") + label + ": " + repr(got))


def side(abbrev, rank=None):
    team = {"abbreviation": abbrev, "id": "1", "displayName": abbrev}
    out = {"homeAway": "home", "team": team, "score": "0"}
    if rank is not None:
        out["curatedRank"] = {"current": rank}
    return out


def event(away, home, headline=None, away_rank=None, home_rank=None, state="pre"):
    a, h = side(away, away_rank), side(home, home_rank)
    a["homeAway"] = "away"
    comp = {"id": "1", "competitors": [a, h],
            "status": {"type": {"state": state, "description": "Scheduled"}}}
    if headline:
        comp["notes"] = [{"headline": headline}]
    return {"id": f"{away}-{home}", "date": "2026-11-02T23:00Z", "competitions": [comp]}


SLATE = [
    event("MIA", "FLA", headline="Orion180 Tipoff Classic", away_rank=14, home_rank=1),
    event("OAK", "MICH", home_rank=8),                       # one ranked team
    event("ARMY", "DUKE"),                                   # the configured favorite
    event("UAB", "MCN", headline="Field of 68 Opening Day Marathon"),
    event("BALL", "GASO", headline="MAC-SBC Challenge"),
    event("SIE", "MRMK", headline="MAAC Championship - Final"),
    event("PITT", "STAN", headline="T. Rowe Price ACC Tournament - 1st Round"),
    event("UML", "UMBC", headline="America East Playoffs - Semifinal"),
    event("RIDER", "FAIR"),                                  # a Tuesday in November
]


def kept(league, slate):
    real_events, real_today = espn._scoreboard_events, espn._is_today_et
    espn._scoreboard_events = lambda cfg: slate
    espn._is_today_et = lambda when: True
    try:
        return [g["id"] for g in espn.fetch_games(league)]
    finally:
        espn._scoreboard_events, espn._is_today_et = real_events, real_today


# 1. what survives the filter, and what does not
survivors = kept("cbb", SLATE)
check("ranked, favorite and bracket games are kept", sorted(survivors),
      ["ARMY-DUKE", "MIA-FLA", "OAK-MICH", "PITT-STAN", "SIE-MRMK", "UML-UMBC"])
check("a TV package name is not a reason to show a game",
      [g for g in survivors if g in ("UAB-MCN", "BALL-GASO")], [])
check("an unranked, unnamed game is dropped", "RIDER-FAIR" in survivors, False)

# 2. no other league is filtered - the NBA shows every game it has
espn.ESPN_LEAGUES.setdefault("nba", {"path": "basketball/nba", "label": "NBA",
                                     "family": "basketball"})
check("only cbb is filtered", len(kept("nba", SLATE)), len(SLATE))

# 3. a bracket game outranks a plain one of the same shape
blank = {"score": 0, "fav": False, "rank": None}
plain = {"away": dict(blank), "home": dict(blank), "isLive": True, "isFinal": False,
         "detail": "", "event": ""}
bracket = dict(plain, event="MAAC Championship - Final")
plain_focus = espn._focus(plain, "basketball")
bracket_focus = espn._focus(bracket, "basketball")
check("bracket game scores higher", bracket_focus["score"] > plain_focus["score"], True)
check("and says why", "TOURNAMENT" in bracket_focus["reasons"], True)
check("a showcase is not a bracket",
      "TOURNAMENT" in espn._focus(dict(plain, event="Maui Invitational"),
                                  "basketball")["reasons"], False)

# 4. the headline is read off the competition, defensively
comp_note = {"notes": [{"headline": "ACC Tournament - Final"}]}
check("headline from the competition", espn._event_headline({}, comp_note),
      "ACC Tournament - Final")
check("no notes at all", espn._event_headline({}, {}), "")
check("notes present but junk", espn._event_headline({}, {"notes": ["nope"]}), "")

# 5. the board aggregates it
from adapters.config import ALL_SPORTS_LEAGUES  # noqa: E402

check("cbb is on the all-sports board", "cbb" in ALL_SPORTS_LEAGUES, True)

print("  ALL PASS" if ok else "  SOME FAIL")
sys.exit(0 if ok else 1)
