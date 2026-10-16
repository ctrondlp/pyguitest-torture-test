#!/bin/bash
# macOS: run the pyguitest unit suite + the torture-test driver from
# /tmp/tt-run. No DISPLAY/WAYLAND_DISPLAY is set -- this is Quartz/AX, and a
# stray DISPLAY would make pyguitest consider an X11 backend.
set -u
PY=$HOME/code/.venv/bin/python
[ -x "$PY" ] || PY=$(command -v python3)
export PYTHONPATH=/tmp/tt-run
export TORTURE_APP_DIR=/tmp/tt-run
export TORTURE_APP_PYTHON=$PY
cd /tmp/tt-run || exit 1

echo "== interpreter: $($PY -V 2>&1), pyguitest $($PY -c 'import pyguitest;print(pyguitest.__version__)')"
echo "== launchd domain here: $(launchctl managername 2>/dev/null)"
echo "== display power: $(pmset -g powerstate IODisplayWrangler 2>/dev/null | tail -1)"
echo "== accessibility trusted: $($PY -c 'import pyguitest; print(pyguitest.accessibility_trusted())' 2>&1 | tail -1)"
echo "== doctor: $($PY -m pyguitest doctor 2>/dev/null | head -4 | tr '\n' ' ')"

echo "== windows visible to the AX tree right now:"
$PY -c 'import pyguitest; g=pyguitest.connect(); print("  ", [(w.title, getattr(w,"pid",None)) for w in g.elements(role="window")][:6]); g.close()' 2>&1 | tail -2

echo "== unit suite"
$PY -m pytest pyguitest-tests -q 2>&1 | tail -4

echo "== torture test (macos.py)"
pkill -f "[t]orture_test" 2>/dev/null
SECONDS=0
"$PY" macos.py >driver_0171.log 2>&1
echo "exit=$? after ${SECONDS}s"
grep -n -E "STATUS CHECK|all controls verified|WARNING|NO CONTROLS|PARTIAL COVERAGE|Traceback" driver_0171.log
echo "-- tail:"
tail -22 driver_0171.log | cut -c1-170
pkill -f "[t]orture_test" 2>/dev/null
pgrep -f "[t]orture_test" >/dev/null || echo "app-closed"
