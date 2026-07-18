"""Weekday dashboard data: weather, schedules, markets, news, quote of the day.

Free sources per the spec:
  - Weather: Open-Meteo (no key) -> always live.
  - Quote of the day: local verified bank -> always live, deterministic per day.
  - Schedules: Google Calendar private iCal URLs (GOOGLE_ICAL_URL_ALEX/JORDAN).
  - Stocks: Finnhub (FINNHUB_API_KEY).
  - Market news: Alpha Vantage NEWS_SENTIMENT (ALPHAVANTAGE_API_KEY).

Anything needing a key/secret falls back to sample data (marked demo=True) so
the board never blanks. Secret values are read by name and never logged.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import requests

from . import config
from .espn import EASTERN

TIMEOUT = 8
UA = {"User-Agent": "DormWire/1.0 (+weekday)"}


# ============ Quote of the day (always live) ============

# Curated, verified attributions (lifted from previews/weekday_preview.html).
QUOTES = [
    {"t": "The credit belongs to the man who is actually in the arena.", "by": "Theodore Roosevelt", "cat": "war"},
    {"t": "A good plan violently executed now is better than a perfect plan next week.", "by": "George S. Patton", "cat": "war"},
    {"t": "Never give in. Never, never, never.", "by": "Winston Churchill", "cat": "war"},
    {"t": "I have not yet begun to fight.", "by": "John Paul Jones", "cat": "war"},
    {"t": "Duty, honor, country.", "by": "Douglas MacArthur", "cat": "war"},
    {"t": "We are not retreating. We are advancing in another direction.", "by": "Douglas MacArthur", "cat": "war"},
    {"t": "The soldier above all others prays for peace, for he must suffer the deepest wounds of war.", "by": "Douglas MacArthur", "cat": "war"},
    {"t": "In the midst of chaos, there is also opportunity.", "by": "Sun Tzu", "cat": "war"},
    {"t": "You have power over your mind, not outside events. Realize this, and you will find strength.", "by": "Marcus Aurelius", "cat": "phil"},
    {"t": "We suffer more often in imagination than in reality.", "by": "Seneca", "cat": "phil"},
    {"t": "It is not what happens to you, but how you react to it that matters.", "by": "Epictetus", "cat": "phil"},
    {"t": "Waste no more time arguing about what a good man should be. Be one.", "by": "Marcus Aurelius", "cat": "phil"},
    {"t": "The impediment to action advances action. What stands in the way becomes the way.", "by": "Marcus Aurelius", "cat": "phil"},
    {"t": "He who has a why to live can bear almost any how.", "by": "Friedrich Nietzsche", "cat": "phil"},
    {"t": "The unexamined life is not worth living.", "by": "Socrates", "cat": "phil"},
    {"t": "No man is free who is not master of himself.", "by": "Epictetus", "cat": "phil"},
    {"t": "Luck is what happens when preparation meets opportunity.", "by": "Seneca", "cat": "phil"},
    {"t": "Molon labe. Come and take them.", "by": "King Leonidas", "cat": "greek"},
    {"t": "What you leave behind is not what is engraved in stone, but what is woven into the lives of others.", "by": "Pericles", "cat": "greek"},
    {"t": "No man ever steps in the same river twice.", "by": "Heraclitus", "cat": "greek"},
    {"t": "Character is destiny.", "by": "Heraclitus", "cat": "greek"},
    {"t": "Let me do some great thing that shall be told among men hereafter.", "by": "Hector, in Homer's Iliad", "cat": "greek"},
    {"t": "Bear up, my heart; you have endured worse than this.", "by": "Odysseus, in Homer's Odyssey", "cat": "greek"},
    {"t": "In peace, sons bury their fathers. In war, fathers bury their sons.", "by": "Herodotus", "cat": "greek"},
    {"t": "The secret to happiness is freedom, and the secret to freedom is courage.", "by": "Thucydides", "cat": "greek"},
    {"t": "Give me a place to stand, and I will move the earth.", "by": "Archimedes", "cat": "greek"},
    {"t": "You miss 100% of the shots you don't take.", "by": "Wayne Gretzky", "cat": "sport"},
    {"t": "I've failed over and over again in my life, and that is why I succeed.", "by": "Michael Jordan", "cat": "sport"},
    {"t": "It ain't over till it's over.", "by": "Yogi Berra", "cat": "sport"},
    {"t": "Hard work beats talent when talent fails to work hard.", "by": "Tim Notke", "cat": "sport"},
    {"t": "It's not whether you get knocked down; it's whether you get up.", "by": "Vince Lombardi", "cat": "sport"},
    {"t": "Don't count the days; make the days count.", "by": "Muhammad Ali", "cat": "sport"},
    {"t": "Today I will do what others won't, so tomorrow I can do what others can't.", "by": "Jerry Rice", "cat": "sport"},
    {"t": "Never let the fear of striking out keep you from playing the game.", "by": "Babe Ruth", "cat": "sport"},
    {"t": "The more difficult the victory, the greater the happiness in winning.", "by": "Pele", "cat": "sport"},
]
CATNAME = {"war": "WAR HEROES", "phil": "PHILOSOPHY", "greek": "ANCIENT GREECE", "sport": "ATHLETES"}


def quote_of_the_day(now: datetime | None = None) -> dict:
    """Deterministic per calendar day, spread across the whole bank so it does
    not repeat for weeks. Matches the preview's selection (day * 7919 % N)."""
    now = now or datetime.now(EASTERN)
    day_number = (now - datetime(1970, 1, 1, tzinfo=now.tzinfo)).days
    q = QUOTES[(day_number * 7919) % len(QUOTES)]
    return {**q, "catName": CATNAME.get(q["cat"], "")}


# ============ Weather (Open-Meteo, no key -> always live) ============

_WMO = {
    0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy",
    45: "Fog", 48: "Fog", 51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    61: "Rain", 63: "Rain", 65: "Heavy Rain", 66: "Freezing Rain", 67: "Freezing Rain",
    71: "Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow",
    80: "Showers", 81: "Showers", 82: "Heavy Showers",
    85: "Snow Showers", 86: "Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}
_WMO_SHORT = {0: "clear", 1: "clear", 2: "partly", 3: "cloudy", 45: "fog", 48: "fog"}


def _cond(code: int) -> str:
    return _WMO.get(int(code), "—")


def _cond_short(code: int) -> str:
    c = int(code)
    return _WMO_SHORT.get(c, "rain" if 51 <= c <= 82 else "snow" if 71 <= c <= 86 else "storm" if c >= 95 else "clear")


def build_weather() -> dict:
    try:
        data = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": config.WEATHER_LAT, "longitude": config.WEATHER_LON,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "hourly": "temperature_2m,weather_code",
                "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
                "timezone": "America/New_York", "forecast_days": 1,
            },
            timeout=TIMEOUT, headers=UA,
        )
        data.raise_for_status()
        d = data.json()
        cur = d.get("current", {})
        daily = d.get("daily", {})
        hourly = d.get("hourly", {})
        now_hour = datetime.now(EASTERN).hour
        hours = []
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        codes = hourly.get("weather_code", [])
        for i, iso in enumerate(times):
            try:
                hr = int(iso[11:13])
            except (ValueError, IndexError):
                continue
            if hr < now_hour or len(hours) >= 5:
                continue
            ap = "A" if hr < 12 else "P"
            h12 = hr % 12 or 12
            hours.append({
                "h": f"{h12}{ap}",
                "t": f"{round(temps[i])}°" if i < len(temps) else "",
                "c": _cond_short(codes[i]) if i < len(codes) else "",
            })
        return {
            "demo": False, "source": "Open-Meteo",
            "temp": round(cur.get("temperature_2m", 0)),
            "condition": _cond(cur.get("weather_code", 0)),
            "hi": round((daily.get("temperature_2m_max") or [0])[0]),
            "lo": round((daily.get("temperature_2m_min") or [0])[0]),
            "wind": round(cur.get("wind_speed_10m", 0)),
            "precip": round((daily.get("precipitation_probability_max") or [0])[0]),
            "location": config.LOCATION_LABEL,
            "hours": hours,
        }
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return _sample_weather()


# ============ Schedules (Google Calendar iCal; secret URLs) ============

def _unfold_ical(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


_WEEKDAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _parse_rrule(value: str) -> dict:
    """Parse an RRULE value ('FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=...') into a dict.
    BYDAY becomes a set of weekday ints; UNTIL a date."""
    rule: dict = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        key = key.strip().upper()
        if key == "BYDAY":
            rule[key] = {_WEEKDAY_CODES[d[-2:]] for d in val.split(",")
                         if d[-2:] in _WEEKDAY_CODES}
        elif key == "UNTIL":
            try:
                rule[key] = datetime.strptime(val[:8], "%Y%m%d").date()
            except ValueError:
                pass
        else:
            rule[key] = val
    return rule


def _iter_occurrences(start: date, freq: str, interval: int, byday, cap: int = 4000):
    """Yield recurrence dates in chronological order (bounded by cap)."""
    if freq == "DAILY":
        for i in range(cap):
            yield start + timedelta(days=i * interval)
    elif freq == "WEEKLY":
        days = sorted(byday) if byday else [start.weekday()]
        week0 = start - timedelta(days=start.weekday())
        for w in range(cap):
            base = week0 + timedelta(weeks=w * interval)
            for wd in days:
                yield base + timedelta(days=wd)
    elif freq == "MONTHLY":
        for i in range(cap):
            m = start.month - 1 + i * interval
            y, mo = start.year + m // 12, m % 12 + 1
            try:
                yield date(y, mo, start.day)
            except ValueError:
                continue
    elif freq == "YEARLY":
        for i in range(cap):
            try:
                yield date(start.year + i * interval, start.month, start.day)
            except ValueError:
                continue


def _recurs_on(start: datetime, rule: dict, exdates: set, target: date) -> bool:
    freq = rule.get("FREQ")
    if not freq or target < start.date() or target in exdates:
        return False
    interval = int(rule.get("INTERVAL") or 1) or 1
    count = int(rule["COUNT"]) if str(rule.get("COUNT", "")).isdigit() else None
    until = rule.get("UNTIL")
    d0 = start.date()
    emitted = 0
    for occ in _iter_occurrences(d0, freq, interval, rule.get("BYDAY")):
        if occ < d0:
            continue
        if until and occ > until:
            break
        emitted += 1
        if count is not None and emitted > count:
            break
        if occ == target:
            return True
        if occ > target:
            break
    return False


def _parse_ical_today(text: str, now: datetime) -> list[dict]:
    today = now.date()
    events: list[dict] = []
    cur: dict = {}
    in_event = False
    for line in _unfold_ical(text):
        if line.startswith("BEGIN:VEVENT"):
            in_event, cur = True, {"exdates": set()}
        elif line.startswith("END:VEVENT"):
            in_event = False
            start = cur.get("start")
            if not start:
                continue
            occurs = start.date() == today or (
                "rrule" in cur and _recurs_on(start, cur["rrule"], cur["exdates"], today))
            if occurs:
                ap = "a" if start.hour < 12 else "p"
                h12 = start.hour % 12 or 12
                events.append({
                    "time": "all-day" if cur.get("allday") else f"{h12}:{start.minute:02d}{ap}",
                    "sort": -1 if cur.get("allday") else start.hour * 60 + start.minute,
                    "title": cur.get("summary", "(busy)"),
                    "room": cur.get("location", "—"),
                    "now": 0,
                })
        elif in_event and line.startswith("DTSTART"):
            value = line.split(":", 1)[-1].strip()
            allday = "VALUE=DATE" in line and "T" not in value
            dt = _parse_ical_dt(value, now.tzinfo)
            if dt:
                cur["start"] = dt
                cur["allday"] = allday
        elif in_event and line.startswith("RRULE"):
            cur["rrule"] = _parse_rrule(line.split(":", 1)[-1].strip())
        elif in_event and line.startswith("EXDATE"):
            for v in line.split(":", 1)[-1].split(","):
                d = _parse_ical_dt(v.strip(), now.tzinfo)
                if d:
                    cur["exdates"].add(d.date())
        elif in_event and line.startswith("SUMMARY"):
            cur["summary"] = line.split(":", 1)[-1].strip()
        elif in_event and line.startswith("LOCATION"):
            cur["location"] = line.split(":", 1)[-1].strip() or "—"
    events.sort(key=lambda e: e["sort"])
    # Mark the event happening now (started, next one not yet). All-day skipped.
    now_min = now.hour * 60 + now.minute
    timed = [e for e in events if e["sort"] >= 0]
    for i, e in enumerate(timed):
        nxt = timed[i + 1]["sort"] if i + 1 < len(timed) else 24 * 60
        if e["sort"] <= now_min < nxt:
            e["now"] = 1
    return events


def _parse_ical_dt(value: str, tz) -> datetime | None:
    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return dt.astimezone(tz)
        if "T" in value:
            return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=tz)
        return datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=tz)
    except ValueError:
        return None


def _fetch_schedule(url: str, now: datetime) -> list[dict] | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=UA)
        r.raise_for_status()
        return _parse_ical_today(r.text, now)
    except requests.RequestException:
        return None


def build_schedules() -> dict:
    now = datetime.now(EASTERN)
    alex = _fetch_schedule(os.getenv("GOOGLE_ICAL_URL_ALEX"), now)
    jordan = _fetch_schedule(os.getenv("GOOGLE_ICAL_URL_JORDAN"), now)
    if alex is None and jordan is None:
        return _sample_schedules()
    return {"demo": False, "source": "Google Calendar",
            "alex": alex or [], "jordan": jordan or []}


# ============ Markets (Finnhub quotes; API key) ============

def _finnhub_quote(symbol: str, key: str) -> dict | None:
    try:
        r = requests.get("https://finnhub.io/api/v1/quote",
                         params={"symbol": symbol, "token": key},
                         timeout=TIMEOUT, headers=UA)
        r.raise_for_status()
        q = r.json()
        if not q or q.get("c") in (None, 0):
            return None
        return {"price": q["c"], "changePct": q.get("dp", 0) or 0}
    except (requests.RequestException, ValueError, KeyError):
        return None


def build_markets() -> dict:
    key = os.getenv("FINNHUB_API_KEY")
    if not key:
        return _sample_markets()
    quotes: dict[str, dict] = {}
    symbols = {h["symbol"] for h in config.PORTFOLIO_HOLDINGS} \
        | set(config.WATCHLIST_SYMBOLS) | set(config.RIBBON_SYMBOLS)
    for sym in symbols:
        q = _finnhub_quote(sym, key)
        if q:
            quotes[sym] = q
    if not quotes:
        return _sample_markets()

    def fmt_pct(p):
        return f"{'+' if p >= 0 else ''}{p:.1f}%"

    holdings, total, day_change = [], 0.0, 0.0
    for h in config.PORTFOLIO_HOLDINGS:
        q = quotes.get(h["symbol"])
        if not q:
            continue
        value = q["price"] * h["shares"]
        total += value
        day_change += value * (q["changePct"] / 100)
        holdings.append({"symbol": h["symbol"], "shares": f"{h['shares']} sh",
                         "price": f"{q['price']:.2f}", "changePct": fmt_pct(q["changePct"]),
                         "up": q["changePct"] >= 0})
    watch = [{"symbol": s, "shares": "", "price": f"{quotes[s]['price']:.2f}",
              "changePct": fmt_pct(quotes[s]["changePct"]), "up": quotes[s]["changePct"] >= 0}
             for s in config.WATCHLIST_SYMBOLS if s in quotes]
    ribbon = [{"symbol": s, "price": f"{quotes[s]['price']:.2f}",
               "changePct": fmt_pct(quotes[s]["changePct"]), "up": quotes[s]["changePct"] >= 0}
              for s in config.RIBBON_SYMBOLS if s in quotes]
    day_pct = (day_change / (total - day_change) * 100) if total else 0
    return {
        "demo": False, "source": "Finnhub",
        "portfolio": {
            "total": f"${total:,.0f}",
            "day": f"{'+' if day_change >= 0 else '-'}${abs(day_change):,.0f} ({fmt_pct(day_pct)})",
            "up": day_change >= 0, "rows": holdings,
        },
        "watchlist": {"rows": watch},
        "ribbon": ribbon,
    }


# ============ Market news (Alpha Vantage NEWS_SENTIMENT; API key) ============

def build_news() -> dict:
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not key:
        return _sample_news()
    try:
        r = requests.get("https://www.alphavantage.co/query",
                         params={"function": "NEWS_SENTIMENT", "limit": 20,
                                 "topics": "financial_markets,technology,economy_macro",
                                 "apikey": key},
                         timeout=TIMEOUT, headers=UA)
        r.raise_for_status()
        feed = r.json().get("feed", [])
        items = []
        for a in feed[:12]:
            topics = [t.get("topic", "") for t in a.get("topics", [])]
            items.append({"cat": _news_cat(topics, a.get("title", "")),
                          "text": a.get("title", "")})
        if items:
            return {"demo": False, "source": "Alpha Vantage", "items": items}
    except (requests.RequestException, ValueError, KeyError):
        pass
    return _sample_news()


def _news_cat(topics: list[str], title: str) -> str:
    joined = (" ".join(topics) + " " + title).lower()
    for key, cat in (("earnings", "EARNINGS"), ("technology", "TECH"), ("blockchain", "CRYPTO"),
                     ("crypto", "CRYPTO"), ("energy", "ENERGY"), ("macro", "MACRO"),
                     ("economy", "MACRO"), ("merger", "DEAL"), ("ai", "AI")):
        if key in joined:
            return cat
    return "MARKETS"


# ============ Aggregate ============

def build_weekday() -> dict:
    now = datetime.now(EASTERN)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "dateline": now.strftime("%A · %b %d").upper(),
        "generatedAt": now.isoformat(),
        "quote": quote_of_the_day(now),
        "weather": build_weather(),
        "schedules": build_schedules(),
        "markets": build_markets(),
        "news": build_news(),
    }


# ============ Sample fallbacks ============

def _sample_weather() -> dict:
    return {"demo": True, "source": "sample", "temp": 64, "condition": "Partly Cloudy",
            "hi": 71, "lo": 55, "wind": 8, "precip": 10, "location": config.LOCATION_LABEL,
            "hours": [{"h": "9A", "t": "58°", "c": "cloudy"}, {"h": "12P", "t": "68°", "c": "clear"},
                      {"h": "3P", "t": "71°", "c": "clear"}, {"h": "6P", "t": "66°", "c": "clear"},
                      {"h": "9P", "t": "60°", "c": "clear"}]}


def _sample_schedules() -> dict:
    return {"demo": True, "source": "sample",
            "alex": [{"time": "9:30a", "title": "FIN 301 Corp Finance", "room": "214", "now": 0},
                     {"time": "11:00a", "title": "ECON 202 Macro", "room": "118", "now": 1},
                     {"time": "1:30p", "title": "ACCT 210 Mgr Acct", "room": "305", "now": 0},
                     {"time": "3:15p", "title": "Study / Gym", "room": "—", "now": 0}],
            "jordan": [{"time": "8:00a", "title": "STAT 240 Bus Stats", "room": "101", "now": 0},
                       {"time": "10:00a", "title": "FIN 320 Investments", "room": "214", "now": 0},
                       {"time": "12:30p", "title": "MKTG 200 Marketing", "room": "220", "now": 1},
                       {"time": "2:00p", "title": "FIN 301 Corp Finance", "room": "214", "now": 0}]}


def _sample_markets() -> dict:
    return {"demo": True, "source": "sample",
            "portfolio": {"total": "$18,432", "day": "+$214 (+1.18%)", "up": True, "rows": [
                {"symbol": "AAPL", "shares": "42 sh", "price": "228.51", "changePct": "+1.2%", "up": True},
                {"symbol": "NVDA", "shares": "15 sh", "price": "178.20", "changePct": "+2.4%", "up": True},
                {"symbol": "MSFT", "shares": "8 sh", "price": "511.30", "changePct": "+0.6%", "up": True},
                {"symbol": "SPY", "shares": "20 sh", "price": "642.10", "changePct": "+0.4%", "up": True},
                {"symbol": "VTI", "shares": "30 sh", "price": "298.44", "changePct": "+0.5%", "up": True},
                {"symbol": "TSLA", "shares": "6 sh", "price": "412.90", "changePct": "-1.8%", "up": False}]},
            "watchlist": {"rows": [
                {"symbol": "PLTR", "shares": "", "price": "62.10", "changePct": "+3.1%", "up": True},
                {"symbol": "AMD", "shares": "", "price": "178.44", "changePct": "+1.9%", "up": True},
                {"symbol": "COIN", "shares": "", "price": "289.30", "changePct": "-2.2%", "up": False},
                {"symbol": "NFLX", "shares": "", "price": "720.11", "changePct": "+0.8%", "up": True},
                {"symbol": "META", "shares": "", "price": "640.22", "changePct": "+1.4%", "up": True},
                {"symbol": "JPM", "shares": "", "price": "301.15", "changePct": "-0.5%", "up": False}]},
            "ribbon": [{"symbol": "S&P 500", "price": "6,421", "changePct": "+0.4%", "up": True},
                       {"symbol": "NASDAQ", "price": "21,880", "changePct": "+0.6%", "up": True},
                       {"symbol": "DOW", "price": "44,120", "changePct": "+0.2%", "up": True},
                       {"symbol": "AAPL", "price": "228.51", "changePct": "+1.2%", "up": True},
                       {"symbol": "NVDA", "price": "178.20", "changePct": "+2.4%", "up": True},
                       {"symbol": "BTC", "price": "118,240", "changePct": "+3.1%", "up": True}]}


def _sample_news() -> dict:
    return {"demo": True, "source": "sample", "items": [
        {"cat": "MACRO", "text": "Fed holds rates steady, signals one more cut could come before year-end"},
        {"cat": "AI", "text": "Nvidia's new chip sells out as data-center demand keeps outrunning supply"},
        {"cat": "MARKETS", "text": "S&P 500 notches a record close as tech leads a broad rally"},
        {"cat": "EARNINGS", "text": "Apple beats on services growth and guides next quarter above estimates"},
        {"cat": "CRYPTO", "text": "Bitcoin pushes past $118K as ETF inflows hit a monthly high"},
        {"cat": "TECH", "text": "Microsoft expands its OpenAI deal as Azure AI revenue jumps"},
        {"cat": "ENERGY", "text": "Oil slips as OPEC+ weighs raising output into year-end"},
        {"cat": "DEAL", "text": "Chipmaker announces $40B takeover, the sector's largest this year"}]}
