# Dorm Wire — Claude Code Session Summary

**Snapshot:** 2026-07-18 · Repo: https://github.com/alexgraz360/dorm_sports_scoreboard (branch `main`, all work below committed + pushed).

This documents everything built in the **Claude Code** session so a **Cowork** session (which has separate work — notably the touchdown scoring animations) can reconcile. It is a status/handoff doc, not the build spec; the full spec remains at `docs/CLAUDE_CODE_HANDOFF.md`.

**⚠️ Known cross-environment gap:** the rich per-type **touchdown animations** (e.g. "Saquon running it in", plus receiving/passing variants) were built in **Cowork** and are **NOT in this repo**. Claude Code only built a placeholder full-screen **"TOUCHDOWN!" text-flash overlay** (`#td-anim` in `templates/football.html`, `fireTdAnimation()` in `static/js/football.js`). The backend already detects TD type (`passing`/`rushing`/`receiving`) via `detect_touchdowns()`, so the Cowork animations just need to be dropped in and keyed off that. **Bring the Cowork animation assets/code into this repo and wire them to `fireTdAnimation(kind, playerText)`.**

---

## How to run (local, Windows dev)

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install tzdata      # Windows only — NOT in requirements.txt
.venv\Scripts\python app.py                     # serves http://127.0.0.1:5000
```

- `tzdata` is installed into the venv only. Do **not** add it to `requirements.txt` — the Raspberry Pi (Linux) has system tzdata; the repo backend must stay portable.
- Flask caches Jinja templates (`debug=False`), so **restart the server after editing any `.html` template** (static JS/CSS reload without a restart).
- Secrets/config live in a gitignored `.env` (loaded by a dependency-free loader in `adapters/config.py`). `.env.example` documents every variable by name.

---

## Boards & routes

| URL | Board | Data source | State |
|-----|-------|-------------|-------|
| `/` | MLB arcade board | MLB statsapi (original `app.py`) | live |
| `/all` | All-sports aggregate + "ALSO ON" sidebar | ESPN (all leagues) | live |
| `/football/nfl`, `/football/cfb` | Football board + fantasy sidebar | ESPN + fantasy | live |
| `/weekday` | Weekday dashboard | weather/markets/news/calendar/quote | live |
| `/control` | Touch control page (force board / sleep) | — | live |
| `/sleep` | Black overnight page (self-wakes) | — | live |
| `/board` | Auto-redirects to the right board by day/time | mode-switcher | live |

**APIs:** `/api/mlb/today` + `/ticker` (statsapi); `/api/<sport>/today` + `/ticker` for `nfl,cfb,nba,cbb,nhl,epl` (ESPN); `/api/all/today` + `/ticker`; `/api/weekday/today`; `/api/fantasy/rail` + `/api/fantasy/wire`; `/api/board` (+ `/api/board/override?board=...`).

---

## Architecture

Original backend (`app.py`, `requirements.txt`, `services/`, `scripts/*` pre-existing) was left intact. Everything new lives in an **`adapters/` package**, registered in `app.py` with a single `register_blueprint` line.

```
adapters/
  config.py          # .env loader, FAVORITES, ESPN league registry, team accents,
                     #   weather location, portfolio holdings/watchlist/ribbon config
  espn.py            # ESPN scoreboard -> game contract mapper (all sports) + aggregator
  board_selector.py  # pure day/time -> board logic (schedule table + seasons)
  routes.py          # Flask blueprint: all /api/* + board routes
  fantasy.py         # Sleeper (primary) + ESPN (secondary) adapters, TD detection
  weekday.py         # weather, iCal schedules, markets, news, quote-of-the-day
templates/  all_sports.html, football.html, weekday.html, sleep.html, control.html
static/js/  all_sports.js, football.js, weekday.js  (+ original app.js for MLB)
```

**Contract golden rule (followed throughout):** `status.abstract` stays exactly `Preview | Live | Final`. New fields were added per game (`sport`, per-team `accent`/`fav`/`rank`, `detail`, `situation`, `leaders`, `flag`, `focusScore`) — MLB fields never renamed.

---

## What was built, by phase

1. **Frontend + spec import + gitignore hardening** — arcade frontend drop-in, 5 board previews, full build spec, `.gitignore` covering `.env*`/keys/venv/logs/data/models.
2. **NFL + CFB ESPN adapters** — defensive scoreboard mapper, `/api/<sport>/today` + `/ticker`, favorites/accents.
3. **All-sports** — NBA/NHL/EPL enabled, aggregated `/api/all/today`, live `/all` board with rotating sidebar; baseball/football `situation` + `viz`, flags, best-effort leaders.
4. **Mode-switcher + overnight sleep** — `board_selector` (weekday dashboard on weekday daytime, NFL Sundays/MNF/TNF, CFB Saturdays, all-sports default, asleep 01:00–06:00); `/board` redirect + `/control` + `/sleep`; `scripts/display_power.sh` (CEC → wlr-randr → vcgencmd) + `scripts/install_display_cron.sh` (01:00 off / 06:00 on / @reboot on).
5. **Football board** — live NFL/CFB board, tile footer (down/distance, possession, red-zone), backend team accents.
6. **Fantasy** — Sleeper (username → leagues → rosters/matchups → scoring) **and** ESPN (private leagues via cookies), season fallback so pre-draft leagues show last season, `detect_touchdowns()` (per-kind, rostered-only), `/api/fantasy/rail` + `/wire`.
7. **Weekday dashboard** — Open-Meteo weather, iCal Google Calendar schedules (with **recurring-event RRULE expansion**), Finnhub markets, Alpha Vantage news, deterministic quote-of-the-day.

**Fixes along the way:** compact-tile overflow on the MLB board and (separately) the football board at wide/short viewports; football fantasy sidebar layout.

---

## Live vs. stubbed data (as of this snapshot)

| Feed | Source | Needs | State |
|------|--------|-------|-------|
| MLB / NFL / CFB / NBA / NHL / EPL scores | ESPN + statsapi | nothing | ✅ live |
| Weather | Open-Meteo | nothing | ✅ live |
| Quote of the day | local verified bank | nothing | ✅ live |
| Sleeper fantasy | Sleeper API | `SLEEPER_USERNAME_ALEX` | ✅ live (3 leagues) |
| ESPN fantasy | ESPN fantasy API | `ESPN_S2`, `ESPN_SWID`, `ESPN_LEAGUE_IDS` | ✅ live (3 leagues) |
| Calendar schedules | Google iCal | `GOOGLE_ICAL_URL_ALEX` (+ `_JORDAN`) | ✅ live (recurring events fixed) |
| Market quotes | Finnhub | `FINNHUB_API_KEY` | ✅ live (⚠ placeholder share counts) |
| Market news | Alpha Vantage | `ALPHAVANTAGE_API_KEY` | ✅ live |
| Fantasy wire (injuries/TDs) | derived | live game feed | ⏳ sample until season |

Env var **names** only (values never committed): `SLEEPER_USERNAME_ALEX/JORDAN`, `ESPN_S2`, `ESPN_SWID`, `ESPN_LEAGUE_IDS`, `FINNHUB_API_KEY`, `ALPHAVANTAGE_API_KEY`, `GOOGLE_ICAL_URL_ALEX/JORDAN`. See `.env.example`.

---

## Open follow-ups

1. **Touchdown animations — pull from Cowork** (the main reason for this doc). Wire the real per-type scenes to `fireTdAnimation()` in `static/js/football.js`, keyed off the TD `kind` from `detect_touchdowns()`. Overlay hook already exists: `#td-anim` in `templates/football.html`.
2. **Real portfolio holdings** — replace placeholder shares in `PORTFOLIO_HOLDINGS` (`adapters/config.py`) with actual symbol+share counts so the markets total is real.
3. **Fantasy wire live data** — currently sample; goes live once the season has real injuries/scoring.
4. **Jordan's feeds** — `SLEEPER_USERNAME_JORDAN` and `GOOGLE_ICAL_URL_JORDAN` not yet set.
5. **Screenshots** — the CRT-styled boards time out the automated screenshot tool; all verification this session was via DOM inspection. Fine on a real display.

---

## Commit trail (this session, on top of the original `8fd8d71`)

```
83ff79e Add arcade frontend, board previews, and full build spec
93f8dc9 Fix compact tile overflow on large slates
960b1db Phase 2: NFL + CFB ESPN adapters
946b893 Phase 3: all-sports aggregation + NBA/NHL/EPL + live board
7684bae Phase 4: mode-switcher + overnight HDMI display sleep
70ca751 Phase 5: live football board (footer + per-sport accents)
280aa95 Phase 6: fantasy layer (Sleeper adapter + rail/wire stub)
357d2ab Phase 7: weekday dashboard connections
4b09d26 Add .env.example documenting env var names (no values)
321aa17 Fix football board tile overflow on wide/short viewports
5b35418 Fantasy: season fallback so a real Sleeper league shows before renewal
1ff047d Fantasy: add ESPN league adapter (private leagues via cookies)
c9b3685 Fantasy ESPN: per-league last-season fallback for pre-draft leagues
7ab4447 Weekday: expand recurring calendar events (iCal RRULE)
4fe057a Fantasy UI: rail + wire + TD animation on the football board
```
