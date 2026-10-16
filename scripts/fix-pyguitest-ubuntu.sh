#!/bin/bash
# Make this Ubuntu box able to run the pyguitest torture test.
#
# Two things were missing when this was written (2026-10-15), and they fail
# in different ways:
#
#   1. No input. A run dies with
#        pyguitest.errors.CapabilityUnsupported: KEY_EVENT is unsupported on atspi
#      because no input backend joined: /dev/uinput here is
#        crw------- 1 root root  /dev/uinput
#      with no group and no ACL, so this user cannot open it, and
#      `pyguitest doctor` offers only "libei (opt-in)".
#
#   2. No window capabilities. Mutter implements no foreign-toplevel
#      protocol, so pyguitest gets window geometry from its own GNOME Shell
#      extension. Without it, ELEMENT_GEOMETRY is unavailable on Wayland
#      (AT-SPI rectangles there are window-relative and need a real window
#      position added), and a run reports "NO CONTROLS FOUND" with the
#      fixture plainly on screen.
#
# This script fixes (2) outright -- a GNOME Shell extension installs into
# your home directory, no root -- and probes (1), recording the answer for
# scripts/run-box-tests.sh. Re-runnable.
#
# If you would rather have uinput than libei (it is what the other Linux
# boxes in this fleet use), that needs root once:
#
#   sudo groupadd -f input
#   sudo usermod -aG input "$USER"
#   printf 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"\n' \
#     | sudo tee /etc/udev/rules.d/99-pyguitest-uinput.rules
#   sudo udevadm control --reload-rules && sudo udevadm trigger
#   # log out and back in for the group to take effect
#
# or, for this boot only:  sudo setfacl -m "u:$USER:rw" /dev/uinput

set -u
PY=$HOME/tt-venv/bin/python
[ -x "$PY" ] || PY=$(command -v python3)
OUT=$HOME/.pyguitest-input-backend
EXT_ID="pyguitest-window-control@pyguitest.local"
EXT_SRC="${PYGUITEST_EXT_DIR:-/tmp/$EXT_ID}"
EXT_DST="$HOME/.local/share/gnome-shell/extensions/$EXT_ID"

say() { printf '%s\n' "$*"; }

# The graphical session's own environment: an ssh shell has none of it, and
# without XDG_CURRENT_DESKTOP pyguitest cannot tell this is GNOME.
U=$(id -u)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$U}"
[ -S "$XDG_RUNTIME_DIR/bus" ] &&
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
cpid=$(pgrep -u "$U" -x gnome-shell | head -1)
if [ -n "$cpid" ] && [ -r "/proc/$cpid/environ" ]; then
  for var in XDG_CURRENT_DESKTOP XDG_SESSION_TYPE WAYLAND_DISPLAY DISPLAY; do
    val=$(tr '\0' '\n' <"/proc/$cpid/environ" | grep "^$var=" | head -1 | cut -d= -f2-)
    [ -n "$val" ] && export "$var=$val"
  done
  say "session env taken from gnome-shell (pid $cpid)"
fi

# --- 1. the GNOME Shell extension (no root) ---------------------------------
say ""
say "--- window-control extension"
if [ -d "$EXT_DST" ]; then
  say "    already installed at $EXT_DST"
elif [ -d "$EXT_SRC" ]; then
  mkdir -p "$(dirname "$EXT_DST")"
  cp -r "$EXT_SRC" "$EXT_DST" && say "    installed from $EXT_SRC"
else
  say "    SOURCE MISSING: expected $EXT_SRC"
  say "    copy it from the pyguitest checkout:"
  say "      scp -r pyguitest/gnome-shell-extension/$EXT_ID <this box>:/tmp/"
  say "    or set PYGUITEST_EXT_DIR to where it is."
fi
if [ -d "$EXT_DST" ] && command -v gnome-extensions >/dev/null 2>&1; then
  state=$(gnome-extensions info "$EXT_ID" 2>/dev/null | sed -n 's/^ *State: *//p')
  say "    state: ${state:-unknown}"
  if [ "$state" != "ACTIVE" ]; then
    gnome-extensions enable "$EXT_ID" 2>&1 | sed 's/^/      /'
    sleep 1
    state=$(gnome-extensions info "$EXT_ID" 2>/dev/null | sed -n 's/^ *State: *//p')
    say "    state now: ${state:-unknown}"
  fi
fi
# Does the Shell actually answer on the extension's interface?
if gdbus call --session --dest org.gnome.Shell \
     --object-path /org/gnome/Shell/Extensions/Pyguitest \
     --method org.gnome.Shell.Extensions.Pyguitest.ListWindows \
     >/dev/null 2>&1; then
  say "    ListWindows: OK -- window capabilities available"
  ext_ok=yes
else
  say "    ListWindows: not answering yet."
  say "    On a Wayland session GNOME Shell cannot be restarted in place, so a"
  say "    freshly installed extension usually needs a LOG OUT AND BACK IN."
  say "    Do that, then run this script again."
  ext_ok=no
fi

# --- 2. input ---------------------------------------------------------------
say ""
say "--- input"
ls -l /dev/uinput 2>&1 | sed 's/^/    /'
# The uinput backend needs python-evdev as well as a writable device, and
# evdev is a C extension: pip cannot build it here (no gcc, no Python
# headers), so it has to come from the distribution. The venv is created
# with --system-site-packages precisely so that works.
if ! "$PY" -c "import evdev" >/dev/null 2>&1; then
  say "    python-evdev is MISSING, so the uinput backend cannot load even"
  say "    with the device writable. pip cannot build it here (no gcc, no"
  say "    Python headers). One apt, no build, and the venv picks it up"
  say "    through --system-site-packages:"
  say ""
  say "        sudo apt install python3-evdev"
  say ""
else
  say "    python-evdev: $("$PY" -c 'import evdev; print(evdev.__version__)')"
fi
if [ -w /dev/uinput ] && "$PY" -c "import evdev" >/dev/null 2>&1; then
  say "    /dev/uinput is writable by you: uinput is used automatically."
  printf 'uinput\n' >"$OUT"
  say "    wrote $OUT"
else
  say "    /dev/uinput not writable by you -- trying libei instead."
  # atspi + eiinput only. Asking for gnomeshell here as well would fail for
  # its own reason (see part 1) and hide whether libei itself works.
  PYTHONPATH=/tmp/tt-run "$PY" - <<'EOF'
import sys
try:
    import pyguitest
    gui = pyguitest.connect(backend=["atspi", "eiinput"])
    caps = gui.capabilities
    caps = caps() if callable(caps) else caps
    names = sorted(getattr(c, "name", str(c)) for c in caps)
    print("    composite:", gui.backend.name)
    print("    KEY_EVENT:", "KEY_EVENT" in names)
    if "KEY_EVENT" not in names:
        sys.exit(2)
    gui.tap_key("Shift_L")      # types nothing, changes nothing
    print("    sent one Shift press through libei: OK")
    gui.close()
except SystemExit:
    raise
except Exception as exc:
    print(f"    eiinput failed -- {type(exc).__name__}: {exc}")
    sys.exit(3)
EOF
  if [ $? = 0 ]; then
    printf 'eiinput\n' >"$OUT"
    say "    libei works. Wrote 'eiinput' to $OUT."
  else
    say "    libei did not work either. Use the uinput steps in the comments"
    say "    at the top of this script (one sudo, then a re-login)."
    rm -f "$OUT"
  fi
fi

# --- 3. accessibility + report ----------------------------------------------
say ""
if command -v gsettings >/dev/null 2>&1; then
  cur=$(gsettings get org.gnome.desktop.interface toolkit-accessibility 2>/dev/null)
  if [ "$cur" != "true" ]; then
    gsettings set org.gnome.desktop.interface toolkit-accessibility true &&
      say "accessibility: toolkit-accessibility -> true (was $cur)"
  else
    say "accessibility: toolkit-accessibility already true"
  fi
fi

say ""
say "--- pyguitest doctor"
PYTHONPATH=/tmp/tt-run "$PY" -m pyguitest doctor 2>&1 | sed -n '1,6p' | sed 's/^/    /'
say ""
if [ "${ext_ok:-no}" = yes ] && [ -s "$OUT" ]; then
  say "READY: extension answering and input via $(cat "$OUT")."
else
  say "NOT READY yet -- see the notes above."
fi
