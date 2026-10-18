#!/usr/bin/env python3
"""Drive the torture-test app on Pop!_OS/COSMIC: live session + atspi + wtype.

Also the driver for Omarchy/Hyprland and KaOS/niri, both of which run it
unmodified -- see VALIDATION.md.

COSMIC differs from every other Linux box this suite has driven in two ways
that matter here:

1. `Window.pid` from the `cosmic` window backend is always `None` --
   confirmed against the real `zcosmic_toplevel_info_v1` protocol XML
   (cosmic-protocols, up to v3): no pid-bearing event exists at any
   version, a permanent protocol limitation, not a missing feature. Every
   `gui.windows()` match in this driver is therefore by title, never pid
   (`Platform(windows_by_pid=False)` below). AT-SPI's own `Element.pid` is
   unaffected -- it comes from `get_process_id()` on the accessible node
   itself, not from the window backend -- confirmed live, so
   `app_frame`-scoped element lookups still filter by pid exactly like
   every other driver in this suite.

2. Pointer injection does not reach the app at all on this box -- the same
   broken uinput/libinput path confirmed on the other blocked GNOME/Wayland
   boxes (Debian 13 VM, this maintainer's own Fedora desktop). Every
   control here is therefore driven through the AT-SPI accessible-action
   route (`Element.click()`) or through real keyboard focus + wtype, never
   `gui.move_mouse()`/`gui.click()`. Two findings from live probing drove
   this split:
     - `Element.click()` (AT-SPI action) reliably fires the real signal for
       buttons, tabs, and menu items -- confirmed live: a page-tab click
       flips the real Qt current page (checked by a Text&Numbers-only
       control becoming visible), not just an AT-SPI-visible state flag.
     - `Element.click()` / `grabFocus()` do NOT reliably move real
       keyboard focus for an entry -- confirmed live: text typed right
       after either landed nowhere (`entry.text` stayed `""`). Real focus
       only moved via actual Tab key presses (wtype), confirmed by
       `entry.focused` flipping True after a few presses and the typed
       text then actually landing. The Tab walk in `driver_core.py` is
       that mechanism.

The strategy itself lives in `driver_core.py`, shared with the other
pointer-free Wayland drivers; this file is only the platform's identity and
the findings above.
"""
from __future__ import annotations

import sys

from driver_core import Platform, run

PLATFORM = Platform(name="cosmic-wayland", windows_by_pid=False)

if __name__ == "__main__":
    sys.exit(run(PLATFORM))
