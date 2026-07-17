"""ESPN scoreboard adapter.

ESPN's unofficial scoreboard JSON is free and keyless but undocumented and can
change shape, so every field access here is defensive: a missing key degrades
to a sensible default rather than throwing. The output matches the arcade game
contract (same away/home/status shape the MLB backend emits) plus the
multi-sport extensions: sport, per-team accent/fav/rank, detail, situation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from .config import ESPN_LEAGUES, accent_for, favorite_people, is_favorite

EASTERN = ZoneInfo("America/New_York")
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/news"
REQUEST_TIMEOUT = 8
USER_AGENT = "DormWire/1.0 (+scoreboard)"

_ORDINAL = {1: "1ST", 2: "2ND", 3: "3RD", 4: "4TH"}


def _get(d, *path, default=None):
    """Safe nested getter: _get(obj, 'a', 0, 'b') -> obj['a'][0]['b'] or default."""
    cur = d
    for key in path:
        if isinstance(key, int):
            if isinstance(cur, (list, tuple)) and -len(cur) <= key < len(cur):
                cur = cur[key]
            else:
                return default
        elif isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur if cur is not None else default


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_start_time(iso_date: str) -> str:
    if not iso_date:
        return "TBD"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.astimezone(EASTERN).strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return "TBD"


def _period_label(family: str, period: int) -> str:
    if family == "hockey":
        return _ORDINAL.get(period, "OT" if period and period > 3 else "")
    if family == "basketball":
        if period and period > 4:
            return "OT" if period == 5 else f"{period - 4}OT"
        return f"Q{period}" if period else ""
    # football
    if period and period > 4:
        return "OT" if period == 5 else f"{period - 4}OT"
    return _ORDINAL.get(period, "")


def _build_detail(family: str, status: dict, comp: dict) -> str:
    """Top-right state string, e.g. '4TH · 1:12', 'BOT 8TH', \"68'\"."""
    state = _get(status, "type", "state", default="pre")
    period = _to_int(_get(status, "period", default=0))
    clock = _get(status, "displayClock", default="") or ""

    if state == "post":
        detail = _get(status, "type", "shortDetail", default="FINAL") or "FINAL"
        return detail.upper()
    if state == "pre":
        return _format_start_time(_get(comp, "date", default=""))

    # live
    if family == "soccer":
        # ESPN gives the minute in displayClock (e.g. "68'").
        return clock.strip() or "LIVE"
    label = _period_label(family, period)
    clock = clock.strip()
    if label and clock:
        return f"{label} · {clock}"
    return label or clock or "LIVE"


def _competitor(comp: dict, home_away: str) -> dict | None:
    for c in _get(comp, "competitors", default=[]) or []:
        if c.get("homeAway") == home_away:
            return c
    return None


def _rank(competitor: dict) -> int | None:
    rank = _get(competitor, "curatedRank", "current")
    rank = _to_int(rank, 0)
    # ESPN uses 99 to mean "unranked".
    return rank if 0 < rank <= 25 else None


def _team_block(league: str, competitor: dict) -> dict:
    team = _get(competitor, "team", default={}) or {}
    abbrev = (team.get("abbreviation") or team.get("shortDisplayName") or "").upper()
    return {
        "abbrev": abbrev,
        "id": _to_int(team.get("id"), 0),
        "name": team.get("displayName") or team.get("name") or abbrev,
        "shortName": team.get("shortDisplayName") or team.get("name") or abbrev,
        "score": _to_int(competitor.get("score"), 0),
        "record": _get(competitor, "records", 0, "summary", default=""),
        "logoUrl": team.get("logo") or "",
        "accent": accent_for(abbrev, team.get("color")),
        "rank": _rank(competitor),
        "fav": is_favorite(league, abbrev),
    }


def _football_situation(comp: dict, away_ab: str, home_ab: str) -> dict | None:
    sit = _get(comp, "situation")
    if not isinstance(sit, dict):
        return None
    poss_id = str(sit.get("possession") or "")
    poss_ab = None
    if poss_id:
        for c in _get(comp, "competitors", default=[]) or []:
            if str(_get(c, "team", "id", default="")) == poss_id:
                poss_ab = (_get(c, "team", "abbreviation", default="") or "").upper()
                break
    yard_line = sit.get("yardLine")
    yard_pct = _to_int(yard_line, 50) if yard_line is not None else 50
    return {
        "possession": poss_ab,
        "downDistance": (sit.get("shortDownDistanceText")
                         or sit.get("downDistanceText") or "").upper(),
        "ballOn": (sit.get("possessionText") or "").upper(),
        "yard": max(0, min(100, yard_pct)),
        "redZone": bool(sit.get("isRedZone")),
    }


def _baseball_situation(comp: dict) -> dict | None:
    sit = _get(comp, "situation")
    if not isinstance(sit, dict):
        return None
    return {
        "bases": {
            "first": bool(sit.get("onFirst")),
            "second": bool(sit.get("onSecond")),
            "third": bool(sit.get("onThird")),
        },
        "balls": _to_int(sit.get("balls"), 0),
        "strikes": _to_int(sit.get("strikes"), 0),
        "outs": _to_int(sit.get("outs"), 0),
    }


def _viz(family: str, game: dict) -> dict | None:
    """Per-sport field graphic descriptor the all-sports board renders."""
    sit = game.get("situation") or {}
    if family == "baseball" and sit:
        extra = f"{sit.get('balls', 0)}-{sit.get('strikes', 0)} · {sit.get('outs', 0)} OUT"
        return {"k": "mlb", "bases": sit.get("bases", {}), "extra": extra}
    if family == "football" and sit:
        return {"k": game["sport"], "yard": sit.get("yard", 50),
                "extra": " · ".join(x for x in (sit.get("downDistance"), sit.get("ballOn")) if x)}
    return None


def _flag(family: str, game: dict) -> tuple[str, bool]:
    """(flag text, hot?) — the small pill on a tile. Hot pulses red."""
    sit = game.get("situation") or {}
    if not game["isLive"]:
        return "", False
    if family == "football" and sit.get("redZone"):
        return "RED ZONE", True
    if family == "baseball":
        b = sit.get("bases", {})
        if b.get("first") and b.get("second") and b.get("third"):
            return "BASES LOADED", True
        if b.get("second") or b.get("third"):
            return "RISP", False
    diff = abs(game["away"]["score"] - game["home"]["score"])
    if diff == 0:
        return "TIE GAME", False
    if family in ("basketball",) and diff <= 3:
        return "CLUTCH", True
    if diff <= 2:
        return "ONE SCORE", False
    return "", False


def _leaders(comp: dict) -> list | None:
    """Best-effort top performer per team: [[teamAbbrev, 'Name 34 PTS'], ...]."""
    cats = _get(comp, "leaders", default=[]) or []
    out = []
    for cat in cats:
        leader = _get(cat, "leaders", 0, default=None)
        if not leader:
            continue
        athlete = _get(leader, "athlete", default={}) or {}
        team_ab = (_get(athlete, "team", "abbreviation", default="") or "").upper()
        name = athlete.get("shortName") or athlete.get("displayName") or ""
        value = leader.get("displayValue") or ""
        if name and value:
            out.append([team_ab, f"{name} {value}"])
        if len(out) >= 2:
            break
    return out or None


def _focus(game: dict, family: str) -> dict:
    """Focus score + human reasons; mirrors the previews' priority logic."""
    score, reasons = 0, []
    away, home = game["away"], game["home"]
    if game["isLive"]:
        score += 50
        reasons.append("LIVE")
    if away["fav"] or home["fav"]:
        score += 45
        reasons.append("FAV TEAM")
    sit = game.get("situation")
    if sit and sit.get("redZone"):
        score += 40
        reasons.append("RED ZONE")
    if away.get("rank") and home.get("rank"):
        score += 30
        reasons.append(f"#{away['rank']} vs #{home['rank']}")
    diff = abs(away["score"] - home["score"])
    if game["isLive"] and diff <= 8 and not game["isFinal"]:
        score += 20
        reasons.append("ONE SCORE")
    if "OT" in (game.get("detail") or ""):
        score += 40
        reasons.append("OT")
    if game.get("hot") and game.get("flag") and game["flag"] not in reasons:
        score += 18
        reasons.append(game["flag"])
    return {"score": score, "reasons": reasons[:4]}


def _map_event(league: str, family: str, event: dict) -> dict | None:
    comp = _get(event, "competitions", 0, default={}) or {}
    status = _get(comp, "status", default={}) or _get(event, "status", default={}) or {}
    away_c = _competitor(comp, "away")
    home_c = _competitor(comp, "home")
    if not away_c or not home_c:
        return None

    state = _get(status, "type", "state", default="pre")
    is_live = state == "in"
    is_final = state == "post"
    abstract = {"in": "Live", "post": "Final"}.get(state, "Preview")

    away = _team_block(league, away_c)
    home = _team_block(league, home_c)
    game = {
        "sport": league,
        "id": str(event.get("id") or comp.get("id") or ""),
        "gamePk": _to_int(event.get("id"), 0),
        "gameDate": event.get("date") or comp.get("date") or "",
        "sortKey": event.get("date") or "",
        "startTime": _format_start_time(event.get("date") or comp.get("date") or ""),
        "away": away,
        "home": home,
        "isLive": is_live,
        "isFinal": is_final,
        "status": {
            "abstract": abstract,
            "detailed": _get(status, "type", "description", default=abstract),
        },
        "detail": _build_detail(family, status, {**comp, "date": event.get("date")}),
    }
    if family == "football":
        game["situation"] = _football_situation(comp, away["abbrev"], home["abbrev"])
    elif family == "baseball":
        game["situation"] = _baseball_situation(comp)
    game["viz"] = _viz(family, game)
    game["leaders"] = _leaders(comp)
    game["winProb"] = None  # ESPN win probability lives on a separate endpoint
    flag, hot = _flag(family, game)
    game["flag"] = flag
    game["hot"] = hot
    focus = _focus(game, family)
    game["focusScore"] = focus["score"]
    game["focusReasons"] = focus["reasons"]
    return game


def _fetch_json(url: str, params: dict | None = None) -> dict:
    resp = requests.get(
        url, params=params, timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_games(league: str) -> list[dict]:
    """Fetch and map today's games for a league. Raises requests exceptions."""
    cfg = ESPN_LEAGUES[league]
    data = _fetch_json(
        SCOREBOARD_URL.format(path=cfg["path"]), params=cfg.get("params"),
    )
    family = cfg["family"]
    games = []
    for event in _get(data, "events", default=[]) or []:
        mapped = _map_event(league, family, event)
        if mapped:
            games.append(mapped)
    games.sort(key=lambda g: (not g["isLive"], g["isFinal"], g["sortKey"]))
    return games


def _favorite_team_label(league: str) -> str:
    people = []
    from .config import FAVORITES
    for person, teams in FAVORITES.get(league, {}).items():
        for t in teams:
            people.append(f"{t} ({person})")
    return ", ".join(people)


def build_today(league: str) -> dict:
    """Full /api/<league>/today payload matching the arcade contract."""
    cfg = ESPN_LEAGUES[league]
    now = datetime.now(EASTERN)
    games = fetch_games(league)
    live = [g for g in games if g["isLive"]]
    featured = None
    ranked = sorted(games, key=lambda g: g["focusScore"], reverse=True)
    if ranked and ranked[0]["focusScore"] > 0:
        featured = ranked[0]["id"]
    return {
        "sport": league,
        "league": cfg["label"],
        "date": now.strftime("%Y-%m-%d"),
        "displayDate": f"{now.strftime('%A, %B')} {now.day}, {now.year}",
        "generatedAt": now.astimezone(timezone.utc).astimezone(EASTERN).isoformat(),
        "source": "ESPN scoreboard",
        "favoriteTeam": _favorite_team_label(league),
        "featured": featured,
        "liveCount": len(live),
        "games": games,
    }


def build_ticker(league: str) -> dict:
    """Ticker derived from live game state, plus ESPN news headlines."""
    cfg = ESPN_LEAGUES[league]
    items: list[dict] = []
    try:
        games = fetch_games(league)
    except requests.RequestException:
        games = []

    for g in games:
        if not g["isLive"]:
            continue
        away, home = g["away"], g["home"]
        sit = g.get("situation") or {}
        if sit.get("redZone"):
            team = sit.get("possession") or away["abbrev"]
            items.append({
                "text": f"RED ZONE: {team} threatening — "
                        f"{away['abbrev']} {away['score']}, {home['abbrev']} {home['score']} ({g['detail']})",
                "category": "breaking", "source": "game state",
            })
        elif abs(away["score"] - home["score"]) <= 4:
            items.append({
                "text": f"{away['shortName']} {away['score']}, "
                        f"{home['shortName']} {home['score']} — {g['detail']}",
                "category": "pressure", "source": "game state",
            })

    for g in games:
        if g["isFinal"]:
            away, home = g["away"], g["home"]
            win, lose = (away, home) if away["score"] > home["score"] else (home, away)
            items.append({
                "text": f"Final: {win['shortName']} {win['score']}, {lose['shortName']} {lose['score']}",
                "category": "news", "source": cfg["label"],
            })

    try:
        news = _fetch_json(NEWS_URL.format(path=cfg["path"]))
        for article in (_get(news, "articles", default=[]) or [])[:6]:
            headline = article.get("headline") or article.get("description")
            if headline:
                items.append({
                    "text": headline, "category": "news", "source": f"{cfg['label']}.com",
                })
    except requests.RequestException:
        pass

    return {
        "sport": league,
        "league": cfg["label"],
        "generatedAt": datetime.now(EASTERN).isoformat(),
        "source": "ESPN",
        "items": items[:24],
    }


def build_all_today(leagues=None) -> dict:
    """Aggregated all-sports payload: the best games across every league today.

    Pulls each league that has games; a league that errors is skipped (never
    blanks the whole board). Games are tagged with `sport` and sorted by focus
    so favorites and live/close games float to the featured slot.
    """
    from .config import ALL_SPORTS_LEAGUES

    leagues = leagues or ALL_SPORTS_LEAGUES
    now = datetime.now(EASTERN)
    all_games: list[dict] = []
    sports_with_games: list[str] = []
    for league in leagues:
        if league not in ESPN_LEAGUES:
            continue
        try:
            games = fetch_games(league)
        except requests.RequestException:
            continue
        if games:
            sports_with_games.append(league)
            all_games.extend(games)

    all_games.sort(key=lambda g: (not g["isLive"], -g["focusScore"], g["sortKey"]))
    live = [g for g in all_games if g["isLive"]]
    featured = all_games[0]["id"] if all_games else None
    return {
        "sport": "all",
        "league": "ALL SPORTS",
        "date": now.strftime("%Y-%m-%d"),
        "displayDate": f"{now.strftime('%A, %B')} {now.day}, {now.year}",
        "generatedAt": now.isoformat(),
        "source": "ESPN scoreboard",
        "featured": featured,
        "sportCount": len(sports_with_games),
        "liveCount": len(live),
        "games": all_games,
    }


def build_all_ticker(leagues=None) -> dict:
    """Combined wire across leagues: live hot items first, then finals."""
    from .config import ALL_SPORTS_LEAGUES

    leagues = leagues or ALL_SPORTS_LEAGUES
    hot: list[dict] = []
    finals: list[dict] = []
    for league in leagues:
        if league not in ESPN_LEAGUES:
            continue
        try:
            games = fetch_games(league)
        except requests.RequestException:
            continue
        for g in games:
            away, home = g["away"], g["home"]
            if g["isLive"] and (g.get("hot") or abs(away["score"] - home["score"]) <= 3):
                label = g.get("flag") or "LIVE"
                hot.append({
                    "text": f"{label}: {away['shortName']} {away['score']}, "
                            f"{home['shortName']} {home['score']} — {g['detail']}",
                    "category": "hot", "source": g["sport"].upper(),
                })
            elif g["isFinal"]:
                win, lose = (away, home) if away["score"] > home["score"] else (home, away)
                finals.append({
                    "text": f"Final ({g['sport'].upper()}): {win['shortName']} {win['score']}, "
                            f"{lose['shortName']} {lose['score']}",
                    "category": "", "source": g["sport"].upper(),
                })
    return {
        "sport": "all",
        "league": "THE WIRE",
        "generatedAt": datetime.now(EASTERN).isoformat(),
        "source": "ESPN",
        "items": (hot + finals)[:30],
    }
