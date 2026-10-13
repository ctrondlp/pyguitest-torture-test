# Agent instructions

Working conventions for the TortureTest fixture and its validation drivers,
learned over prior sessions. This is
about *how* the validation loop is built and run; read the app source and the
drivers in `drivers/` for the code itself.

## What this repo is

TortureTest is a Qt/PySide6 desktop app stuffed with (nearly) every widget
family, built as the worst-case test target for pyguitest and
pyguitest-recorder. It is a *fixture*, not a product:

- **The entire point of this app is to exercise pyguitest, and eventually
  pyguitest-recorder.** It exists to prove those two libraries' own APIs
  work — never to route around them. Concretely: **no use of XTEST or
  XRECORD (or any other raw X11/Xlib/uinput/UIA/AX API) anywhere in this
  application or in the driver scripts that exercise it.** Every interaction
  (`move_mouse`, `click`, `tap_key`, `type_text`, window lookups, waits) goes
  through pyguitest's own input/tree API, full stop — if pyguitest can't do
  it, that is a pyguitest gap to fix, not a reason to reach for a lower-level
  API in the driver. The one explicit exception is pyguitest-recorder's own
  capture mechanism: when a session is *recorded*, pyguitest-recorder uses
  XRecord internally to capture input — that is the recorder's own job and
  lives inside pyguitest-recorder, not in this app or its drivers, so it does
  not violate this rule.
- **Driven by pyguitest, recorded by pyguitest-recorder.** It is deliberately
  *not* packaged with either; the relationship runs the other way. The
  drivers in `drivers/` connect, drive it through
  pyguitest's own input API, and record the session with pyguitest-recorder.
- Every control carries a stable, unique accessible name, and the status bar
  reports every action a control takes (`Clicked: Primary Action`,
  `Toggled: ...`, `Changed: ...`) — so a driver asserts that an interaction
  *landed* by reading the status bar, never by guessing.
- `tests/test_app.py` is the app's own self-test (headless, Qt offscreen) and
  owns `EXPECTED_CONTROLS`, the `(name, role)` inventory the drivers drive
  against. Run it with `python -m unittest discover tests`.

## The validation drivers

The per-platform drivers live in `drivers/` and are deployed to each box by
`scp`:

| Driver | Target platform |
|---|---|
| `drivers/bsd.py` | FreeBSD / GhostBSD, X11 |
| `drivers/cosmic.py` | COSMIC (Pop!_OS), Wayland |
| `drivers/debian.py` | Debian, Wayland |
| `drivers/linux.py` | a local Wayland/GNOME desktop, *not* a dedicated test box |
| `drivers/windows.py` | Windows 11 |
| `drivers/macos.py` | macOS |

Host addresses and credentials are **not** recorded here — ask for them, or
read them from wherever the session already keeps them.

Each driver derives the repo root from its own location, so a checkout needs
no configuration. Override with `TORTURE_APP_DIR` for a checkout elsewhere,
and `TORTURE_APP_PYTHON` where the app's interpreter is not the driver's —
the app needs PySide6, the driver needs pyguitest, and on several boxes those
live in different virtualenvs. **Never hard-code a path**: this repo is meant
to be pushed.

Two earlier drivers were superseded and have been moved out of the repo (to
`../pyguitest-torture-test-archive/`): the private-Xvfb BSD template, replaced
by `drivers/bsd.py` driving the real X11 desktop, and the pointer-driven
Debian attempt, replaced by `drivers/debian.py` once pointer injection was
found to be dropped there. Don't restore them to start from.

They share one contract:

1. Enumerate only *enabled*, *expected* (in `EXPECTED_CONTROLS`) controls
   whose click point is **inside the app's own window** — not merely
   on-screen. A control scrolled below the fold still reports a plausible
   rectangle, and clicking its centre does not miss harmlessly: it clicks
   whatever else owns that point (on macOS that was the Dock — see the
   gotchas).
2. Drive each one through **pyguitest's input API** — `move_mouse`, `click`,
   `tap_key`, `type_text`, or `Element.click()`/`do_action()` — **never raw
   XTEST/XRECORD/Xlib (or other lower-level platform) calls**. Connect with
   `event_delay=0.15` and `key_delay=0.08` for settle time.
3. Poll the status bar for the control's name after driving it. **Record the
   miss and keep going** — one retry, then move on. (An earlier contract said
   "fail immediately on the first miss"; that was removed deliberately, because
   one early miss then left the rest of the app unexercised and hid how much
   was actually broken.)
4. Walk every tab page and the whole menu bar, not just the first visible page.
5. All five dedicated test platforms (GhostBSD, COSMIC, Debian, Windows,
   macOS) reach `all controls verified` with zero failures — see
   `VALIDATION.md` for the per-platform record. `drivers/linux.py`
   targets a *live local desktop* rather than a dedicated box, is not part
   of that matrix, and its last fix has not been re-run there; **ask before
   launching anything on a local desktop.** The remaining step is the
   recorder round-trip: record a session with pyguitest-recorder and check
   the generated source matches the recording.

## Platform / backend matrix

Each platform exercises its *native* backend — do not force Xvfb/X11
everywhere. "Input strategy" matters as much as the backend: three of these
boxes cannot deliver synthetic *pointer* input at all, and their drivers are
built around that rather than fighting it.

| Host | Backend | Input strategy |
|------|---------|----------------|
| GhostBSD (FreeBSD) | `x11` input + `atspi` tree | pointer + keyboard, both work |
| Pop!_OS / COSMIC | `atspi` tree, `wtype` keyboard | **pointer-free**: AT-SPI action clicks + a Tab-seek walk for real keyboard focus |
| Debian 13 (Wayland) | `atspi` tree, `uinput` keyboard | **pointer-free**, same strategy as COSMIC |
| Local Wayland/GNOME desktop | `atspi` tree, `uinput` keyboard | **pointer-free**, same strategy as COSMIC |
| Windows 11 | `uia` + `win32` | pointer + keyboard, both work |
| macOS | `macos` tree + `macquartz` input | pointer + keyboard, both work |
| Omarchy / Hyprland (Arch) | `hyprland` windows, `atspi` tree, `wtype` keyboard, `grim` capture | **pointer-free**, but for a different and *fixable* reason — see below |

On COSMIC, Debian and the local GNOME/Wayland desktop, `uinput` pointer
events are accepted by the kernel
and then silently dropped before the compositor — keyboard injection through
the same backend works fine. That split is why those three drivers never
move the pointer at all: they click through `Element.click()` (the
accessible action) and reach keyboard-only controls by Tab-seeking until
`Element.focused` is true on the one they want.

## Omarchy / Hyprland, the newest target

The first wlroots compositor this project has reached — Hyprland and niri
were previously on record as never having met a live one. Several things
about it are worth knowing before touching it.

**pyguitest needed no changes for it.** `connect()` composes
`hyprland+atspi+input:wtype+capture:grim+clipboard:wl-copy+imagesearch:compare`
on its own, with every window capability (list, state, activate, minimize,
geometry, placement, resize, **pid**, at-point) served by `hyprland`.
`pyguitest` with no subcommand already prints `compositor wlroots
(Hyprland)` and lists `hyprctl` among its tools, and `hints.py` already knew
Arch's package names. Nothing had to be added.

**`drivers/cosmic.py` runs here unmodified**, which is why there is no
`drivers/hyprland.py`. The COSMIC driver matches windows by title because
COSMIC's protocol carries no pid; Hyprland does carry one, so title matching
is merely less precise there, not wrong. One driver covering both
wlroots-family compositors is the point — do not fork it without a reason
the code can state.

**Its pointer limitation is a permission, not a protocol.** `/dev/uinput`
exists but is `root`-owned and the login account is not in the `input`
group, so `POINTER_MOVE`/`POINTER_BUTTON` are absent and the pointer-free
strategy applies. Unlike COSMIC and Debian, this is fixable: `sudo usermod -aG input
<user>` and a re-login turns on the full pointer-driven strategy. `pyguitest`
diagnoses it unprompted, in those words. Omarchy has no passwordless sudo,
so this is the maintainer's call.

**Two traps that cost real time here:**

- **Resolution is load-bearing, not cosmetic.** The VBox adapter's
  `preferred` mode is 1024x768, and Omarchy sets `scale = "auto"` with
  `GDK_SCALE=2`. At that size most of the fixture falls outside the window
  and the driver can only reach **7** actable controls on the first tab
  against 17 at 1920x1080 — a run that would "pass" having checked a
  fraction. `scale = 1` matters independently: pyguitest skips its rectangle
  checks on a scaled screen, because AT-SPI extents and window geometry stop
  sharing units.
- **`hyprctl keyword` does not work.** Omarchy uses Hyprland's new **Lua**
  config, which is what "keyword can't work with non-legacy parsers" means.
  Set the mode in `~/.config/hypr/monitors.lua`
  (`hl.monitor({ output = "VGA-1", mode = "1920x1080@60", position = "0x0",
  scale = 1 })`) and `hyprctl reload`.

**`Element.focus()` actually works here**, unlike on COSMIC and the local
GNOME desktop where it was measured not to move real keyboard focus. That is
why the `entry`/`text` branch tries `seek_focus` first and only then falls
back to the library primitive — the fallback is for controls Tab cannot
reach, such as a `QTextEdit` that publishes only `Set Focus`.

## Gotchas that cost real time

- **A new modal dialog must be added to `MENU_DIALOG_ITEMS` in every
  driver.** Each driver keeps a set naming the menu entries that open a
  dialog, and only those get the
  wait-for-window / `focus_window` / Escape / wait-for-close treatment.
  Adding `QErrorMessage` to the Tools menu without listing it killed the
  Windows run mid-walk (`STATUS_CONTROL_C_EXIT`, app left stranded on the
  desktop): the driver clicked the item, never dismissed it, and an
  application-modal dialog then blocked every later menu click. macOS
  tolerated the same stray dialog and passed -- so one green platform does
  not prove an inventory change is complete.
- **Adding a control means re-running every platform.** A new control
  changes `EXPECTED_CONTROLS`, which is what all six drivers drive against,
  so the previous "all controls verified" result no longer covers the app
  that exists. Add the control, then add its `ROLE_BY_CLASS` entry, its
  `ACTION_SIGNALS` entry, its `EXPECTED_CONTROLS` row and its Japanese
  strings -- `test_every_named_widget_has_a_known_role` and
  `test_expected_controls_is_complete` will each tell you which of those you
  forgot -- and only then re-run.
- **Read-only fields never report.** A `setReadOnly(True)` QLineEdit (e.g.
  "Read Only Field") reports only via `textChanged`, which typed input can
  never fire. Exclude it the same way disabled controls are excluded — its
  AT-SPI `READ_ONLY` state is the honest signal.
- **"Toolbar Zoom" reflows the whole layout.** It is the persistent toolbar
  combo whose change rescales the app-wide font. Drive combo boxes *last*
  (so the reflow cannot break the control driven right after it), and re-read
  each control's extents live (`live_extents`) rather than trusting an
  enumeration-time snapshot.
- **`ACTABLE_ROLES` must be a tuple, not a set.** A set iterates in
  arbitrary order (per-process hash randomization), making the drive order
  nondeterministic run-to-run — the source of a recurring
  "Option A → 'Changed: Toolbar Zoom = 125%'" miss.
- **"page tab" role exists at more than one level.** The two embedded demo
  tab bars ("Nested Tabs", "Standalone Tab Bar") share the role with the real
  main navigation bar. The main bar is the *topmost* row (smallest y).
- **Qt publishes a combo box's current *text* as its Name**, discarding
  `setAccessibleName`; the stable id is in the accessible description
  (`base.py::named()` documents this).
- **`event_delay` defaults to 0.0** (no settle between pointer-move and
  click). Setting `event_delay=0.15` is what made the macOS driver stable and
  plausibly explains years of low resemblance scores.
- **Modal dialogs under a WM-less compositor** need `gui.wait_for_window()`
  then `gui.focus_window()` before the Escape — a bare Escape has no focused
  window to reach.
- **A control's rectangle can lie outside the app's own window**, and
  clicking its centre then hits *whatever else owns that point*. On macOS
  "Rich Text" extends below the window and its centre landed on the **Dock's
  Notes icon** — so the driver launched Notes, Notes took key focus, and
  every subsequent `type_text` and Escape went into a note while the driver
  reported progress. This cost more time than every other bug in validation
  combined. Two rules came out of it: clip every click point to the app
  window's extents (`_clickable()` in `drivers/macos.py`), and when
  input seems to vanish, call **`gui.element_at(x, y)` on the exact click
  point** — it names what you are really about to hit.
- **"The right app is frontmost" is not the same as "keys go there."** On
  macOS `CGEventPost(kCGHIDEventTap, ...)` delivers to the frontmost
  *application's* key window; `AXRaise` only reorders a window *within* its
  app, so raising is not activating (pyguitest's `activate_window()` now does
  both). Worse, a panel at window layer 25 (Quick Note's
  `LinkedNotesUIService`) swallows keystrokes **without** changing the
  frontmost application — so `NSWorkspace.frontmostApplication()` and
  `active_window()` both keep answering correctly while nothing lands.
- **macOS Hot Corners fire from synthetic pointer moves.** With
  `wvous-br-corner = 14` (Quick Note), a driver that moves the pointer into
  the bottom-right corner opens a Quick Note panel mid-run. Ask before
  changing someone's desktop setting, then
  `defaults write com.apple.dock wvous-br-corner -int 0` and restore
  `-int 14` afterwards.
- **macOS Qt dialogs are native by default**, so `QFileDialog`,
  `QColorDialog` and `QFontDialog` publish nothing into Qt's accessibility
  tree. `app.py` passes `DontUseNativeDialog` on `darwin` only — Qt's own
  dialogs are what the fixture is there to exercise.
- **Diff windows by handle, never by `(title, pid)`.** Three `QMessageBox`
  dialogs all report an empty title, so a title-based diff cannot tell a new
  one from the one still open — and pyguitest's window list is cached for
  0.25s on top of that.
- **An SSH session on Windows is Session 0 and has no desktop**, so pointer,
  capture and `windows()` all fail there by design. Run the driver as a
  **Scheduled Task** with `/ru <user>` and no password (which forces
  "Interactive only" → Session 1). Point `/tr` at a `.bat` wrapper rather
  than an inline command line (an inline one died with
  `STATUS_CONTROL_C_EXIT`), create the task fresh each run rather than
  re-running a completed one, and invoke Python as `py -u` — buffered output
  makes a working run look like a hang.
- **A wedged accessibility call survives SIGTERM.** If a driver stops with no
  output and will only die to SIGKILL, suspect a blocked AT-SPI/GI call, not
  the app; pyguitest now bounds those and raises `BackendCallTimeout`
  instead. `faulthandler.dump_traceback_later(N, repeat=True)` names the
  frame.
- **"Pointer injection is broken" does not mean the box is blocked.** On
  three of the six hosts `uinput` pointer events are dropped before the
  compositor while *keyboard* injection through the same backend works
  perfectly. Two hosts were wrongly written off as unusable before that
  split was noticed — check the two halves separately.
- **Re-run the whole batch after a fix, not an isolated probe.** A fix
  rescoped for Debian's `table` handling silently regressed three `list`
  controls and the Data Grid; only a full re-run surfaced it.

## Layout

    torture_test/     the app package (importable; `python -m torture_test`)
      pages/          one module per tab page
    tests/            the app's own headless self-test
    drivers/          one validation driver per platform
    examples/         a pyguitest-recorder output, kept verbatim

Nothing here is hyphenated-and-unimportable any more: the package is
`torture_test`, so there is no `importlib.util.spec_from_file_location`
bootstrap to maintain and `python -m torture_test` just works. Do not
reintroduce one.

## Git

The agent never commits; the user commits their own work, always.

The app still reaches each test host by being **copied** (`scp`), not pulled
— that convention has not changed, and nothing may be written into a test
box's own checkouts.
