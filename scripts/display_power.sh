#!/usr/bin/env bash
# Turn the TV/HDMI output off or on WITHOUT powering the Pi down.
# Usage: display_power.sh off | on
#
# Tries, in order: HDMI-CEC (turns the actual TV to standby/on), then the
# Wayland compositor power control (wlr-randr), then legacy vcgencmd. This
# covers Raspberry Pi OS Bookworm (Wayland) and older releases. The Pi keeps
# running so the kiosk browser and Flask stay up; only the panel sleeps.

set -u
ACTION="${1:-}"

log(){ echo "[display_power] $*"; }

case "$ACTION" in
  off|on) ;;
  *) echo "Usage: $0 off|on" >&2; exit 2 ;;
esac

did_something=0

# 1) HDMI-CEC: put the TV itself into standby / wake it. Address 0 = TV.
if command -v cec-client >/dev/null 2>&1; then
  if [ "$ACTION" = "off" ]; then
    echo 'standby 0' | cec-client -s -d 1 >/dev/null 2>&1 && did_something=1
  else
    echo 'on 0' | cec-client -s -d 1 >/dev/null 2>&1 && did_something=1
  fi
  log "cec-client $ACTION sent"
fi

# 2) Wayland (labwc/wayfire on Bookworm): blank/unblank the output.
if command -v wlr-randr >/dev/null 2>&1; then
  OUT="$(wlr-randr 2>/dev/null | awk 'NR==1{print $1}')"
  if [ -n "${OUT:-}" ]; then
    if [ "$ACTION" = "off" ]; then
      wlr-randr --output "$OUT" --off >/dev/null 2>&1 && did_something=1
    else
      wlr-randr --output "$OUT" --on >/dev/null 2>&1 && did_something=1
    fi
    log "wlr-randr $OUT --$ACTION"
  fi
fi

# 3) Legacy fallback (pre-Wayland): vcgencmd display_power 0|1.
if [ "$did_something" -eq 0 ] && command -v vcgencmd >/dev/null 2>&1; then
  if [ "$ACTION" = "off" ]; then
    vcgencmd display_power 0 >/dev/null 2>&1 && did_something=1
  else
    vcgencmd display_power 1 >/dev/null 2>&1 && did_something=1
  fi
  log "vcgencmd display_power $ACTION"
fi

if [ "$did_something" -eq 0 ]; then
  log "WARNING: no display-power tool succeeded (install cec-utils or wlr-randr)"
  exit 1
fi
exit 0
