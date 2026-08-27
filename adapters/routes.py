"""Flask blueprint exposing /api/<sport>/today and /api/<sport>/ticker.

Registered from app.py with a single line so the MLB routes there stay
untouched. MLB keeps its dedicated statsapi endpoints; this blueprint serves
the ESPN-backed leagues in ENABLED_LEAGUES.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import requests
from flask import Blueprint, jsonify, redirect, render_template, request

from . import board_selector
from .config import ENABLED_LEAGUES, ESPN_LEAGUES
from .espn import (
    EASTERN,
    build_all_ticker,
    build_all_today,
    build_ticker,
    build_today,
    fetch_games,
)

sports_bp = Blueprint("sports", __name__)

# ---------------- static asset cache-busting ----------------
# The kiosk browser held on to an old all_sports.js after a deploy: the server
# had the new file but the screen kept rendering the previous build. Stamp every
# static URL with the newest mtime in static/ so a deploy always produces a new
# URL and the kiosk cannot serve a stale copy.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _asset_version() -> str:
    latest = 0.0
    try:
        for f in _STATIC_DIR.rglob("*"):
            if f.is_file():
                latest = max(latest, f.stat().st_mtime)
    except OSError:
        pass
    return str(int(latest))


@sports_bp.app_context_processor
def _inject_asset_version():
    return {"asset_v": _asset_version()}


# Where each board id currently lives. Boards not yet built (a dedicated NFL/CFB
# football board is Phase 5, weekday is Phase 7) fall back to the all-sports
# board, which already includes those games.
BOARD_URLS = {
    board_selector.ASLEEP: "/sleep",
    board_selector.WEEKDAY: "/weekday",
    board_selector.NFL: "/football/nfl",
    board_selector.CFB: "/football/cfb",
    board_selector.ALL: "/all",
    "mlb": "/",
}

# ---------------- remote-control state ----------------
# Everything the phone remote can change lives here. `rev` bumps on every
# change; the boards poll /api/board and re-render when it moves, which is what
# makes a tap on the phone show up on the TV a few seconds later.
_state: dict = {
    "board": None,      # forced board id, None = follow the day/time schedule
    "pin": None,        # game id locked into the GAME FOCUS slot
    "scale": None,      # display scale override (None = per-device default)
    "safe": None,       # overscan safe-area override
    "rev": 0,
}


def _bump(**changes) -> None:
    _state.update(changes)
    _state["rev"] += 1


# Backwards-compatible alias: existing code reads _override["board"].
class _OverrideView:
    def __getitem__(self, k):
        return _state.get(k)

    def __setitem__(self, k, v):
        _bump(**{k: v})


_override = _OverrideView()

# Tiny cache so the Mon/Thu "is an NFL game on?" check does not hit ESPN often.
_nfl_cache: dict = {"at": None, "value": False}


def _nfl_game_today() -> bool:
    now = datetime.now(EASTERN)
    if _nfl_cache["at"] and now - _nfl_cache["at"] < timedelta(minutes=15):
        return _nfl_cache["value"]
    try:
        games = fetch_games("nfl")
        today = now.strftime("%Y-%m-%d")
        value = any((g.get("gameDate") or "")[:10] == today for g in games)
    except requests.RequestException:
        value = False
    _nfl_cache.update(at=now, value=value)
    return value


# Cache "does this league have games today" so the empty-board guard below does
# not hit ESPN on every poll (the boards ask every 5s).
_slate_cache: dict = {}


def _league_has_games(league: str) -> bool:
    now = datetime.now(EASTERN)
    hit = _slate_cache.get(league)
    if hit and now - hit[0] < timedelta(minutes=15):
        return hit[1]
    try:
        value = bool(fetch_games(league))
    except requests.RequestException:
        value = True   # network trouble: do not strand the board on a fallback
    _slate_cache[league] = (now, value)
    return value


def _current_board() -> str:
    if _override["board"]:
        return _override["board"]
    now = datetime.now(EASTERN)
    has_nfl = False
    if now.weekday() in (0, 3) and board_selector.is_nfl_season(now):
        has_nfl = _nfl_game_today()
    board = board_selector.select_board(now, has_nfl)
    # A dedicated league board with nothing on it is a dead screen. Now that the
    # slate is filtered to today only, that happens all through the offseason
    # (e.g. a Saturday before the college season opens), so fall back to the
    # all-sports board, which shows whatever IS on.
    if board in (board_selector.NFL, board_selector.CFB) and not _league_has_games(board):
        return board_selector.ALL
    return board


@sports_bp.route("/all")
def all_sports_board():
    """Live all-sports board (arcade). Mirrors previews/all_sports_preview.html
    but fetches /api/all/today + /api/all/ticker instead of embedded demo data."""
    return render_template("all_sports.html")


@sports_bp.route("/football/<league>")
def football_board(league: str):
    """Live NFL / CFB board with the football tile footer (down & distance,
    possession, red-zone) and backend-provided team accent colors."""
    league = league.lower()
    if league not in ("nfl", "cfb"):
        return jsonify({"error": f"No football board for '{league}'"}), 404
    return render_template("football.html", league=league,
                           label=ESPN_LEAGUES[league]["label"])


@sports_bp.route("/api/all/today")
def all_today():
    try:
        return jsonify(build_all_today())
    except requests.RequestException as exc:
        return jsonify({
            "sport": "all",
            "generatedAt": datetime.now(EASTERN).isoformat(),
            "error": f"Could not reach ESPN scoreboard: {exc}",
            "featured": None, "games": [],
        }), 502


@sports_bp.route("/api/all/ticker")
def all_ticker():
    try:
        return jsonify(build_all_ticker())
    except requests.RequestException as exc:
        return jsonify({
            "sport": "all",
            "generatedAt": datetime.now(EASTERN).isoformat(),
            "error": f"Could not build ticker feed: {exc}",
            "items": [],
        }), 502


def _supported(sport: str) -> bool:
    return sport in ENABLED_LEAGUES and sport in ESPN_LEAGUES


@sports_bp.route("/api/<sport>/today")
def sport_today(sport: str):
    sport = sport.lower()
    if not _supported(sport):
        return jsonify({"error": f"Unsupported sport '{sport}'", "games": []}), 404
    try:
        return jsonify(build_today(sport))
    except requests.RequestException as exc:
        return jsonify({
            "sport": sport,
            "date": datetime.now(EASTERN).strftime("%Y-%m-%d"),
            "generatedAt": datetime.now(EASTERN).isoformat(),
            "source": "ESPN scoreboard",
            "error": f"Could not reach ESPN scoreboard: {exc}",
            "featured": None,
            "games": [],
        }), 502


@sports_bp.route("/api/<sport>/ticker")
def sport_ticker(sport: str):
    sport = sport.lower()
    if not _supported(sport):
        return jsonify({"error": f"Unsupported sport '{sport}'", "items": []}), 404
    try:
        return jsonify(build_ticker(sport))
    except requests.RequestException as exc:
        return jsonify({
            "sport": sport,
            "generatedAt": datetime.now(EASTERN).isoformat(),
            "error": f"Could not build ticker feed: {exc}",
            "items": [],
        }), 502


# ---------------- mode-switcher (which board shows) ----------------

@sports_bp.route("/board")
def board():
    """Redirect the kiosk to whichever board should show right now.
    The Pi points its browser here; it always lands on the right board.
    Query args are carried through so ?scale=1.2 (the per-TV text-size knob)
    survives the redirect instead of being dropped."""
    target = BOARD_URLS.get(_current_board(), "/all")
    if request.query_string:
        sep = "&" if "?" in target else "?"
        target = f"{target}{sep}{request.query_string.decode('utf-8', 'ignore')}"
    return redirect(target)


@sports_bp.route("/api/board")
def api_board():
    now = datetime.now(EASTERN)
    auto = board_selector.select_board(
        now,
        _nfl_game_today() if now.weekday() in (0, 3)
        and board_selector.is_nfl_season(now) else False,
    )
    current = _current_board()
    return jsonify({
        "board": current,
        "url": BOARD_URLS.get(current, "/all"),
        "auto": auto,
        "override": _override["board"],
        "asleep": current == board_selector.ASLEEP,
        "now": now.isoformat(),
        "pin": _state["pin"],
        "scale": _state["scale"],
        "safe": _state["safe"],
        "rev": _state["rev"],
    })


@sports_bp.route("/api/board/override")
def api_board_override():
    """Manual override: /api/board/override?board=all|nfl|cfb|weekday|mlb|asleep|auto."""
    choice = (request.args.get("board") or "").lower()
    if choice in ("", "auto"):
        _override["board"] = None
    elif choice in BOARD_URLS:
        _override["board"] = choice
    else:
        return jsonify({"error": f"Unknown board '{choice}'"}), 400
    return jsonify({"override": _override["board"], "board": _current_board()})


# ---------------- weekday dashboard ----------------

@sports_bp.route("/weekday")
def weekday_board():
    """Live weekday dashboard: quote of the day, schedules, weather, markets,
    news. Mirrors previews/weekday_preview.html; fetches /api/weekday/today."""
    return render_template("weekday.html")


@sports_bp.route("/api/weekday/today")
def api_weekday():
    from .weekday import build_weekday
    try:
        return jsonify(build_weekday())
    except requests.RequestException as exc:
        return jsonify({"error": f"Weekday feed error: {exc}"}), 502


# ---------------- fantasy (Sleeper primary) ----------------

@sports_bp.route("/api/fantasy/rail")
def api_fantasy_rail():
    from .fantasy import build_fantasy_rail
    try:
        return jsonify(build_fantasy_rail())
    except requests.RequestException as exc:
        return jsonify({"error": f"Fantasy rail unavailable: {exc}",
                        "demo": True, "people": []}), 502


@sports_bp.route("/api/fantasy/wire")
def api_fantasy_wire():
    from .fantasy import build_fantasy_wire
    try:
        return jsonify(build_fantasy_wire())
    except requests.RequestException as exc:
        return jsonify({"error": f"Fantasy wire unavailable: {exc}",
                        "demo": True, "items": []}), 502




# ---------------- phone remote endpoints ----------------

@sports_bp.route("/api/control/pin")
def api_control_pin():
    """Lock a game into the GAME FOCUS slot. ?game=<id>, or ?game= to clear."""
    game = (request.args.get("game") or "").strip()
    _bump(pin=game or None)
    return jsonify({"pin": _state["pin"], "rev": _state["rev"]})


@sports_bp.route("/api/control/display")
def api_control_display():
    """Set the per-TV display knobs from the remote: ?scale=1.1&safe=6."""
    changes = {}
    if "scale" in request.args:
        try:
            changes["scale"] = max(0.8, min(2.5, float(request.args["scale"])))
        except ValueError:
            return jsonify({"error": "scale must be a number"}), 400
    if "safe" in request.args:
        try:
            changes["safe"] = max(0.0, min(12.0, float(request.args["safe"])))
        except ValueError:
            return jsonify({"error": "safe must be a number"}), 400
    if not changes:
        return jsonify({"error": "nothing to set"}), 400
    _bump(**changes)
    return jsonify({"scale": _state["scale"], "safe": _state["safe"], "rev": _state["rev"]})


@sports_bp.route("/api/control/state")
def api_control_state():
    """Everything the remote needs in one call: current board + today's games."""
    try:
        today = build_all_today()
        games = [{
            "id": g["id"], "sport": g["sport"],
            "away": g["away"]["abbrev"], "home": g["home"]["abbrev"],
            "awayName": g["away"]["shortName"], "homeName": g["home"]["shortName"],
            "awayScore": g["away"]["score"], "homeScore": g["home"]["score"],
            "detail": g["detail"], "isLive": g["isLive"], "isFinal": g["isFinal"],
            "fav": bool(g["away"]["fav"] or g["home"]["fav"]),
            "startTime": g.get("startTime", ""),
        } for g in today.get("games", [])]
    except requests.RequestException:
        games = []
    return jsonify({
        "board": _current_board(),
        "auto": board_selector.select_board(datetime.now(EASTERN)),
        "override": _state["board"],
        "pin": _state["pin"],
        "scale": _state["scale"],
        "safe": _state["safe"],
        "rev": _state["rev"],
        "games": games,
    })


@sports_bp.route("/sleep")
def sleep_page():
    return render_template("sleep.html")


@sports_bp.route("/control")
def control_page():
    return render_template("control.html")
