#!/usr/bin/env bash
# Install the overnight display-sleep schedule into the current user's crontab:
#   01:00  HDMI/panel off   (protects the TV, saves power; Pi stays running)
#   06:00  HDMI/panel on
#   @reboot  panel on        (so a reboot always comes back to a lit board)
#
# Idempotent: re-running replaces the Dorm Wire block, leaves other cron lines
# alone. Run as the user that owns the kiosk session (usually `pi`).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POWER="$SCRIPT_DIR/display_power.sh"
chmod +x "$POWER"

MARK_BEGIN="# >>> dorm-wire display sleep >>>"
MARK_END="# <<< dorm-wire display sleep <<<"

# Keep any existing crontab minus our previous block.
existing="$(crontab -l 2>/dev/null | sed "/$MARK_BEGIN/,/$MARK_END/d" || true)"

block="$MARK_BEGIN
0 1 * * * $POWER off
0 6 * * * $POWER on
@reboot $POWER on
$MARK_END"

printf '%s\n%s\n' "$existing" "$block" | crontab -

echo "Installed Dorm Wire display-sleep cron:"
crontab -l | sed -n "/$MARK_BEGIN/,/$MARK_END/p"
