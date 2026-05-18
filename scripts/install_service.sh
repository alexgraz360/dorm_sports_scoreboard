#!/usr/bin/env bash
set -euo pipefail

# Installs Dorm Sports Wire as a systemd service so the Flask app starts on boot.

SERVICE_NAME="dorm-sports-wire"
PROJECT_DIR="$HOME/dorm_sports_scoreboard"
SERVICE_TEMPLATE="$PROJECT_DIR/services/${SERVICE_NAME}.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CURRENT_USER="$(whoami)"

if [ ! -x "$PROJECT_DIR/.venv/bin/python" ]; then
  echo "Virtual environment not found. Run ./scripts/pi_setup.sh first."
  exit 1
fi

if [ ! -f "$SERVICE_TEMPLATE" ]; then
  echo "Service template not found: $SERVICE_TEMPLATE"
  exit 1
fi

echo "Installing systemd service for user: $CURRENT_USER"
echo "Project directory: $PROJECT_DIR"

TMP_SERVICE="$(mktemp)"
sed \
  -e "s|__USER__|$CURRENT_USER|g" \
  -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
  "$SERVICE_TEMPLATE" > "$TMP_SERVICE"

sudo cp "$TMP_SERVICE" "$SERVICE_FILE"
rm "$TMP_SERVICE"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo
echo "Service installed and started."
echo "Check it with:"
echo "  systemctl status ${SERVICE_NAME}.service"
echo "  journalctl -u ${SERVICE_NAME}.service -f"
