from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
MLB_TRANSACTIONS_URL = "https://statsapi.mlb.com/api/v1/transactions"
MLB_NEWS_RSS_URL = "https://www.mlb.com/feeds/news/rss.xml"
EASTERN = ZoneInfo("America/New_York")
YANKEES_TEAM_ID = 147
MANUAL_ALERTS_PATH = Path(__file__).with_name("manual_test_alerts.json")


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_start_time(iso_game_date: str) -> str:
    if not iso_game_date:
        return "TBD"

    game_dt = datetime.fromisoformat(iso_game_date.replace("Z", "+00:00"))
    local_dt = game_dt.astimezone(EASTERN)
    return local_dt.strftime("%I:%M %p").lstrip("0")


def _format_display_date(value: datetime) -> str:
    return f"{value.strftime('%A, %B')} {value.day}, {value.year}"


def _display_date_from_string(date_string: str) -> str:
    try:
        return _format_display_date(datetime.strptime(date_string, "%Y-%m-%d"))
    except ValueError:
        return date_string


def _team_payload(team_block: dict) -> dict:
    team = team_block.get("team", {})
    team_id = team.get("id")
    return {
        "id": team_id,
        "name": team.get("name", "TBD"),
        "shortName": team.get("shortName") or team.get("teamName") or team.get("name", "TBD"),
        "abbrev": team.get("abbreviation") or team.get("fileCode", "TBD").upper(),
        "score": _to_int(team_block.get("score"), 0),
        "record": team_block.get("leagueRecord", {}).get("summary", ""),
        "logoUrl": f"https://www.mlbstatic.com/team-logos/{team_id}.svg" if team_id else "",
    }


def _inning_label(linescore: dict, status: dict) -> str:
    inning = linescore.get("currentInningOrdinal")
    inning_state = linescore.get("inningState")
    detailed = status.get("detailedState", "")

    if inning and inning_state:
        return f"{inning_state} {inning}"
    if inning:
        return str(inning)
    return detailed or "Scheduled"


def _bases_payload(linescore: dict) -> dict:
    offense = linescore.get("offense", {})
    return {
        "first": bool(offense.get("first")),
        "second": bool(offense.get("second")),
        "third": bool(offense.get("third")),
    }


def _normalize_game(game: dict) -> dict:
    status = game.get("status", {})
    linescore = game.get("linescore", {})
    teams = game.get("teams", {})
    away = _team_payload(teams.get("away", {}))
    home = _team_payload(teams.get("home", {}))
    abstract_state = status.get("abstractGameState", "Preview")

    return {
        "gamePk": game.get("gamePk"),
        "gameDate": game.get("gameDate"),
        "startTime": _format_start_time(game.get("gameDate", "")),
        "venue": game.get("venue", {}).get("name", ""),
        "status": {
            "abstract": abstract_state,
            "detailed": status.get("detailedState", "Scheduled"),
            "coded": status.get("codedGameState", ""),
        },
        "inning": _inning_label(linescore, status),
        "currentInning": _to_int(linescore.get("currentInning"), 0),
        "inningState": linescore.get("inningState", ""),
        "outs": _to_int(linescore.get("outs"), 0),
        "balls": _to_int(linescore.get("balls"), 0),
        "strikes": _to_int(linescore.get("strikes"), 0),
        "bases": _bases_payload(linescore),
        "away": away,
        "home": home,
        "isYankees": away["id"] == YANKEES_TEAM_ID or home["id"] == YANKEES_TEAM_ID,
        "isLive": abstract_state == "Live",
        "isFinal": abstract_state == "Final",
        "sortKey": game.get("gameDate", ""),
    }


def _game_priority(game: dict) -> tuple[int, str]:
    if game["isYankees"]:
        return (0, game["sortKey"])
    if game["isLive"]:
        return (1, game["sortKey"])
    if not game["isFinal"]:
        return (2, game["sortKey"])
    return (3, game["sortKey"])


def _fallback_game(date_string: str) -> dict:
    """Local demo game shown only when the live MLB API cannot be reached."""
    demo_game_date = f"{date_string}T23:05:00Z"
    return {
        "gamePk": "demo-yankees-redsox",
        "gameDate": demo_game_date,
        "startTime": _format_start_time(demo_game_date),
        "venue": "Demo Stadium",
        "status": {
            "abstract": "Preview",
            "detailed": "MLB API unavailable - demo display",
            "coded": "D",
        },
        "inning": "Demo",
        "currentInning": 0,
        "inningState": "",
        "outs": 0,
        "balls": 0,
        "strikes": 0,
        "bases": {"first": False, "second": False, "third": False},
        "away": {
            "id": 111,
            "name": "Boston Red Sox",
            "shortName": "Boston",
            "abbrev": "BOS",
            "score": 0,
            "record": "",
            "logoUrl": "https://www.mlbstatic.com/team-logos/111.svg",
        },
        "home": {
            "id": YANKEES_TEAM_ID,
            "name": "New York Yankees",
            "shortName": "Yankees",
            "abbrev": "NYY",
            "score": 0,
            "record": "",
            "logoUrl": f"https://www.mlbstatic.com/team-logos/{YANKEES_TEAM_ID}.svg",
        },
        "isYankees": True,
        "isLive": False,
        "isFinal": False,
        "sortKey": demo_game_date,
    }


def fallback_mlb_games(date_string: str, error: Exception | None = None) -> dict:
    now = datetime.now(timezone.utc).astimezone(EASTERN)
    game = _fallback_game(date_string)
    payload = {
        "date": date_string,
        "generatedAt": now.isoformat(),
        "displayDate": _display_date_from_string(date_string),
        "source": "Fallback demo data - MLB Stats API unavailable",
        "fallback": True,
        "favoriteTeam": "New York Yankees",
        "featured": game,
        "games": [game],
    }
    if error is not None:
        payload["error"] = f"Could not reach MLB Stats API: {error}"
    return payload


def fetch_mlb_games(date_string: str) -> dict:
    params = {
        "sportId": 1,
        "date": date_string,
        "hydrate": "team,linescore",
    }
    try:
        response = requests.get(MLB_SCHEDULE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return fallback_mlb_games(date_string, exc)

    games = []
    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            games.append(_normalize_game(game))

    games.sort(key=_game_priority)
    featured = next((game for game in games if game["isYankees"]), None)
    if featured is None and games:
        featured = games[0]

    now = datetime.now(timezone.utc).astimezone(EASTERN)
    return {
        "date": date_string,
        "generatedAt": now.isoformat(),
        "displayDate": _display_date_from_string(date_string),
        "source": "MLB Stats API",
        "favoriteTeam": "New York Yankees",
        "featured": featured,
        "games": games,
    }


def _ticker_item(text: str, category: str, source: str, priority: int = 50, url: str = "") -> dict:
    return {
        "text": text,
        "category": category,
        "source": source,
        "priority": priority,
        "url": url,
    }


def _stat_int(stats: dict, key: str) -> int:
    return _to_int(stats.get(key), 0)


def _inning_float(value: str) -> float:
    if not value:
        return 0.0
    whole, _, thirds = str(value).partition(".")
    return _to_int(whole, 0) + (_to_int(thirds, 0) / 3)


def _team_abbrev_by_id(games: list[dict]) -> dict[int, str]:
    mapping = {}
    for game in games:
        mapping[game["away"]["id"]] = game["away"]["abbrev"]
        mapping[game["home"]["id"]] = game["home"]["abbrev"]
    return mapping


def _hr_phrase(player_name: str, team_abbrev: str, home_runs: int, rbi: int, game: dict) -> str:
    blast = "solo shot"
    if rbi >= 4:
        blast = "grand-slam swing"
    elif rbi == 3:
        blast = "3-run blast"
    elif rbi == 2:
        blast = "2-run blast"
    elif home_runs >= 2:
        blast = "second homer"

    context = game.get("inning") or "MLB"
    return f"{context}: {player_name} goes deep for {team_abbrev} with a {blast}"


def fetch_boxscore_performers(games: list[dict]) -> list[dict]:
    items = []
    team_abbrevs = _team_abbrev_by_id(games)
    candidate_games = [game for game in games if game["status"]["abstract"] != "Preview"][:12]

    for game in candidate_games:
        try:
            response = requests.get(MLB_BOXSCORE_URL.format(game_pk=game["gamePk"]), timeout=8)
            response.raise_for_status()
            boxscore = response.json()
        except requests.RequestException:
            continue

        for side in ("away", "home"):
            team = boxscore.get("teams", {}).get(side, {}).get("team", {})
            team_abbrev = team_abbrevs.get(team.get("id"), team.get("abbreviation", "MLB"))
            players = boxscore.get("teams", {}).get(side, {}).get("players", {})

            for player in players.values():
                name = player.get("person", {}).get("boxscoreName") or player.get("person", {}).get("fullName", "Player")
                full_name = player.get("person", {}).get("fullName", name)
                batting = player.get("stats", {}).get("batting", {})
                pitching = player.get("stats", {}).get("pitching", {})

                hits = _stat_int(batting, "hits")
                home_runs = _stat_int(batting, "homeRuns")
                rbi = _stat_int(batting, "rbi")
                doubles = _stat_int(batting, "doubles")
                triples = _stat_int(batting, "triples")
                stolen_bases = _stat_int(batting, "stolenBases")

                if home_runs:
                    items.append(_ticker_item(_hr_phrase(full_name, team_abbrev, home_runs, rbi, game), "performer", "MLB Stats API boxscore", 95))
                if rbi >= 3:
                    items.append(_ticker_item(f"{game.get('inning', 'MLB')}: {full_name} drives in {rbi} for {team_abbrev}", "performer", "MLB Stats API boxscore", 90))
                if hits >= 3:
                    items.append(_ticker_item(f"{full_name} keeps finding grass: {hits} hits for {team_abbrev}", "performer", "MLB Stats API boxscore", 86))
                if doubles + triples >= 2:
                    items.append(_ticker_item(f"{full_name} has {doubles + triples} extra-base knocks for {team_abbrev}", "performer", "MLB Stats API boxscore", 82))
                if stolen_bases >= 2:
                    items.append(_ticker_item(f"{full_name} turns up the pressure with {stolen_bases} steals for {team_abbrev}", "performer", "MLB Stats API boxscore", 78))

                strikeouts = _stat_int(pitching, "strikeOuts")
                innings = pitching.get("inningsPitched", "")
                earned_runs = _stat_int(pitching, "earnedRuns")
                saves = _stat_int(pitching, "saves")
                blown_saves = _stat_int(pitching, "blownSaves")

                if strikeouts >= 7:
                    items.append(_ticker_item(f"{game.get('inning', 'MLB')}: {full_name} dealing for {team_abbrev} with {strikeouts} strikeouts", "performer", "MLB Stats API boxscore", 94))
                if _inning_float(innings) >= 6 and earned_runs <= 1:
                    items.append(_ticker_item(f"{full_name} sets the tone for {team_abbrev}: {innings} IP, {earned_runs} ER", "performer", "MLB Stats API boxscore", 88))
                if saves:
                    items.append(_ticker_item(f"{full_name} closes the door for {team_abbrev}", "performer", "MLB Stats API boxscore", 76))
                if blown_saves:
                    items.append(_ticker_item(f"{team_abbrev} bullpen wobble: {full_name} charged with a blown save", "performer", "MLB Stats API boxscore", 84))

    unique = {}
    for item in sorted(items, key=lambda entry: entry["priority"], reverse=True):
        unique.setdefault(item["text"], item)
    return list(unique.values())[:16]


def build_pressure_alerts(games: list[dict]) -> list[dict]:
    alerts = []
    for game in games:
        if not game["isLive"]:
            continue

        bases_loaded = game["bases"]["first"] and game["bases"]["second"] and game["bases"]["third"]
        scoring_position = game["bases"]["second"] or game["bases"]["third"]
        late = game["currentInning"] >= 8
        close = abs(game["away"]["score"] - game["home"]["score"]) <= 2
        matchup = f'{game["away"]["abbrev"]}-{game["home"]["abbrev"]}'

        if game["currentInning"] > 9:
            alerts.append(_ticker_item(f"FREE BASEBALL: {matchup} goes extras", "pressure", "derived from MLB Stats API game state", 99))
        if bases_loaded:
            alerts.append(_ticker_item(f"Bases loaded in {matchup}, {game['inning']}", "pressure", "derived from MLB Stats API game state", 96))
        if late and close and scoring_position:
            alerts.append(_ticker_item(f"Late pressure: tying run in scoring position for {matchup}", "pressure", "derived from MLB Stats API game state", 93))
        if late and close:
            alerts.append(_ticker_item(f"Close game late: {matchup} separated by two or fewer in {game['inning']}", "pressure", "derived from MLB Stats API game state", 88))

    return alerts[:8]


def fetch_transactions(date_string: str) -> list[dict]:
    params = {
        "sportId": 1,
        "startDate": date_string,
        "endDate": date_string,
    }
    try:
        response = requests.get(MLB_TRANSACTIONS_URL, params=params, timeout=8)
        response.raise_for_status()
    except requests.RequestException:
        return []

    items = []
    important_terms = ("injured list", "trade", "traded", "ejected", "designated for assignment", "recalled", "activated")
    for transaction in response.json().get("transactions", []):
        description = transaction.get("description", "")
        if not description:
            continue
        lower = description.lower()
        if any(term in lower for term in important_terms):
            category = "breaking" if any(term in lower for term in ("trade", "traded", "ejected")) else "news"
            priority = 98 if category == "breaking" else 64
            items.append(_ticker_item(description, category, "MLB Stats API transactions", priority))

    return items[:8]


def fetch_mlb_news() -> list[dict]:
    try:
        response = requests.get(MLB_NEWS_RSS_URL, timeout=8)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except (requests.RequestException, ElementTree.ParseError):
        return []

    items = []
    for item in root.findall("./channel/item")[:8]:
        title_node = item.find("title")
        link_node = item.find("link")
        title = title_node.text.strip() if title_node is not None and title_node.text else ""
        link = link_node.text.strip() if link_node is not None and link_node.text else ""
        if title:
            category = "breaking" if any(term in title.lower() for term in ("trade", "ejected", "historic", "record")) else "news"
            items.append(_ticker_item(title, category, "MLB.com RSS news", 72 if category == "news" else 92, link))
    return items


def load_manual_alerts() -> list[dict]:
    if not MANUAL_ALERTS_PATH.exists():
        return []
    try:
        data = json.loads(MANUAL_ALERTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not data.get("enabled"):
        return []

    alerts = []
    for alert in data.get("alerts", []):
        text = alert.get("text", "").strip()
        if not text:
            continue
        alerts.append(
            _ticker_item(
                f"TEST ALERT: {text}",
                alert.get("category", "breaking-test"),
                "manual_test_alerts.json mock/test only",
                _to_int(alert.get("priority"), 100),
            )
        )
    return alerts


def fetch_ticker_feed(date_string: str) -> dict:
    games_payload = fetch_mlb_games(date_string)
    if games_payload.get("fallback"):
        return {
            "date": date_string,
            "generatedAt": datetime.now(timezone.utc).astimezone(EASTERN).isoformat(),
            "sources": {
                "scoreboard": "Fallback demo data because MLB Stats API is unavailable",
                "performers": "Inactive until MLB box scores are reachable",
                "pressureAlerts": "Inactive until live MLB game state is reachable",
                "transactions": "Inactive until MLB Stats API transactions are reachable",
                "news": "Inactive until MLB.com RSS is reachable",
                "manualTestAlerts": "manual_test_alerts.json when enabled",
            },
            "mockActive": True,
            "items": [
                _ticker_item(
                    "DEMO MODE: Live MLB data is unavailable, but the scoreboard display is still running",
                    "breaking-test",
                    "local fallback demo data",
                    100,
                ),
                *load_manual_alerts(),
            ],
        }

    games = games_payload["games"]
    performers = fetch_boxscore_performers(games)
    pressure = build_pressure_alerts(games)
    transactions = fetch_transactions(date_string)
    news = fetch_mlb_news()
    manual = load_manual_alerts()

    items = [*manual, *performers, *pressure, *transactions, *news]
    items.sort(key=lambda item: item["priority"], reverse=True)

    return {
        "date": date_string,
        "generatedAt": datetime.now(timezone.utc).astimezone(EASTERN).isoformat(),
        "sources": {
            "scoreboard": "MLB Stats API schedule",
            "performers": "MLB Stats API boxscore",
            "pressureAlerts": "Derived locally from MLB Stats API game state",
            "transactions": "MLB Stats API transactions",
            "news": "MLB.com RSS news",
            "manualTestAlerts": "manual_test_alerts.json when enabled",
        },
        "mockActive": bool(manual),
        "items": items[:24],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/mlb/today")
def today_mlb():
    requested_date = request.args.get("date")
    date_string = requested_date or datetime.now(EASTERN).strftime("%Y-%m-%d")

    try:
        return jsonify(fetch_mlb_games(date_string))
    except requests.RequestException as exc:
        return jsonify(
            {
                "date": date_string,
                "generatedAt": datetime.now(EASTERN).isoformat(),
                "source": "MLB Stats API",
                "error": f"Could not reach MLB Stats API: {exc}",
                "favoriteTeam": "New York Yankees",
                "featured": None,
                "games": [],
            }
        ), 502


@app.route("/api/mlb/ticker")
def mlb_ticker():
    requested_date = request.args.get("date")
    date_string = requested_date or datetime.now(EASTERN).strftime("%Y-%m-%d")

    try:
        return jsonify(fetch_ticker_feed(date_string))
    except requests.RequestException as exc:
        return jsonify(
            {
                "date": date_string,
                "generatedAt": datetime.now(EASTERN).isoformat(),
                "error": f"Could not build ticker feed: {exc}",
                "items": [],
            }
        ), 502


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
