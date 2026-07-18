"""Fantasy layer — Sleeper primary (free, no auth), ESPN secondary.

The real Sleeper flow (username -> user id -> leagues -> rosters + matchups ->
live scoring) is implemented here, but the leagues do not exist yet (season is
far off) and no usernames are configured, so the endpoints fall back to sample
data. Set SLEEPER_USERNAME_ALEX / SLEEPER_USERNAME_JORDAN (config, not secret)
and the rail switches to live automatically.

Shapes returned:
  rail  -> { people:[ { person, leagues:[ { league, week, me:{name,points,
            starters:[{name,pos,points}]}, opp:{name,points} } ] } ], demo }
  wire  -> { items:[ { kind:'inj'|'td'|'score', text, player, source } ], demo }
"""

from __future__ import annotations

import os
from datetime import datetime

import requests

from .espn import EASTERN

SLEEPER = "https://api.sleeper.app/v1"
TIMEOUT = 8
UA = {"User-Agent": "DormWire/1.0 (+fantasy)"}

# Default starting lineup if a league's roster settings can't be read.
DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "D/ST", "K"]


# ---------------- low-level Sleeper calls (no auth) ----------------

def _get(url: str):
    r = requests.get(url, timeout=TIMEOUT, headers=UA)
    r.raise_for_status()
    return r.json()


def get_user(username: str) -> dict | None:
    try:
        return _get(f"{SLEEPER}/user/{username}")
    except requests.RequestException:
        return None


def get_leagues(user_id: str, season: str) -> list:
    try:
        return _get(f"{SLEEPER}/user/{user_id}/leagues/nfl/{season}") or []
    except requests.RequestException:
        return []


def get_rosters(league_id: str) -> list:
    try:
        return _get(f"{SLEEPER}/league/{league_id}/rosters") or []
    except requests.RequestException:
        return []


def get_matchups(league_id: str, week: int) -> list:
    try:
        return _get(f"{SLEEPER}/league/{league_id}/matchups/{week}") or []
    except requests.RequestException:
        return []


def get_league_users(league_id: str) -> list:
    try:
        return _get(f"{SLEEPER}/league/{league_id}/users") or []
    except requests.RequestException:
        return []


def get_nfl_state() -> dict:
    try:
        return _get(f"{SLEEPER}/state/nfl") or {}
    except requests.RequestException:
        return {}


# Player metadata is a big (~5MB) map; cache it in-process for the session.
_players_cache: dict = {"data": None}


def get_players() -> dict:
    if _players_cache["data"] is None:
        try:
            _players_cache["data"] = _get(f"{SLEEPER}/players/nfl") or {}
        except requests.RequestException:
            _players_cache["data"] = {}
    return _players_cache["data"]


# ---------------- assembly ----------------

def _slot_positions(league: dict) -> list:
    slots = [p for p in (league.get("roster_positions") or []) if p != "BN"]
    return slots or DEFAULT_SLOTS


def _build_person_rail(username: str, season: str, week: int) -> dict | None:
    user = get_user(username)
    if not user or not user.get("user_id"):
        return None
    uid = user["user_id"]
    players = get_players()
    out_leagues = []
    for league in get_leagues(uid, season):
        lid = league.get("league_id")
        if not lid:
            continue
        rosters = get_rosters(lid)
        mine = next((r for r in rosters if r.get("owner_id") == uid), None)
        if not mine:
            continue
        matchups = get_matchups(lid, week)
        my_mu = next((m for m in matchups if m.get("roster_id") == mine.get("roster_id")), None)
        opp_mu = None
        if my_mu and my_mu.get("matchup_id") is not None:
            opp_mu = next((m for m in matchups
                           if m.get("matchup_id") == my_mu["matchup_id"]
                           and m.get("roster_id") != mine.get("roster_id")), None)
        users = {u["user_id"]: u for u in get_league_users(lid)}
        slots = _slot_positions(league)
        starters = []
        pts = (my_mu or {}).get("players_points", {}) or {}
        for i, pid in enumerate((my_mu or {}).get("starters", []) or []):
            meta = players.get(pid, {}) if isinstance(players, dict) else {}
            starters.append({
                "name": meta.get("full_name") or meta.get("last_name") or pid,
                "pos": slots[i] if i < len(slots) else meta.get("position", ""),
                "points": round(float(pts.get(pid, 0) or 0), 1),
            })
        opp_owner = next((r.get("owner_id") for r in rosters
                          if r.get("roster_id") == (opp_mu or {}).get("roster_id")), None)
        out_leagues.append({
            "league": league.get("name", "League"),
            "week": week,
            "me": {
                "name": user.get("display_name", username),
                "points": round(float((my_mu or {}).get("points", 0) or 0), 1),
                "starters": starters,
            },
            "opp": {
                "name": (users.get(opp_owner, {}) or {}).get("display_name", "Opponent"),
                "points": round(float((opp_mu or {}).get("points", 0) or 0), 1),
            },
        })
    if not out_leagues:
        return None
    return {"person": user.get("display_name", username), "leagues": out_leagues}


def build_fantasy_rail() -> dict:
    """Live rail from Sleeper if usernames are configured, else sample data.

    Tries the current NFL season first; if a person has no league yet (e.g. the
    new season hasn't been renewed/drafted), it falls back to the most recent
    prior season so a real league still shows. It auto-upgrades to the current
    season the moment that league exists.
    """
    people_cfg = {
        "Alex": os.getenv("SLEEPER_USERNAME_ALEX"),
        "Jordan": os.getenv("SLEEPER_USERNAME_JORDAN"),
    }
    state = get_nfl_state()
    cur_season = int(state.get("season") or datetime.now(EASTERN).year)
    week = int(state.get("week") or 1) or 1
    candidate_seasons = [cur_season, cur_season - 1, cur_season - 2]

    people = []
    used_seasons: set[str] = set()
    for _person, username in people_cfg.items():
        if not username:
            continue
        for season in candidate_seasons:
            rail = _build_person_rail(username, str(season), week)
            if rail:
                rail["season"] = str(season)
                rail["current"] = season == cur_season
                used_seasons.add(str(season))
                people.append(rail)
                break

    # ESPN leagues (secondary): merged into Alex's entry, or added if absent.
    espn_cookies = _espn_cookies()
    if espn_cookies and _espn_league_ids():
        for espn_year in (cur_season, cur_season - 1):
            espn_person = _build_espn_person(espn_cookies, espn_year)
            if espn_person:
                alex = next((p for p in people if p["person"] == "Alex"), None)
                if alex:
                    alex["leagues"].extend(espn_person["leagues"])
                else:
                    people.append(espn_person)
                break

    if people:
        return {"source": "Sleeper+ESPN", "season": str(cur_season), "week": week,
                "seasonsShown": sorted(used_seasons), "demo": False, "people": people}
    return _sample_rail()


# ============ ESPN fantasy (secondary; private leagues need cookies) ============

ESPN_FANTASY_BASE = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
                     "/seasons/{year}/segments/0/leagues/{league_id}")
# lineupSlotId -> position label. Bench/IR (20/21) and slot 24 are not starters.
ESPN_SLOTS = {0: "QB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE", 6: "TE",
              7: "OP", 16: "D/ST", 17: "K", 23: "FLEX"}
ESPN_BENCH_SLOTS = {20, 21, 24}


def _espn_cookies() -> dict | None:
    s2, swid = os.getenv("ESPN_S2"), os.getenv("ESPN_SWID")
    if not s2 or not swid:
        return None
    if not swid.startswith("{"):
        swid = "{" + swid.strip("{}") + "}"
    return {"espn_s2": s2, "SWID": swid}


def _espn_league_ids() -> list[str]:
    raw = os.getenv("ESPN_LEAGUE_IDS", "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _fetch_espn_league(league_id: str, year: int, cookies: dict) -> dict | None:
    url = ESPN_FANTASY_BASE.format(year=year, league_id=league_id)
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=UA, cookies=cookies,
                         params=[("view", v) for v in
                                 ("mTeam", "mRoster", "mMatchup", "mSettings")])
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def _espn_my_team(league: dict, swid: str) -> dict | None:
    swid_norm = swid.strip("{}").upper()
    for team in league.get("teams", []) or []:
        owners = [str(o).strip("{}").upper() for o in (team.get("owners") or [])]
        if swid_norm in owners:
            return team
    return None


def _espn_team_name(team: dict) -> str:
    return (team.get("name")
            or f"{team.get('location', '')} {team.get('nickname', '')}".strip()
            or f"Team {team.get('id', '?')}")


def _espn_starters(team: dict) -> list[dict]:
    entries = ((team.get("roster") or {}).get("entries")) or []
    out = []
    for e in entries:
        slot = e.get("lineupSlotId")
        if slot in ESPN_BENCH_SLOTS:
            continue
        player = ((e.get("playerPoolEntry") or {}).get("player")) or {}
        out.append({
            "name": player.get("fullName", "—"),
            "pos": ESPN_SLOTS.get(slot, ""),
            "points": round(float(e.get("playerPoolEntry", {}).get("appliedStatTotal", 0) or 0), 1),
        })
    return out


def _espn_current_week(league: dict) -> int:
    status = league.get("status") or {}
    return int(status.get("currentMatchupPeriod") or 1) or 1


def _build_espn_person(cookies: dict, year: int) -> dict | None:
    swid = cookies["SWID"]
    leagues_out = []
    for lid in _espn_league_ids():
        league = _fetch_espn_league(lid, year, cookies)
        if not league:
            continue
        me = _espn_my_team(league, swid)
        if not me:
            continue
        week = _espn_current_week(league)
        # Find this week's matchup for my team -> opponent.
        opp_team, my_pts, opp_pts = None, 0.0, 0.0
        for g in league.get("schedule", []) or []:
            if g.get("matchupPeriodId") != week:
                continue
            home, away = g.get("home") or {}, g.get("away") or {}
            if home.get("teamId") == me.get("id"):
                my_pts, opp_pts = home.get("totalPoints", 0), away.get("totalPoints", 0)
                opp_team = _espn_team_by_id(league, away.get("teamId"))
                break
            if away.get("teamId") == me.get("id"):
                my_pts, opp_pts = away.get("totalPoints", 0), home.get("totalPoints", 0)
                opp_team = _espn_team_by_id(league, home.get("teamId"))
                break
        leagues_out.append({
            "league": (league.get("settings") or {}).get("name", "ESPN League"),
            "week": week, "platform": "espn",
            "me": {"name": _espn_team_name(me), "points": round(float(my_pts or 0), 1),
                   "starters": _espn_starters(me)},
            "opp": {"name": _espn_team_name(opp_team) if opp_team else "Opponent",
                    "points": round(float(opp_pts or 0), 1)},
        })
    return {"person": "Alex", "leagues": leagues_out, "platform": "espn"} if leagues_out else None


def _espn_team_by_id(league: dict, team_id) -> dict | None:
    for t in league.get("teams", []) or []:
        if t.get("id") == team_id:
            return t
    return None


def detect_touchdowns(prev_stats: dict, curr_stats: dict, rostered: set) -> list:
    """Compare two Sleeper stat snapshots and emit TD events for rostered
    players. `stats` maps player_id -> {pass_td, rush_td, rec_td, ...}. Returns
    [{player_id, kind:'passing'|'rushing'|'receiving', count}]. The animation
    layer fires the matching retro effect off `kind`.
    """
    events = []
    for pid in rostered:
        prev = prev_stats.get(pid, {}) or {}
        curr = curr_stats.get(pid, {}) or {}
        for stat, kind in (("pass_td", "passing"), ("rush_td", "rushing"), ("rec_td", "receiving")):
            gained = float(curr.get(stat, 0) or 0) - float(prev.get(stat, 0) or 0)
            if gained >= 1:
                events.append({"player_id": pid, "kind": kind, "count": int(gained)})
    return events


def build_fantasy_wire() -> dict:
    """Injuries + scoring events for rostered players. Sample until leagues
    exist; the live version diffs Sleeper stat snapshots via detect_touchdowns
    and reads injury_status from the players map."""
    # Live injury pass (works even without leagues once usernames are set is
    # not meaningful, so we ship sample wire until the season is live).
    return _sample_wire()


# ---------------- sample data (until the season / usernames exist) ----------------

def _sample_rail() -> dict:
    return {
        "source": "sample", "season": "2026", "week": 1, "demo": True,
        "people": [
            {"person": "Alex", "leagues": [
                {"league": "Hurst 11 Dynasty", "week": 1,
                 "me": {"name": "Alex", "points": 96.4, "starters": [
                     {"name": "Josh Allen", "pos": "QB", "points": 24.6},
                     {"name": "Bijan Robinson", "pos": "RB", "points": 18.2},
                     {"name": "Breece Hall", "pos": "RB", "points": 11.5},
                     {"name": "CeeDee Lamb", "pos": "WR", "points": 15.1},
                     {"name": "Garrett Wilson", "pos": "WR", "points": 9.0},
                     {"name": "Sam LaPorta", "pos": "TE", "points": 7.4},
                     {"name": "Jahmyr Gibbs", "pos": "FLEX", "points": 6.2},
                     {"name": "DK Metcalf", "pos": "FLEX", "points": 4.4},
                     {"name": "SF DST", "pos": "D/ST", "points": 6.0},
                     {"name": "Harrison Butker", "pos": "K", "points": 8.0}]},
                 "opp": {"name": "Jordan", "points": 88.1}}]},
            {"person": "Jordan", "leagues": [
                {"league": "Hurst 11 Dynasty", "week": 1,
                 "me": {"name": "Jordan", "points": 88.1, "starters": [
                     {"name": "Jalen Hurts", "pos": "QB", "points": 21.3},
                     {"name": "Saquon Barkley", "pos": "RB", "points": 20.8},
                     {"name": "Kyren Williams", "pos": "RB", "points": 9.4},
                     {"name": "Justin Jefferson", "pos": "WR", "points": 16.2},
                     {"name": "Amon-Ra St. Brown", "pos": "WR", "points": 10.1},
                     {"name": "Trey McBride", "pos": "TE", "points": 6.3},
                     {"name": "De'Von Achane", "pos": "FLEX", "points": 2.0},
                     {"name": "Mike Evans", "pos": "FLEX", "points": 1.0},
                     {"name": "DEN DST", "pos": "D/ST", "points": 1.0},
                     {"name": "Jake Bates", "pos": "K", "points": 0.0}]},
                 "opp": {"name": "Alex", "points": 96.4}}]},
        ],
    }


def _sample_wire() -> dict:
    return {
        "source": "sample", "demo": True, "items": [
            {"kind": "td", "text": "TOUCHDOWN: Bijan Robinson 12-yd rush (ALEX starter)",
             "player": "Bijan Robinson", "source": "live"},
            {"kind": "td", "text": "TOUCHDOWN: Josh Allen 4-yd pass to Dalton Kincaid (ALEX)",
             "player": "Josh Allen", "source": "live"},
            {"kind": "inj", "text": "Q: Garrett Wilson questionable to return (ankle) — ALEX WR",
             "player": "Garrett Wilson", "source": "injury"},
            {"kind": "score", "text": "Saquon Barkley now 20.8 pts, leads JORDAN's flex",
             "player": "Saquon Barkley", "source": "scoring"},
            {"kind": "inj", "text": "OUT: De'Von Achane (knee) — JORDAN flex",
             "player": "De'Von Achane", "source": "injury"},
        ],
    }
