"""Shared core for the pointer-free AT-SPI driver family.

The Wayland drivers (``linux.py``, ``debian.py``, ``cosmic.py``) proved out
one strategy -- AT-SPI action clicks for buttons/tabs/menus, real Tab-walked
keyboard focus for everything that types or arrows -- and then each carried a
full private copy of it. This module is that strategy, written once: a thin
platform driver now supplies a :class:`Platform` and its own module docstring
(the live-verified platform findings stay with the platform), and calls
:func:`run`.

``bsd.py`` (X11, pointer-driven -- a genuinely different interaction
strategy) imports only the shared fixture constants from here. ``macos.py``
and ``windows.py`` (AX / UIA) still carry their own copies and are not served
by this module; migrating their shared constants needs a live box to verify
the changed deployment, which is recorded as open in VALIDATION.md.

The one behavioral change from the drivers this was extracted from is how
keyboard focus reaches a control. The old shape walked Tab up to 60 times
*per control*, re-walking the whole ring from scratch for each target --
O(n^2) presses per page, measured as the direct cause of the 900 s timeouts
on KaOS/niri and Omarchy/Hyprland where the key path is slow. The new shape
(:meth:`DriverRun._ring_drive`) walks the ring *once per page*: after each
Tab press it asks which pending target took focus, drives that control right
there, and moves on. Controls the ring never reaches -- QScrollBar,
QTableView, QUndoView are never Tab-reachable at all -- fall through to the
same per-role fallbacks the old drivers used (``Element.focus()``, child
action clicks), now after a short confirmation seek instead of a 60-press
one, because the full ring walk already supplied the "not Tab-reachable"
verdict the long seek existed to produce.
"""

from __future__ import annotations

import contextlib
import faulthandler
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pyguitest

# The repo root: this file lives in <repo>/drivers/, so the app package
# `torture_test` sits next to it one level up. Overridable for a checkout
# somewhere else, but needs no configuration in the normal case -- nothing
# here may hard-code a developer's own path, since this is a pushable repo.
APP_DIR = os.environ.get("TORTURE_APP_DIR") or str(
    Path(__file__).resolve().parent.parent
)
# The interpreter that runs the *app*, which is not always the one running
# the driver: the app needs PySide6, the driver needs pyguitest, and on
# several test boxes those live in different virtualenvs.
APP_PYTHON = os.environ.get("TORTURE_APP_PYTHON") or sys.executable

# --minimal: drive one representative control per role (and one menu item)
# rather than every one. A button proven clickable proves the others are too,
# so this is the fast core pass -- used for stability campaigns where the
# full per-control sweep would be redundant. Without it, every control is
# driven.
MINIMAL = "--minimal" in sys.argv

# A tuple rather than a set, and "combo box" deliberately last. This is the
# canonical statement of both reasons; the other drivers in this directory
# point here rather than repeating them.
#
# A tuple because a set iterates in arbitrary order under per-process hash
# randomization, which makes the drive order differ from run to run. That
# was the source of a recurring "Option A -> 'Changed: Toolbar Zoom = 125%'"
# miss: a combo box driven earlier than expected had already reflowed the
# layout under the control being checked.
#
# "combo box" last because "Toolbar Zoom" is one, and changing it rescales
# the app-wide font and so reflows the whole window. Driving every combo box
# after everything else means that reflow cannot stale the extents of the
# control driven right after it.
ACTABLE_ROLES = (
    "push button", "check box", "radio button", "entry", "text", "spin button",
    "list", "tree", "table", "calendar", "slider", "dial",
    "scroll bar", "page tab list", "layered pane", "combo box",
)
ALL_ROLES = ACTABLE_ROLES + ("status bar", "page tab")

# The roles the ring pass drives through real keyboard focus; everything
# else in ACTABLE_ROLES is driven through its accessible action and needs no
# focus at all. "scroll bar" is deliberately NOT here: a QScrollBar is never
# reachable via Tab (confirmed live, Debian 13) and publishes
# "Increase"/"Decrease" actions that need no focus, so it is driven as an
# action control.
KEYBOARD_ROLES = (
    "entry", "text", "spin button", "combo box", "slider", "dial",
    "list", "calendar", "tree", "table",
)

# Ring-walk budgets. The fruitless limit is the operative one: 35 presses in
# a row that land on nothing pending means the walk has been around every
# reachable widget on the page, so whatever is still pending is not
# Tab-reachable and belongs to the fallback path. This has to be as patient
# as the old per-control seek was at *entering* a freshly-switched page: a
# tab is switched by an AT-SPI action click, which moves no keyboard focus,
# so when the ring starts pressing Tab focus is wherever the previous page
# left it -- often on a now-hidden widget, from which the first Ctrl+Tab
# escape (below) is what cycles focus back into the visible page. At 35 the
# ring gave up after a single escape and dumped a whole page to the slow
# fallback (measured live on this maintainer's Fedora box, the Choosers tab:
# 12 controls, ring 0 hits, then 10-16 s each via fallback) -- flaky,
# because whether focus re-entered within 35 presses was marginal. 60 (the
# old seek's own budget) gives the escape two firings and far more plain
# Tabs, matching the persistence that made the old code land. The press
# budget is a hard backstop so a page that keeps yielding hits still
# terminates; it scales with the page so a long tab order is not cut short.
RING_FRUITLESS_LIMIT = 60
RING_PRESS_BUDGET = 200
# A text area consumes Tab instead of moving focus, so the walk can enter
# one and never leave (KaOS: focus sat in 'Notes' for 27 straight presses,
# and every control after it in the tab order failed). Ctrl+Tab is Qt's way
# out, sent on a counter because reading focus state every press costs a bus
# round trip and made the run crawl.
RING_ESCAPE_EVERY = 25
# The fallback seek for a control the ring pass did not reach. Kept at the
# old per-control budget, deliberately: a control the ring missed is NOT
# proven unreachable -- the ring also misses an entire page when focus never
# entered it (see RING_FRUITLESS_LIMIT), and a shortened seek there would
# fail to focus genuinely reachable controls. The ring is the fast path; the
# fallback must stay exactly as capable as the seek it replaced, so the
# worst case (focus will not enter a page at all) degrades to the old
# behaviour rather than to a new failure.
FALLBACK_SEEK_PRESSES = 60

# Window focus is re-read during the run rather than trusted from startup.
# `run()` establishing it once was a snapshot, and a run is minutes long:
# an idle lock, a screensaver, a notification or another app's dialog takes
# focus, and from that point every Tab and every keystroke lands in whatever
# took it while the driver still believes it has focus. That is the measured
# shape of the macOS run that walked into the Dock and the Mint and Omarchy
# runs that looked like driver bugs and were session locks. Re-reading costs
# a bus round trip, so the answer is cached this long -- short enough that a
# steal is caught within one control, long enough that the ring's Tab presses
# do not each pay for it.
FOCUS_RECHECK_SECONDS = 2.0
# Consecutive failed re-assertions before the run stops asking. Without a
# bound, a session that will not grant focus at all (a locked screen) pays a
# full focus_window retry per keyboard control -- the "27 failures for one
# cause" the startup warning exists to avoid. With it, the driver says so
# once and lets the remaining controls report honestly.
FOCUS_GIVE_UP_AFTER = 3

# "Menu Button" is an InstantPopup QToolButton -- opening its menu, not
# emitting `clicked`, is the real click behavior. Click, dismiss with Escape,
# and skip the status-bar assertion (no report is coming).
POPUP_ONLY_BUTTONS = {"Menu Button"}

# "Open", "Save As" and "About TortureTest" each open a real top-level window
# (QFileDialog / QMessageBox). "Open"/"Save As" only report inside `if path:`,
# so a cancelled one is a real no-report case, not a tooling gap. "About
# TortureTest" reports unconditionally once its dialog returns.
DIALOG_BUTTONS = {"Open", "Save As", "About TortureTest"}

# The menu bar's own top-level items (app.py: _build_menus()).
MENU_BAR_NAMES = ("File", "Edit", "View", "Tools", "Help")

# Clicking these would corrupt the rest of the run rather than exercise it:
# New Window/Exit change which process is even being driven, the three
# "Show ..." toggles can hide the status bar or dock every other
# verification depends on, Dark Theme/Zoom/Reset Demo Controls mutate shared
# visual state with no defined before/after, and Undo/Redo/Cut/Copy/Paste
# act on whatever selection happens to exist with no guarantee one does. The
# menu/submenu containing each is still opened and walked -- only the leaf
# click itself is skipped.
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
MENU_ROLES = ("menu", "menu item", "check menu item", "radio menu item")


@dataclass(frozen=True)
class Platform:
    """What genuinely varies between the platforms this core serves.

    ``windows_by_pid``: every backend in this family except COSMIC's
    populates a real ``Window.pid``, so window matching is pid-based there.
    COSMIC's toplevel-info protocol carries no pid at any version (a
    permanent protocol limitation, not a missing feature), so its driver
    matches windows by title instead -- the best available signal on that
    box.

    ``backends``: names passed straight to ``pyguitest.connect(backend=...)``
    to compose exactly those, or None for pyguitest's own selection. The
    headless-sway driver needs this: a second compositor session nested
    inside a live desktop can out-rank the compositor actually hosting the
    fixture during auto-selection (measured live on this maintainer's
    Fedora box: with SWAYSOCK and XDG_CURRENT_DESKTOP=sway both set, the
    session's `windows()` still answered with the outer GNOME desktop's
    windows), and the sequence form also fails loudly when a named backend
    cannot build instead of quietly substituting another.
    """

    name: str
    windows_by_pid: bool = True
    backends: tuple[str, ...] | None = None


class Failure(Exception):
    """A control did not report the interaction the driver drove it with.

    Collected rather than raised out of the run: the driver records every
    miss and keeps going, so one early failure cannot leave the rest of the
    app unexercised.
    """


def install_fault_handlers():
    """Crash and on-demand hang diagnostics.

    Not ``dump_traceback_later(..., repeat=True)``: that walks every
    thread's frames from a watchdog thread, without the GIL, on a timer --
    and in a process that starts a thread per bounded AT-SPI call
    (pyguitest's atspi backend, dozens a second) one of those periodic walks
    eventually coincides with a pthread_create and segfaults the run.
    Measured on Omarchy, Python 3.14.7: the sixth dump of a 150 s run,
    crashing thread = the watchdog, inside libpython. A run that looks hung
    gets ``kill -USR1 <pid>`` instead, which dumps once, on request.
    """
    faulthandler.enable()
    faulthandler.register(signal.SIGUSR1, all_threads=True)


def app_environment():
    """The environment the fixture app is launched with.

    The app must run as a native Wayland client, not through XWayland, so
    any DISPLAY the outer shell carries is dropped. Some shells export
    NO_AT_BRIDGE=1, which silently keeps any GTK3/Qt app launched with it
    from registering with the accessibility bus at all -- it would publish
    no elements whatsoever, not fail loudly -- so that is dropped too.
    """
    environment = {**os.environ, "QT_QPA_PLATFORM": "wayland",
                   "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1"}
    environment.pop("DISPLAY", None)
    environment.pop("NO_AT_BRIDGE", None)
    return environment


def start_app():
    """Launch the fixture app under its own interpreter."""
    return subprocess.Popen([APP_PYTHON, "-m", "torture_test"], cwd=APP_DIR,
                            env=app_environment(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def expected_controls():
    """The (name, role) inventory the app's own self-test declares."""
    text = Path(APP_DIR, "tests", "test_app.py").read_text(encoding="utf-8")
    block = text.split("EXPECTED_CONTROLS = (", 1)[1].split("\n)", 1)[0]
    return re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', block)


def _safe_click(el):
    """``el.click()``, swallowing anything but a genuine hang.

    Confirmed live on COSMIC: an AT-SPI bus can occasionally answer a
    ``doActionNamed`` call with a transient D-Bus reply failure, which
    dogtail re-raises as the same exception type it uses for "this role
    publishes no such action at all" -- no way for a caller to tell them
    apart. ``pyguitest.BackendCallTimeout`` (a genuine, bounded hang) is let
    through so the per-control handling above this still sees it; everything
    else degrades to "the click did nothing", which the normal
    status-bar/open-path failure paths already handle correctly.
    """
    try:
        el.click()
        return True
    except pyguitest.BackendCallTimeout:
        raise
    except Exception:
        return False


def _is_read_only(el):
    """Whether `el` (an "entry"/"text" element) rejects typed input.

    "Read Only Field" (app.py: `setReadOnly(True)`) exists on purpose, same
    spirit as "Disabled Action" -- the app wires QLineEdit's report only to
    `textChanged` (reporting.py), which a read-only field can never emit,
    since nothing typed into it is ever accepted. AT-SPI's READ_ONLY state
    is the honest signal here, the same way `enabled=False` already is for
    disabled controls.
    """
    try:
        states = el.node.state_set or []
        names = {getattr(s, "name", None)
                 or getattr(s, "value_name", "").removeprefix("ATSPI_STATE_")
                 for s in states}
        return "READ_ONLY" in names
    except Exception:
        return False


def _is_showing(el):
    """Whether `el` is actually on screen right now, by AT-SPI's own
    SHOWING state -- not by its extents.

    Menu walking first tried "nonzero extents" as a stand-in for "this menu
    item's parent menu is currently open". Confirmed live on GhostBSD/X11
    that this does not hold for menus: a closed QMenu's items kept
    reporting their last-real, nonzero on-screen rectangle via dogtail even
    while hidden, so opening just the File menu "discovered" all ~46 leaves
    across every menu in the app at once -- including "Language", which
    then got clicked as if it were a plain leaf and genuinely switched the
    running app to Japanese. SHOWING is AT-SPI's actual answer to "is this
    rendered right now", independent of what geometry a hidden widget
    happens to still be carrying around.
    """
    try:
        states = el.node.state_set or []
        names = {getattr(s, "name", None)
                 or getattr(s, "value_name", "").removeprefix("ATSPI_STATE_")
                 for s in states}
        return "SHOWING" in names
    except Exception:
        return False


def _focus_via_api(el):
    """Give ``el`` real keyboard focus through pyguitest, or return False.

    ``Element.focus()`` is the library's own primitive for this. Checked
    against the published "Set Focus" action on Hyprland and found to do the
    same thing, so there is no reason to reach past it. The focus is
    verified rather than assumed: on the desktops this driver family was
    built for, ``focus()`` was measured not to move *real* keyboard focus,
    which is why the Tab walk exists and is still tried first.
    """
    try:
        el.focus()
    except Exception:
        return False
    time.sleep(0.2)
    try:
        return bool(el.focused)
    except Exception:
        return False


def _status_text(status_bar_el):
    """The status bar's current message, via AT-SPI.

    Takes the status bar Element directly rather than re-searching for it
    on every poll: a ``find_elements`` walk on each poll made this the
    dominant cost of a whole run. :class:`DriverRun` holds one resolved node
    and only re-resolves it when a read comes back empty.
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


def _element_name(el, role):
    """The stable control name: Qt publishes a combo box's current text as
    its Name, so the stable id for one is in the description.
    """
    return (el.description or el.name) if role == "combo box" else el.name


class DriverRun:
    """One full drive of the fixture: controls, tab pages, then menus."""

    def __init__(self, gui, platform, app_pid, expected, app_frame, has_focus,
                 window=None):
        """Bind the live session and the run's bookkeeping."""
        self.gui = gui
        self.platform = platform
        self.app_pid = app_pid
        self.expected = expected
        self.app_frame = app_frame
        self.window = window
        # The startup answer seeds the cache; `ensure_focus` re-reads it.
        self._focus_ok = has_focus
        self._focus_checked = time.monotonic() if has_focus else 0.0
        self._focus_failures = 0
        self._focus_hopeless = False
        self._refocused = 0
        self.failures = []
        self._seen = set()
        self._driven_roles = set()
        # Re-resolved on an empty read rather than cached for the whole run.
        # `_status_text` returns "" both when the app genuinely said nothing
        # and when the node it is reading has gone stale -- the two are
        # indistinguishable from the outside, and a node that dies mid-run
        # makes every control after it fail identically. Seen exactly that
        # shape live: nine consecutive push buttons on one tab, every one
        # reporting '', where the same controls passed in the previous run.
        # Re-resolving cannot mask a real miss: if the application really
        # did not report, the fresh node reads the same text and the failure
        # still stands.
        self._status_el = self._resolve_status_bar()

    # -- windows -----------------------------------------------------------

    def _window_is_apps(self, w):
        if self.platform.windows_by_pid:
            return getattr(w, "pid", None) == self.app_pid
        return True

    def _window_titles(self):
        """Titles of the app's current windows (every window's, on a
        platform whose backend carries no pid to scope by).
        """
        return {w.title for w in self.gui.windows() if self._window_is_apps(w)}

    def wait_new_app_window(self, before_titles, timeout):
        """Poll for a window that is new since ``before_titles`` and is not
        the main "TortureTest" window itself.

        Scoped by pid where the platform's backend populates one -- see
        the pid+title-diff multi-window-desktop bug in drivers/linux.py's
        git history -- and by title-diff alone where it cannot be.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                for w in self.gui.windows():
                    if not self._window_is_apps(w):
                        continue
                    title = getattr(w, "title", None)
                    if title == "TortureTest" or title in before_titles:
                        continue
                    return w
            except Exception:
                pass
            time.sleep(0.2)
        return None

    # -- status bar --------------------------------------------------------

    def _resolve_status_bar(self):
        try:
            for el in self.gui.find_elements(role="status bar",
                                             within=self.app_frame):
                if getattr(el, "pid", None) == self.app_pid:
                    return el
        except Exception:
            pass
        return None

    def status_text(self):
        """The current status-bar message, re-resolving a stale node."""
        text = _status_text(self._status_el)
        if not text:
            self._status_el = self._resolve_status_bar()
            text = _status_text(self._status_el)
        return text

    def status_shows(self, name):
        """Whether the status bar currently names ``name``."""
        return name in self.status_text()

    def _await_report(self, name):
        return self.gui.wait_until(lambda: self.status_shows(name),
                                   timeout=0.8, interval=0.1)

    # -- keyboard ----------------------------------------------------------

    def tap(self, name):
        """One key tap through pyguitest."""
        self.gui.tap_key(name)

    def ensure_focus(self):
        """Whether the fixture window holds keyboard focus *now*, re-taking it.

        This used to be a flag read once in `run()` and trusted for the whole
        run. It is a snapshot of a thing that does not hold still: a run is
        minutes long, and an idle lock, a screensaver, a notification or
        another application's dialog takes focus part-way through. From that
        moment the driver keeps believing it has focus while every Tab and
        every keystroke it sends lands in whatever took it -- which is
        exactly how the macOS run walked into the Dock and clicked Notes, and
        how the Mint and Omarchy runs looked like driver bugs and turned out
        to be session locks. A stale True is the dangerous direction: it
        produces confident, wrong failures spread across every keyboard
        control instead of one honest report.

        So the answer is re-read, and re-asserted through `focus_window` --
        pyguitest's own activate-retry-and-confirm primitive, which also
        waits out a window still animating -- rather than remembered. The
        stale *False* is fixed too: focus arriving late (a compositor with
        focus-stealing prevention, a greeter that has just gone away) used to
        leave the run declining every keyboard control for its whole length.

        Cached for `FOCUS_RECHECK_SECONDS`, because reading focus costs a bus
        round trip and the ring walk asks often. Gives up after
        `FOCUS_GIVE_UP_AFTER` consecutive failed re-assertions so a session
        that will not grant focus at all is paid for once, not per control.
        """
        if self.window is None or self._focus_hopeless:
            return False
        now = time.monotonic()
        if now - self._focus_checked < FOCUS_RECHECK_SECONDS:
            return self._focus_ok
        self._focus_checked = now
        try:
            if self.gui.active_window() == self.window:
                self._focus_ok = True
                self._focus_failures = 0
                return True
        except Exception:
            # Cannot ask -- a backend without WINDOW_STATE. Fall through to
            # the re-assertion, which reports False for the same reason
            # rather than raising.
            pass
        # Focus is elsewhere. Ask for it back, and believe the answer.
        regained = False
        try:
            regained = bool(self.gui.focus_window(self.window))
        except Exception:
            regained = False
        self._focus_ok = regained
        if regained:
            self._refocused += 1
            self._focus_failures = 0
            print(f"    (window had lost focus; re-focused it, "
                  f"{self._refocused} so far)", flush=True)
        else:
            self._focus_failures += 1
            if self._focus_failures >= FOCUS_GIVE_UP_AFTER:
                self._focus_hopeless = True
                print("WARNING: the window will not take keyboard focus "
                      f"(gave up after {self._focus_failures} attempts); "
                      "controls that need typing or Tab will not report. "
                      "On a VM this is usually the session's idle lock.",
                      flush=True)
        return self._focus_ok

    def escape_focus(self):
        """Ctrl+Tab: moves focus on where Tab itself is being consumed."""
        try:
            self.gui.send_keys("^{TAB}")
        except Exception:
            self.tap("Tab")

    def seek_focus(self, el, max_presses=FALLBACK_SEEK_PRESSES):
        """Walk real keyboard focus onto ``el`` by pressing Tab, checking
        AT-SPI's own ``focused`` state after each press.

        ``Element.click()``/``grabFocus()`` do not move real focus on the
        boxes this family serves -- see each driver's module docstring -- so
        a real Tab walk is the only confirmed-working way to get genuine
        keyboard focus onto a specific widget. This is now the short
        *fallback* seek: the ring pass has already walked the whole page
        once, so the budget here only needs to cover a transient focus-read
        failure, not a full traversal.
        """
        try:
            if el.focused:
                return True
        except Exception:
            pass
        if not self.ensure_focus():
            # The window does not hold keyboard focus, so every Tab below
            # would land somewhere else. Decline up front and let the control
            # report honestly instead. Asked live rather than read from a
            # startup flag: focus can have been taken since, and can equally
            # have arrived since.
            return False
        for i in range(max_presses):
            if i and i % RING_ESCAPE_EVERY == 0:
                self.escape_focus()
            else:
                self.tap("Tab")
            time.sleep(0.05)
            try:
                if el.focused:
                    return True
            except Exception:
                continue
        return False

    def _focused_interact(self, role):
        """The keystrokes for a control that already has keyboard focus.

        Shared verbatim between the ring pass and the fallback path so the
        two cannot drift. Each sequence is a live-verified platform finding;
        the reasons live with the role:

        - entry/text: type -- the report is the text change itself.
        - spin button: Up -- one step fires valueChanged.
        - combo box: a focused QComboBox changes its current index directly
          on Down (no popup needs to be opened first) -- confirmed on COSMIC
          to be the simpler, real-focus-only path.
        - slider/dial: Up then Right -- either fires on whichever
          orientation the widget has.
        - list/calendar: Up before Down, because a lone Down is not enough
          for every list. A plain QListWidget opens with
          currentRow() == -1, so Down moves it; a list whose selection
          already sits on its last row has nowhere to go. Up-then-Down moves
          the selection wherever it starts.
        - tree: a freshly-loaded QTreeWidget is collapsed to a single root
          row -- confirmed live (Debian 13) that a lone Down has nothing to
          move the selection to. Right (expand) first gives Down an actual
          second row to land on.
        - table: Down moves the current cell of a focused QTableWidget.
        """
        if role in ("entry", "text"):
            self.gui.type_text("torture")
        elif role == "spin button":
            self.tap("Up")
        elif role == "combo box":
            self.tap("Down")
            self.gui.wait_for_idle(self.app_pid, timeout=1.5)
        elif role in ("slider", "dial"):
            self.tap("Up")
            self.tap("Right")
        elif role in ("list", "calendar"):
            self.tap("Up")
            self.tap("Down")
        elif role == "tree":
            self.tap("Right")
            self.tap("Down")
        elif role == "table":
            self.tap("Down")

    def _unfocused_interact(self, el, role):
        """The no-focus fallbacks for keyboard roles the Tab walk never
        reached, preserved exactly from the drivers this was extracted from.

        - list: a QUndoView ("Undo History") never takes focus in a full
          walk and its container publishes only "Set Focus" -- but its rows
          each publish a "Toggle" action, which ``Element.click()`` already
          treats as a click, and choosing a row that is not the current one
          moves the undo stack's index and fires the real signal.
        - table: a QTableView ("Model Table") is never reachable via Tab at
          all, but its cells each publish their own clickable action,
          confirmed live to fire the real selection-changed signal with no
          focus needed. (A QTableWidget focuses normally and is handled by
          the ring; the walk's failure is the discriminator for which kind
          this is.)
        - entry/text and the value widgets: ``Element.focus()`` does move
          real focus on some of these desktops (confirmed live on
          Hyprland/Omarchy for "Rich Text", which no Tab walk reaches), so
          it is tried and, where the focus verifiably stuck, the normal
          focused keys run.
        """
        if role in ("entry", "text", "spin button", "combo box", "slider",
                    "dial"):
            if _focus_via_api(el):
                self._focused_interact(role)
        elif role in ("list", "calendar"):
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
        elif role == "table":
            child = next((c for c in el.children if c.actions), None)
            if child is not None:
                _safe_click(child)

    def interact(self, el, role):
        """Drive one control: the role-appropriate action or key sequence.

        The fallback path for controls the ring pass did not reach, and the
        whole path for the action-driven roles. The short ``seek_focus``
        here covers a transient ring miss; a control it still cannot focus
        gets the role's no-focus fallback.
        """
        if role in ("push button", "check box", "radio button"):
            _safe_click(el)
        elif role == "scroll bar":
            # Never reachable via Tab at all (confirmed live, Debian 13);
            # publishes "Increase"/"Decrease" AT-SPI actions directly,
            # usable with no keyboard focus -- confirmed live to fire the
            # real valueChanged signal.
            with contextlib.suppress(Exception):
                el.do_action("Increase")
        elif role in ("page tab list", "layered pane"):
            self._interact_pane(el)
        elif role in KEYBOARD_ROLES:
            if self.seek_focus(el):
                self._focused_interact(role)
            else:
                self._unfocused_interact(el, role)

    def _interact_pane(self, el):
        """A tab list or QToolBox: click it, or its last section header.

        A QToolBox container publishes no actions of its own, and the
        application reports ``currentChanged`` for one -- so a click on the
        container cannot report even in principle, because it switches no
        page. Its section headers are real push buttons, and pressing one is
        also what a *user* does to switch pages, so this is the semantic
        action rather than a way around a missing one. The last header is
        chosen because the first is already the open page, and switching to
        the page already shown fires nothing.
        """
        if el.actions:
            _safe_click(el)
            return
        headers = [c for c in el.children
                   if c.role == "push button" and c.name]
        if headers:
            _safe_click(headers[-1])
        else:
            _safe_click(el)

    # -- enumeration -------------------------------------------------------

    def enumerate_page(self, collect_tabs=False):
        """One pass over the tree: the expected controls now actable, the
        expected controls clipped out of view, and (optionally) the main tab
        row with its current selection.
        """
        try:
            elements = self.gui.find_elements(role=ALL_ROLES,
                                              within=self.app_frame)
        except Exception:
            elements = []

        clip_bottom = None
        for el in elements:
            if getattr(el, "pid", None) == self.app_pid and el.role == "status bar":
                with contextlib.suppress(Exception):
                    _, sy, _, _ = self.gui.extents(el)
                    clip_bottom = sy
                break

        actable = []
        clipped = []
        tab_candidates = []
        current = None
        for el in elements:
            try:
                if getattr(el, "pid", None) != self.app_pid:
                    continue
                role = el.role
            except Exception:
                continue
            if role == "status bar":
                continue
            if role == "page tab":
                if collect_tabs:
                    self._collect_tab(el, tab_candidates)
                    with contextlib.suppress(Exception):
                        if el.selected:
                            current = el.name
                continue
            self._classify_control(el, role, clip_bottom, actable, clipped)
        return actable, clipped, self._main_tab_row(tab_candidates), current

    def _classify_control(self, el, role, clip_bottom, actable, clipped):
        """Sort one element into ``actable`` or ``clipped``, or drop it."""
        try:
            if not el.enabled:
                return
            name = _element_name(el, role)
        except Exception:
            return
        if not name or (name, role) not in self.expected:
            return
        if role in ("entry", "text") and _is_read_only(el):
            return
        try:
            _, y, w, h = self.gui.extents(el)
        except pyguitest.CapabilityUnsupported:
            # The element has a rectangle; its *window* has no position, so
            # there are no screen coordinates on this compositor for
            # anything. Keep it -- every interaction goes through the
            # accessible action or Tab-walked focus, never a coordinate --
            # and accept that clipping cannot be assessed here.
            actable.append((name, role, el))
            return
        except Exception:
            return
        if clip_bottom is not None and y + h > clip_bottom:
            clipped.append((name, role))
            return
        if w > 0 and h > 0:
            actable.append((name, role, el))

    def _collect_tab(self, el, tab_candidates):
        try:
            name = el.name
        except Exception:
            return
        if not name:
            return
        try:
            _, y, w, h = self.gui.extents(el)
        except pyguitest.CapabilityUnsupported:
            # No screen coordinates anywhere on this compositor. `None`
            # marks "unmeasured", and the top-row test below switches to
            # grouping by the containing tab list.
            y = None
        except Exception:
            return
        else:
            if w <= 0 or h <= 0:
                return
        tab_candidates.append((name, el, y))

    def _main_tab_row(self, candidates):
        """The main tab bar's tabs, out of every page tab on screen.

        Measured boxes pick the top row; an unmeasured box (no screen
        coordinates) groups by the containing tab list and takes the biggest
        group -- the fixture's main bar carries every page, a nested bar
        inside one page carries a handful.
        """
        if not candidates:
            return []
        if any(y is None for (_n, _e, y) in candidates):
            groups = {}
            for (n, e, _y) in candidates:
                try:
                    parent = e.parent
                    key = (parent.role, parent.name, len(parent.children))
                except Exception:
                    key = ("?", "?", 0)
                groups.setdefault(key, []).append((n, e))
            return max(groups.values(), key=len)
        top_y = min(y for (_n, _e, y) in candidates)
        return [(n, e) for (n, e, y) in candidates if y <= top_y + 5]

    def _find_fresh(self, name, role):
        """Re-find ``name``/``role``'s current element -- a reflow (eg
        Toolbar Zoom) can make the enumeration-time element stale.
        """
        try:
            for el in self.gui.find_elements(role=role, enabled=True,
                                             within=self.app_frame):
                if getattr(el, "pid", None) != self.app_pid:
                    continue
                if _element_name(el, role) == name:
                    return el
        except Exception:
            pass
        return None

    # -- driving -----------------------------------------------------------

    def drive_one(self, name, role, el):
        """Drive one control and verify its status-bar report, retrying
        once against a freshly-found element.
        """
        if role == "push button" and name in POPUP_ONLY_BUTTONS:
            _safe_click(el)
            self.gui.wait_for_element(role="menu", within=self.app_frame,
                                      timeout=1.0)
            self.tap("Escape")
            self.gui.wait_until_gone(role="menu", within=self.app_frame,
                                     timeout=1.0)
            return True
        if role == "push button" and name in DIALOG_BUTTONS:
            return self._drive_dialog_button(name, role, el)
        self.interact(el, role)
        if self._await_report(name):
            return True
        # One retry, re-finding the element fresh first -- a reflow since
        # enumeration can stale the element driven the first time.
        fresh = self._find_fresh(name, role)
        if fresh is not None:
            el = fresh
        self.interact(el, role)
        if self._await_report(name):
            return True
        self.failures.append(f"{name} ({role}) -> {self.status_text()!r}")
        return False

    def _dismiss_dialog(self, dialog, opener_label):
        """Focus and Escape a modal dialog, recording the failure if it
        stays open -- these dialogs are application-modal, so one that
        stays open makes every later interaction fail for a reason that has
        nothing to do with what is being driven.
        """
        self.gui.focus_window(dialog)
        if not self.gui.wait_window_focus(dialog, timeout=2.0):
            # Escape goes wherever focus actually is, so without this the
            # dialog stays open and blocks everything driven after it.
            self.gui.focus_window(dialog)
            self.gui.wait_window_focus(dialog, timeout=2.0)
        self.tap("Escape")
        if not self.gui.wait_window_close(dialog, timeout=2.0):
            # One more Escape: a single press can genuinely miss while a
            # dialog is still settling.
            self.tap("Escape")
            if not self.gui.wait_window_close(dialog, timeout=2.0):
                self.failures.append(
                    f"{opener_label} -> its dialog never closed; every "
                    "later interaction ran against a modal window"
                )
                return False
        return True

    def _drive_dialog_button(self, name, role, el):
        before = self._window_titles()
        _safe_click(el)
        dialog = self.wait_new_app_window(before, timeout=15.0)
        if dialog is None:
            self.failures.append(f"{name} ({role}) -> dialog never appeared")
            return False
        if not self._dismiss_dialog(dialog, f"{name} ({role})"):
            return False
        if name not in ("Open", "Save As") and not self._await_report(name):
            self.failures.append(f"{name} ({role}) -> {self.status_text()!r}")
            return False
        return True

    def _take_minimal(self, items):
        """Honor --minimal and the already-driven set: what remains to do.

        The role is marked driven only on success, so a representative that
        fails lets the next of its kind be tried rather than leaving the
        role unproven.
        """
        out = []
        for (name, role, el) in items:
            if (name, role) in self._seen:
                continue
            if MINIMAL and role in self._driven_roles:
                continue
            out.append((name, role, el))
        return out

    def _finish_one(self, name, role, ok):
        self._seen.add((name, role))
        if ok:
            self._driven_roles.add(role)
        return ok

    def _ring_drive(self, pending):
        """One Tab walk around the current page, driving each pending
        keyboard control as focus lands on it; returns what it never
        reached.

        This replaces the old per-control 60-press seek, whose per-target
        re-walks were O(n^2) presses per page and the measured cause of the
        900 s timeouts on the boxes with a slow key path. Focus is checked
        against every pending target after each press (early-exit, in
        enumeration order, which tracks Qt's tab order); a hit is driven
        and verified right there, so the walk visits the ring once however
        many targets it carries. A control whose report never shows goes
        back to the caller for the fallback path rather than being failed
        here -- `drive_one` owns the retry and the failure record.
        """
        if not pending or not self.ensure_focus():
            return pending
        leftover = []
        presses = 0
        fruitless = 0
        # The backstop scales with the page: each control may sit up to the
        # fruitless limit apart in the tab order, so a flat cap would cut a
        # long page short. The fruitless counter (reset on every hit) is the
        # normal terminator; this only guards against a focus read that flaps.
        press_budget = max(RING_PRESS_BUDGET,
                           RING_FRUITLESS_LIMIT + 12 * len(pending))
        while pending and presses < press_budget \
                and fruitless < RING_FRUITLESS_LIMIT:
            hit = None
            for item in pending:
                try:
                    if item[2].focused:
                        hit = item
                        break
                except Exception:
                    continue
            if hit is not None:
                fruitless = 0
                pending.remove(hit)
                name, role, el = hit
                t0 = time.monotonic()
                print(f"  driving {name!r} ({role}) [ring]...", flush=True)
                try:
                    self._focused_interact(role)
                    ok = self._await_report(name)
                except pyguitest.BackendCallTimeout as exc:
                    self.failures.append(f"{name} ({role}) -> {exc}")
                    self._finish_one(name, role, False)
                    print(f"    ...done in {time.monotonic() - t0:.2f}s",
                          flush=True)
                    continue
                if ok:
                    self._finish_one(name, role, True)
                    if MINIMAL:
                        pending = [p for p in pending
                                   if p[1] not in self._driven_roles]
                else:
                    # Not failed here: the caller's fallback pass re-finds
                    # the element fresh and owns the failure record.
                    leftover.append(hit)
                print(f"    ...done in {time.monotonic() - t0:.2f}s",
                      flush=True)
                if role in ("entry", "text"):
                    # The control just typed into may be a Tab-consuming
                    # text area; Ctrl+Tab moves on from one and is harmless
                    # on a plain entry.
                    self.escape_focus()
                continue
            if fruitless and fruitless % RING_ESCAPE_EVERY == 0:
                self.escape_focus()
            else:
                self.tap("Tab")
            presses += 1
            fruitless += 1
            if fruitless and fruitless % 20 == 0:
                print(f"    ring walk: {fruitless} presses since the last "
                      "pending control took focus", flush=True)
                # A long fruitless stretch is what losing focus mid-walk
                # looks like from here, so this is the cheap place to ask.
                # If focus has gone and will not come back, every remaining
                # press lands in whatever took it -- stop walking and let the
                # fallback path report honestly instead of typing into it.
                if not self.ensure_focus():
                    break
            time.sleep(0.05)
        return leftover + pending

    def drive_items(self, current_items):
        """Drive a page's controls: action-driven ones first in enumeration
        order (combo-box-last protection included), then one ring walk for
        the keyboard-driven ones, then the fallback path for whatever the
        ring never reached.
        """
        todo = self._take_minimal(current_items)
        keyboard = [it for it in todo if it[1] in KEYBOARD_ROLES]
        for (name, role, el) in todo:
            if role in KEYBOARD_ROLES:
                continue
            self._seen.add((name, role))
            t0 = time.monotonic()
            print(f"  driving {name!r} ({role})...", flush=True)
            try:
                self._finish_one(name, role, self.drive_one(name, role, el))
            except pyguitest.BackendCallTimeout as exc:
                self.failures.append(f"{name} ({role}) -> {exc}")
            print(f"    ...done in {time.monotonic() - t0:.2f}s", flush=True)
        try:
            leftovers = self._ring_drive(keyboard)
        except pyguitest.BackendCallTimeout as exc:
            self.failures.append(f"ring walk -> {exc}")
            leftovers = [it for it in keyboard
                         if (it[0], it[1]) not in self._seen]
        for (name, role, el) in self._take_minimal(leftovers):
            self._seen.add((name, role))
            t0 = time.monotonic()
            print(f"  driving {name!r} ({role}) [fallback]...", flush=True)
            try:
                self._finish_one(name, role, self.drive_one(name, role, el))
            except pyguitest.BackendCallTimeout as exc:
                self.failures.append(f"{name} ({role}) -> {exc}")
            print(f"    ...done in {time.monotonic() - t0:.2f}s", flush=True)

    def drive(self, items):
        """Drive the first page's controls, then walk every main tab page
        and drive what each one shows.
        """
        self.drive_items(items)
        try:
            _, _, _, current = self.enumerate_page(collect_tabs=True)
        except pyguitest.BackendCallTimeout as exc:
            current = None
            self.failures.append(f"enumerate_page() (initial) -> {exc}")
        clicked_tabs = {current} if current else set()
        for i in range(40):
            t0 = time.monotonic()
            print(f"tab scan {i}: enumerate_page()...", flush=True)
            try:
                _, _, tabs, _ = self.enumerate_page(collect_tabs=True)
            except pyguitest.BackendCallTimeout as exc:
                print(f"  -> BackendCallTimeout after "
                      f"{time.monotonic() - t0:.2f}s: {exc}", flush=True)
                self.failures.append(f"enumerate_page() (tab scan) -> {exc}")
                break
            print(f"  -> {len(tabs)} tabs in {time.monotonic() - t0:.2f}s",
                  flush=True)
            nxt = next((t for t in tabs if t[0] not in clicked_tabs), None)
            if nxt is None:
                break
            tname, tel = nxt
            clicked_tabs.add(tname)
            print(f"  clicking tab {tname!r}...", flush=True)
            _safe_click(tel)
            self.gui.wait_for_idle(self.app_pid, timeout=1.5)
            t1 = time.monotonic()
            try:
                actable, _, _, _ = self.enumerate_page()
            except pyguitest.BackendCallTimeout as exc:
                print(f"  -> BackendCallTimeout after "
                      f"{time.monotonic() - t1:.2f}s: {exc}", flush=True)
                self.failures.append(f"enumerate_page() (tab {tname!r}) -> {exc}")
                continue
            print(f"  -> {len(actable)} actable items on {tname!r}"
                  f" in {time.monotonic() - t1:.2f}s", flush=True)
            self.drive_items(actable)

    # -- menus -------------------------------------------------------------

    def _visible_menu_items(self):
        try:
            elements = self.gui.find_elements(role=MENU_ROLES,
                                              within=self.app_frame)
        except Exception:
            return []
        out = []
        for el in elements:
            try:
                if getattr(el, "pid", None) != self.app_pid:
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

    def _close_menus(self):
        for _ in range(4):
            self.gui.tap_key("Escape")

    def _open_menu_path(self, path):
        items = self._visible_menu_items()
        for hop in path:
            match = next((it for it in items if it[0] == hop), None)
            if match is None:
                return None
            _, _, el = match
            if not _safe_click(el):
                return None
            if not self.gui.wait_for_element(role=MENU_ROLES,
                                             within=self.app_frame,
                                             timeout=1.0):
                return None
            time.sleep(0.5)
            items = self._visible_menu_items()
        return items

    def _discover_menu_leaves(self, path, depth, leaves):
        if depth > 3:
            return
        items = self._open_menu_path(path)
        self._close_menus()
        if items is None:
            return
        for name, role, _el in items:
            if name in MENU_BAR_NAMES:
                continue
            if role == "menu":
                if name in MENU_SKIP_SUBMENUS:
                    continue
                self._discover_menu_leaves([*path, name], depth + 1, leaves)
                continue
            leaves.append((list(path), name))

    def _open_and_click_leaf(self, path, name):
        items = self._open_menu_path(path)
        if items is None:
            return False, None
        match = next((it for it in items if it[0] == name), None)
        if match is None:
            self._close_menus()
            return False, None
        _, _, el = match
        before = self._window_titles()
        if not _safe_click(el):
            self._close_menus()
            return False, None
        return True, before

    def _click_one_leaf(self, path, name):
        if name in MENU_SKIP_ITEMS or name in MENU_SKIP_SUBMENUS:
            return
        clicked, before = self._open_and_click_leaf(path, name)
        if not clicked:
            return
        label = f"{'/'.join([*path, name])} (menu item)"
        if name in MENU_DIALOG_ITEMS:
            dialog = self.wait_new_app_window(before, timeout=15.0)
            if dialog is None:
                self._close_menus()
                clicked, before = self._open_and_click_leaf(path, name)
                if clicked:
                    dialog = self.wait_new_app_window(before, timeout=15.0)
                if dialog is None:
                    self.failures.append(f"{label} -> dialog never appeared")
                    self._close_menus()
                    return
            if not self._dismiss_dialog(dialog, label):
                self._close_menus()
                return
        self._close_menus()
        self.gui.wait_until_gone(role="menu", within=self.app_frame,
                                 timeout=1.0)

    def drive_menus(self):
        """Open every top-level menu and walk its items via AT-SPI action
        clicks on the elements themselves -- no pointer coordinates needed.
        """
        leaves = []
        for bar_name in MENU_BAR_NAMES:
            try:
                self._discover_menu_leaves([bar_name], 0, leaves)
            except pyguitest.BackendCallTimeout as exc:
                self.failures.append(f"{bar_name} (menu discovery) -> {exc}")
                self._close_menus()
        # --minimal: one menu item proves the menu-action path works;
        # driving every leaf across every submenu is the redundant part
        # this skips.
        if MINIMAL:
            leaves = leaves[:1]
        for path, name in leaves:
            try:
                self._click_one_leaf(path, name)
            except pyguitest.BackendCallTimeout as exc:
                self.failures.append(
                    f"{'/'.join([*path, name])} (menu item) -> {exc}")
                self._close_menus()


def _wait_app_window(gui, app_pid, timeout, platform):
    """Poll for the app's own toplevel window: by pid where the backend
    populates one, by title where it cannot (see :class:`Platform`).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in gui.windows():
            if platform.windows_by_pid:
                if getattr(w, "pid", None) == app_pid:
                    return w
            elif getattr(w, "title", None) == "TortureTest":
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


def _close_app(app):
    app.terminate()
    try:
        app.wait(timeout=5)
    except Exception:
        # terminate() is a request, and a Qt app wedged in a modal dialog
        # can ignore it. Escalate rather than swallowing the timeout: a
        # driver that leaves the app running strands a window on the
        # desktop, and a dozen runs strand a dozen.
        with contextlib.suppress(Exception):
            app.kill()
            app.wait(timeout=5)


def run(platform):
    """Launch the fixture, drive everything, and return the exit code."""
    install_fault_handlers()
    app = start_app()
    gui = None
    try:
        gui = pyguitest.connect(
            backend=list(platform.backends) if platform.backends else None,
            event_delay=0.15, key_delay=0.08)
        window = _wait_app_window(gui, app.pid, 15.0, platform)
        has_focus = False
        if window is None and app.poll() is not None:
            raise Failure(
                f"torture-test app exited immediately with {app.returncode}")
        if window is not None:
            # focus_window is pyguitest's own primitive for this: it waits
            # for the window's geometry to settle, asks more than once (a
            # compositor with focus-stealing prevention drops a single
            # request), and checks the result instead of assuming it. The
            # longer wait after it covers a compositor that grants focus
            # later still, which activate_window alone never waited for.
            has_focus = gui.focus_window(window) or gui.wait_window_focus(
                window, timeout=5.0)
            if not has_focus:
                # A real answer, not an exception: the compositor declined
                # to focus the window, so every key sent from here lands
                # somewhere else. Said once, loudly, because the alternative
                # is one "interaction did not report" per keyboard-driven
                # control -- 27 of them on Omarchy, each showing the
                # previous control's status line, for a single cause. Action
                # clicks still work without focus, so the run continues
                # rather than aborting.
                print("WARNING: the window never took keyboard focus; "
                      "controls that need typing or Tab will not report")
        app_frame = _wait_app_frame(gui, app.pid, 5.0)
        expected = set(expected_controls())
        drv = DriverRun(gui, platform, app.pid, expected, app_frame, has_focus,
                        window)
        items, clipped, _, _ = drv.enumerate_page()
        print(f"actable controls found (visible): {len(items)}")
        if clipped:
            # Geometry, not a fault: these are expected controls whose
            # rectangle fell below the status bar, so the window is clipping
            # the fixture -- usually a screen smaller than it needs. Said
            # out loud because the verdict below covers only what was
            # driven.
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
        drv.drive(items)
        drv.drive_menus()
        if drv.failures:
            print(f"STATUS CHECK FAILED: {len(drv.failures)} interaction(s) "
                  "did not report")
            for failure in drv.failures:
                print(f"  - {failure}")
            return 2
        print("all controls verified")
        return 0
    finally:
        if gui is not None:
            with contextlib.suppress(Exception):
                gui.close()
        _close_app(app)
