# Dorm Sports Wire

A local Flask scoreboard appliance for a dorm common room TV or monitor. The current build focuses on MLB scores with a retro stadium-board style, Hurst 11 branding, a rotating featured game, subtle team-logo watermarks, and a slow editorial ticker.

## Features

- Fullscreen 16:9 retro sports-bar scoreboard display
- MLB scoreboard from free public MLB data
- Yankees priority without hiding the rest of the league
- Rotating Game Focus based on simple pressure/excitement logic
- Bottom ticker led by box-score performers and game-state alerts
- Official MLB transaction/news ticker layer when available
- Clearly labeled manual test alerts for breaking-news visual testing
- Fallback demo state if the live MLB API is temporarily unavailable

## Local Windows Run

```powershell
cd C:\Users\lmgra\OneDrive\Documents\Playground\dorm_sports_scoreboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Raspberry Pi Quick Setup

These steps assume Raspberry Pi OS Desktop is installed, WiFi works, and the project has been pushed to GitHub.

```bash
cd ~
git clone https://github.com/alexgraz360/dorm_sports_scoreboard.git
cd dorm_sports_scoreboard
chmod +x scripts/*.sh
./scripts/pi_setup.sh
./scripts/install_service.sh
./scripts/install_kiosk.sh
sudo reboot
```

After reboot, the Pi should start the Flask server automatically and open Chromium to the scoreboard in kiosk mode.

## Manual Pi Test

Before installing kiosk mode, you can test the app manually:

```bash
cd ~/dorm_sports_scoreboard
./.venv/bin/python app.py
```

Then open Chromium to:

```text
http://127.0.0.1:5000
```

Press `Ctrl+C` in the terminal to stop the manual server.

## Update The Pi App

After pushing changes to GitHub:

```bash
cd ~/dorm_sports_scoreboard
./scripts/update_app.sh
```

This runs `git pull`, refreshes Python dependencies, and restarts the service.

## Raspberry Pi Scripts

- `scripts/pi_setup.sh`: installs apt packages, creates `.venv`, installs `requirements.txt`, and installs Chromium if missing.
- `scripts/install_service.sh`: creates and starts the `dorm-sports-wire` systemd service for the current user.
- `scripts/install_kiosk.sh`: writes `~/.config/labwc/autostart` so Chromium opens the dashboard in kiosk mode on boot.
- `scripts/update_app.sh`: pulls the latest GitHub code, reinstalls requirements, and restarts the service.

## Logs And Troubleshooting

Check service status:

```bash
systemctl status dorm-sports-wire.service
```

Follow live Flask logs:

```bash
journalctl -u dorm-sports-wire.service -f
```

Restart the Flask service:

```bash
sudo systemctl restart dorm-sports-wire.service
```

If Chromium opens but the page does not load, wait 10-20 seconds, then press `Ctrl+R` or reboot. The kiosk startup intentionally waits before launching Chromium so the Flask service has time to start.

## Rollback / Disable

Disable the Flask auto-start service:

```bash
sudo systemctl stop dorm-sports-wire.service
sudo systemctl disable dorm-sports-wire.service
```

Remove the service file completely:

```bash
sudo rm /etc/systemd/system/dorm-sports-wire.service
sudo systemctl daemon-reload
```

Disable Chromium kiosk startup:

```bash
nano ~/.config/labwc/autostart
```

Comment out the Chromium line by adding `#` at the front, then reboot:

```bash
sudo reboot
```

## Data Sources

Real live data:

- MLB schedule, scores, status, inning, bases, count, and team info:
  `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=team,linescore`
- MLB box-score performers:
  `https://statsapi.mlb.com/api/v1/game/{gamePk}/boxscore`
- MLB transactions and official injured-list moves:
  `https://statsapi.mlb.com/api/v1/transactions?sportId=1&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`
- MLB.com news RSS:
  `https://www.mlb.com/feeds/news/rss.xml`
- Team logo assets:
  `https://www.mlbstatic.com/team-logos/{teamId}.svg`

Derived data:

- Pressure alerts such as `FREE BASEBALL`, bases loaded, late close games, and runners in scoring position are computed locally from MLB game state.
- Game Focus ranking is computed locally from Yankees priority, live status, late close games, runners on base, extra innings, and score pressure.

Mock/test-only data:

- `manual_test_alerts.json` is disabled by default and exists only to test breaking-news visuals.
- If the MLB API is unreachable, the board shows a clearly labeled fallback demo state so the TV does not go blank.

The app does not fake injuries, trades, or breaking news as real. Official transactions and MLB.com RSS items are treated as real source-backed news.

## Test A Breaking Alert

Edit `manual_test_alerts.json`:

```json
{
  "enabled": true,
  "alerts": [
    {
      "text": "Manual kiosk test from Hurst 11",
      "category": "breaking-test",
      "priority": 100
    }
  ]
}
```

Restart the service:

```bash
sudo systemctl restart dorm-sports-wire.service
```

The ticker will label it as `TEST ALERT` from `manual_test_alerts.json mock/test only`. Set `"enabled": false` when finished.

## Project Structure

```text
dorm_sports_scoreboard/
  app.py
  requirements.txt
  manual_test_alerts.json
  services/
    dorm-sports-wire.service
  scripts/
    pi_setup.sh
    install_service.sh
    install_kiosk.sh
    update_app.sh
  templates/
    index.html
  static/
    css/styles.css
    js/app.js
  README.md
```
