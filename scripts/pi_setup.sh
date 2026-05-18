#!/usr/bin/env bash
set -euo pipefail

# Installs the basic system and Python dependencies needed by Dorm Sports Wire.
# Run this from the cloned project folder on Raspberry Pi OS Desktop.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo "Dorm Sports Wire setup"
echo "Project directory: $PROJECT_DIR"

echo
echo "Installing Raspberry Pi OS packages..."
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

if ! command -v chromium-browser >/dev/null 2>&1 && ! command -v chromium >/dev/null 2>&1; then
  echo "Installing Chromium..."
  sudo apt install -y chromium-browser || sudo apt install -y chromium
fi

echo
echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

echo
echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

echo
echo "Setup complete."
echo "Manual test:"
echo "  $VENV_DIR/bin/python $PROJECT_DIR/app.py"
echo "Then open http://127.0.0.1:5000"
