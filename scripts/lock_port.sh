#!/usr/bin/env bash
# Restrict the Dorm Wire port to loopback + Tailscale only.
#
# The app binds 0.0.0.0 so the phone remote can reach it, but the board has no
# authentication — on a campus network that would let anyone on the same SSID
# control the TV. These rules allow the kiosk (loopback) and your own tailnet,
# and drop everything else. Only port 5000 is touched, so SSH is unaffected.
set -euo pipefail
PORT=5000
# run iptables directly when we are already root (systemd), else via sudo
IPT="iptables"; [ "$(id -u)" -eq 0 ] || IPT="sudo iptables"
add() {  # add rule only if it isn't already present
  $IPT -C "$@" 2>/dev/null || $IPT -A "$@"
}
add INPUT -p tcp --dport "$PORT" -i lo -j ACCEPT
add INPUT -p tcp --dport "$PORT" -i tailscale0 -j ACCEPT
add INPUT -p tcp --dport "$PORT" -j DROP
echo "Rules for port $PORT:"
$IPT -L INPUT -n --line-numbers | grep ":$PORT" || true
