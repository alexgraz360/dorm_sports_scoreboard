# Dorm Wire — HANDOFF

Snapshot date: 2026-07-09. This file lets a fresh Claude session on another machine continue the project without this thread's history. No secrets are in this repo; see "Secret files to hand-carry."

---

## 1. Goal and current status

Dorm Wire is a Raspberry Pi kiosk that displays a retro-arcade live sports scoreboard on a dorm-room TV, with four modes: MLB, NFL Sunday, college football Saturday, and a weekday finance/school dashboard. As of 2026-07-09, the retro-arcade frontend redesign is complete and the MLB board is drop-in ready against the existing Flask backend; the other three boards exist as self-contained visual previews, and the multi-sport backend, fantasy layer, and mode-switcher are designed but not yet built.

---

## 2. Done / in-progress / not-started

### Done
- Retro-arcade frontend redesign: `templates/index.html`, `static/css/styles.css`, `static/js/app.js`. This is a drop-in replacement for the old frontend and uses the SAME backend endpoints and JSON shape (`/api/mlb/today`, `/api/mlb/ticker`). Render-verified in a headless DOM.
- Four board designs as standalone, double-click previews (sample data, no server): `previews/mlb_preview.html`, `previews/football_preview.html`, `previews/college_preview.html`, `previews/weekday_preview.html`.
- Weekday dashboard design: dual class schedules, weather, a rotating portfolio/watchlist rail (terminal style), and a tagged one-sentence market news wire.
- Backend build spec for multi-sport: `docs/CLAUDE_CODE_HANDOFF.md` (NFL + CFB adapters, the data contract to preserve, fantasy, focus/ticker logic, acceptance checks).

### In-progress
- None. Project is paused for migration to the mini PC.

### Not started
- Mode-switcher: auto-pick the board by day and time (NFL Sundays, CFB Saturdays, weekday dashboard, MLB otherwise), with manual override.
- Multi-sport backend (NFL then CFB) via ESPN feeds, per `docs/CLAUDE_CODE_HANDOFF.md`.
- Football frontend tile footer (down/distance, possession, red zone) and NFL/CFB team accent colors.
- Fantasy layer: Sleeper (primary) + ESPN (secondary), the fantasy wire (injuries + scoring), and touchdown detection driving the scoring animations.
- Weekday live data: market news wire (Alpha Vantage / Finnhub), stock quotes, weather, and Google Calendar via iCal for the schedules.

---

## 3. Key decisions and why (do not relitigate)

- **Frontend redesigned but backend data contract left unchanged.** The new arcade frontend reads the exact same MLB JSON the old backend already produces, so it is a pure drop-in. Reason: do not rewrite a working backend; lowest-risk path to the new look.
- **Extend the JSON contract, never break it.** Football/CFB add fields (`sport`, `situation`, `rank`) without removing MLB fields, and `status.abstract` must stay exactly `Preview | Live | Final`. Reason: one renderer serves all sports.
- **Offline sample-data fallback lives in `static/js/app.js`.** If the API is unreachable, the board renders bundled demo games instead of going blank; this also lets previews run with no server. Reason: a kiosk must never show an empty screen.
- **Multi-sport data from ESPN's unofficial JSON endpoints** (`site.api.espn.com`). Reason: free, no key, rich live data (quarter, clock, possession). Tradeoff: undocumented and can change, so parse defensively.
- **Fantasy: Sleeper primary, ESPN secondary.** Sleeper's API is free and needs no login; ESPN is free too but private leagues need the `ESPN_S2` and `ESPN_SWID` browser cookies. Reason: least-friction live scoring first.
- **Look is mode-specific.** Sports boards use a neon retro-arcade aesthetic; the weekday board uses a modern base with a terminal-green finance rail and ribbon. Reason: the finance-terminal styling reads as a live market feed and fits the context.
- **Kiosk stack stays Raspberry Pi OS + systemd service + Chromium kiosk** (from the original repo scripts). Reason: unattended boot straight to the board.

---

## 4. File / directory map

```
dorm-sports-wire/
  HANDOFF.md                     <- this file
  README.md
  .gitignore                     <- excludes secrets, venv, node/test pollution, logs, data
  templates/
    index.html                   <- arcade board markup (Flask/Jinja, loads static/)
  static/
    css/styles.css               <- arcade stylesheet (neon, CRT, per-team accent var)
    js/app.js                    <- board logic + team colors + offline sample fallback
  previews/
    mlb_preview.html             <- MLB board, references ../static (open in browser)
    football_preview.html        <- NFL Sunday board (self-contained)
    college_preview.html         <- College Saturday board (self-contained)
    weekday_preview.html         <- Weekday dashboard w/ market wire (self-contained)
  docs/
    CLAUDE_CODE_HANDOFF.md        <- backend build spec (NFL/CFB, fantasy, contract)
```

Not in this snapshot but required to run the live app: the original Flask backend (`app.py`, `requirements.txt`, `services/`, `scripts/`) from the existing `dorm_sports_scoreboard` repo. See gotchas.

---

## 5. Setup and run

### Frontend previews (no server, fastest check)
Open any file in `previews/` directly in a browser. They use bundled sample data. `previews/mlb_preview.html` also pulls the real `static/css` and `static/js`, so keep the folder structure intact.

### Full app (Flask backend + arcade frontend)
The backend from the original `dorm_sports_scoreboard` repo must be present at the project root. Then:

```
python -m venv .venv
# activate: source .venv/bin/activate  (Linux/mac)  |  .\.venv\Scripts\Activate.ps1  (Windows)
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5000
```

Drop the arcade frontend in by replacing the old `templates/index.html`, `static/css/styles.css`, and `static/js/app.js` with the ones in this repo. No backend change needed for the MLB board.

### Raspberry Pi kiosk (from original repo scripts)
`scripts/pi_setup.sh`, `scripts/install_service.sh`, `scripts/install_kiosk.sh`, then reboot. Update with `scripts/update_app.sh`.

### Environment variables (BY NAME ONLY, never store values in the repo)
None are required for the current MLB-only board. The upcoming backend features will need:
- `ALPHAVANTAGE_API_KEY` — market news wire and/or stock quotes
- `FINNHUB_API_KEY` — market news / quotes (backup source)
- `ESPN_S2`, `ESPN_SWID` — only for private ESPN fantasy leagues
- `SLEEPER_USERNAME` — Sleeper account handle (not secret, but config)
- `WEATHER_API_KEY` — weekday weather
- `STOCK_API_KEY` — quote provider if separate from the above
- `GOOGLE_CALENDAR_ICAL_URL_ALEX`, `GOOGLE_CALENDAR_ICAL_URL_JORDAN` — private iCal secret URLs (treat as secrets)

Put these in a local `.env` (gitignored). Never commit values.

---

## 6. Known gotchas and dead ends

- **Do not break the JSON contract.** The frontend branches on `status.abstract` being exactly `Preview | Live | Final`, and reads specific fields. Extend, do not rename or remove.
- **ESPN endpoints are unofficial.** The fantasy base URL moved to `lm-api-reads.fantasy.espn.com` in the past and can change again. Wrap all parsing defensively and keep the offline fallback so the TV never blanks.
- **The original Flask backend is not in this snapshot.** `app.py` etc. live in the `dorm_sports_scoreboard` repo and must be merged in to run the live app. This repo is the new frontend + previews + specs.
- **Sample data is not live behavior.** The demo games are defined at the bottom of `static/js/app.js` and only render when the API fetch fails. Do not mistake them for real data.
- **Editing lesson (process):** batching multiple simultaneous edits to the same file once truncated `weekday_preview.html`; it was rebuilt. Make one file change at a time.
- **Team accent colors are stylized for a neon board.** Dark navy teams (e.g., Yankees) are brightened so they glow on black; they are not exact brand colors by design.

---

## 7. Next steps in priority order

1. Merge the original Flask backend (`app.py`, `requirements.txt`, `services/`, `scripts/`) into this repo so it runs end to end.
2. Install the new arcade frontend (files already here) and verify the MLB board against live data.
3. Build the mode-switcher (day/time auto-select + manual override).
4. Implement the multi-sport backend per `docs/CLAUDE_CODE_HANDOFF.md`: NFL first, then CFB.
5. Add the football tile footer variant and NFL/CFB accent colors in the frontend.
6. Build the fantasy layer (Sleeper first), the fantasy wire, and TD detection wired to the scoring animations.
7. Wire weekday live data: market news wire, stock quotes, weather, and Google Calendar iCal schedules.

---

## 8. Currently broken

Nothing in the delivered files is known to be broken. The MLB frontend and all four previews render correctly (headless-DOM verified on 2026-07-09). The multi-sport, fantasy, and weekday-live features are simply not built yet, which is different from broken.

---

## Secret files to hand-carry to the mini PC (never commit, never print values)

- `.env` — API keys and the private Google Calendar iCal URLs (see the env-var names above)
- The Raspberry Pi SSH private key (e.g., `id_ed25519` or a `*.pem`) used to reach the Pi
- `espn_cookies.json` — if you store the `ESPN_S2` / `ESPN_SWID` cookies as a file instead of env vars

All of the above are already listed in `.gitignore`.
