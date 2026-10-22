#!/usr/bin/env python3
"""Drive the torture-test app on KDE Plasma 6: atspi + uinput keyboard.

UNVALIDATED: no full run has been recorded in VALIDATION.md yet. Written
2026-10-21 against the Fedora 44 KDE box, the first KDE torture driver;
KDE was validated for pyguitest itself (Plasma 6, XWayland and a genuine
kwin_wayland login) with no torture driver at all.

What is known going in, from the box dossier and pyguitest's own source
rather than a completed run:

- `Window.pid` from the `kdotool` window backend does not exist at all:
  `KdotoolBackend.capabilities` subtracts `WINDOW_PID` (window ids are KWin
  UUIDs and kdotool offers no pid lookup), so every `gui.windows()` match
  here is by title, never pid -- `Platform(windows_by_pid=False)` below,
  the same arrangement proven on COSMIC. AT-SPI's own `Element.pid` is
  unaffected (it comes from `get_process_id()` on the accessible node, not
  the window backend), so `app_frame`-scoped element lookups still filter
  by pid exactly like every other driver in this suite.

- Input on KDE is opt-in, not composed by a plain `connect()`: the
  `eiinput` (libei RemoteDesktop portal) route raises a consent dialog
  that needs a human at the box's screen per session, so this driver
  relies on the `uinput` rung instead -- `/dev/uinput` writable (ACL or
  udev) plus `python3-evdev`, the same provisioning the Ubuntu GNOME box
  needed. Keyboard injection is all the shared core asks for: the
  interaction strategy is the pointer-free one (AT-SPI accessible-action
  clicks for buttons/tabs/menus, real Tab-walked keyboard focus + typed
  input for entries/combos/sliders), so whether uinput *pointer* events
  reach KWin is deliberately never tested here.

- No forced backend list: under the session env lifted from
  `kwin_wayland`'s own process (`run-box-tests.sh`), auto-selection
  composes kdotool windows + atspi + spectacle capture + wl-copy +
  kwinevents + uinput input, and there is no nested-compositor ambiguity
  for it to get wrong.

The strategy itself lives in `driver_core.py`, shared with the other
pointer-free Wayland drivers; this file is only the platform's identity and
the findings above.
"""

from __future__ import annotations

import sys

from driver_core import Platform, run

PLATFORM = Platform(name="kde-plasma-wayland", windows_by_pid=False)

if __name__ == "__main__":
    sys.exit(run(PLATFORM))
