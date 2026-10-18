#!/bin/bash
# Run the pyguitest unit suite + one torture-test driver from /tmp/tt-run.
# Usage: run-box-tests.sh <driver.py> [session-type]
# Expects /tmp/tt-run to already hold pyguitest/, pyguitest-tests/,
# torture_test/, tests/test_app.py, the driver, and driver_core.py (the
# shared module the Linux-family drivers and bsd.py import, which must sit
# flat next to the driver script).
set -u
DRV=${1:?driver}
PY=$HOME/code/.venv/bin/python
[ -x "$PY" ] || PY=$HOME/tt-venv/bin/python
[ -x "$PY" ] || PY=python3

# Land on the graphical session: a plain ssh shell has none of this. Take
# the variables from the compositor's own process rather than guessing --
# XDG_CURRENT_DESKTOP in particular, because without it pyguitest's doctor
# reports `compositor other`, no compositor backend is selected, and on
# Wayland that costs ELEMENT_GEOMETRY (AT-SPI rectangles are
# window-relative there, so geometry is only advertised once a window
# source like the gnomeshell extension is wired in). Measured on Debian:
# every control then fails the driver's extents() filter and the run says
# "NO CONTROLS FOUND".
U=$(id -u)
for d in "/run/user/$U" "/var/run/user/$U"; do
  [ -d "$d" ] || continue
  export XDG_RUNTIME_DIR="$d"
  [ -S "$d/bus" ] && export DBUS_SESSION_BUS_ADDRESS="unix:path=$d/bus"
  break
done
session_env() { # $1 = pid -> one VAR=VALUE per line
  if [ -r "/proc/$1/environ" ]; then
    tr '\0' '\n' <"/proc/$1/environ"
  elif command -v procstat >/dev/null 2>&1; then
    # FreeBSD/GhostBSD: no /proc/<pid>/environ. Its XDG_RUNTIME_DIR is
    # /var/run/xdg/<user> and its session bus a /tmp/dbus-* socket, so
    # guessing /run/user/$(id -u) hands the fixture a bus that does not
    # exist -- the Qt app then registers with nothing and publishes no
    # AT-SPI at all, for a verdict of "NO CONTROLS FOUND".
    procstat -e "$1" 2>/dev/null | tr ' ' '\n'
  fi
}

for comp in gnome-shell cosmic-comp Hyprland niri sway kwin_wayland marco \
            xfwm4 mutter plasmashell kwin_x11 mate-session cinnamon muffin; do
  cpid=$(pgrep -u "$U" -x "$comp" 2>/dev/null | head -1)
  [ -n "$cpid" ] || continue
  env_dump=$(session_env "$cpid")
  [ -n "$env_dump" ] || continue
  for var in XDG_CURRENT_DESKTOP XDG_SESSION_TYPE XDG_RUNTIME_DIR \
             WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS \
             HYPRLAND_INSTANCE_SIGNATURE NIRI_SOCKET SWAYSOCK AT_SPI_BUS; do
    val=$(printf '%s\n' "$env_dump" | grep "^$var=" | head -1 | cut -d= -f2-)
    [ -n "$val" ] && export "$var=$val"
  done
  echo "== session env taken from $comp (pid $cpid)"
  break
done
# niri and sway hand their IPC socket to the clients they spawn, so the
# compositor's own environment does not carry it and an ssh shell has no
# way to inherit it. Without NIRI_SOCKET `ipc.py` refuses, the niri backend
# never joins the composite, and on Wayland that costs ELEMENT_GEOMETRY --
# `extents()` then refuses every control and the run reports "NO CONTROLS
# FOUND" with the fixture publishing 60 buttons perfectly well.
if [ -z "${NIRI_SOCKET:-}" ]; then
  for s in "$XDG_RUNTIME_DIR"/niri.*.sock; do
    [ -S "$s" ] && export NIRI_SOCKET="$s" && break
  done
fi
if [ -z "${SWAYSOCK:-}" ]; then
  for s in "$XDG_RUNTIME_DIR"/sway-ipc.*.sock; do
    [ -S "$s" ] && export SWAYSOCK="$s" && break
  done
fi
# Hyprland generates a per-session instance signature and hands it only to the
# clients it spawns, so -- exactly like niri's and sway's IPC sockets above --
# the compositor's own environment does not carry it and an ssh shell cannot
# inherit it. Without HYPRLAND_INSTANCE_SIGNATURE pyguitest selects the generic
# `wlroots` backend instead of the dedicated `hyprland` one, whose window
# activation does not reliably grab keyboard focus; `seek_focus` then exhausts
# its budget and every keyboard-driven control fails, each run grinding to the
# 900 s cap. Confirmed live on Omarchy (2026-10-17): with it set the composite
# becomes hyprland+... and typing/Tab land; without it, 11 controls miss. The
# signature is the name of the live directory under $XDG_RUNTIME_DIR/hypr.
if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && [ -d "$XDG_RUNTIME_DIR/hypr" ]; then
  sig=$(ls -t "$XDG_RUNTIME_DIR/hypr" 2>/dev/null | head -1)
  [ -n "$sig" ] && export HYPRLAND_INSTANCE_SIGNATURE="$sig"
fi

# Fallbacks for a box with no readable compositor environ (FreeBSD has no
# /proc/<pid>/environ at all).
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ]; then
  for w in "$XDG_RUNTIME_DIR"/wayland-[0-9]*; do
    case "$w" in *.lock) continue ;; esac
    [ -S "$w" ] && export WAYLAND_DISPLAY=$(basename "$w") XDG_SESSION_TYPE=wayland
  done
  [ -n "${WAYLAND_DISPLAY:-}" ] || export DISPLAY=:0 XDG_SESSION_TYPE=x11
fi
export PYTHONPATH=/tmp/tt-run
export TORTURE_APP_DIR=/tmp/tt-run
export TORTURE_APP_PYTHON=$PY
unset NO_AT_BRIDGE
# A box that could not apt-install a Qt runtime dependency (no sudo) may have
# it extracted under ~/xcbcursor from a user-level `apt-get download` + `dpkg
# -x`; PySide6's xcb platform plugin needs libxcb-cursor0 from 6.5 on. Adding
# it here is harmless where the directory does not exist.
for d in "$HOME"/xcbcursor/usr/lib/*/; do
  [ -d "$d" ] && export LD_LIBRARY_PATH="$d${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
done
cd /tmp/tt-run || exit 1

echo "== interpreter: $($PY -V 2>&1), pyguitest $($PY -c 'import pyguitest;print(pyguitest.__version__)')"
echo "== session: type=${XDG_SESSION_TYPE:-?} desktop=${XDG_CURRENT_DESKTOP:-none} wayland=${WAYLAND_DISPLAY:-none} display=${DISPLAY:-none}"
echo "== doctor: $($PY -m pyguitest doctor 2>/dev/null | head -3 | tr '\n' ' ')"

echo "== unit suite"
# test_docs/test_api_docs read README.md and docs/ from the repo root, and
# only source+tests are deployed to a box (deliberately), so they error at
# collection and take the whole run with them. test_style wants the src/
# layout for the same reason.
$PY -m pytest pyguitest-tests -q \
  --ignore=pyguitest-tests/test_docs.py \
  --ignore=pyguitest-tests/test_api_docs.py \
  --ignore=pyguitest-tests/test_style.py 2>&1 | tail -4

# RUNS: how many back-to-back torture runs to do (default 1). A multi-run
# campaign checks stability -- same verdict every time, or flaky -- rather
# than trusting a single pass. Each run gets a fresh app (the driver launches
# and tears down its own), and its own log driver_run<N>.log.
RUNS=${RUNS:-${2:-1}}
echo "== torture test ($DRV), $RUNS run(s)"
summary=""
for run in $(seq 1 "$RUNS"); do
  pkill -f "[t]orture_test" 2>/dev/null
  log="driver_run${run}.log"
  SECONDS=0
  timeout 900 "$PY" "$DRV" ${TORTURE_DRIVER_ARGS:-} >"$log" 2>&1
  code=$?
  dur=$SECONDS
  verdict=$(grep -m1 -E "all controls verified|NO CONTROLS|PARTIAL COVERAGE|STATUS CHECK FAILED" "$log" | sed 's/^[0-9]*://')
  fails=$(grep -cE "^\s+- " "$log")
  echo "-- run $run: exit=$code after ${dur}s | ${verdict:-(no verdict)} | $fails failure line(s)"
  grep -nE "STATUS CHECK FAILED|Traceback|Segmentation|NO CONTROLS" "$log" | head -3
  grep -E "^\s+- " "$log" | head -8
  summary="${summary}run ${run}: exit=${code} ${dur}s ${verdict}
"
  pkill -f "[t]orture_test" 2>/dev/null
done
echo "== campaign summary ($DRV) =="
printf '%s' "$summary"
pgrep -f "[t]orture_test" >/dev/null || echo "app-closed"
