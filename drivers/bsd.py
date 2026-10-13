#!/usr/bin/env python3
"""Drive the torture-test app on GhostBSD/FreeBSD: the real X11 desktop
(DISPLAY :0, marco/MATE, lightdm), no private Xvfb.

Drives every actable control through pyguitest's own input API (the `x11`
backend) and verifies each interaction landed by polling the status bar.
Mirrors drivers/linux.py's contract exactly; the only difference is
no private display/a11y bus -- this is a live, multi-application desktop
(mate-panel, caja, mate-terminal, ... are all already AT-SPI-registered),
so every search is scoped to the app's own pid and frame, same as Linux's.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pyguitest

# The repo root: this file lives in <repo>/drivers/, so the app package
# `torture_test` sits next to it one level up. Overridable for a checkout
# somewhere else, but needs no configuration in the normal case -- nothing
# here may hard-code a developer's own path, since this is a pushable repo.
APP_DIR = os.environ.get("TORTURE_APP_DIR") or str(Path(__file__).resolve().parent.parent)
# The interpreter that runs the *app*, which is not always the one running
# this driver: the app needs PySide6, the driver needs pyguitest, and on
# several test boxes those live in different virtualenvs.
APP_PYTHON = os.environ.get("TORTURE_APP_PYTHON") or sys.executable


# A tuple, not a set, so the drive order is deterministic: iterating a set is
# arbitrary and varies per process (str hash randomization), which made the
# order controls are driven in nondeterministic run-to-run. "combo box" is
# deliberately LAST because "Toolbar Zoom" (the persistent toolbar combo)
# changes the app-wide font size when driven, reflowing every control's
# geometry -- driving it last means its reflow cannot break the control driven
# immediately after it.
ACTABLE_ROLES = (
    "push button", "check box", "radio button", "entry", "text", "spin button",
    "list", "tree", "table", "calendar", "slider", "dial",
    "scroll bar", "page tab list", "layered pane", "combo box",
)

# ACTABLE_ROLES plus "status bar" and "page tab", searched together in one
# call: enumerate_now() (the tab-walking loop's own per-switch re-scan)
# used to run three separate find_elements calls -- the actable controls,
# the status bar for clip_bottom, and the main tab bar's own tabs -- and
# each one pays for a full walk of the same subtree, the same cost
# ACTABLE_ROLES alone (16 calls -> 1) was fixed for. No `enabled=True` at
# the search level here since a status bar's and a tab's own enabled state
# are beside the point; enabled is checked per-element below instead, for
# the roles that care about it.
ALL_ROLES = ACTABLE_ROLES + ("status bar", "page tab")


def _is_read_only(el):
    """Whether `el` (an "entry"/"text" element) rejects typed input.

    "Read Only Field" (app.py: `setReadOnly(True)`) exists on purpose, same
    spirit as "Disabled Action" -- the app wires QLineEdit's report only to
    `textChanged` (reporting.py), which a read-only field can never emit,
    since nothing typed into it is ever accepted. AT-SPI's READ_ONLY state is
    the honest signal here, the same way `enabled=False` already is for
    disabled controls.
    """
    try:
        states = el.node.state_set or []
        names = {getattr(s, "name", None) or getattr(s, "value_name", "").removeprefix("ATSPI_STATE_") for s in states}
        return "READ_ONLY" in names
    except Exception:
        return False


def _is_showing(el):
    """Whether `el` is actually on screen right now, by AT-SPI's own
    SHOWING state -- not by its extents.

    drive_menus() below first tried "nonzero extents" as a stand-in for
    "this menu item's parent menu is currently open", the same trick
    enumerate_now() uses for tab pages. Confirmed live on GhostBSD/X11 that
    this does not hold for menus: a closed QMenu's items kept reporting
    their last-real, nonzero on-screen rectangle via dogtail even while
    hidden, so opening just the File menu "discovered" all ~46 leaves
    across every menu in the app at once -- including "Language", which
    then got clicked as if it were a plain leaf and genuinely switched the
    running app to Japanese. SHOWING is AT-SPI's actual answer to "is this
    rendered right now", independent of what geometry a hidden widget
    happens to still be carrying around.
    """
    try:
        states = el.node.state_set or []
        names = {getattr(s, "name", None) or getattr(s, "value_name", "").removeprefix("ATSPI_STATE_") for s in states}
        return "SHOWING" in names
    except Exception:
        return False


# "Menu Button" is an InstantPopup QToolButton -- opening its menu, not
# emitting `clicked`, is the real click behavior. Click, dismiss with Escape,
# and skip the status-bar assertion (no report is coming).
POPUP_ONLY_BUTTONS = {"Menu Button"}

# "Open", "Save As" and "About TortureTest" each open a real top-level window
# (QFileDialog / QMessageBox). "Open"/"Save As" only report inside `if path:`,
# so a cancelled one is a real no-report case, not a tooling gap. "About
# TortureTest" reports unconditionally once its dialog returns.
DIALOG_BUTTONS = {"Open", "Save As", "About TortureTest"}

# The menu bar's own top-level items (app.py: _build_menus()), walked by
# drive_menus() below.
MENU_BAR_NAMES = ("File", "Edit", "View", "Tools", "Help")

# Clicking these would corrupt the rest of the run rather than exercise it:
# New Window/Exit change which process is even being driven, the three
# "Show ..." toggles can hide the status bar or dock every other
# verification in this script depends on, Dark Theme/Zoom/Reset Demo
# Controls mutate shared visual state with no defined before/after, and
# Undo/Redo/Cut/Copy/Paste act on whatever selection happens to exist with
# no guarantee one does. The menu/submenu containing each is still opened
# and walked -- only the leaf click itself is skipped.
MENU_SKIP_ITEMS = {
    "New Window", "Exit",
    "Show Status Bar", "Show Tool Bar", "Show Tool Palette",
    "Undo", "Redo", "Cut", "Copy", "Paste", "Select All",
    "Reset Demo Controls", "Dark Theme",
    "Zoom In", "Zoom Out", "Reset Zoom",
}
# "Language" switches every control's accessible name to Japanese -- fatal
# to a driver that matches controls by name for the rest of the run.
MENU_SKIP_SUBMENUS = {"Language"}

# Leaves that open a real dialog, verified the same way DIALOG_BUTTONS
# above already is: wait for a new top-level window, dismiss with Escape.
# "Open…"/"Save As…" are already driven via the toolbar buttons; the
# longer Slow Dialog presets are skipped to keep one pass bounded.
MENU_DIALOG_ITEMS = {
    "Information", "Warning", "Critical", "Question",
    # Modal, like its QMessageBox siblings above -- it must be listed
    # here or the driver clicks it, never dismisses it, and the
    # application-modal dialog then blocks every later menu click.
    "Error Message",
    "Get Text", "Get Integer", "Get Item",
    "Color Picker…", "Font Picker…", "File Dialog…",
    "Progress Dialog…", "Custom Dialog…", "Wizard…", "MDI Workspace…",
    "1 second",
    "About TortureTest…", "About Qt…",
}

MENU_ROLES = ("menu", "menu item", "check menu item", "radio menu item")


class Failure(Exception):
    """A control did not report the interaction the driver drove it with.

    Collected rather than raised out of the run: the driver records every
    miss and keeps going, so one early failure cannot leave the rest of the
    app unexercised.
    """


def app_environment():
    environment = {**os.environ, "DISPLAY": ":0", "QT_QPA_PLATFORM": "xcb",
                   "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1", "GDK_BACKEND": "x11"}
    environment.pop("WAYLAND_DISPLAY", None)
    return environment


def start_app():
    return subprocess.Popen([APP_PYTHON, "-m", "torture_test"], cwd=APP_DIR,
                            env=app_environment(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_app_window(gui, app_pid, timeout):
    """Poll for the app's own toplevel window, by pid -- see
    drivers/linux.py's identical helper for why this replaces a
    blind sleep rather than just shortening one.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in gui.windows():
            if getattr(w, "pid", None) == app_pid:
                return w
        time.sleep(0.2)
    return None


def _wait_app_frame(gui, app_pid, timeout):
    """Poll for the app's own AT-SPI frame element, by pid -- same race
    as _wait_app_window, one layer down.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for f in gui.elements(role="frame"):
            if getattr(f, "pid", None) == app_pid:
                return f
        time.sleep(0.2)
    return None


def expected_controls():
    text = Path(APP_DIR, "tests", "test_app.py").read_text(encoding="utf-8")
    block = text.split("EXPECTED_CONTROLS = (", 1)[1].split("\n)", 1)[0]
    return re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', block)


def _wait_new_app_window(gui, app_pid, before_titles, timeout):
    """Poll for a window that is new since `before_titles`, belongs to
    `app_pid`, and is not the main "TortureTest" window itself -- the real
    fix for a bug `wait_for_window(title=regex-not-TortureTest)` had on any
    desktop with other windows already open (a VS Code window, a terminal,
    anything): that regex matches whichever pre-existing window happens to
    be first in the list, not the new dialog, so `focus_window` +
    `Escape` lands on the wrong window and the real Open/Save As dialog is
    left open. Confirmed live: this is exactly what happened on a real
    multi-window desktop, never on the private, app-only Xvfb this drive
    loop was first proven on. Scoping to the app's own pid and a
    before/after title diff is immune to how many unrelated windows exist.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            for w in gui.windows():
                if getattr(w, "pid", None) != app_pid:
                    continue
                title = getattr(w, "title", None)
                if title == "TortureTest" or title in before_titles:
                    continue
                return w
        except Exception:
            pass
        time.sleep(0.2)
    return None


def _status_text(status_bar_el):
    """The status bar's current message, via AT-SPI.

    Takes the status bar Element directly -- see drivers/linux.py's
    identical function for why re-searching for it on every poll (up to 8
    times per control, twice with the retry) turned into the dominant cost
    of the whole run.
    """
    if status_bar_el is None:
        return ""
    try:
        name = getattr(status_bar_el, "name", None)
        if name:
            return name
        parts = []
        for child in getattr(status_bar_el, "children", []):
            child_name = getattr(child, "name", None)
            if child_name:
                parts.append(child_name)
        if parts:
            return " ".join(parts)
    except Exception:
        pass
    return ""


def enumerate_controls(gui, app_pid, expected, app_frame=None):
    """Enumerate visible, actable controls from an already-open session.

    Mirrors the X11 driver's filtering: enabled, expected (name, role), on
    screen, and excluding read-only entry/text fields. `gui` is the session
    opened once by main(), reused here and in drive().

    One `find_elements(role=ACTABLE_ROLES, ...)` call, not one per role: the
    walk this triggers costs the same few seconds regardless of how many
    roles the predicate accepts, so 16 separate calls paid for 16 walks of
    the same subtree -- confirmed live (GhostBSD, ~130 elements): over a
    minute role-by-role, a few seconds combined. See pyguitest's own
    CHANGELOG for the fix this is written against.
    """
    try:
        elements = gui.find_elements(role=ALL_ROLES, within=app_frame)
    except Exception:
        elements = []
    clip_bottom = None
    for el in elements:
        if getattr(el, "pid", None) == app_pid and el.role == "status bar":
            try:
                _, sy, _, _ = gui.extents(el)
                clip_bottom = sy
            except Exception:
                pass
            break
    found = []
    for el in elements:
        try:
            if getattr(el, "pid", None) != app_pid:
                continue
            role = el.role
            if role == "status bar":
                continue
            if not el.enabled:
                continue
            # Qt's AT-SPI bridge publishes a combo box's current text as its
            # Name; the stable id is in the description.
            name = (el.description or el.name) if role == "combo box" else el.name
        except Exception:
            continue
        if not name or (name, role) not in expected:
            continue
        if role in ("entry", "text") and _is_read_only(el):
            continue
        try:
            x, y, w, h = gui.extents(el)
        except Exception:
            continue
        if clip_bottom is not None and y + h > clip_bottom:
            continue
        if w > 0 and h > 0:
            found.append((name, role, x, y, w, h))
    return found


def drive(gui, items, failures, app_pid, expected, app_frame=None, window=None):
    """Drive each control through pyguitest's input API, verify via the status
    bar, then walk every main tab page.
    """
    status_bar_el = None
    try:
        for el in gui.find_elements(role="status bar", within=app_frame):
            if getattr(el, "pid", None) == app_pid:
                status_bar_el = el
                break
    except Exception:
        pass

    def live_extents(name, role):
        """`name`/`role`'s current extents, re-read so a reflow cannot stale
        the enumeration-time snapshot.
        """
        try:
            for el in gui.find_elements(role=role, enabled=True, within=app_frame):
                if getattr(el, "pid", None) != app_pid:
                    continue
                el_name = (el.description or el.name) if role == "combo box" else el.name
                if el_name == name:
                    return gui.extents(el)
        except Exception:
            pass
        return None

    def tap(name):
        gui.tap_key(name)
    def point(x, y):
        gui.move_mouse(int(x), int(y))
    def click(button=1):
        gui.click(button)
    def type_text(text):
        gui.type_text(text)

    def interact(role):
        if role in ("push button", "check box", "radio button"):
            click()
        elif role in ("entry", "text"):
            click()
            type_text("torture")
        elif role == "spin button":
            click()
            tap("Up")
        elif role == "combo box":
            click()
            time.sleep(0.3)
            tap("Down")
            tap("Return")
            gui.wait_for_idle(app_pid, timeout=1.5)
        elif role in ("slider", "dial", "scroll bar"):
            click()
            tap("Up")
            tap("Right")
        elif role in ("list", "tree", "table", "calendar"):
            click()
            tap("Down")
        elif role in ("page tab list", "layered pane"):
            click()

    def enumerate_now():
        try:
            elements = gui.find_elements(role=ALL_ROLES, within=app_frame)
        except Exception:
            elements = []

        clip_bottom = None
        for el in elements:
            if getattr(el, "pid", None) == app_pid and el.role == "status bar":
                try:
                    _, sy, _, _ = gui.extents(el)
                    clip_bottom = sy
                except Exception:
                    pass
                break

        actable = []
        candidates = []
        current = None
        for el in elements:
            try:
                if getattr(el, "pid", None) != app_pid:
                    continue
                role = el.role
            except Exception:
                continue

            if role == "status bar":
                continue

            if role == "page tab":
                # The main tab bar is the topmost "page tab" row; embedded
                # demo tab bars ("Nested Tabs", "Standalone Tab Bar") share
                # the role but sit lower in the window.
                try:
                    name = el.name
                except Exception:
                    continue
                if not name:
                    continue
                try:
                    x, y, w, h = gui.extents(el)
                except Exception:
                    continue
                if w <= 0 or h <= 0:
                    continue
                candidates.append((name, x, y, w, h))
                try:
                    if el.selected:
                        current = name
                except Exception:
                    pass
                continue

            try:
                if not el.enabled:
                    continue
                name = (el.description or el.name) if role == "combo box" else el.name
            except Exception:
                continue
            if not name or (name, role) not in expected:
                continue
            if role in ("entry", "text") and _is_read_only(el):
                continue
            try:
                x, y, w, h = gui.extents(el)
            except Exception:
                continue
            if clip_bottom is not None and y + h > clip_bottom:
                continue
            if w > 0 and h > 0:
                actable.append((name, role, x, y, w, h))

        tabs = []
        if candidates:
            top_y = min(y for (_n, _x, y, _w, _h) in candidates)
            tabs = [t for t in candidates if t[2] <= top_y + 5]
        return actable, tabs, current

    seen = set()

    def drive_items(current_items):
        # Every item is attempted regardless of an earlier miss in this same
        # batch -- a narrower instance of the same bug the top-level
        # drive()/drive_items() gating fix (see the module docstring) was
        # meant to close: the top-level fix stops a miss in one tab from
        # aborting *later* tabs, but this loop still returned False (and the
        # for-loop broke) on the very first miss, abandoning every other
        # control in *that same* batch. Confirmed live: tab 1's "Primary
        # Action" alone missing left the other 12 tab-1 controls never even
        # attempted. A call that genuinely hangs inside pyguitest's own
        # atspi backend now raises BackendCallTimeout there (bounded, not
        # unbounded -- see pyguitest's CHANGELOG/BackendCallTimeout), which
        # is recorded here as a failure the same as an ordinary miss,
        # rather than crashing the whole run.
        ok = True
        for (name, role, x, y, w, h) in current_items:
            if (name, role) in seen:
                continue
            seen.add((name, role))
            try:
                if not drive_one(name, role, x, y, w, h):
                    ok = False
            except pyguitest.BackendCallTimeout as exc:
                failures.append(f"{name} ({role}) -> {exc}")
                ok = False
        return ok

    def status_shows(name):
        return name in _status_text(status_bar_el)

    def drive_one(name, role, x, y, w, h):
        # No live re-fetch here: see drivers/linux.py's identical
        # comment -- (x, y, w, h) is already fresh from the batch this
        # control was just pulled from, and re-fetching unconditionally
        # before every click cost one more full find_elements walk per
        # control. live_extents() still runs on the retry path below.
        cx, cy = int(x) + int(w) // 2, int(y) + int(h) // 2
        point(cx, cy)
        if role == "push button" and name in POPUP_ONLY_BUTTONS:
            click()
            gui.wait_for_element(role="menu", within=app_frame, timeout=1.0)
            tap("Escape")
            gui.wait_until_gone(role="menu", within=app_frame, timeout=1.0)
            return True
        if role == "push button" and name in DIALOG_BUTTONS:
            before = {
                w.title for w in gui.windows()
                if getattr(w, "pid", None) == app_pid
            }
            click()
            dialog = _wait_new_app_window(gui, app_pid, before, timeout=15.0)
            if dialog is None:
                failures.append(f"{name} ({role}) -> dialog never appeared")
                return False
            gui.focus_window(dialog)
            gui.wait_window_focus(dialog, timeout=2.0)
            tap("Escape")
            gui.wait_window_close(dialog, timeout=2.0)
            if name not in ("Open", "Save As") and not gui.wait_until(
                lambda: status_shows(name), timeout=0.8, interval=0.1
            ):
                failures.append(f"{name} ({role}) -> {_status_text(status_bar_el)!r}")
                return False
            return True
        interact(role)
        if gui.wait_until(lambda: status_shows(name), timeout=0.8, interval=0.1):
            return True
        fresh = live_extents(name, role)
        if fresh is not None:
            x, y, w, h = fresh
            cx, cy = int(x) + int(w) // 2, int(y) + int(h) // 2
        point(cx, cy)
        interact(role)
        if gui.wait_until(lambda: status_shows(name), timeout=0.8, interval=0.1):
            return True
        failures.append(f"{name} ({role}) -> {_status_text(status_bar_el)!r}")
        return False

    # A miss on one control used to abort the rest of the walk entirely --
    # see drivers/linux.py's identical comment for the full story
    # (confirmed live: this is why GhostBSD never reached tabs 5-9 once
    # "Model Tree" missed on tab 4). Every failure is still recorded in
    # `failures` -- driving the rest of the app is the point.
    drive_items(items)
    try:
        _, _, current = enumerate_now()
    except pyguitest.BackendCallTimeout as exc:
        current = None
        failures.append(f"enumerate_now() (initial) -> {exc}")
    clicked_tabs = {current} if current else set()
    for _ in range(40):
        try:
            _, tabs, _ = enumerate_now()
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"enumerate_now() (tab scan) -> {exc}")
            break
        nxt = next((t for t in tabs if t[0] not in clicked_tabs), None)
        if nxt is None:
            break
        tname, tx, ty, tw, th = nxt
        clicked_tabs.add(tname)
        point(int(tx) + int(tw) // 2, int(ty) + int(th) // 2)
        click()
        gui.wait_for_idle(app_pid, timeout=1.5)
        try:
            actable, _, _ = enumerate_now()
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"enumerate_now() (tab {tname!r}) -> {exc}")
            continue
        drive_items(actable)



def drive_menus(gui, app_frame, app_pid, failures):
    """Open every top-level menu and walk its items: descend into
    submenus, click the leaves that are safe to click (MENU_SKIP_ITEMS/
    MENU_SKIP_SUBMENUS are not), verify the ones that open a dialog the
    same way drive_one() already does for DIALOG_BUTTONS.

    Two passes per menu level, not one: Qt closes the *entire* open menu
    chain the instant any leaf action fires, so a single top-to-bottom
    walk could only ever click one leaf per menu before every sibling's
    cached geometry went stale. Pass 1 opens each level read-only (no
    leaf clicks) and records what is there; pass 2 re-opens the exact
    path to each discovered leaf, one at a time, to click it.
    """
    def visible_items():
        try:
            elements = gui.find_elements(role=MENU_ROLES, within=app_frame)
        except Exception:
            return []
        out = []
        for el in elements:
            try:
                if getattr(el, "pid", None) != app_pid:
                    continue
                name = el.name
                if not name:
                    continue
                # SHOWING, not extents -- see _is_showing's own docstring
                # for why a hidden menu's items cannot be told apart from
                # an open one's by geometry alone on every platform.
                if not _is_showing(el):
                    continue
                x, y, w, h = gui.extents(el)
            except Exception:
                continue
            if w <= 0 or h <= 0:
                continue
            out.append((name, el.role, x, y, w, h))
        return out

    def click_at(x, y, w, h):
        gui.move_mouse(int(x) + int(w) // 2, int(y) + int(h) // 2)
        # A real QAction under a menu needs the pointer to actually arrive
        # and settle before a click registers as *activating* that item,
        # not just dismissing the menu -- confirmed live on GhostBSD: every
        # one of 9 real dialog-opening leaves under Tools/Help was reached
        # and clicked at the right coordinate (confirmed in a live trace)
        # yet never fired, including "Tools/File Dialog…", which calls the
        # exact same `_file_open` callback a toolbar click already drives
        # successfully elsewhere in this file with no dwell time needed.
        # Same shape of fix as the Toolbar Zoom combo box's own
        # `time.sleep(0.3)` before its keypresses, just applied here too.
        time.sleep(0.3)
        gui.click(1)

    def close_all():
        for _ in range(4):
            gui.tap_key("Escape")

    def open_path(path):
        """Click through `path` (menu bar name, then each submenu header
        in order) so the final name's siblings are now visible. Returns
        the visible items at that final level, or None if any hop failed
        to open.
        """
        items = visible_items()
        for hop in path:
            match = next((it for it in items if it[0] == hop), None)
            if match is None:
                return None
            _, _, x, y, w, h = match
            click_at(x, y, w, h)
            if not gui.wait_for_element(role=MENU_ROLES, within=app_frame, timeout=1.0):
                return None
            # wait_for_element only confirms *a* menu-role element exists,
            # not that the whole level has finished rendering -- confirmed
            # live (GhostBSD) that this is why every one of 9 leaves under
            # Tools/Help (the two biggest, flattest menus -- Tools alone has
            # 10 direct entries) consistently failed: the click landed at
            # the right coordinate every time (confirmed via live trace in
            # an earlier session) but never fired, while the exact same
            # leaves succeed when opened via the toolbar. A plain 0.5s
            # settle here, before trusting this level's extents, closed the
            # gap in a live repro of "Tools/Color Picker..." that failed
            # with the old 0.3s click_at()-only dwell and passed with this
            # added. Small menus (1-3 entries) pay the same 0.5s too, but
            # correctness matters more than shaving it per-level-size here.
            time.sleep(0.5)
            items = visible_items()
        return items

    def discover(path, depth, leaves):
        """Read-only DFS: records (path, name) for every clickable leaf
        under `path` into `leaves`, recursing into submenu headers.
        """
        if depth > 3:
            return
        items = open_path(path)
        close_all()
        if items is None:
            return
        for name, role, *_ in items:
            # The menu bar's own items (File/Edit/...) stay visible and
            # "showing" the whole time any one of them is open -- without
            # this, each one gets mistaken for a submenu header nested
            # inside whichever menu is actually open and recursed into,
            # which is combinatorial (every bar name found "inside" every
            # other bar name, down to the depth cap) and was confirmed
            # live to hang the whole run well past a 170s timeout with no
            # further output.
            if name in MENU_BAR_NAMES:
                continue
            if role == "menu":
                if name in MENU_SKIP_SUBMENUS:
                    continue
                discover([*path, name], depth + 1, leaves)
                continue
            leaves.append((list(path), name))

    leaves = []
    for bar_name in MENU_BAR_NAMES:
        try:
            discover([bar_name], 0, leaves)
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"{bar_name} (menu discovery) -> {exc}")
            close_all()

    def _open_and_click(path, name):
        """One attempt: open `path` fresh, click `name` if still there.
        Returns (clicked, before_titles) -- `clicked` is False if the hop
        or the leaf itself could not be found this time.
        """
        items = open_path(path)
        if items is None:
            return False, None
        match = next((it for it in items if it[0] == name), None)
        if match is None:
            close_all()
            return False, None
        _, _, x, y, w, h = match
        before = {w2.title for w2 in gui.windows() if getattr(w2, "pid", None) == app_pid}
        click_at(x, y, w, h)
        return True, before

    def _click_one_leaf(path, name):
        # MENU_SKIP_SUBMENUS is checked again here, not just in discover()'s
        # recursion above -- a submenu header that is ever misclassified as
        # a plain leaf (confirmed live: this is exactly how "Language" got
        # clicked instead of skipped) must still never be clicked, whatever
        # caused the misclassification.
        if name in MENU_SKIP_ITEMS or name in MENU_SKIP_SUBMENUS:
            return
        clicked, before = _open_and_click(path, name)
        if not clicked:
            return
        if name in MENU_DIALOG_ITEMS:
            # 15.0, matching DIALOG_BUTTONS' own timeout in drive() -- 5.0
            # was not enough margin here: confirmed live on GhostBSD, where
            # AT-SPI/dogtail's own per-call cost is already several seconds,
            # every menu-triggered dialog in a 9-leaf run timed out, while
            # the identical dialogs opened from the toolbar (15.0s) did not.
            dialog = _wait_new_app_window(gui, app_pid, before, timeout=15.0)
            if dialog is None:
                # One retry, fresh open-and-click, before giving up --
                # mirrors drive_one()'s own retry shape for an ordinary
                # control. Confirmed live (GhostBSD) via isolated repro
                # that these specific leaves (all 9: Tools/Help's direct,
                # depth-1 children) can land at the right coordinate
                # without firing -- a one-shot miss, not a structurally
                # unreachable target -- so a second, independent attempt is
                # a real second chance, not a repeat of the same failure.
                close_all()
                clicked, before = _open_and_click(path, name)
                if clicked:
                    dialog = _wait_new_app_window(gui, app_pid, before, timeout=15.0)
                if dialog is None:
                    failures.append(f"{'/'.join([*path, name])} (menu item) -> dialog never appeared")
                    close_all()
                    return
            gui.focus_window(dialog)
            gui.wait_window_focus(dialog, timeout=2.0)
            gui.tap_key("Escape")
            gui.wait_window_close(dialog, timeout=2.0)
        close_all()
        gui.wait_until_gone(role="menu", within=app_frame, timeout=1.0)

    for path, name in leaves:
        # A call that genuinely hangs inside pyguitest's own atspi backend
        # now raises BackendCallTimeout there rather than blocking forever
        # -- see pyguitest's CHANGELOG. Caught here the same way
        # drive_items() catches it for a plain control.
        try:
            _click_one_leaf(path, name)
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"{'/'.join([*path, name])} (menu item) -> {exc}")
            close_all()


def main():
    app = start_app()
    try:
        gui = pyguitest.connect(
            backend=["x11", "atspi"],
            environment=pyguitest.detect(app_environment()),
            event_delay=0.15,
            key_delay=0.08,
        )
        window = _wait_app_window(gui, app.pid, timeout=15.0)
        if window is None and app.poll() is not None:
            raise Failure(f"torture-test app exited immediately with {app.returncode}")
        if window is not None:
            gui.activate_window(window)
            # activate_window() asks for focus and returns immediately; a
            # fixed sleep after it is a guess, not a guarantee the window
            # manager actually granted focus by then -- see
            # drivers/linux.py's identical comment and
            # Session.wait_window_focus's own docstring. Confirmed live:
            # with a blind sleep, the very first control driven after
            # launch consistently missed, every run -- the window had not
            # actually taken focus yet when that first click landed.
            gui.wait_window_focus(window, timeout=5.0)
        # Scope every search to the app's own frame: on a live desktop
        # the AT-SPI tree spans every app (VS Code's is huge), so an
        # unscoped find_elements walks all of it and looks stuck.
        app_frame = _wait_app_frame(gui, app.pid, timeout=5.0)
        expected = set(expected_controls())
        items = enumerate_controls(gui, app.pid, expected, app_frame)
        print(f"actable controls found (visible): {len(items)}")
        print(f"  sample: {sorted({n for n, *_ in items})[:14]}")
        failures = []
        drive(gui, items, failures, app.pid, expected, app_frame, window)
        drive_menus(gui, app_frame, app.pid, failures)
        if failures:
            print(f"STATUS CHECK FAILED: {len(failures)} interaction(s) did not report")
            for failure in failures:
                print(f"  - {failure}")
            return 2
        print("all controls verified")
        return 0
    finally:
        try:
            gui.close()
        except Exception:
            pass
        app.terminate()
        try:
            app.wait(timeout=5)
        except Exception:
            # terminate() is a request, and a Qt app wedged in a modal
            # dialog can ignore it. Escalate rather than swallowing the
            # timeout: a driver that leaves the app running strands a
            # window on the desktop, and a dozen runs strand a dozen.
            try:
                app.kill()
                app.wait(timeout=5)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
