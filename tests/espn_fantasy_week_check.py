"""ESPN fantasy points belong to the current week, not the season so far.

On the Saturday of week 2 the board showed week 2's matchups with week 1's
scores: roster points came from the season-to-date total, and a side whose live
score was a real 0.0 fell back to that stale starter sum. These cases pin the
behaviour that replaced it.

Run from the repo root: python tests/espn_fantasy_week_check.py
No network (every input is a literal). Exits non-zero on any failure.
"""
import sys

sys.path.insert(0, ".")

from adapters import fantasy  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(("  PASS " if good else "  FAIL ") + label + ": " + repr(got))


def player(name, splits, season_total=0.0):
    """An ESPN player whose stats splits are (period, sourceId, splitType, points)."""
    return {"fullName": name,
            "stats": [{"scoringPeriodId": p, "statSourceId": src,
                       "statSplitTypeId": split, "appliedTotal": pts}
                      for p, src, split, pts in splits]
            + [{"scoringPeriodId": 0, "statSourceId": 0, "statSplitTypeId": 0,
                "appliedTotal": season_total}]}


def entry(slot, player_dict, season_total=0.0):
    return {"lineupSlotId": slot,
            "playerPoolEntry": {"appliedStatTotal": season_total, "player": player_dict}}


# 1. the per-week actual is picked out of the splits
herbert = player("Justin Herbert",
                 [(1, 0, 1, 13.26),    # week 1 actual
                  (2, 1, 1, 19.48),    # week 2 projection, not an actual
                  (1, 1, 1, 18.99)],   # week 1 projection
                 season_total=13.26)
check("week 1 actual", fantasy._espn_week_points(herbert, 1), 13.3)
check("a projection is not a score", fantasy._espn_week_points(herbert, 2), 0.0)
check("season total is never the week", fantasy._espn_week_points(herbert, 3), 0.0)
check("no stats at all", fantasy._espn_week_points({}, 2), 0.0)

# 2. starters carry this week's points, bench and IR are left out
team = {"roster": {"entries": [
    entry(0, herbert, season_total=13.26),
    entry(4, player("A.J. Brown", [(2, 0, 1, 35.2)], season_total=63.9)),
    entry(20, player("Benched Guy", [(2, 0, 1, 99.0)], season_total=99.0)),
    entry(21, player("Injured Guy", [(2, 0, 1, 50.0)], season_total=50.0)),
]}}
starters = fantasy._espn_starters(team, 2)
check("bench and IR dropped", [p["name"] for p in starters], ["Justin Herbert", "A.J. Brown"])
check("points are this week's", [p["points"] for p in starters], [0.0, 35.2])
check("the season total is not shown", sum(p["points"] for p in starters), 35.2)

# 3. a live 0.0 is a real score, not missing data
stale = [{"points": 80.0}, {"points": 84.2}]
check("live zero before kickoff", fantasy._espn_side_total({"totalPointsLive": 0.0,
                                                            "totalPoints": 0.0}, stale), 0.0)
check("live score in progress", fantasy._espn_side_total({"totalPointsLive": 35.1,
                                                          "totalPoints": 0.0}, stale), 35.1)
check("finalised week uses totalPoints", fantasy._espn_side_total({"totalPoints": 120.5},
                                                                  stale), 120.5)
check("neither field falls back to the starters", fantasy._espn_side_total({}, stale), 164.2)

# 4. the scoring period ESPN is on
check("scoringPeriodId wins", fantasy._espn_scoring_period(
    {"scoringPeriodId": 2, "status": {"latestScoringPeriod": 1}}), 2)
check("falls back to latestScoringPeriod", fantasy._espn_scoring_period(
    {"status": {"latestScoringPeriod": 5, "currentMatchupPeriod": 4}}), 5)
check("then to the matchup period", fantasy._espn_scoring_period(
    {"status": {"currentMatchupPeriod": 4}}), 4)
check("empty league is week 1", fantasy._espn_scoring_period({}), 1)

print("  ALL PASS" if ok else "  SOME FAIL")
sys.exit(0 if ok else 1)
