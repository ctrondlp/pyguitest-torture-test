#!/usr/bin/env python3
"""Drive the torture-test app on this maintainer's own Linux desktop
(Fedora, GNOME/Wayland): live session + atspi + uinput keyboard.

This box was previously treated as fully blocked, the same conclusion
reached on Debian: a thoroughly-isolated system-level libinput/Mutter
failure means no uinput-created device can deliver *pointer* input to this
session (confirmed live via a bare-minimum `evdev` device built with zero
code from this project -- see VALIDATION.md). Re-tested 2026-10-12 and
found that conclusion was half right: pointer injection is still dead, but
*keyboard* injection through the same `uinput` backend works perfectly here
-- confirmed live, `gui.tap_key("Tab")` genuinely moves real AT-SPI-visible
focus (`Element.focused` flips True) and `gui.type_text()` right after
lands real characters. This is the exact same split already proven on
Pop!_OS/COSMIC, so this driver borrows that platform's pointer-free
strategy wholesale rather than being abandoned:

- Push buttons, checkboxes, radio buttons, page tabs, and menu items go
  through `Element.click()` (the AT-SPI accessible-action route) --
  confirmed live that a tab click via the action genuinely flips the real
  Qt page (a Text-&-Numbers-only control's `.visible` actually becomes
  `True`), not just an AT-SPI state flag.
- Entries, spin buttons, sliders/dials, lists/trees/tables/calendars, and
  combo boxes go through real Tab-walked keyboard focus followed by real
  keyboard input -- confirmed live that `Element.click()`/`grabFocus()` do
  NOT reliably move real keyboard focus the way actual Tab presses do.

Unlike COSMIC, this box's `gnomeshell` window backend DOES populate a real
`Window.pid` (confirmed live), so window matching here stays pid-based,
the same as every pre-COSMIC driver in this suite -- only the interaction
strategy changed, not the window-identification strategy.

The strategy itself lives in `driver_core.py`, shared with the other
pointer-free Wayland drivers; this file is only the platform's identity and
the findings above.
"""
from __future__ import annotations

import sys

from driver_core import Platform, run

PLATFORM = Platform(name="fedora-gnome-wayland")

if __name__ == "__main__":
    sys.exit(run(PLATFORM))
