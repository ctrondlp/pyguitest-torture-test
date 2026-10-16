#!/usr/bin/env bash
# Stop a test box from locking, blanking or sleeping while a driver runs.
#
# A locked session looks exactly like a broken driver on every platform
# here: the Mac keeps listing windows while its AX tree goes empty, Hyprland
# answers `ok` to every focus dispatch while `activewindow` stays `Invalid`,
# and nothing in either compositor's IPC says "locked". Run this once, as
# the desktop user, inside (or with the environment of) the graphical
# session; it is idempotent and prints what it changed. It does not unlock
# anything -- that is PAM's job, at the console.
#
# Windows has its own: scripts/disable-idle-lock.cmd.

set -u

say() { printf '%s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# gsettings/xfconf need the session bus; plain ssh does not have it. The
# runtime dir is /run/user on Linux and /var/run/user on FreeBSD -- dconf
# writes there, so point both variables at the one that holds the bus.
for dir in "/run/user/$(id -u)" "/var/run/user/$(id -u)"; do
  if [ -S "$dir/bus" ]; then
    export XDG_RUNTIME_DIR="$dir"
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$dir/bus}"
    break
  fi
done

gset() { # schema key value -- set and echo the result, skip a missing schema
  if gsettings list-schemas 2>/dev/null | grep -qx "$1"; then
    gsettings set "$1" "$2" "$3" && say "  $1 $2 = $(gsettings get "$1" "$2")"
  fi
}

done_something=0

# --- Omarchy (Hyprland, quickshell-based omarchy-shell) -------------------
# Verified 2026-10-15 on the .82 box. The shell's own idle service locks
# after `idle.lock` seconds (300 by default, ~/.config/omarchy/shell.json);
# its stay-awake state file cancels the whole idle cycle -- screensaver,
# lock and display-off -- and survives reboots.
if have omarchy-toggle-idle; then
  say "Omarchy: enabling stay-awake (cancels the shell's idle cycle)"
  omarchy-toggle-idle stay-awake >/dev/null
  say "  $(omarchy-toggle-idle status)"
  if [ -n "${OMARCHY_PATH:-/usr/share/omarchy}" ] && have omarchy-shell; then
    locked=$(OMARCHY_PATH="${OMARCHY_PATH:-/usr/share/omarchy}" omarchy-shell lock isLocked 2>/dev/null || true)
    say "  session currently locked: ${locked:-unknown}"
    case "$locked" in
      true|True) say "  -> unlock once at the console; it will not lock again" ;;
    esac
  fi
  done_something=1
fi

# --- Generic Wayland idle daemons (hypridle / swayidle) -------------------
# Not used by Omarchy (its shell does the job above) or by the KaOS/niri box
# (noctalia-shell, no idle daemon at all, checked 2026-10-15); here for a
# box that grows one.
for unit in hypridle swayidle; do
  if have systemctl && systemctl --user is-active --quiet "$unit" 2>/dev/null; then
    say "$unit: disabling the user unit"
    systemctl --user disable --now "$unit" && say "  stopped and disabled"
    done_something=1
  elif pgrep -x "$unit" >/dev/null 2>&1; then
    say "$unit: running without a unit -- killing it (restart your session's autostart to undo)"
    pkill -x "$unit" && say "  killed"
    done_something=1
  fi
done

# --- MATE (GhostBSD .77) ---------------------------------------------------
# Verified 2026-10-15: these were already off there.
if pgrep -x mate-session >/dev/null 2>&1 || pgrep -x mate-screensaver >/dev/null 2>&1; then
  say "MATE: disabling screensaver, lock and display sleep"
  gset org.mate.screensaver idle-activation-enabled false
  gset org.mate.screensaver lock-enabled false
  gset org.mate.power-manager lock-blank-screen false
  gset org.mate.power-manager sleep-display-ac 0
  gset org.mate.power-manager sleep-computer-ac 0
  done_something=1
fi

# --- GNOME ------------------------------------------------------------------
if pgrep -x gnome-shell >/dev/null 2>&1; then
  say "GNOME: disabling screen lock, idle blank and sleep"
  gset org.gnome.desktop.screensaver lock-enabled false
  gset org.gnome.desktop.screensaver idle-activation-enabled false
  gset org.gnome.desktop.session idle-delay 'uint32 0'
  gset org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type "'nothing'"
  gset org.gnome.settings-daemon.plugins.power idle-dim false
  done_something=1
fi

# --- Xfce -------------------------------------------------------------------
if pgrep -x xfce4-session >/dev/null 2>&1 && have xfconf-query; then
  say "Xfce: disabling screensaver, lock and DPMS"
  xfconf-query -c xfce4-screensaver -p /saver/enabled -n -t bool -s false
  xfconf-query -c xfce4-screensaver -p /lock/enabled -n -t bool -s false
  xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -n -t bool -s false
  xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/blank-on-ac -n -t int -s 0
  xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/inactivity-on-ac -n -t int -s 14
  pgrep -x light-locker >/dev/null 2>&1 && pkill -x light-locker && say "  killed light-locker"
  say "  done"
  done_something=1
fi

# --- KDE Plasma ------------------------------------------------------------
if pgrep -x plasmashell >/dev/null 2>&1; then
  kw=kwriteconfig6; have "$kw" || kw=kwriteconfig5
  if have "$kw"; then
    say "KDE: disabling autolock and idle actions"
    "$kw" --file kscreenlockerrc --group Daemon --key Autolock false
    "$kw" --file kscreenlockerrc --group Daemon --key LockOnResume false
    "$kw" --file powerdevilrc --group AC --group Display --key TurnOffDisplayIdleTimeoutSec -- -1
    "$kw" --file powerdevilrc --group AC --group SuspendAndShutdown --key AutoSuspendAction 0
    have qdbus6 && qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1
    say "  done (log out/in if the lock still fires)"
    done_something=1
  fi
fi

# --- COSMIC (Pop!_OS .79) --------------------------------------------------
# UNVERIFIED: the box was off when this was written. cosmic-idle reads its
# config from these one-value-per-file entries; `None` means "never".
if pgrep -x cosmic-comp >/dev/null 2>&1; then
  idle_dir="$HOME/.config/cosmic/com.system76.CosmicIdle/v1"
  say "COSMIC: setting screen-off and suspend to never in $idle_dir (unverified path)"
  mkdir -p "$idle_dir"
  for key in screen_off_time suspend_on_ac_time suspend_on_battery_time; do
    printf 'None' >"$idle_dir/$key" && say "  $key = None"
  done
  say "  screen *lock* lives in COSMIC Settings > Desktop > Screen Lock; check it there"
  done_something=1
fi

# --- X11 server-side blanking (any X session) -----------------------------
if [ -n "${DISPLAY:-}" ] && have xset; then
  xset s off -dpms 2>/dev/null && say "X11: xset s off -dpms"
fi

# --- macOS (.36) -----------------------------------------------------------
if [ "$(uname -s)" = Darwin ]; then
  say "macOS: screensaver never, display/system sleep never"
  defaults -currentHost write com.apple.screensaver idleTime -int 0
  say "  com.apple.screensaver idleTime = $(defaults -currentHost read com.apple.screensaver idleTime)"
  say "  pmset needs sudo (you will be prompted):"
  sudo pmset -a displaysleep 0 sleep 0 disksleep 0 && say "  $(pmset -g custom | grep -E ' (sleep|displaysleep)' | tr -s ' ' | tr '\n' ';')"
  say "  'Require password after screensaver' is PAM-side: run"
  say "    sysadminctl -screenLock off -password -"
  say "  yourself if the Mac still asks for one after blanking."
  done_something=1
fi

if [ "$done_something" = 0 ]; then
  say "nothing recognised to change on this box"
  say "  (no omarchy-shell, hypridle/swayidle, MATE, GNOME, Xfce, KDE, COSMIC or macOS session found)"
  if have niri; then
    say "  niri itself never locks; a locker would be a separate process -- none is running"
  fi
fi
