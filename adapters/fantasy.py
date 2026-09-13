"""Fantasy layer — Sleeper primary (free, no auth), ESPN secondary.

The real Sleeper flow (username -> user id -> leagues -> rosters + matchups ->
live scoring) is implemented here, but the leagues do not exist yet (season is
far off) and no usernames are configured, so the endpoints fall back to sample
data. Set SLEEPER_USERNAME_ALEX / SLEEPER_USERNAME_NOLAN (config, not secret)
and the rail switches to live automatically.

Shapes returned:
  rail  -> { people:[ { person, leagues:[ { league, week, me:{name,points,
            starters:[{name,pos,points}]}, opp:{name,points} } ] } ], demo }
  wire  -> { items:[ { kind:'inj'|'td'|'score', text, player, source } ], demo }
"""

from __future__ import annotations

import os
import threading
import time
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


# Player metadata is a big (~5MB) map. It used to be cached for the life of
# the process, which on the Pi means weeks: injury tags on the fantasy wire
# stayed frozen at whatever they were when the service last restarted (a
# player marked OUT at 2am was still OUT after scoring twice). Refresh every
# few hours; it is a heavy payload that Sleeper asks clients not to poll.
_PLAYERS_TTL = 3 * 3600
_players_cache: dict = {"data": None, "at": 0.0}


def get_players() -> dict:
    now = time.monotonic()
    if _players_cache["data"] is None or now - _players_cache["at"] > _PLAYERS_TTL:
        try:
            _players_cache["data"] = _get(f"{SLEEPER}/players/nfl") or {}
            _players_cache["at"] = now
        except requests.RequestException:
            # keep serving the last good copy and retry in ten minutes
            if _players_cache["data"] is None:
                _players_cache["data"] = {}
            _players_cache["at"] = now - _PLAYERS_TTL + 600
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
                "id": pid,
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
        "Nolan": os.getenv("SLEEPER_USERNAME_NOLAN"),
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
                # _build_person_rail labels by Sleeper display name ("AlexGraz360"),
                # but the ESPN merge below looks for the config key ("Alex"). Keep
                # the handle for reference and label by the key, or ESPN leagues get
                # attached to a separate person and you appear on the board twice.
                rail["handle"] = rail.get("person")
                rail["person"] = _person
                rail["season"] = str(season)
                rail["current"] = season == cur_season
                used_seasons.add(str(season))
                people.append(rail)
                break

    # ESPN leagues (secondary): merged into Alex's entry, or added if absent.
    espn_cookies = _espn_cookies()
    if espn_cookies and _espn_league_ids():
        espn_person = _build_espn_person(espn_cookies, [cur_season, cur_season - 1])
        if espn_person:
            alex = next((p for p in people if p["person"] == "Alex"), None)
            if alex:
                alex["leagues"].extend(espn_person["leagues"])
            else:
                people.append(espn_person)

    # Drop leagues with no roster. A Sleeper account accumulates leagues that
    # were created but never drafted; they carry no starters and no score, so
    # rotating the rail through them just shows empty panels.
    for person in people:
        drafted = [lg for lg in person.get("leagues", [])
                   if (lg.get("me") or {}).get("starters")]
        if drafted:
            person["leagues"] = drafted
    people = [p for p in people if p.get("leagues")]

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


# Canonical fantasy lineup order: QB, RB, WR, TE, FLEX, D/ST, K. ESPN returns
# roster entries in acquisition order, so without this the lineup reads as a
# jumble (QB showing up eighth). Sleeper already comes back in slot order.
ESPN_POS_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3,
                  "FLEX": 4, "RB/WR": 4, "WR/TE": 4, "OP": 4,
                  "D/ST": 6, "K": 7}


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
    # Stable sort, so multiple RBs/WRs keep ESPN's own ordering within a slot.
    # Anything unrecognised sorts between FLEX and D/ST rather than vanishing.
    out.sort(key=lambda p: ESPN_POS_ORDER.get(p["pos"], 5))
    return out


def _espn_current_week(league: dict) -> int:
    status = league.get("status") or {}
    return int(status.get("currentMatchupPeriod") or 1) or 1


def _build_espn_league(lid: str, year: int, cookies: dict) -> dict | None:
    """One ESPN league for one season, mapped to the rail shape, or None."""
    league = _fetch_espn_league(lid, year, cookies)
    if not league:
        return None
    me = _espn_my_team(league, cookies["SWID"])
    if not me:
        return None
    week = _espn_current_week(league)
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
    my_starters = _espn_starters(me)
    opp_starters = _espn_starters(opp_team) if opp_team else []

    # ESPN's matchup totalPoints stays 0 until the week is finalised, so a live
    # Sunday showed every starter scoring while the team total read 0. Fall back
    # to the sum of the starters, which is what the players are actually worth
    # right now. A real reported total still wins once ESPN fills it in.
    def _total(reported, starters):
        reported = float(reported or 0)
        return reported if reported else round(sum(p.get("points", 0) or 0 for p in starters), 1)

    return {
        "league": (league.get("settings") or {}).get("name", "ESPN League"),
        "week": week, "platform": "espn", "season": str(year),
        "me": {"name": _espn_team_name(me), "points": round(_total(my_pts, my_starters), 1),
               "starters": my_starters},
        "opp": {"name": _espn_team_name(opp_team) if opp_team else "Opponent",
                "points": round(_total(opp_pts, opp_starters), 1)},
    }


def _build_espn_person(cookies: dict, seasons: list[int]) -> dict | None:
    """Each league tries the seasons in order and keeps the first that has a
    filled roster (so a pre-draft current season falls back to last year's real
    lineup, matching the Sleeper behavior)."""
    leagues_out = []
    for lid in _espn_league_ids():
        best = None
        for year in seasons:
            entry = _build_espn_league(lid, year, cookies)
            if not entry:
                continue
            best = best or entry  # remember the first that at least resolves
            if entry["me"]["starters"]:
                best = entry
                break
        if best:
            best["current"] = best["season"] == str(seasons[0])
            leagues_out.append(best)
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


# ---------------- live wire ----------------

_CACHE_TTL = 60          # seconds; the board polls rail and wire together
_FRESH_SECONDS = 300     # a touchdown counts as "just scored" for five minutes
_DOT, _DASH = chr(183), chr(8212)

_rail_lock = threading.Lock()
_rail_cache: dict = {"at": 0.0, "data": None}
_stats_cache: dict = {"at": 0.0, "key": None, "data": {}}
_name_index_cache: dict = {"src": None, "index": {}}
_td_state: dict = {"primed": False, "seen": {}}

_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_SLOT_POSITIONS = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}}
_FLEX_POSITIONS = {"RB", "WR", "TE", "QB"}
_INJURY_LABEL = {"Out": "OUT", "IR": "IR", "Sus": "SUS", "PUP": "PUP",
                 "Doubtful": "D", "Questionable": "Q"}
_INJURY_RANK = {"OUT": 0, "IR": 0, "SUS": 1, "PUP": 1, "D": 1, "Q": 2}


def cached_rail() -> dict:
    """build_fantasy_rail with a short TTL.

    The board requests /rail and /wire in parallel, and the wire is built from
    the rail, so without this every poll paid for the Sleeper and ESPN league
    fetches twice.
    """
    with _rail_lock:
        now = time.monotonic()
        if _rail_cache["data"] is not None and now - _rail_cache["at"] < _CACHE_TTL:
            return _rail_cache["data"]
        data = build_fantasy_rail()
        _rail_cache.update(at=now, data=data)
        return data


def get_week_stats(season, week) -> dict:
    """Sleeper's cumulative per-player stats for the week: player_id -> stats."""
    key = (str(season), int(week))
    now = time.monotonic()
    if _stats_cache["key"] == key and now - _stats_cache["at"] < _CACHE_TTL:
        return _stats_cache["data"]
    try:
        data = _get(f"{SLEEPER}/stats/nfl/regular/{key[0]}/{key[1]}") or {}
    except requests.RequestException:
        return _stats_cache["data"] if _stats_cache["key"] == key else {}
    _stats_cache.update(at=now, key=key, data=data)
    return data


def _norm_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == " " else " " for ch in (name or "").lower())
    return " ".join(t for t in cleaned.split() if t not in _NAME_SUFFIXES)


def _name_index(players: dict) -> dict:
    if _name_index_cache["src"] is players:
        return _name_index_cache["index"]
    index: dict = {}
    for pid, meta in (players or {}).items():
        if isinstance(meta, dict) and meta.get("full_name"):
            index.setdefault(_norm_name(meta["full_name"]), []).append(pid)
    _name_index_cache.update(src=players, index=index)
    return index


def _match_player_id(name: str, slot: str, players: dict, index: dict) -> str | None:
    """ESPN starters arrive by name only; resolve them to a Sleeper id for stats
    and injury status. Duplicate names are settled by the lineup slot's
    position, then by who is actually on an NFL roster."""
    candidates = index.get(_norm_name(name)) or []
    if not candidates:
        return None
    allowed = _SLOT_POSITIONS.get(slot, _FLEX_POSITIONS)

    def rank(pid):
        meta = players.get(pid) or {}
        return (meta.get("position") not in allowed, not meta.get("team"), not meta.get("active"))

    return min(candidates, key=rank)


def _owners_label(owners: list) -> str:
    by_person: dict = {}
    for person, league in owners:
        leagues = by_person.setdefault(person, [])
        if league not in leagues:
            leagues.append(league)
    parts = []
    for person, leagues in by_person.items():
        where = leagues[0] if len(leagues) == 1 else f"{len(leagues)} leagues"
        parts.append(f"{person.upper()} {_DOT} {where}")
    return " / ".join(parts)


def _td_freshness(ids: list, now: float) -> dict:
    """When the server first saw each touchdown.

    The first stats snapshot after a restart is backfill - scores from before we
    were watching - so it is recorded as not fresh. Otherwise every restart or
    deploy would replay the whole day's touchdowns on the TV.
    """
    seen = _td_state["seen"]
    for i in ids:
        seen.setdefault(i, now if _td_state["primed"] else None)
    _td_state["primed"] = True
    return {i: seen[i] is not None and now - seen[i] < _FRESH_SECONDS for i in ids}


def build_fantasy_wire() -> dict:
    """Live wire for everyone's starters: touchdowns, injuries, top scorers.

    Built from the rail the board already shows, plus Sleeper's weekly stats
    (touchdowns) and player map (injury status). Only starters count: a benched
    player's touchdown is not news for your matchup.
    """
    rail = cached_rail()
    if rail.get("demo"):
        return _sample_wire()
    season, week = rail.get("season"), rail.get("week") or 1
    players = get_players()
    index = _name_index(players)
    stats = get_week_stats(season, week)

    roster: dict = {}
    leaders: dict = {}
    for person in rail.get("people", []):
        who = person.get("person", "")
        for lg in person.get("leagues", []):
            league_name = lg.get("league", "")
            for s in (lg.get("me") or {}).get("starters") or []:
                slot = s.get("pos", "")
                if slot in ("D/ST", "DEF"):
                    continue
                pid = s.get("id") or _match_player_id(s.get("name", ""), slot, players, index)
                if not pid:
                    continue
                entry = roster.setdefault(pid, {"name": s.get("name", ""), "slot": slot, "owners": []})
                entry["owners"].append((who, league_name))
                pts = float(s.get("points") or 0)
                best = leaders.get(who)
                if pts > 0 and (best is None or pts > best["points"]):
                    leaders[who] = {"name": s.get("name", ""), "points": pts, "league": league_name}

    td_items = []
    for pid, e in roster.items():
        st = stats.get(pid) or {}
        for stat, kind, label in (("pass_td", "passing", "pass"),
                                  ("rush_td", "rushing", "rush"),
                                  ("rec_td", "receiving", "rec")):
            n = int(float(st.get(stat) or 0))
            if n < 1:
                continue
            td_items.append({
                "kind": "td", "id": f"{season}:{week}:{pid}:{stat}:{n}", "tdType": kind,
                "player": e["name"], "count": n,
                "text": f"TD: {e['name']} {_DASH} {n} {label} TD{'s' if n > 1 else ''} "
                        f"({_owners_label(e['owners'])})",
            })
    # Only judge freshness once real stats exist; otherwise an empty pre-game
    # snapshot becomes the baseline and the first real scores all look new at once.
    fresh = _td_freshness([t["id"] for t in td_items], time.monotonic()) if stats else {}
    for t in td_items:
        t["fresh"] = bool(fresh.get(t["id"]))

    inj_items = []
    for pid, e in roster.items():
        label = _INJURY_LABEL.get((players.get(pid) or {}).get("injury_status") or "")
        if label:
            inj_items.append({"kind": "inj", "player": e["name"], "rank": _INJURY_RANK[label],
                              "text": f"{label}: {e['name']} {_DASH} {_owners_label(e['owners'])} {e['slot']}"})

    score_items = [{"kind": "score", "player": v["name"],
                    "text": f"{v['name']} leads {who.upper()} with {v['points']:.1f} pts ({v['league']})"}
                   for who, v in leaders.items()]

    td_items.sort(key=lambda t: -t["count"])
    inj_items.sort(key=lambda i: i["rank"])
    # The panel shows about six rows, so order by what matters for your matchup
    # right now: just-scored touchdowns, injuries that cost you a starter, each
    # person's top scorer, then the rest of the day's touchdowns, then
    # questionable tags. Leaders used to sit behind every touchdown and never
    # made the cut on a busy Sunday.
    items = ([t for t in td_items if t["fresh"]]
             + [i for i in inj_items if i["rank"] < 2]
             + score_items
             + [t for t in td_items if not t["fresh"]]
             + [i for i in inj_items if i["rank"] >= 2])
    for i in items:
        i.pop("rank", None)
    return {"source": "Sleeper+ESPN", "demo": False, "season": season, "week": week,
            "items": items[:8]}


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
                 "opp": {"name": "Nolan", "points": 88.1}}]},
            {"person": "Nolan", "leagues": [
                {"league": "Hurst 11 Dynasty", "week": 1,
                 "me": {"name": "Nolan", "points": 88.1, "starters": [
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
            {"kind": "score", "text": "Saquon Barkley now 20.8 pts, leads NOLAN's flex",
             "player": "Saquon Barkley", "source": "scoring"},
            {"kind": "inj", "text": "OUT: De'Von Achane (knee) — NOLAN flex",
             "player": "De'Von Achane", "source": "injury"},
        ],
    }
