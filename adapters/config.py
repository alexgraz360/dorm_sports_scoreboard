"""Shared config for the multi-sport boards: favorites, league registry, accents.

The focus/priority logic and the star markers key off FAVORITES. Team accent
colors come from ESPN per team at build time (cleaner than a giant static map
for ~130 CFB teams); this module only holds fallbacks for when a feed omits a
color.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env(path: str | None = None) -> None:
    """Load KEY=VALUE lines from a repo-root .env into os.environ (dependency
    free — we cannot add python-dotenv to requirements.txt). Existing env vars
    win, so a real exported value is never overwritten. Values are never logged.
    """
    env_path = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


# Load .env once on import so os.getenv(...) works for local dev and the Pi.
load_env()

# Favorites for both people, per league (abbreviations as ESPN returns them).
# A game involving any favorite gets a focus boost and a star on its tile.
FAVORITES: dict[str, dict[str, list[str]]] = {
    "mlb": {"Alex": ["NYY"]},
    "nba": {"Alex": ["NYK"]},
    "nfl": {"Alex": ["NYG"], "Nolan": ["DEN"]},
    "cfb": {"Alex": ["UGA", "DUKE"], "Nolan": ["OSU"]},
    "nhl": {"Alex": ["NYR"], "Nolan": ["NJD"]},
    "epl": {"Nolan": ["MANU"]},  # Manchester United
    "cbb": {"Alex": ["DUKE"]},
}

# ESPN scoreboard registry. path is the <sport>/<league> segment; params are
# extra query args (CFB needs groups=80 for FBS). "family" drives how the live
# detail string and situation are built.
ESPN_LEAGUES: dict[str, dict] = {
    "mlb": {"path": "baseball/mlb", "label": "MLB", "family": "baseball"},
    "nfl": {"path": "football/nfl", "label": "NFL", "family": "football"},
    "cfb": {
        "path": "football/college-football",
        "label": "CFB",
        "family": "football",
        "params": {"groups": "80"},
    },
    "nba": {"path": "basketball/nba", "label": "NBA", "family": "basketball"},
    "cbb": {
        "path": "basketball/mens-college-basketball",
        "label": "CBB",
        "family": "basketball",
    },
    "nhl": {"path": "hockey/nhl", "label": "NHL", "family": "hockey"},
    "epl": {"path": "soccer/eng.1", "label": "EPL", "family": "soccer"},
    "mls": {"path": "soccer/usa.1", "label": "MLS", "family": "soccer"},
}

# Which leagues have their own live /api/<sport>/today endpoint via the ESPN
# blueprint. MLB is intentionally excluded here: it keeps its dedicated
# statsapi route in app.py (the blueprint's dynamic route would be shadowed by
# it anyway). ESPN's mlb entry above is used only by the all-sports aggregator.
ENABLED_LEAGUES = ("nfl", "cfb", "nba", "cbb", "nhl", "epl")

# Leagues the all-sports board aggregates, in display priority order. The
# aggregator pulls whichever of these have games today and skips the rest.
ALL_SPORTS_LEAGUES = ("mlb", "nba", "nhl", "epl", "mls", "nfl", "cfb")

# ---- Weekday dashboard config (not secret) ----
# Location for weather (Open-Meteo, no key). Default: Madison, NJ (Drew Univ).
WEATHER_LAT = 40.766
WEATHER_LON = -74.425
LOCATION_LABEL = "HURST 11"

# Portfolio holdings (local config; quotes come from Finnhub). shares only.
# Fractional shares come from dividend reinvestment — keep the decimals.
PORTFOLIO_HOLDINGS = [
    {"symbol": "AMC", "shares": 1},
    {"symbol": "ASTS", "shares": 5},
    {"symbol": "B", "shares": 8.03},
    {"symbol": "CAIE", "shares": 26.23},
    {"symbol": "COF", "shares": 2.096},
    {"symbol": "COIN", "shares": 1},
    {"symbol": "GMAB", "shares": 5},
    {"symbol": "GOOG", "shares": 2.013},
    {"symbol": "HIMS", "shares": 4},
    {"symbol": "IBIT", "shares": 3},
    {"symbol": "LMT", "shares": 4.077},
    {"symbol": "LNTH", "shares": 2},
    {"symbol": "LUNR", "shares": 5},
    {"symbol": "NEM", "shares": 5.024},
    {"symbol": "OKLO", "shares": 10},
    {"symbol": "PFE", "shares": 3.368},
    {"symbol": "PL", "shares": 5},
    {"symbol": "PLTR", "shares": 2},
    {"symbol": "RKLB", "shares": 5},
    {"symbol": "SFM", "shares": 3},
    {"symbol": "SKYW", "shares": 5},
    {"symbol": "TGB", "shares": 35},
    {"symbol": "TSLA", "shares": 4},
    {"symbol": "UNH", "shares": 4.054},
    {"symbol": "VNQ", "shares": 5.193},
    {"symbol": "VOO", "shares": 4.088},
]
WATCHLIST_SYMBOLS = ["PLTR", "AMD", "COIN", "NFLX", "META", "JPM"]
# Ribbon: broad indices/tickers scrolled along the bottom.
RIBBON_SYMBOLS = ["SPY", "QQQ", "DIA", "AAPL", "NVDA", "TSLA"]

# Fallback accent colors (hex) used only when a feed does not supply one.
FALLBACK_ACCENTS: dict[str, str] = {
    "NYY": "#132448", "NYG": "#0b2265", "DEN": "#fb4f14", "UGA": "#ba0c2f",
    "DUKE": "#00539b", "OSU": "#bb0000", "NYR": "#0038a8", "NJD": "#ce1126",
    "MANU": "#da020e", "NYK": "#f58426",
}
DEFAULT_ACCENT = "#23f0ff"  # arcade cyan


def favorite_people(league: str, abbrev: str) -> list[str]:
    """Return the list of people who favorite this team in this league."""
    if not abbrev:
        return []
    people = []
    for person, teams in FAVORITES.get(league, {}).items():
        if abbrev.upper() in {t.upper() for t in teams}:
            people.append(person)
    return people


def is_favorite(league: str, abbrev: str) -> bool:
    return bool(favorite_people(league, abbrev))


# Team codes are drawn in the team's own colour on a near-black tile. Navy,
# black and dark-brown teams (MIL, SD, BUF, MISS...) come out unreadable from
# across a room, so lift anything below this relative luminance.
MIN_ACCENT_LUMA = 0.34


def _brighten(hex6: str, min_luma: float = MIN_ACCENT_LUMA) -> str:
    """Lift a colour toward white until it clears min_luma, keeping its hue."""
    try:
        r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return f"#{hex6}"
    luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if luma >= min_luma:
        return f"#{hex6}"
    # blend toward white by however much we are short
    t = min(0.85, (min_luma - luma) / max(min_luma, 0.01))
    r, g, b = (round(c + (255 - c) * t) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def accent_for(abbrev: str, feed_color: str | None) -> str:
    """Prefer the feed-provided team color; fall back to our map, then cyan.
    Dark colours are brightened so the team code stays legible on a TV."""
    color = (feed_color or "").strip().lstrip("#")
    if color and len(color) == 3:
        color = "".join(c * 2 for c in color)
    if color and len(color) == 6:
        return _brighten(color.lower())
    fallback = FALLBACK_ACCENTS.get((abbrev or "").upper(), DEFAULT_ACCENT)
    return _brighten(fallback.lstrip("#")) if fallback != DEFAULT_ACCENT else fallback
