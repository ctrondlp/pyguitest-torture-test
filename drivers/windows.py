"""Drive the torture-test app on Windows: UIA + win32, on the real
interactive desktop.

Must be launched via a Scheduled Task bound to the interactive session
("Logon Mode: Interactive only", created with `/ru <user>` and no stored
password), not plain SSH -- confirmed live: a plain SSH session lands in
Session 0 ("Background"/services session, confirmed via `(Get-Process -Id
$PID).SessionId`), where `gui.windows()` sees nothing at all. A scheduled
task created the same way (no `/rp` password, which forces "run only when
user is logged on") correctly lands in Session 1, the real interactive
desktop. See the deploy/run instructions kept alongside this file (not in
any repo) for the exact `schtasks` invocation.

Structurally closer to BSD/Linux than to macOS: `role="menu bar"` is the
app's own, embedded window-child menu bar (not a separate system-wide
one), `role="status bar"`/`role="page tab"` both work directly and report
real text via `.name`, and a combo box's stable name is `.name` itself
(no `.description` fallback needed, unlike Qt's AT-SPI bridge on Linux).
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


def _app_python():
    """`pythonw.exe`, not `python.exe` -- a console-subsystem interpreter
    would flash a visible command-prompt window on the real desktop for
    every run.
    """
    return str(Path(sys.executable).with_name("pythonw.exe"))


# A tuple, not a set -- see drivers/linux.py's identical comment
# for why (deterministic drive order; "combo box" last since "Toolbar
# Zoom" reflows the whole layout).
ACTABLE_ROLES = (
    "push button", "check box", "radio button", "entry", "text", "spin button",
    "list", "tree", "table", "calendar", "slider", "dial",
    "scroll bar", "layered pane", "combo box",
)
ALL_ROLES = ACTABLE_ROLES + ("status bar", "page tab")

# "Read Only Field" (app.py: setReadOnly(True)) can never report a change --
# nothing typed into it is accepted, by design, the same way "Disabled
# Action" never reports either. Excluded by name, matching every other
# platform's driver in this suite.
READ_ONLY_FIELDS = {"Read Only Field"}

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
    # The whole Slow Dialog submenu, not just the first entry: each one
    # opens a modal dialog after its own delay (`QTimer.singleShot`), and
    # an undismissed one surfaces in the middle of a later leaf and blocks
    # it. `_wait_new_app_window`'s 15 s budget covers the 10 s case.
    "1 second", "3 seconds", "5 seconds", "10 seconds", "Custom…",
    # Opens a modal "Control Inventory" window that stays up until closed.
    "Dump Controls",
    "About TortureTest…", "About Qt…",
}
MENU_ROLES = ("menu", "menu item")


class Failure(Exception):
    """A control did not report the interaction the driver drove it with.

    Collected rather than raised out of the run: the driver records every
    miss and keeps going, so one early failure cannot leave the rest of the
    app unexercised.
    """


def start_app():
    return subprocess.Popen(
        [_app_python(), "-m", "torture_test"], cwd=APP_DIR,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _wait_app_window(gui, app_pid, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in gui.windows():
            if getattr(w, "pid", None) == app_pid:
                return w
        time.sleep(0.2)
    return None


def _wait_new_app_window(gui, app_pid, before_titles, timeout):
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


def expected_controls():
    text = Path(APP_DIR, "tests", "test_app.py").read_text(encoding="utf-8")
    block = text.split("EXPECTED_CONTROLS = (", 1)[1].split("\n)", 1)[0]
    return re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', block)


def _control_name(el, role):
    """Combo boxes name themselves directly on this backend -- confirmed
    live ("Country"/"Font"/"Toolbar Zoom" all report via `.name`, with
    `.description` empty), unlike Qt's AT-SPI bridge on Linux/BSD, where
    the stable id lives in `.description` instead. No fallback needed,
    but tried anyway for robustness against a build where that changes.
    """
    try:
        if role == "combo box":
            return el.name or el.description
        return el.name
    except Exception:
        return None


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


def enumerate_controls(gui, app_pid, expected):
    try:
        elements = gui.find_elements(role=ALL_ROLES)
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
    clipped = []
    for el in elements:
        try:
            if getattr(el, "pid", None) != app_pid:
                continue
            role = el.role
            if role == "status bar":
                continue
            if not el.enabled:
                continue
            name = _control_name(el, role)
        except Exception:
            continue
        if not name or (name, role) not in expected:
            continue
        if role in ("entry", "text") and name in READ_ONLY_FIELDS:
            continue
        try:
            x, y, w, h = gui.extents(el)
        except Exception:
            continue
        if clip_bottom is not None and y + h > clip_bottom:
            clipped.append((name, role))
            continue
        if w > 0 and h > 0:
            found.append((name, role, el))
    return found, clipped


def drive(gui, items, failures, app_pid, expected):
    status_bar_el = None
    try:
        for el in gui.find_elements(role="status bar"):
            if getattr(el, "pid", None) == app_pid:
                status_bar_el = el
                break
    except Exception:
        pass

    def tap(name):
        gui.tap_key(name)

    def point(el):
        try:
            x, y, w, h = gui.extents(el)
        except Exception:
            return
        gui.move_mouse(int(x) + int(w) // 2, int(y) + int(h) // 2)

    def click(button=1):
        gui.click(button)

    def type_text(text):
        gui.type_text(text)

    def interact(el, role):
        point(el)
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
        elif role == "layered pane":
            click()

    def enumerate_now():
        try:
            elements = gui.find_elements(role=ALL_ROLES)
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
                name = _control_name(el, role)
            except Exception:
                continue
            if not name or (name, role) not in expected:
                continue
            if role in ("entry", "text") and name in READ_ONLY_FIELDS:
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
            try:
                if not drive_one(name, role, el):
                    ok = False
            except pyguitest.BackendCallTimeout as exc:
                failures.append(f"{name} ({role}) -> {exc}")
                ok = False
        return ok

    def status_shows(name):
        return name in _status_text(status_bar_el)

    def _find_fresh(name, role):
        try:
            for el in gui.find_elements(role=role, enabled=True):
                if getattr(el, "pid", None) != app_pid:
                    continue
                if _control_name(el, role) == name:
                    return el
        except Exception:
            pass
        return None

    def drive_one(name, role, el):
        if role == "push button" and name in POPUP_ONLY_BUTTONS:
            point(el)
            click()
            gui.wait_for_element(role="menu", timeout=1.0)
            tap("Escape")
            gui.wait_until_gone(role="menu", timeout=1.0)
            return True
        if role == "push button" and name in DIALOG_BUTTONS:
            before = {w.title for w in gui.windows() if getattr(w, "pid", None) == app_pid}
            point(el)
            click()
            dialog = _wait_new_app_window(gui, app_pid, before, timeout=15.0)
            if dialog is None:
                failures.append(f"{name} ({role}) -> dialog never appeared")
                return False
            gui.focus_window(dialog)
            if not gui.wait_window_focus(dialog, timeout=2.0):
                # Escape goes wherever focus actually is, so without this the
                # dialog stays open and blocks everything driven after it.
                gui.focus_window(dialog)
                gui.wait_window_focus(dialog, timeout=2.0)
            tap("Escape")
            if not gui.wait_window_close(dialog, timeout=2.0):
                # One more Escape: a single press can genuinely miss while a
                # dialog is still settling.
                tap("Escape")
                if not gui.wait_window_close(dialog, timeout=2.0):
                    # Named here, against the control that opened it. These
                    # dialogs are application-modal, so one that stays open
                    # makes every later control fail for a reason that has
                    # nothing to do with those controls.
                    failures.append(
                        f"{name} ({role}) -> its dialog never closed; "
                        "every control after this one ran against a modal window"
                    )
                    return False
            if name not in ("Open", "Save As") and not gui.wait_until(
                lambda: status_shows(name), timeout=0.8, interval=0.1
            ):
                failures.append(f"{name} ({role}) -> {_status_text(status_bar_el)!r}")
                return False
            return True
        interact(el, role)
        if gui.wait_until(lambda: status_shows(name), timeout=0.8, interval=0.1):
            return True
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
    for _ in range(40):
        try:
            _, tabs, _ = enumerate_now()
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"enumerate_now() (tab scan) -> {exc}")
            break
        nxt = next((t for t in tabs if t[0] not in clicked_tabs), None)
        if nxt is None:
            break
        tname, tel = nxt
        clicked_tabs.add(tname)
        point(tel)
        click()
        gui.wait_for_idle(app_pid, timeout=1.5)
        try:
            actable, _, _ = enumerate_now()
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"enumerate_now() (tab {tname!r}) -> {exc}")
            continue
        drive_items(actable)


def drive_menus(gui, app_pid, failures):
    """Open every top-level menu and walk its items, the same two-pass
    (discover read-only, then click leaves one at a time) shape as
    drivers/linux.py's own -- a QMenu closes its entire open chain
    the instant any leaf fires, same here as there.
    """
    def visible_items():
        try:
            elements = gui.find_elements(role=MENU_ROLES)
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
                if not el.visible:
                    continue
                x, y, w, h = gui.extents(el)
            except Exception:
                continue
            if w <= 0 or h <= 0:
                continue
            out.append((name, el.role, el))
        return out

    def click_at(el):
        try:
            x, y, w, h = gui.extents(el)
        except Exception:
            return
        gui.move_mouse(int(x) + int(w) // 2, int(y) + int(h) // 2)
        time.sleep(0.3)
        gui.click(1)

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
            click_at(el)
            if not gui.wait_for_element(role=MENU_ROLES, timeout=1.0):
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
        before = {w.title for w in gui.windows() if getattr(w, "pid", None) == app_pid}
        click_at(el)
        return True, before

    def _click_one_leaf(path, name):
        if name in MENU_SKIP_ITEMS or name in MENU_SKIP_SUBMENUS:
            return
        clicked, before = _open_and_click(path, name)
        if not clicked:
            return
        if name in MENU_DIALOG_ITEMS:
            dialog = _wait_new_app_window(gui, app_pid, before, timeout=15.0)
            if dialog is None:
                close_all()
                clicked, before = _open_and_click(path, name)
                if clicked:
                    dialog = _wait_new_app_window(gui, app_pid, before, timeout=15.0)
                if dialog is None:
                    failures.append(f"{'/'.join([*path, name])} (menu item) -> dialog never appeared")
                    close_all()
                    return
            gui.focus_window(dialog)
            if not gui.wait_window_focus(dialog, timeout=2.0):
                # Escape goes wherever focus actually is, so without this the
                # dialog stays open and blocks everything driven after it.
                gui.focus_window(dialog)
                gui.wait_window_focus(dialog, timeout=2.0)
            gui.tap_key("Escape")
            if not gui.wait_window_close(dialog, timeout=2.0):
                # One more Escape: a single press can genuinely miss while a
                # dialog is still settling.
                gui.tap_key("Escape")
                if not gui.wait_window_close(dialog, timeout=2.0):
                    # Named here, against the control that opened it. These
                    # dialogs are application-modal, so one that stays open
                    # makes every later control fail for a reason that has
                    # nothing to do with those controls.
                    failures.append(
                        f"{'/'.join([*path, name])} (menu item) -> its "
                        "dialog never closed; every later interaction ran "
                        "against a modal window"
                    )
                    close_all()
                    return
        close_all()
        gui.wait_until_gone(role="menu", timeout=1.0)

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
        window = _wait_app_window(gui, app.pid, timeout=15.0)
        if window is None and app.poll() is not None:
            raise Failure(f"torture-test app exited immediately with {app.returncode}")
        if window is not None:
            gui.activate_window(window)
            if not gui.wait_window_focus(window, timeout=5.0):
                # A real answer, not an exception: the compositor declined to
                # focus the window, so every key sent from here lands somewhere
                # else. Said once, loudly, because the alternative is one
                # "interaction did not report" per keyboard-driven control --
                # 27 of them on Omarchy, each showing the previous control's
                # status line, for a single cause. Action clicks still work
                # without focus, so the run continues rather than aborting.
                print("WARNING: the window never took keyboard focus; "
                      "controls that need typing or Tab will not report")
        expected = set(expected_controls())
        items, clipped = enumerate_controls(gui, app.pid, expected)
        print(f"actable controls found (visible): {len(items)}")
        if clipped:
            # Geometry, not a fault: these are expected controls
            # whose rectangle fell below the status bar, so the
            # window is clipping the fixture -- usually a screen
            # smaller than it needs. Said out loud because the
            # verdict below covers only what was driven.
            print(f"PARTIAL COVERAGE: {len(clipped)} expected control(s) are "
                  f"outside the visible window and will not be driven; "
                  f"a verdict below covers the rest only")
            print(f"  skipped: {sorted(n for n, _ in clipped)[:12]}")
        print(f"  sample: {sorted({n for n, *_ in items})[:14]}")
        if not items:
            # Nothing was enumerated, so nothing below can fail and the
            # verdict would read as a pass over the whole fixture. Measured
            # on macOS, where the window had not come up: three lines of
            # output, "all controls verified", exit 0. Coverage varies
            # legitimately by screen size, so no floor is imposed beyond
            # this one -- zero means the fixture was never reached.
            print("NO CONTROLS FOUND: the fixture published none of the "
                  "expected controls, so nothing was verified. Check that "
                  "the application window actually opened and that the "
                  "accessibility backend can see it.")
            return 2
        failures = []
        drive(gui, items, failures, app.pid, expected)
        drive_menus(gui, app.pid, failures)
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
