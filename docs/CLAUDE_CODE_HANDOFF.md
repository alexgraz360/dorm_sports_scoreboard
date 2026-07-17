# Dorm Wire — Full Build Spec (for Claude Code)

Snapshot date: 2026-07-09. This supersedes the earlier `docs/CLAUDE_CODE_HANDOFF.md` (which covered only NFL/CFB). Drop this into the repo as `docs/CLAUDE_CODE_HANDOFF.md` (replace it) and work from here. Never print or commit secrets.

The frontend for every board already exists in the repo as double-click previews under `previews/`. Those previews are the source of truth for the exact rendering shape and sample data each board expects. Read them before writing backend code; match their data shapes.

---

## 1. What exists vs what to build

**Exists:** the retro-arcade frontend (`templates/`, `static/`) is a drop-in for the current MLB Flask backend and reads `/api/mlb/today` and `/api/mlb/ticker`. Four board designs are done as previews: `previews/mlb_preview.html`, `football_preview.html`, `college_preview.html`, `weekday_preview.html`, plus a fifth all-sports board (see note below).

**Build, in priority order (details in each section):**
1. Merge the original Flask backend in, confirm MLB board runs live.
2. Multi-sport backend adapters (NFL, CFB, and NBA/NHL/MLB/EPL for the all-sports board).
3. The all-sports board endpoint + add its frontend to the repo.
4. Mode-switcher + overnight display sleep.
5. Football tile footer + per-sport accent colors in the frontend.
6. Fantasy layer (Sleeper then ESPN) + fantasy wire + touchdown detection.
7. Weekday live data: Google Calendar (iCal), weather, stock quotes, market news wire.
8. Quote of the day (bank already written in `weekday_preview.html`).

Note: the all-sports board preview is named `all_sports_preview.html`. If it is not yet in the repo, it is provided alongside this spec; add it to `previews/`.

---

## 2. Golden rule: extend the data contract, never break it

The frontend renders every game from one JSON shape. `status.abstract` MUST stay exactly `Preview | Live | Final`. Add fields for new sports; never remove or rename the MLB ones. The multi-sport shape the previews expect includes, per game: `sport` (`mlb|nfl|cfb|nba|nhl|mls|epl|cbb`), teams (`abbrev`, `name`, `shortName`, score, accent color, `fav` flag, optional `rank`), a `detail` string (the top-right state, e.g. `4TH · 1:12`, `BOT 8TH`, `68'`), a sport-appropriate `situation`/`viz` object, optional `leaders`, optional `winProb`, `focusReasons`, and a `flag` (e.g. `BASES LOADED`, `CLUTCH`, `RED ZONE`). See `all_sports_preview.html` and `football_preview.html` for exact keys.

---

## 3. Data sources (all free)

- **MLB:** `statsapi.mlb.com` (already used). Bases, count, inning.
- **NFL / CFB / NBA / NHL / MLB / EPL / MLS:** ESPN's unofficial scoreboard JSON, e.g. `https://site.api.espn.com/apis/site/v2/sports/<sport>/<league>/scoreboard`. Examples: `football/nfl`, `football/college-football?groups=80`, `basketball/nba`, `hockey/nhl`, `soccer/eng.1` (Premier League), `soccer/usa.1` (MLS), `basketball/mens-college-basketball`. Each event gives status (`pre|in|post`), clock/period, competitors, and a `situation` for live football. Undocumented and can change; parse defensively and keep the offline fallback.
- **AP rankings (CFB / CBB):** ESPN rankings endpoint for the `rank` badges.
- **Fantasy:** Sleeper API (free, no auth) primary; ESPN fantasy (needs cookies) secondary. See section 7.
- **Weather:** Open-Meteo (`api.open-meteo.com`) is free and needs NO API key. Use it.
- **Market news wire:** Alpha Vantage `NEWS_SENTIMENT` (topic-tagged summaries, free 25/day, refresh a few times daily) with Finnhub as backup.
- **Stock quotes (portfolio/watchlist/ribbon):** Finnhub free tier, or Alpha Vantage.
- **Google Calendar (schedules):** each person's private iCal secret URL (Calendar settings). No OAuth. See section 8.

---

## 4. Favorites config (both people, all sports)

Put this in one config module; the focus/priority logic and the star markers key off it. `fav` should be set true on a team when its abbreviation is in the matching league set.

```
FAVORITES = {
  "mlb":    { "Alex": ["NYY"] },
  "nba":    { "Alex": ["NYK"] },
  "nfl":    { "Alex": ["NYG"], "Jordan": ["DEN"] },
  "cfb":    { "Alex": ["UGA", "DUKE"], "Jordan": ["OSU"] },
  "nhl":    { "Alex": ["NYR"], "Jordan": ["NJD"] },
  "epl":    { "Jordan": ["MANU"] },   # Manchester United, English Premier League
  "cbb":    { "Alex": ["DUKE"] }
}
```

A game involving any favorite gets a priority boost in the focus score and a star on its tile. Keep team abbreviations matched to whatever ESPN returns for each league (verify at build time).

---

## 5. Mode-switcher + runtime schedule

Two separate mechanisms.

**A. Which board shows (the app picks by day/time).** All times local.

| Window | Mon–Fri | Sat–Sun |
|--------|---------|---------|
| 06:00–16:00 | Weekday dashboard | Sports board for the day |
| 16:00–01:00 | Sports board for the day | Sports board for the day |
| 01:00–06:00 | Display asleep (board irrelevant) | Display asleep |

Weekdays flip to sports at 16:00 (market close). Weekends show sports all day (no classes, markets closed).

Sports board choice during sports hours:
- Sunday in NFL season (Sep–early Feb): NFL board. Monday and Thursday nights in season: NFL board if a game is scheduled, else all-sports.
- Saturday in CFB season (late Aug–early Jan): college football board.
- Every other time: the all-sports board (the default).

Always provide a manual override (a keypress or a tiny local web control) to force any board or wake/sleep the screen.

**B. Overnight display sleep (protects the TV, saves power; the Pi stays running).** Do NOT power the Pi off. Instead schedule the HDMI output off at 01:00 and on at 06:00 via cron. On Raspberry Pi OS use CEC (`echo 'standby 0' | cec-client -s -d 1` / `'on 0'`) or the display-power control for the compositor (`wlr-randr`/`vcgencmd display_power 0|1` depending on OS). If the Pi is ever fully rebooted, the kiosk autostart brings the board back with no keyboard needed.

---

## 6. Frontend follow-ups (match the previews)

- Add the **football tile footer** variant (down and distance, possession, red-zone flag) keyed off `sport` in the live app, as shown in `football_preview.html`.
- Add **per-sport accent colors** (team colors). The all-sports preview stores an accent color per team; prefer a backend-provided `accent` hex per team (cleaner for the ~130 CFB and many soccer teams) with a frontend fallback map.
- Add the **all-sports board** and the **quote of the day** bar to the live templates (both already built in the previews).

---

## 7. Fantasy layer

- **Sleeper (primary, no auth).** Config: `SLEEPER_USERNAME_ALEX`, `SLEEPER_USERNAME_JORDAN` (not secret). Flow: username -> user id -> leagues -> rosters + matchups -> live scoring. Powers the fantasy rail (rotates through each person's leagues), showing the starting lineup (QB, RB, RB, WR, WR, TE, Flex, Flex, D/ST, K by default; read each league's actual roster settings), live points, and the head-to-head total vs the opponent.
- **ESPN (secondary).** Private leagues need the `ESPN_S2` and `ESPN_SWID` browser cookies (a one-time paste, occasional refresh). Public leagues need nothing. Build to the same shape as Sleeper so the rail treats them the same.
- **Fantasy wire** (the bottom-right panel on the football board): injuries and scoring events for rostered players.
- **Touchdown detection -> animation:** watch the live feed for a rostered player's TD (the stat that scored tells you passing vs rushing vs receiving) and fire the matching retro animation. Keep the reason short.

We will provide Sleeper usernames and league IDs when the leagues exist (season is far off). Build the adapter and stub with sample data until then.

---

## 8. Weekday live data (the "connections" phase)

- **Schedules -> Google Calendar via iCal.** Each of us pastes our calendar's private iCal secret URL: `GOOGLE_ICAL_URL_ALEX`, `GOOGLE_ICAL_URL_JORDAN` (treat as secrets). Pull today's events, sort by time, map event location into the room field, handle all-day events. This replaces the hand-typed schedules.
- **Weather -> Open-Meteo** (no key): today's temp, condition, hi/lo, wind, and the hourly strip.
- **Portfolio / watchlist / ribbon -> stock quotes** (Finnhub free). Holdings are configured locally; quotes and day change come from the API.
- **Market news wire -> Alpha Vantage NEWS_SENTIMENT** (topic tags + summaries), tagged MACRO / AI / MARKETS / EARNINGS / CRYPTO / TECH / ENERGY / DEAL as in the preview. Optionally tighten each to one sentence with an LLM pass.

---

## 9. Quote of the day

The curated, verified quote bank already lives in `previews/weekday_preview.html` (the `QUOTES` array, tagged war / phil / greek / sport). Lift it into the app. Selection is deterministic per calendar day and spread across the whole bank so it does not repeat for weeks. The bank can be grown; keep attributions verified (avoid the common misattributions).

---

## 10. Environment variables (by NAME only, never commit values)

- `SLEEPER_USERNAME_ALEX`, `SLEEPER_USERNAME_JORDAN` (config, not secret)
- `ESPN_S2`, `ESPN_SWID` (secret; private ESPN fantasy leagues only)
- `ALPHAVANTAGE_API_KEY`, `FINNHUB_API_KEY`
- `GOOGLE_ICAL_URL_ALEX`, `GOOGLE_ICAL_URL_JORDAN` (secret iCal URLs)
- Weather needs no key (Open-Meteo)

Keep these in a local `.env` (gitignored). ESPN scoreboard, MLB statsapi, and Sleeper need no key.

---

## 11. Build phases (do in order; each is demoable)

1. Merge the original Flask backend; confirm the arcade MLB board runs against live data.
2. Add NFL, then CFB adapters (ESPN) behind `/api/<sport>/today` and `/ticker`, matching the contract.
3. Add NBA/NHL/MLB/EPL adapters and the aggregated all-sports endpoint; add its frontend + quote bar.
4. Mode-switcher (day/time board selection) + the overnight HDMI sleep cron.
5. Football tile footer + per-sport accent colors.
6. Fantasy: Sleeper adapter + rail (sample data first), then the fantasy wire and TD detection; ESPN adapter second.
7. Weekday connections: Open-Meteo weather, Finnhub quotes, Alpha Vantage news wire, Google Calendar iCal schedules.

---

## 12. Acceptance checks

- `/api/mlb/today` and `/api/mlb/ticker` return the identical shape as before; the MLB board looks unchanged.
- Each new league endpoint returns valid payloads with `status.abstract` in the allowed set and sport-correct `situation`/`detail`.
- Favorites star and float correctly for both people across all leagues.
- The board on screen matches the day/time schedule, and the display sleeps 01:00–06:00 and wakes on its own.
- All feeds degrade gracefully (offline fallback, never a blank TV).
- No secret values are committed; `.gitignore` covers `.env` and keys.
