#!/usr/bin/env bash
set -euo pipefail

# Configures Raspberry Pi OS Desktop labwc autostart to open Chromium in kiosk mode.

if command -v chromium-browser >/dev/null 2>&1; then
  CHROMIUM_CMD="chromium-browser"
elif command -v chromium >/dev/null 2>&1; then
  CHROMIUM_CMD="chromium"
else
  echo "Chromium not found. Run ./scripts/pi_setup.sh first."
  exit 1
fi

AUTOSTART_DIR="$HOME/.config/labwc"
AUTOSTART_FILE="$AUTOSTART_DIR/autostart"

echo "Configuring Chromium kiosk autostart"
echo "Autostart file: $AUTOSTART_FILE"

mkdir -p "$AUTOSTART_DIR"

if [ -f "$AUTOSTART_FILE" ]; then
  cp "$AUTOSTART_FILE" "$AUTOSTART_FILE.backup.$(date +%Y%m%d%H%M%S)"
fi

cat > "$AUTOSTART_FILE" <<EOF
# Dorm Sports Wire kiosk autostart
# Used by current Raspberry Pi OS Desktop with labwc.
sleep 12
$CHROMIUM_CMD --kiosk --noerrdialogs --disable-infobars --no-first-run --start-maximized http://127.0.0.1:5000 &
EOF

echo
echo "Kiosk autostart installed."
echo "Reboot to test:"
echo "  sudo reboot"
