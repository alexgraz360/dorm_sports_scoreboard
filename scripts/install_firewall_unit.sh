#!/usr/bin/env bash
# Re-apply the port lockdown on every boot.
#
# iptables rules live in memory, so without this a reboot silently reopens port
# 5000 to the whole campus network. Runs after Tailscale is up so the
# tailscale0 rule matches a live interface.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT=/etc/systemd/system/dorm-wire-firewall.service

sudo tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=Dorm Wire: restrict port 5000 to loopback + Tailscale
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash $SCRIPT_DIR/lock_port.sh

[Install]
WantedBy=multi-user.target
UNITEOF

sudo systemctl daemon-reload
sudo systemctl enable --now dorm-wire-firewall.service
echo "Installed. Status:"
systemctl is-enabled dorm-wire-firewall.service
systemctl is-active dorm-wire-firewall.service
