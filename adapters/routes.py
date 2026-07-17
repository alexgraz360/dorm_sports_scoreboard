"""Flask blueprint exposing /api/<sport>/today and /api/<sport>/ticker.

Registered from app.py with a single line so the MLB routes there stay
untouched. MLB keeps its dedicated statsapi endpoints; this blueprint serves
the ESPN-backed leagues in ENABLED_LEAGUES.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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

# Where each board id currently lives. Boards not yet built (a dedicated NFL/CFB
# football board is Phase 5, weekday is Phase 7) fall back to the all-sports
# board, which already includes those games.
BOARD_URLS = {
    board_selector.ASLEEP: "/sleep",
    board_selector.WEEKDAY: "/all",  # dedicated weekday board is Phase 7
    board_selector.NFL: "/football/nfl",
    board_selector.CFB: "/football/cfb",
    board_selector.ALL: "/all",
    "mlb": "/",
}

# In-memory manual override (kiosk control). board="auto" clears it.
_override: dict = {"board": None}

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


def _current_board() -> str:
    if _override["board"]:
        return _override["board"]
    now = datetime.now(EASTERN)
    has_nfl = False
    if now.weekday() in (0, 3) and board_selector.is_nfl_season(now):
        has_nfl = _nfl_game_today()
    return board_selector.select_board(now, has_nfl)


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
    The Pi points its browser here; it always lands on the right board."""
    return redirect(BOARD_URLS.get(_current_board(), "/all"))


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


@sports_bp.route("/sleep")
def sleep_page():
    return render_template("sleep.html")


@sports_bp.route("/control")
def control_page():
    return render_template("control.html")
