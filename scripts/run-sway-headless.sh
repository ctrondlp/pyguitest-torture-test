#!/bin/bash
# Boot a headless sway and run the sway torture driver inside it.
# Usage: run-sway-headless.sh [python] [extra driver args...]
#
# Needs: sway, wtype (keyboard injection -- sway's zwp_virtual_keyboard_v1;
# uinput must NOT be used here, a headless sway has no seat and a uinput
# device would type into the live desktop instead), and an interpreter with
# pyguitest + PySide6 (defaults to ~/code/.venv/bin/python, then python3).
#
# The compositor is private to this run: a throwaway config with no bars,
# no idle and no outputs beyond the headless default, torn down on exit.
set -eu
PY=${1:-}
if [ -z "$PY" ]; then
  PY=$HOME/code/.venv/bin/python
  [ -x "$PY" ] || PY=python3
else
  shift
fi
HERE=$(cd "$(dirname "$0")/.." && pwd)

CONF=$(mktemp)
RUNDIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
cat >"$CONF" <<'EOF'
# Throwaway config for the torture run: nothing but defaults.
output HEADLESS-1 resolution 1920x1080
EOF

cleanup() {
  [ -n "${SWAY_PID:-}" ] && kill "$SWAY_PID" 2>/dev/null
  rm -f "$CONF"
}
trap cleanup EXIT

# Discover the wayland socket sway picks by diffing before/after: a headless
# sway chooses the first free wayland-N itself and exports it only to the
# clients it spawns, never to this outer shell.
before=$(ls "$RUNDIR"/wayland-* 2>/dev/null | grep -v '\.lock$' || true)
WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 \
  sway -c "$CONF" >/tmp/tt-sway.log 2>&1 &
SWAY_PID=$!
for _ in $(seq 1 50); do
  sleep 0.2
  after=$(ls "$RUNDIR"/wayland-* 2>/dev/null | grep -v '\.lock$' || true)
  NEW=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  [ -n "$NEW" ] && break
done
if [ -z "${NEW:-}" ]; then
  echo "headless sway never created a wayland socket; see /tmp/tt-sway.log" >&2
  exit 1
fi
export WAYLAND_DISPLAY=$(basename "$NEW")
export XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=sway
for _ in $(seq 1 50); do
  SOCK=$(ls -t "$RUNDIR"/sway-ipc.*.sock 2>/dev/null | head -1)
  [ -S "${SOCK:-/nonexistent}" ] && break
  sleep 0.2
done
if [ ! -S "${SOCK:-/nonexistent}" ]; then
  echo "no sway IPC socket appeared; see /tmp/tt-sway.log" >&2
  exit 1
fi
export SWAYSOCK=$SOCK
unset DISPLAY NO_AT_BRIDGE
echo "== headless sway up: WAYLAND_DISPLAY=$WAYLAND_DISPLAY SWAYSOCK=$SWAYSOCK"
if ! command -v wtype >/dev/null; then
  # A refusal, not a warning: without wtype, pyguitest's input selection
  # falls through to uinput, and a uinput device created against a headless
  # (seat-less) sway attaches to the LIVE desktop's libinput -- the torture
  # run would type into the user's own session.
  echo "wtype is not installed; refusing to run against a headless sway" >&2
  echo "(install it: sudo dnf install wtype)" >&2
  exit 1
fi

exec "$PY" "$HERE/drivers/sway.py" "$@"
