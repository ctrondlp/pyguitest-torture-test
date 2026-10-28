#!/usr/bin/env python3
"""Drive the torture-test app on macOS: native AX backend, pointer+keyboard.

Not the uinput/libinput-constrained Linux story -- macOS's own Accessibility
API event injection works normally for both pointer and keyboard, confirmed
live, so this driver follows BSD's pointer-and-keyboard pattern (click to
focus/select, then arrow keys), not COSMIC's pointer-free one.

Two structural differences from every Linux/BSD driver in this suite,
confirmed live before writing a line of this:

1. Qt moves this app's menu bar to the native, system-wide macOS menu bar --
   it is never a child of the app's own window, and it coexists with every
   other running app's own menu bar in the same unscoped search, so every
   lookup here filters by `pid`. Its *entire* structure (each top-level item
   -> its one "menu" child -> that menu's own item children, recursively for
   a submenu header) is walkable via `.children` at all times, open or
   closed -- unlike AT-SPI/dogtail, which only reports a QMenu's children
   once it is actually open. This makes discovery trivial (no
   click-open-read-close dance needed), and since every leaf item publishes
   a `click`/`pick` action, clicking is trivial too: a leaf's own `.click()`
   fires correctly with the parent menu never visually opened at all --
   confirmed live ("Reset Zoom" clicked and reported with "View" never
   opened on screen).
2. The main tab bar reports its tabs as `role="radio button"`, not
   `"page tab"` -- `role="page tab"` matches nothing on this backend at all.
   Scoped via the "page tab list" container's own children, not an unscoped
   role search, which would otherwise be indistinguishable from the app's
   *other*, ordinary radio-button groups (Option A/B/C, etc.) sharing the
   same role name. `enumerate_controls`'s own (name, role) filter against
   `expected` already excludes a tab's name from being treated as an
   ordinary "radio button" control (the expected set pairs that name with
   "page tab", never "radio button"), so only the explicit tab-container
   walk below needs this role-name awareness at all.
3. There is no "status bar" role at all -- Qt's QStatusBar reports as a
   plain, unnamed "label" container. The one with a "grow area" child
   (QStatusBar's own size-grip, always present) is identified by that
   unique structural marker rather than by role or name, and its own
   "label" children (the message, and the "controls: N" counter) are
   joined the same way every other platform's status text is.
"""
from __future__ import annotations

import os
import re
import shlex
import signal
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

# --minimal: drive one representative control per role (and one menu item).
MINIMAL = "--minimal" in sys.argv

# A tuple, not a set, for a deterministic drive order -- see
# drivers/linux.py's identical comment. No "page tab" (matches
# nothing here, see module docstring) and no "radio button" tab-list
# ambiguity: ordinary radio-button groups are driven from this list, the
# main tab bar's own radio-button children are walked separately in
# enumerate_now()/_tab_candidates() below. "combo box" is deliberately
# last -- "Toolbar Zoom"'s reflow must not stale a control driven right
# after it.
ACTABLE_ROLES = (
    "push button", "check box", "radio button", "entry", "text", "spin button",
    "list", "tree", "table", "calendar", "slider", "dial",
    "scroll bar", "layered pane", "combo box",
)
ALL_ROLES = ACTABLE_ROLES + ("page tab list",)

# "Read Only Field" (app.py: setReadOnly(True)) can never report a change --
# nothing typed into it is accepted, by design, the same way "Disabled
# Action" never reports either. Excluded by name, matching this file's own
# style for every other by-design special case (POPUP_ONLY_BUTTONS,
# MENU_SKIP_ITEMS, ...) rather than reaching into AX's own "settable"
# attribute for an equivalent answer -- simpler, and consistent with how
# this whole file already names its special cases.
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
    # AutoFill/dictation/emoji live in macOS's own Edit menu, not the
    # fixture's: each one opens system UI in another process entirely
    # (Keychain, the dictation HUD, the character palette), so driving
    # them tests macOS, not this application, and leaves windows behind
    # that nothing here owns.
    "Contact…", "Passwords…", "Credit Card…",
    "Start Dictation…", "Emoji & Symbols",
}
MENU_SKIP_SUBMENUS = {"Language"}
FULLSCREEN_ITEMS = {"Enter Full Screen", "Exit Full Screen"}
"""macOS's own View-menu toggle, driven as a pair rather than clicked once.

Clicking one flips it into the other, so the walk enters full screen,
verifies the flip, leaves again and verifies the flip back -- and the
application is in the same state afterwards as before, which every later
leaf depends on.
"""
MENU_DIALOG_ITEMS = {
    "Information", "Warning", "Critical", "Question",
    # Modal, like its QMessageBox siblings above -- it must be listed
    # here or the driver clicks it, never dismisses it, and the
    # application-modal dialog then blocks every later menu click.
    "Error Message",
    "Get Text", "Get Integer", "Get Item",
    # File > Open… and File > Save As… open the same file dialog as Tools >
    # File Dialog…, and on macOS that is the *native* NSOpenPanel: a
    # separate process, application-modal, and it does not go away on its
    # own. Left off this list the walk opened two of them and dismissed
    # neither, and every later dialog leaf was then behind a modal panel --
    # which is how `Tools/Message Boxes/Information` and
    # `Tools/Progress Dialog…` came to fail a full run while both pass in
    # isolation (confirmed live 2026-10-15: two stray `Open File` windows
    # still listed at the end of the walk).
    "Open…", "Save As…",
    "Color Picker…", "Font Picker…", "File Dialog…",
    "Progress Dialog…", "Custom Dialog…", "Wizard…", "MDI Workspace…",
    # The whole Slow Dialog submenu, not just "1 second": each one opens a
    # dialog after its own delay, and an undismissed one surfaces in the
    # middle of a later leaf and blocks it. `_wait_new_app_window`'s 15 s
    # budget covers the 10 s case.
    "1 second", "3 seconds", "5 seconds", "10 seconds", "Custom…",
    # Opens a "Control Inventory" window that stays up until dismissed.
    "Dump Controls",
    "About TortureTest…", "About Qt…",
}


class Failure(Exception):
    """A control did not report the interaction the driver drove it with.

    Collected rather than raised out of the run: the driver records every
    miss and keeps going, so one early failure cannot leave the rest of the
    app unexercised.
    """


def start_app():
    """Launch the app into the real Aqua session, not this SSH shell's own.

    Confirmed live: `launchctl managername` for a plain SSH session answers
    "Background", not "Aqua" -- processes started directly here (a plain
    `subprocess.Popen`) land in the same background bootstrap domain, which
    lacks full access to WindowServer-dependent services even though basic
    window rendering partially still works. `QFileDialog`'s native open/
    save panel and `QTextEdit`'s Cocoa text services (spelling,
    substitutions) both hang the entire app indefinitely under that
    domain -- confirmed live, including that the process never exits
    (`app.poll()` stays `None`) while every other control also stops
    responding to input.

    `open -a <target>` fixes this: confirmed live (`launchctl managername`
    read back from a process started this way answers "Aqua"), and it
    needs no elevated privilege -- `launchctl asuser`, the other
    documented way to do this, requires root (confirmed live: "Operation
    not permitted" for this user without `sudo`).

    `<target>` is a small generated shell-script wrapper, not the Python
    interpreter directly with `--args` -- confirmed live that `open -a
    <python3-path> --args <script>` silently never launches anything at
    all (no process, no window, no error): `-a` appears to need something
    LaunchServices will treat as a launchable application (a `.app`
    bundle, or a plain Unix-executable script), and a bare interpreter
    binary passed as the target does not qualify the same way. The
    wrapper is written fresh to a temp file on every call rather than
    expected to already exist on the box, so this driver stays
    self-contained.

    `open` itself only hands the launch request to `launchd` and returns
    immediately; the real app process is a separate pid, discovered below
    by matching its window title (see `_wait_app_window_by_title`), not
    returned by this call.
    """
    wrapper = "/tmp/pyguitest_torture_mac_launch.sh"
    with open(wrapper, "w") as f:
        # Both paths quoted: a checkout directory with a space in it would
        # otherwise split into two shell words and the launch would fail
        # with a confusing "No such file or directory".
        f.write(
            "#!/bin/bash\n"
            f"cd {shlex.quote(APP_DIR)}\n"
            f"exec {shlex.quote(APP_PYTHON)} -m torture_test\n"
        )
    os.chmod(wrapper, 0o755)
    subprocess.run(
        ["open", "-a", wrapper],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _wait_app_window_by_title(gui, title, timeout):
    """Poll for the app's own toplevel window, by title -- its pid is not
    known ahead of time since `start_app()` launches via `open`, which
    reports no pid of its own for the real app process.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in gui.windows():
            if getattr(w, "title", None) == title:
                return w
        time.sleep(0.2)
    return None


def _wait_app_window_element(gui, app_pid, timeout):
    """Poll for the app's own top-level AX "window" element, by pid."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in gui.elements(role="window"):
            if getattr(w, "pid", None) == app_pid:
                return w
        time.sleep(0.2)
    return None


def _wait_new_app_window(gui, before_handles, timeout):
    """Poll for a window whose handle was not in `before_handles`.

    Diffs on the window *handle* -- the window server's own number for one
    window, unique per window -- and is not scoped to the app's own pid at
    all. Two separate live findings forced each half of that:

    - Not pid-scoped, because macOS's native open/save panel is a separate
      process (a system XPC service, not the app) reporting the exact same
      title as the main window it belongs to, under its own pid. Filtering
      by the app's pid -- what every other platform's identical-looking
      helper in this suite does -- would never detect that panel at all.
    - Handles rather than (title, pid) pairs, because this app's three
      `QMessageBox` leaves (Warning/Critical/Question) all open dialogs
      whose title is the empty string, one straight after another. With a
      pair-based diff they are indistinguishable from each other and from
      the one just dismissed, and `windows()` caches the window-server list
      for `_SNAPSHOT_SECONDS` (0.25s), which is long enough for a
      just-closed `('', pid)` to still be in the "before" set captured for
      the next leaf. The next dialog then looks like it was already there
      and is never detected -- confirmed live: exactly those three, plus
      the leaf after them, were the only menu failures left in a full run,
      while every one of them passes in isolation where the extra delay
      lets the cache turn over. A handle is new for a new window however
      identical its title, so the diff is exact rather than probabilistic.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            for w in gui.windows():
                if w.handle in before_handles:
                    continue
                return w
        except Exception:
            pass
        time.sleep(0.2)
    return None


# Dismiss-button preference order: Cancel before Close before OK, so a file
# dialog is dismissed rather than accepted (Return/OK on a save panel would
# write a file; Cancel never has a side effect).
DISMISS_BUTTONS = ("Cancel", "Close", "OK")


def _dismiss_dialog(gui, app_pid, dialog):
    """Close `dialog`: Escape first, then its own dismiss button via AX.

    Escape alone is not enough on every macOS, and the reason is Cocoa, not
    focus. The fixture's QErrorMessage (shown via `showMessage()`, i.e.
    `show()` + modal) comes up on Sequoia 15.8 as an *AXSheet* attached to
    the main window rather than a standalone window: empty CG title, absent
    from the app's AX window list. It nonetheless holds keyboard focus --
    measured live, an injected Space activates its OK button and an injected
    Return hits the default button, both closing it -- so pyguitest's
    `wait_window_focus` reporting it focused is correct. Only injected
    Escape fails to fire its reject, while an in-process Escape fires it
    fine. The differentiator is the sheet: a standalone dialog *window*
    (AXDialog -- the fixture's Progress dialog) closes on injected Escape,
    whereas a sheet swallows it, because Cocoa maps Escape to the sheet's
    cancel operation and QErrorMessage carries no cancel button. macOS 26 on
    the old box showed these same leaves passing over Escape alone, which is
    why this never failed before the Sequoia box joined the fleet.

    So this is a cancel-less-sheet quirk, not a focus bug. The route that
    always works is the dialog's own button over the AX action API, which
    needs no key routing at all. Scoping it is free: a modally-BLOCKED push
    button publishes no actions whatsoever (confirmed live -- the main
    window's buttons raise ElementNotActionable while a dialog is up), so
    "publishes click" selects the active dialog's buttons and can never
    press the main window's.
    """
    gui.tap_key("Escape")
    if gui.wait_window_close(dialog, timeout=2.0):
        return True
    for wanted in DISMISS_BUTTONS:
        for el in gui.find_elements(role="push button"):
            if getattr(el, "pid", None) != app_pid or el.name != wanted:
                continue
            if "click" not in (el.actions or ()):
                continue
            try:
                el.click()
            except Exception:
                continue
            if gui.wait_window_close(dialog, timeout=2.0):
                return True
    # One more Escape: a single press can genuinely miss while a dialog is
    # still settling, and for a dialog with unnamed/localized buttons it is
    # still the only route left.
    gui.tap_key("Escape")
    return gui.wait_window_close(dialog, timeout=2.0)


def expected_controls():
    text = Path(APP_DIR, "tests", "test_app.py").read_text(encoding="utf-8")
    block = text.split("EXPECTED_CONTROLS = (", 1)[1].split("\n)", 1)[0]
    return re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', block)


def _clickable(gui, app_window, x, y, w, h):
    """Whether this rectangle's centre is a point inside the app's own window.

    A control scrolled past the bottom of the page still reports a real,
    plausible-looking rectangle here, and clicking its centre does not miss
    harmlessly -- it clicks whatever else owns that point. Both halves of
    that were confirmed live and both did real damage:

    - Five spin buttons on "Text & Numbers" reported centres at y=1004..1156
      on an 800px-tall display. `CGEventPost` clamps a pointer move to the
      display, so those clicks landed on the screen's bottom edge.
    - "Rich Text" reported (160, 724, 883, 80) against an app window of
      (0, 31, 1080, 704) -- 11 pixels of it visible, centre at y=764, which
      is *below the window entirely and on top of the Dock*. `element_at`
      resolved that exact point to `role='dock item' name='Notes'`: the
      driver was clicking the Notes icon in the Dock, which launched Notes,
      took keyboard focus away from the app, and so swallowed every
      subsequent `type_text` and every `Escape` meant for a dialog. That is
      what made whole runs look like the app had hung, and what filled a
      real Note with the word "torture".

    Clipping to the window's own rectangle is the direct form of the
    `clip_bottom` guard the Linux and BSD drivers already carry (they clip
    against the status bar's top edge), and it catches a control pushed off
    any edge rather than only off the bottom. A control clipped out here is
    genuinely unreachable without scrolling the page, which is the same
    thing those drivers decided.
    """
    try:
        wx, wy, ww, wh = gui.extents(app_window)
    except Exception:
        return True
    cx, cy = int(x) + int(w) // 2, int(y) + int(h) // 2
    return wx <= cx < wx + ww and wy <= cy < wy + wh


def _find_status_container(gui, app_pid, app_window):
    """QStatusBar's own container, identified by its unique "grow area"
    (size-grip) child -- see the module docstring for why role/name cannot
    identify it on this backend.

    Walked manually via `.children` rather than `find_elements(role="grow
    area", ...)`: confirmed live that search finds nothing at all for this
    role (0 results, scoped or not) even though the element is right there
    in the tree and a plain recursive `.children` walk finds it
    immediately -- a real, narrow gap in this backend's role-name matching
    for "grow area" specifically, not something to work around by
    guessing a different role string. Worth a closer look as a pyguitest
    bug in its own right; noted, not chased further here since the
    manual walk is a correct, available alternative using pyguitest's own
    public `.children` API, not a reach around it.
    """
    def find(el, depth=0):
        if depth > 12:
            return None
        try:
            if el.role == "grow area":
                return el
        except Exception:
            return None
        try:
            children = el.children
        except Exception:
            return None
        for c in children:
            found = find(c, depth + 1)
            if found is not None:
                return found
        return None

    grow = find(app_window)
    if grow is None:
        return None
    try:
        if getattr(grow, "pid", None) != app_pid:
            return None
    except Exception:
        pass
    return grow.parent


def _status_text(status_container):
    """The status bar's current message, via its two "label" children.

    Reads `.text`, not `.name` -- confirmed live this is the one AX
    attribute macOS exposes a QLabel's string through at all (`.name`/
    `.value`/`.description` are all empty for every label in this app,
    always, including the always-populated "controls: N" counter visible
    from the moment the app starts). `Element.text`'s own docstring
    already says as much ("on a Mac the label's string is in the one
    attribute that holds text") -- this is pyguitest's own, correctly
    documented API; the first version of this driver reached for `.name`
    out of habit from every Linux/BSD driver's identical-looking helper,
    not because `.text` was hidden or hard to find.
    """
    if status_container is None:
        return ""
    try:
        parts = []
        for child in status_container.children:
            if child.role == "label":
                text = child.text
                if text:
                    parts.append(text)
        return " ".join(parts)
    except Exception:
        return ""


def _tab_candidates(gui, app_pid, app_window):
    """The main tab bar's own tabs: (name, element). The main bar is the
    topmost "page tab list" container; embedded demo tab bars share the
    role but sit lower in the window -- same disambiguation
    drivers/linux.py's own enumerate_now() uses, just applied to a
    container search here instead of a flat "page tab" role search, which
    matches nothing on this backend (see module docstring).
    """
    try:
        lists = gui.find_elements(role="page tab list", within=app_window)
    except Exception:
        return []
    own = []
    for lst in lists:
        if getattr(lst, "pid", None) != app_pid:
            continue
        try:
            x, y, w, h = gui.extents(lst)
        except Exception:
            continue
        if w <= 0 or h <= 0:
            continue
        own.append((lst, y))
    if not own:
        return []
    top_y = min(y for (_lst, y) in own)
    out = []
    for lst, y in own:
        if y > top_y + 5:
            continue
        try:
            for c in lst.children:
                if c.role != "radio button":
                    continue
                name = c.name
                if not name:
                    continue
                out.append((name, c))
        except Exception:
            continue
    return out


def enumerate_controls(gui, app_pid, expected, app_window=None):
    try:
        elements = gui.find_elements(role=ACTABLE_ROLES, within=app_window)
    except Exception:
        elements = []
    found = []
    clipped = []
    for el in elements:
        try:
            if getattr(el, "pid", None) != app_pid:
                continue
            role = el.role
            if not el.enabled:
                continue
            # Qt publishes a combo box's current text as its Name; the
            # stable id is in the description.
            name = (el.description or el.name) if role == "combo box" else el.name
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
        if not (w > 0 and h > 0):
            # No rectangle at all: not clipped, just not realised yet.
            continue
        if not _clickable(gui, app_window, x, y, w, h):
            # A real rectangle outside the app's own window -- the case
            # `_clickable` exists for, and the one worth counting: clicking
            # its centre would hit whatever else owns that point.
            clipped.append((name, role))
            continue
        found.append((name, role, el))
    return found, clipped


def drive(gui, items, failures, app_pid, expected, app_window=None, window=None):
    status_container = _find_status_container(gui, app_pid, app_window)

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
        elif role in ("spin button", "slider", "dial", "scroll bar"):
            # Confirmed live: `.focused` stays False after click() for all
            # four of these, unlike entry/text (where click() does grant
            # real keyboard focus) -- a subsequent arrow-key press lands
            # nowhere and the control never reports. Each one publishes
            # "increment"/"decrement" AX actions directly, usable with no
            # keyboard focus at all -- confirmed live to fire the real
            # valueChanged-equivalent signal for a spin button, a slider,
            # and a scroll bar alike.
            try:
                el.do_action("increment")
            except Exception:
                pass
        elif role == "combo box":
            click()
            time.sleep(0.3)
            tap("Down")
            tap("Return")
            gui.wait_for_idle(app_pid, timeout=1.5)
        elif role in ("list", "tree", "table", "calendar"):
            # The container itself publishes only "raise" (confirmed live)
            # -- no click/select action, and `.focused` stays False after
            # click() the same way spin buttons/sliders do, so arrow-key
            # navigation has nothing to act on either. Each row/item child
            # publishes its own "raise" action though, and clicking one
            # directly (the AX action route, same `Element.click()` used
            # everywhere else) fires the real selection-changed signal --
            # confirmed live for a table row; used uniformly for all four
            # container roles rather than only the one it was found on.
            #
            # Any row *except* the selected one: clicking the row a widget's
            # selection already sits on changes nothing and emits nothing,
            # which is how "Undo History" came back reporting the previous
            # control's status line. A QUndoView's first actionable child is
            # the row its stack index is on, so "the first one with actions"
            # was reliably the one that could not work. drivers/linux.py
            # skips the selected child for the same reason, found on the
            # same control.
            def _unselected_rows(container):
                for candidate in container.children:
                    if not candidate.actions:
                        continue
                    try:
                        if candidate.selected:
                            continue
                    except Exception:
                        # No selected state to read: still worth clicking,
                        # which is the old behaviour for such a child.
                        pass
                    yield candidate

            for child in _unselected_rows(el):
                try:
                    child.click()
                    break
                except Exception:
                    continue
        elif role == "layered pane":
            click()

    def enumerate_now():
        try:
            elements = gui.find_elements(role=ACTABLE_ROLES, within=app_window)
        except Exception:
            elements = []
        actable = []
        for el in elements:
            try:
                if getattr(el, "pid", None) != app_pid:
                    continue
                role = el.role
                if not el.enabled:
                    continue
                name = (el.description or el.name) if role == "combo box" else el.name
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
            if w > 0 and h > 0 and _clickable(gui, app_window, x, y, w, h):
                actable.append((name, role, el))
        tabs = _tab_candidates(gui, app_pid, app_window)
        current = next((name for name, el in tabs if el.selected), None)
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
        return name in _status_text(status_container)

    def _find_fresh(name, role):
        try:
            for el in gui.find_elements(role=role, within=app_window):
                if getattr(el, "pid", None) != app_pid or not el.enabled:
                    continue
                el_name = (el.description or el.name) if role == "combo box" else el.name
                if el_name == name:
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
            return True
        if role == "push button" and name in DIALOG_BUTTONS:
            before = {w.handle for w in gui.windows()}
            point(el)
            click()
            dialog = _wait_new_app_window(gui, before, timeout=15.0)
            if dialog is None:
                failures.append(f"{name} ({role}) -> dialog never appeared")
                return False
            gui.focus_window(dialog)
            if not gui.wait_window_focus(dialog, timeout=2.0):
                # Escape goes wherever focus actually is, so without this the
                # dialog stays open and blocks everything driven after it.
                gui.focus_window(dialog)
                gui.wait_window_focus(dialog, timeout=2.0)
            if not _dismiss_dialog(gui, app_pid, dialog):
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
                failures.append(
                    f"{name} ({role}) -> {_status_text(status_container)!r}"
                )
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
        failures.append(f"{name} ({role}) -> {_status_text(status_container)!r}")
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


def drive_menus(gui, app_pid, failures, window=None):
    """Walk the whole native menu bar structurally -- no opening/closing
    needed at all, see the module docstring for why this is correct here
    (and simpler than every other platform's click-open-read-close dance).
    """
    try:
        bar = next(b for b in gui.find_elements(role="menu bar") if getattr(b, "pid", None) == app_pid)
    except StopIteration:
        failures.append("menu bar -> not found")
        return

    def submenu_of(item):
        """The one "menu" child holding `item`'s own entries, or None."""
        try:
            for c in item.children:
                if c.role == "menu":
                    return c
        except Exception:
            pass
        return None

    def discover(menu, path, depth, leaves):
        if depth > 3:
            return
        try:
            items = list(menu.children)
        except Exception:
            return
        for item in items:
            try:
                name = item.name
            except Exception:
                continue
            if not name:
                continue
            if name in MENU_BAR_NAMES and depth == 0:
                continue
            sub = submenu_of(item)
            if sub is not None:
                if name in MENU_SKIP_SUBMENUS:
                    continue
                discover(sub, [*path, name], depth + 1, leaves)
                continue
            leaves.append((list(path), name, item))

    leaves = []
    for bar_name in MENU_BAR_NAMES:
        try:
            top = next((c for c in bar.children if c.name == bar_name), None)
            if top is None:
                continue
            sub = submenu_of(top)
            if sub is None:
                continue
            discover(sub, [bar_name], 0, leaves)
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"{bar_name} (menu discovery) -> {exc}")

    def _view_item(wanted):
        """Re-find a View-menu leaf by name.

        Re-reads the menu *bar* from the session every call, not just the
        View menu's children: the children list captured when the walk
        started keeps reporting the old name after macOS flips the
        full-screen item, so a search through it never sees the flip.
        Confirmed live -- re-fetching sees `Exit Full Screen` within a
        second, the cached list never does.
        """
        try:
            fresh = next(
                b for b in gui.find_elements(role="menu bar")
                if getattr(b, "pid", None) == app_pid
            )
        except Exception:
            fresh = bar
        top = next((c for c in fresh.children if c.name == "View"), None)
        menu = submenu_of(top) if top is not None else None
        if menu is None:
            return None
        try:
            return next((c for c in menu.children if c.name == wanted), None)
        except Exception:
            return None

    def _toggle_full_screen_back(path, name):
        """`name` has just been clicked, so the item now reads as its
        opposite: confirm that, click it, and confirm it reads as `name`
        again. Leaving the app full-screen would break every later leaf.
        """
        label = "/".join([*path, name])
        opposite = ("Exit Full Screen" if name == "Enter Full Screen"
                    else "Enter Full Screen")
        if not gui.wait_until(lambda: _view_item(opposite) is not None,
                              timeout=6.0, interval=0.3):
            failures.append(
                f"{label} (menu item) -> the item never flipped to "
                f"{opposite!r}, so full screen did not toggle"
            )
            return
        leaf = _view_item(opposite)
        try:
            leaf.click()
        except pyguitest.BackendCallTimeout:
            raise
        except Exception:
            failures.append(f"{label} (menu item) -> {opposite!r} click failed")
            return
        if not gui.wait_until(lambda: _view_item(name) is not None,
                              timeout=8.0, interval=0.3):
            failures.append(
                f"{label} (menu item) -> {opposite!r} did not restore the "
                f"window; the app is still full screen and every later "
                f"interaction ran that way"
            )
            return
        if window is not None:
            try:
                gui.activate_window(window)
                gui.wait_window_focus(window, timeout=3.0)
            except Exception:
                pass

    def _click_leaf(path, name, item):
        if name in MENU_SKIP_ITEMS or name in MENU_SKIP_SUBMENUS:
            return
        if window is not None:
            try:
                gui.activate_window(window)
            except Exception:
                pass
        before = {w.handle for w in gui.windows()}
        try:
            item.click()
        except pyguitest.BackendCallTimeout:
            raise
        except Exception:
            failures.append(f"{'/'.join([*path, name])} (menu item) -> click failed")
            return
        if name in FULLSCREEN_ITEMS:
            _toggle_full_screen_back(path, name)
            return
        if name in MENU_DIALOG_ITEMS:
            dialog = _wait_new_app_window(gui, before, timeout=15.0)
            if dialog is None:
                failures.append(f"{'/'.join([*path, name])} (menu item) -> dialog never appeared")
                return
            gui.focus_window(dialog)
            if not gui.wait_window_focus(dialog, timeout=2.0):
                # Escape goes wherever focus actually is, so without this the
                # dialog stays open and blocks everything driven after it.
                gui.focus_window(dialog)
                gui.wait_window_focus(dialog, timeout=2.0)
            if not _dismiss_dialog(gui, app_pid, dialog):
                # Named here, against the control that opened it. These
                # dialogs are application-modal, so one that stays open
                # makes every later control fail for a reason that has
                # nothing to do with those controls.
                failures.append(
                    f"{'/'.join([*path, name])} (menu item) -> its "
                    "dialog never closed; every later interaction ran "
                    "against a modal window"
                )
                return

    for path, name, item in leaves:
        try:
            _click_leaf(path, name, item)
        except pyguitest.BackendCallTimeout as exc:
            failures.append(f"{'/'.join([*path, name])} (menu item) -> {exc}")


def main():
    start_app()
    app_pid = None
    gui = None
    try:
        gui = pyguitest.connect(backend=["macos", "macquartz"], event_delay=0.15, key_delay=0.05)
        window = _wait_app_window_by_title(gui, "TortureTest", timeout=15.0)
        if window is None:
            raise Failure("torture-test app window never appeared")
        app_pid = window.pid
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
        app_window = _wait_app_window_element(gui, app_pid, timeout=5.0)
        expected = set(expected_controls())
        items, clipped = enumerate_controls(gui, app_pid, expected, app_window)
        print(f"actable controls found (visible): {len(items)}")
        if clipped:
            # Geometry, not a fault: expected controls whose rectangle falls
            # outside the app window, so the verdict below covers only what
            # was driven. Said out loud because that verdict otherwise reads
            # identically to a full pass.
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
        drive(gui, items, failures, app_pid, expected, app_window, window)
        drive_menus(gui, app_pid, failures, window)
        if failures:
            print(f"STATUS CHECK FAILED: {len(failures)} interaction(s) did not report")
            for failure in failures:
                print(f"  - {failure}")
            return 2
        print("all controls verified")
        return 0
    finally:
        if gui is not None:
            try:
                gui.close()
            except Exception:
                pass
        if app_pid is not None:
            # SIGTERM only, deliberately not escalated to SIGKILL. The app
            # here is not a child of this driver -- it was started through
            # `open -a`, so launchd owns it and its pid was found by window
            # title -- which means this cannot `wait()` on it to learn
            # whether it exited. Polling with `kill(pid, 0)` does not
            # answer that either: the call still succeeds for a process
            # that has died but not yet been reaped by its real parent, so
            # a poll-then-SIGKILL loop escalates even when SIGTERM worked,
            # and if the pid has been reaped *and reused* by then the
            # SIGKILL lands on an unrelated process. SIGTERM is enough in
            # practice: a Qt app with no modal dialog open exits on it, and
            # a leftover window is visible in the next run's window diff.
            try:
                os.kill(app_pid, signal.SIGTERM)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
