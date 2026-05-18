#!/usr/bin/env bash
set -euo pipefail

# Pulls the latest GitHub version, refreshes Python packages, and restarts the app.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
SERVICE_NAME="dorm-sports-wire"

cd "$PROJECT_DIR"

echo "Pulling latest code..."
git pull

if [ ! -d "$VENV_DIR" ]; then
  echo "Virtual environment missing; creating it now..."
  python3 -m venv "$VENV_DIR"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

echo "Restarting service..."
sudo systemctl restart "${SERVICE_NAME}.service"

echo
echo "Update complete."
echo "Check it with:"
echo "  systemctl status ${SERVICE_NAME}.service"
