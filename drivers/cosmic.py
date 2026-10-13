#!/usr/bin/env python3
"""Drive the torture-test app on Pop!_OS/COSMIC: live session + atspi + wtype.

COSMIC differs from every other Linux box this suite has driven in two ways
that matter here:

1. `Window.pid` from the `cosmic` window backend is always `None` --
   confirmed against the real `zcosmic_toplevel_info_v1` protocol XML
   (cosmic-protocols, up to v3): no pid-bearing event exists at any
   version, a permanent protocol limitation, not a missing feature. Every
   `gui.windows()` match in this file is therefore by title, never pid.
   AT-SPI's own `Element.pid` is unaffected -- it comes from
   `get_process_id()` on the accessible node itself, not from the window
   backend -- confirmed live, so `app_frame`-scoped element lookups below
   still filter by pid exactly like every other driver in this suite.

2. Pointer injection does not reach the app at all on this box -- the same
   broken uinput/libinput path confirmed on the other blocked GNOME/Wayland
   boxes (Debian 13 VM, this maintainer's own Fedora box). Every control
   here is therefore driven through the AT-SPI accessible-action route
   (`Element.click()`) or through real keyboard focus + wtype, never
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
       text then actually landing. `seek_focus()` below is that Tab walk.
"""
from __future__ import annotations

import faulthandler
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pyguitest

faulthandler.dump_traceback_later(25, repeat=True)

# The repo root: this file lives in <repo>/drivers/, so the app package
# `torture_test` sits next to it one level up. Overridable for a checkout
# somewhere else, but needs no configuration in the normal case -- nothing
# here may hard-code a developer's own path, since this is a pushable repo.
APP_DIR = os.environ.get("TORTURE_APP_DIR") or str(Path(__file__).resolve().parent.parent)
# The interpreter that runs the *app*, which is not always the one running
# this driver: the app needs PySide6, the driver needs pyguitest, and on
# several test boxes those live in different virtualenvs.
APP_PYTHON = os.environ.get("TORTURE_APP_PYTHON") or sys.executable

# See drivers/linux.py for why this is a tuple (deterministic order)
# and why "combo box" is last (Toolbar Zoom's reflow must not stale a
# control driven right after it).
ACTABLE_ROLES = (
    "push button", "check box", "radio button", "entry", "text", "spin button",
    "list", "tree", "table", "calendar", "slider", "dial",
    "scroll bar", "page tab list", "layered pane", "combo box",
)
ALL_ROLES = ACTABLE_ROLES + ("status bar", "page tab")

# Roles whose real behavior needs actual keyboard focus (typed text, an
# arrow-key nudge) rather than just an accessible-action click -- see the
# module docstring's finding 2. Everything else is driven via
# `Element.click()` alone.
FOCUS_ROLES = ("entry", "text", "spin button", "slider", "dial", "scroll bar",
               "list", "tree", "table", "calendar", "combo box")

MAX_SEEK_PRESSES = 60

POPUP_ONLY_BUTTONS = {"Menu Button"}
DIALOG_BUTTONS = {"Open", "Save As", "About TortureTest"}
MENU_BAR_NAMES = ("File", "Edit", "View", "Tools", "Help")
MENU_SKIP_ITEMS = {
    "New Window", "Exit",
    "Show Status Bar", "Show Tool Bar", "Show Tool Palette",
    "Undo", "Redo", "Cut", "Copy", "Paste", "Select All",
    "Reset Demo Controls", "Dark Theme",
    "Zoom In", "Zoom Out", "Reset Zoom",
}
MENU_SKIP_SUBMENUS = {"Language"}
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


def _safe_click(el):
    """`el.click()`, swallowing anything but a genuine hang.

    Confirmed live: COSMIC's AT-SPI bus occasionally answers a
    `doActionNamed` call with a D-Bus reply timeout, which dogtail then
    re-raises as `ActionNotSupported` -- the same exception type it uses
    for "this role publishes no such action at all", with no way for a
    caller to tell a transient communication failure apart from a real
    one. Left unguarded this crashed the whole run on the very first
    control driven. `pyguitest.BackendCallTimeout` (a genuine, bounded
    hang) is let through so its own handling above this still sees it;
    everything else degrades to "the click did nothing", which the normal
    status-bar/open-path failure paths already handle correctly.
    """
    try:
        el.click()
        return True
    except pyguitest.BackendCallTimeout:
        raise
    except Exception:
        return False


def app_environment():
    environment = {**os.environ, "QT_QPA_PLATFORM": "wayland",
                   "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1"}
    environment.pop("DISPLAY", None)
    environment.pop("NO_AT_BRIDGE", None)
    return environment


def start_app():
    return subprocess.Popen([APP_PYTHON, "-m", "torture_test"], cwd=APP_DIR,
                            env=app_environment(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_app_window(gui, timeout):
    """Poll for the app's own toplevel window, by title -- `Window.pid` is
    always `None` on the `cosmic` backend, see module docstring.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in gui.windows():
            if getattr(w, "title", None) == "TortureTest":
                return w
        time.sleep(0.2)
    return None


def _wait_app_frame(gui, app_pid, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for f in gui.elements(role="frame"):
            if getattr(f, "pid", None) == app_pid:
                return f
        time.sleep(0.2)
    return None


def _wait_new_app_window(gui, before_titles, timeout):
    """Poll for a window that is new since `before_titles` and is not the
    main "TortureTest" window itself. Not scoped by pid -- `Window.pid` is
    always `None` here, see module docstring -- so a title-only diff is the
    best available signal on this box.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            for w in gui.windows():
                title = getattr(w, "title", None)
                if title == "TortureTest" or title in before_titles:
                    continue
                return w
        except Exception:
            pass
        time.sleep(0.2)
    return None


def expected_controls():
    text = Path(APP_DIR, "tests", "test_app.py").read_text(encoding="utf-8")
    block = text.split("EXPECTED_CONTROLS = (", 1)[1].split("\n)", 1)[0]
    return re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', block)


def _is_read_only(el):
    try:
        states = el.node.state_set or []
        names = {getattr(s, "name", None) or getattr(s, "value_name", "").removeprefix("ATSPI_STATE_") for s in states}
        return "READ_ONLY" in names
    except Exception:
        return False


def _is_showing(el):
    try:
        states = el.node.state_set or []
        names = {getattr(s, "name", None) or getattr(s, "value_name", "").removeprefix("ATSPI_STATE_") for s in states}
        return "SHOWING" in names
    except Exception:
        return False


def _status_text(status_bar_el):
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
            # Qt publishes a combo box's current text as its Name; the
            # stable id is in the description.
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
            found.append((name, role, el))
    return found


def drive(gui, items, failures, app_pid, expected, app_frame=None):
    """Drive each control via AT-SPI action clicks + real-focus keyboard
    input, verify via the status bar, then walk every main tab page.
    """
    status_bar_el = None
    try:
        for el in gui.find_elements(role="status bar", within=app_frame):
            if getattr(el, "pid", None) == app_pid:
                status_bar_el = el
                break
    except Exception:
        pass

    def tap(name):
        gui.tap_key(name)

    def type_text(text):
        gui.type_text(text)

    def seek_focus(el, max_presses=MAX_SEEK_PRESSES):
        """Walk real keyboard focus onto `el` by pressing Tab, checking
        AT-SPI's own `focused` state after each press. `Element.click()`/
        `grabFocus()` do not move real focus on this box -- see module
        docstring finding 2 -- so this is the only confirmed-working way to
        get genuine keyboard focus onto a specific widget.
        """
        try:
            if el.focused:
                return True
        except Exception:
            pass
        for i in range(max_presses):
            tap("Tab")
            time.sleep(0.05)
            try:
                if el.focused:
                    return True
            except Exception:
                continue
            if i and i % 20 == 0:
                print(
                    f"    seek_focus: {i} tab presses so far, still not focused",
                    flush=True,
                )
        return False

    def interact(el, role):
        if role in ("push button", "check box", "radio button"):
            _safe_click(el)
        elif role in ("entry", "text"):
            if seek_focus(el):
                type_text("torture")
        elif role == "spin button":
            if seek_focus(el):
                tap("Up")
        elif role == "combo box":
            # A focused QComboBox changes its current index directly on
            # Down (no popup needs to be opened first) -- confirmed to be
            # the simpler, real-focus-only path rather than
            # click()-to-open-popup, which this box's click() cannot be
            # confirmed to land keyboard focus inside reliably (see module
            # docstring finding 2).
            if seek_focus(el):
                tap("Down")
                gui.wait_for_idle(app_pid, timeout=1.5)
        elif role in ("slider", "dial"):
            if seek_focus(el):
                tap("Up")
                tap("Right")
        elif role == "scroll bar":
            # Confirmed live on Debian 13/Fedora: a QScrollBar is never
            # reachable via Tab at all (seek_focus exhausts its full
            # budget, unlike slider/dial which focus normally), so Up/Right
            # land on whatever else happens to have focus and do nothing.
            # It publishes "Increase"/"Decrease" AT-SPI actions directly,
            # usable with no keyboard focus at all. Not yet reproduced on
            # this box (its own runs passed clean before this fix existed),
            # but this path is a strict superset -- a scroll bar that *is*
            # focusable here still has this action available -- so it is
            # safe to apply unconditionally rather than only where proven
            # broken.
            try:
                el.do_action("Increase")
            except Exception:
                pass
        elif role in ("list", "calendar"):
            if seek_focus(el):
                # Up before Down, because a lone Down is not enough for
                # every list. A plain QListWidget opens with
                # currentRow() == -1, so Down moves it; a list whose
                # selection already sits on its last row has nowhere to go.
                # Up-then-Down moves the selection wherever it starts.
                tap("Up")
                tap("Down")
            else:
                # Not Tab-reachable at all -- same situation as QScrollBar
                # and QTableView above, and confirmed live here for
                # "Undo History": a QUndoView never took focus in 60 Tab
                # presses, and the container publishes only "Set Focus".
                # Its rows do each publish a "Toggle" action though, which
                # Element.click() already treats as a click, and choosing a
                # row that is not the current one moves the undo stack's
                # index and fires the real signal. seek_focus's own
                # success or failure is the discriminator, exactly as it is
                # for "table".
                for child in el.children:
                    try:
                        if child.selected:
                            continue
                    except Exception:
                        pass
                    try:
                        child.click()
                        break
                    except Exception:
                        continue
        elif role == "tree":
            # A freshly-loaded QTreeWidget here is collapsed to a single
            # root row -- confirmed live on Debian 13/Fedora that a lone
            # Down has nothing else to move the selection to and never
            # fires a report. Right (expand) first gives Down an actual
            # second row to land on. Same "safe superset" reasoning as the
            # scroll bar branch above.
            if seek_focus(el):
                tap("Right")
                tap("Down")
        elif role == "table":
            # "table" covers two widget types with opposite keyboard
            # behavior, confirmed live on Debian 13/Fedora: a QTableWidget
            # (eg "Data Grid") focuses normally via Tab and Down already
            # works; a QTableView (eg "Model Table") is never reachable
            # via Tab at all (seek_focus exhausts its full budget) -- but
            # its cells each publish their own clickable action, confirmed
            # live to fire the real selection-changed signal with no focus
            # needed. seek_focus's own success/failure is the signal for
            # which kind this is.
            if seek_focus(el):
                tap("Down")
            else:
                child = next((c for c in el.children if c.actions), None)
                if child is not None:
                    _safe_click(child)
        elif role in ("page tab list", "layered pane"):
            _safe_click(el)

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
                candidates.append((name, el, y))
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
                actable.append((name, role, el))

        tabs = []
        if candidates:
            top_y = min(y for (_n, _e, y) in candidates)
            tabs = [(n, e) for (n, e, y) in candidates if y <= top_y + 5]
        return actable, tabs, current

    seen = set()

    def drive_items(current_items):
        ok = True
        for (name, role, el) in current_items:
            if (name, role) in seen:
                continue
            seen.add((name, role))
            t0 = time.monotonic()
            print(f"  driving {name!r} ({role})...", flush=True)
            try:
                if not drive_one(name, role, el):
                    ok = False
            except pyguitest.BackendCallTimeout as exc:
                failures.append(f"{name} ({role}) -> {exc}")
                ok = False
            print(f"    ...done in {time.monotonic() - t0:.2f}s", flush=True)
        return ok

    def status_shows(name):
        return name in _status_text(status_bar_el)

    def _find_fresh(name, role):
        """Re-find `name`/`role`'s current element -- a reflow (eg Toolbar
        Zoom) can make the enumeration-time element stale.
        """
        try:
            for el in gui.find_elements(role=role, enabled=True, within=app_frame):
                if getattr(el, "pid", None) != app_pid:
                    continue
                el_name = (el.description or el.name) if role == "combo box" else el.name
                if el_name == name:
                    return el
        except Exception:
            pass
        return None

    def drive_one(name, role, el):
        if role == "push button" and name in POPUP_ONLY_BUTTONS:
            _safe_click(el)
            gui.wait_for_element(role="menu", within=app_frame, timeout=1.0)
            tap("Escape")
            gui.wait_until_gone(role="menu", within=app_frame, timeout=1.0)
            return True
        if role == "push button" and name in DIALOG_BUTTONS:
            before = {w.title for w in gui.windows()}
            _safe_click(el)
            dialog = _wait_new_app_window(gui, before, timeout=15.0)
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
        interact(el, role)
        if gui.wait_until(lambda: status_shows(name), timeout=0.8, interval=0.1):
            return True
        # One retry, re-finding the element fresh first -- mirrors the
        # other drivers' own retry shape for a one-shot miss.
        fresh = _find_fresh(name, role)
        if fresh is not None:
            el = fresh
        interact(el, role)
        if gui.wait_until(lambda: status_shows(name), timeout=0.8, interval=0.1):
            return True
        failures.append(f"{name} ({role}) -> {_status_text(status_bar_el)!r}")
        return False

    drive_items(items)
    try:
        _, _, current = enumerate_now()
    except pyguitest.BackendCallTimeout as exc:
        current = None
        failures.append(f"enumerate_now() (initial) -> {exc}")
    clicked_tabs = {current} if current else set()
    for i in range(40):
        t0 = time.monotonic()
        print(f"tab scan {i}: enumerate_now()...", flush=True)
        try:
            _, tabs, _ = enumerate_now()
        except pyguitest.BackendCallTimeout as exc:
            print(
                f"  -> BackendCallTimeout after "
                f"{time.monotonic() - t0:.2f}s: {exc}",
                flush=True,
            )
            failures.append(f"enumerate_now() (tab scan) -> {exc}")
            break
        print(f"  -> {len(tabs)} tabs in {time.monotonic() - t0:.2f}s", flush=True)
        nxt = next((t for t in tabs if t[0] not in clicked_tabs), None)
        if nxt is None:
            break
        tname, tel = nxt
        clicked_tabs.add(tname)
        print(f"  clicking tab {tname!r}...", flush=True)
        _safe_click(tel)
        gui.wait_for_idle(app_pid, timeout=1.5)
        t1 = time.monotonic()
        try:
            actable, _, _ = enumerate_now()
        except pyguitest.BackendCallTimeout as exc:
            print(
                f"  -> BackendCallTimeout after "
                f"{time.monotonic() - t1:.2f}s: {exc}",
                flush=True,
            )
            failures.append(f"enumerate_now() (tab {tname!r}) -> {exc}")
            continue
        print(
            f"  -> {len(actable)} actable items on {tname!r}"
            f" in {time.monotonic() - t1:.2f}s", flush=True
        )
        drive_items(actable)


def drive_menus(gui, app_frame, app_pid, failures):
    """Open every top-level menu and walk its items via AT-SPI action
    clicks on the elements themselves -- no pointer coordinates needed,
    unlike every other platform's driver in this suite.
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
                if not _is_showing(el):
                    continue
            except Exception:
                continue
            out.append((name, el.role, el))
        return out

    def close_all():
        for _ in range(4):
            gui.tap_key("Escape")

    def open_path(path):
        items = visible_items()
        for hop in path:
            match = next((it for it in items if it[0] == hop), None)
            if match is None:
                return None
            _, _, el = match
            if not _safe_click(el):
                return None
            if not gui.wait_for_element(role=MENU_ROLES, within=app_frame, timeout=1.0):
                return None
            time.sleep(0.5)
            items = visible_items()
        return items

    def discover(path, depth, leaves):
        if depth > 3:
            return
        items = open_path(path)
        close_all()
        if items is None:
            return
        for name, role, _el in items:
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
        items = open_path(path)
        if items is None:
            return False, None
        match = next((it for it in items if it[0] == name), None)
        if match is None:
            close_all()
            return False, None
        _, _, el = match
        before = {w.title for w in gui.windows()}
        if not _safe_click(el):
            close_all()
            return False, None
        return True, before

    def _click_one_leaf(path, name):
        if name in MENU_SKIP_ITEMS or name in MENU_SKIP_SUBMENUS:
            return
        clicked, before = _open_and_click(path, name)
        if not clicked:
            return
        if name in MENU_DIALOG_ITEMS:
            dialog = _wait_new_app_window(gui, before, timeout=15.0)
            if dialog is None:
                close_all()
                clicked, before = _open_and_click(path, name)
                if clicked:
                    dialog = _wait_new_app_window(gui, before, timeout=15.0)
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
        try:
            _click_one_leaf(path, name)
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"{'/'.join([*path, name])} (menu item) -> {exc}")
            close_all()


def main():
    app = start_app()
    try:
        gui = pyguitest.connect(event_delay=0.15, key_delay=0.08)
        window = _wait_app_window(gui, timeout=15.0)
        if window is None and app.poll() is not None:
            raise Failure(f"torture-test app exited immediately with {app.returncode}")
        if window is not None:
            gui.activate_window(window)
            gui.wait_window_focus(window, timeout=5.0)
        app_frame = _wait_app_frame(gui, app.pid, timeout=5.0)
        expected = set(expected_controls())
        items = enumerate_controls(gui, app.pid, expected, app_frame)
        print(f"actable controls found (visible): {len(items)}")
        print(f"  sample: {sorted({n for n, *_ in items})[:14]}")
        failures = []
        drive(gui, items, failures, app.pid, expected, app_frame)
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
