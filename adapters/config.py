"""Shared config for the multi-sport boards: favorites, league registry, accents.

The focus/priority logic and the star markers key off FAVORITES. Team accent
colors come from ESPN per team at build time (cleaner than a giant static map
for ~130 CFB teams); this module only holds fallbacks for when a feed omits a
color.
"""

from __future__ import annotations

# Favorites for both people, per league (abbreviations as ESPN returns them).
# A game involving any favorite gets a focus boost and a star on its tile.
FAVORITES: dict[str, dict[str, list[str]]] = {
    "mlb": {"Alex": ["NYY"]},
    "nba": {"Alex": ["NYK"]},
    "nfl": {"Alex": ["NYG"], "Jordan": ["DEN"]},
    "cfb": {"Alex": ["UGA", "DUKE"], "Jordan": ["OSU"]},
    "nhl": {"Alex": ["NYR"], "Jordan": ["NJD"]},
    "epl": {"Jordan": ["MANU"]},  # Manchester United
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


def accent_for(abbrev: str, feed_color: str | None) -> str:
    """Prefer the feed-provided team color; fall back to our map, then cyan."""
    color = (feed_color or "").strip().lstrip("#")
    if color and len(color) in (3, 6):
        return f"#{color}"
    return FALLBACK_ACCENTS.get((abbrev or "").upper(), DEFAULT_ACCENT)
