#!/usr/bin/env python3
"""Drive the torture-test app under a headless sway (wlroots) session.

UNVALIDATED: no full run has been recorded in VALIDATION.md yet. Written
2026-10-18 as the first wlroots-family torture driver; sway was the only
desktop validated for pyguitest itself (7/7, headless, 2026-09-22) with no
torture driver at all. Run it through `scripts/run-sway-headless.sh`, which
boots the headless compositor, discovers its sockets, and sets the session
environment this driver inherits.

What is known going in, and what is not:

- A headless sway (`WLR_BACKENDS=headless`) has NO input devices and no
  seat hardware, so uinput/ydotool are not merely unavailable -- a uinput
  device created here would attach to the *live* desktop's libinput and
  type into the user's own session. Keyboard injection must go through
  sway's `zwp_virtual_keyboard_v1` protocol, i.e. pyguitest's tool input
  backend running `wtype`. **wtype must be installed** or every
  keyboard-driven control will fail honestly.
- AT-SPI is session-global: the Qt fixture launched inside sway registers
  on the same user a11y bus this driver reads, exactly as on every other
  Linux box. Element actions (`Element.click()`) need no compositor
  cooperation at all.
- sway's IPC tree carries a real pid per view, so `windows_by_pid=True` is
  expected to hold -- unverified live, which is half of why this driver is
  marked unvalidated.
"""

from __future__ import annotations

import sys

from driver_core import Platform, run

# The backend list is forced rather than auto-selected: measured live that
# a headless sway nested inside a live GNOME session loses window-backend
# selection to the outer desktop (gui.windows() answered with the GNOME
# session's windows), and the sequence form fails loudly if the sway IPC
# socket is missing instead of quietly substituting another backend.
# "windows" is the registered name of pyguitest's whole window tier -- one
# factory that picks Sway/Hyprland/niri/KWin/... from the detected
# compositor, so there is no "sway" spelling to name here. That selection
# reads XDG_CURRENT_DESKTOP *and* XDG_SESSION_DESKTOP/DESKTOP_SESSION, and
# "gnome" in any of them outranks the wlroots hints -- which is the actual
# mechanism of the nested-selection failure above, and why the runner must
# override all three, not just XDG_CURRENT_DESKTOP.
# "input" is pyguitest's input factory, which on a wlroots session with
# wtype installed resolves to the virtual-keyboard route this driver needs.
PLATFORM = Platform(name="sway-headless", backends=("windows", "atspi", "input"))

if __name__ == "__main__":
    sys.exit(run(PLATFORM))
