#!/bin/bash
# Set this Ubuntu box up to run pyguitest and the Qt torture-test fixture.
#
# Everything here is user-level: no sudo, no apt. Run it again any time --
# each step checks before acting.
#
# Why not apt: this box (Ubuntu 26.10, python 3.14.8) has no pip, no
# ensurepip, no virtualenv, no pipx, no uv and no curl, so the usual
# `python3 -m venv` fails with "ensurepip is not available". The venv is
# therefore built with --without-pip and pip is bootstrapped into it with
# Python's own urllib. apt would want root for python3.14-venv, and its
# python3-dogtail is 1.0.7 against 2.1.0 on PyPI.
#
#   --system-site-packages, deliberately: PyGObject (`gi`) comes from the
#   distro (python3-gi) and is painful to build in a venv, while dogtail
#   needs it. Inheriting the system packages gets `gi` for free and PySide6
#   / dogtail / pytest sit on top from PyPI.
#
# Checked on this box 2026-10-15: PySide6 ships its own Qt 6.12.0, so the
# fixture does not depend on the distro's Qt version at all.

set -u
VENV=$HOME/tt-venv
PY=$VENV/bin/python

say() { printf '%s\n' "$*"; }

# --- 1. the venv ------------------------------------------------------------
if [ -x "$PY" ]; then
  say "venv: already at $VENV ($("$PY" -V 2>&1))"
else
  say "venv: creating $VENV (--system-site-packages, --without-pip)"
  python3 -m venv --system-site-packages --without-pip "$VENV" || {
    say "  FAILED. If this complains about ensurepip, that is expected and"
    say "  handled -- but a hard failure here needs: sudo apt install python3-venv"
    exit 1
  }
fi

# --- 2. pip, bootstrapped without curl/ensurepip ----------------------------
if "$PY" -m pip --version >/dev/null 2>&1; then
  say "pip: $("$PY" -m pip --version)"
else
  say "pip: bootstrapping with urllib (no curl on this box)"
  "$PY" - <<'EOF' || exit 1
import urllib.request
url = "https://bootstrap.pypa.io/get-pip.py"
data = urllib.request.urlopen(url, timeout=30).read()
with open("/tmp/get-pip.py", "wb") as f:
    f.write(data)
print(f"  fetched {len(data)} bytes")
EOF
  "$PY" /tmp/get-pip.py --quiet || exit 1
  say "  $("$PY" -m pip --version)"
fi

# --- 3. the packages --------------------------------------------------------
# pyside6 for the fixture, dogtail for pyguitest's AT-SPI backend, pytest to
# run pyguitest's own suite on the box.
missing=""
for mod in PySide6 dogtail pytest; do
  "$PY" -c "import $mod" >/dev/null 2>&1 || missing="$missing $mod"
done
if [ -n "$missing" ]; then
  say "packages: installing$missing"
  "$PY" -m pip install --quiet pyside6 dogtail pytest || exit 1
else
  say "packages: PySide6, dogtail and pytest already present"
fi

# --- 4. accessibility -------------------------------------------------------
# Without this no GTK or Qt application publishes an AT-SPI tree at all, and
# a torture-test run reports "NO CONTROLS FOUND" with the window plainly on
# screen. It was false on this box, and on Debian .78.
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"
if command -v gsettings >/dev/null 2>&1; then
  current=$(gsettings get org.gnome.desktop.interface toolkit-accessibility 2>/dev/null)
  if [ "$current" = "true" ]; then
    say "accessibility: toolkit-accessibility already true"
  else
    gsettings set org.gnome.desktop.interface toolkit-accessibility true &&
      say "accessibility: toolkit-accessibility -> true (was $current)"
  fi
fi

# --- 5. report --------------------------------------------------------------
say ""
say "--- versions"
"$PY" - <<'EOF'
import sys
print(f"  python   {sys.version.split()[0]}")
try:
    from PySide6.QtCore import qVersion
    import PySide6
    print(f"  PySide6  {PySide6.__version__} (bundled Qt {qVersion()})")
except Exception as exc:
    print(f"  PySide6  FAILED: {exc}")
for mod in ("gi", "dogtail.tree", "pytest"):
    try:
        __import__(mod)
        print(f"  {mod:8s} ok")
    except Exception as exc:
        print(f"  {mod:8s} FAILED: {type(exc).__name__}: {exc}")
EOF

say ""
say "To run the torture test (from the pyguitest-torture-test repo):"
say "  scripts/run-box-tests.sh debian.py        # after deploying to /tmp/tt-run"
say ""
say "Remaining gotchas on a GNOME Wayland box, both handled by that script:"
say "  * export XDG_CURRENT_DESKTOP, or pyguitest's doctor reports"
say "    'compositor other', the gnomeshell backend never joins, and on"
say "    Wayland that silently costs ELEMENT_GEOMETRY."
say "  * keep the session unlocked and awake (scripts/disable-idle-lock.sh)."
