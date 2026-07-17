"""Flask blueprint exposing /api/<sport>/today and /api/<sport>/ticker.

Registered from app.py with a single line so the MLB routes there stay
untouched. MLB keeps its dedicated statsapi endpoints; this blueprint serves
the ESPN-backed leagues in ENABLED_LEAGUES.
"""

from __future__ import annotations

from datetime import datetime

import requests
from flask import Blueprint, jsonify

from .config import ENABLED_LEAGUES, ESPN_LEAGUES
from .espn import EASTERN, build_ticker, build_today

sports_bp = Blueprint("sports", __name__)


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
