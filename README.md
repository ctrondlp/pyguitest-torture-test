# TortureTest

[![Contributing](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![License](https://img.shields.io/badge/license-GPL--2.0--or--later-blue.svg)](LICENSE)
[![Platforms driven clean](https://img.shields.io/badge/platforms%20driven%20clean-4%20of%206-yellow.svg)](VALIDATION.md)

A desktop application stuffed with (nearly) every Qt control, built to be the
worst case for [pyguitest](https://github.com/ctrondlp/pyguitest) — and for any
other accessibility-driven GUI automation tool.

Every control is given a stable, unique accessible name and published under its
real accessible role, so a test can find and drive it by name
(`gui.button("Primary Action").click()`) rather than by coordinates. The
status bar reports every action a control takes, so a test can assert that a
click or keystroke actually landed instead of guessing.

It is a test target, not a product. It is deliberately **not** packaged with
pyguitest, and it is deliberately boring — plain labels, stable names, no
state-dependent renaming — so a lookup written once keeps resolving across
themes, resizes and platform changes.

## Scale

| | |
|---|---|
| Live `QWidget` instances | **702** |
| Distinct Qt widget classes | **61** |
| Menu-bar and toolbar actions | **95** |
| Tab pages | **9** |
| Uniquely-named controls driven and verified | **105** |
| Platforms driven clean, zero failures | **4 of 6** |

The last two rows are the ones that matter: every one of the 105 named
controls is individually driven *and* confirmed landed by reading the status
bar — plus the whole menu bar. Clean as of 2026-10-14 on FreeBSD/GhostBSD,
Pop!_OS/COSMIC, Debian and Windows. Neither of the other two is a pyguitest
defect. macOS is one control short — `Undo History`, whose rows do not move
the undo stack through the AX API, a gap in this repo's own driver. Omarchy/
Hyprland has no known bug in either project: Hyprland hands keyboard focus to
a layer surface and will not give it to a window, which pyguitest reports
accurately. The run there did find a real pyguitest bug — every window
control had become a silent no-op after Hyprland changed its dispatch syntax
— and that is fixed. See [VALIDATION.md](VALIDATION.md) for the per-platform
record, including the bugs each run found in pyguitest itself.

## Requirements

- Python 3.10+
- [PySide6](https://pypi.org/project/PySide6/)

## Run

From a checkout:

```sh
pip install PySide6
python -m torture_test            # English
python -m torture_test --lang ja  # Japanese
```

Or install it, which also puts a `torture-test` command on the path:

```sh
pip install -e .
torture-test
```

The interface can also be switched at runtime via **View ▸ Language**. In
Japanese the window title uses a neutral name ("コントロールテスト") rather than a
translation of "torture"; every control's accessible name stays English, so a
test written against `gui.button("Primary Action")` keeps resolving in either
language.

The application sets `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` itself, so on
Linux/BSD the Qt accessibility bridge publishes its widget tree to AT-SPI even
when no screen reader is running — which is what lets pyguitest find the
controls. On Windows (UIA) and macOS (NSAccessibility) the tree is published
without that flag.

## What is in it

A menu bar (File / Edit / View / Tools / Help), a toolbar, a dockable tool
palette, a status bar, and nine tabs:

| Tab | Controls |
|---|---|
| Buttons & Toggles | push/tool/command-link buttons, check boxes (incl. tri-state), radio buttons |
| Text & Numbers | line edits (validation, mask, completion, echo modes), text/rich-text views, spin boxes, date/time editors, key-sequence capture |
| Choosers | editable/read-only combo boxes, font picker, and lists themed around colors, planets and moons |
| Trees & Tables | checkable tree, table grid, column view, and their model/view counterparts |
| Displays | plain/rich/image labels, LCD number, progress bars, calendar, graphics view |
| Image Search | pixel-identical look-alike controls plus a unique calibration target |
| Sliders & Ranges | sliders, dials, scroll bars, an animated progress bar |
| Containers | group boxes, frames, nested tabs, tool box, stacked widget, splitter, scroll area |
| Kitchen Sink | a dense, realistic form mixing many control types |

`Tools` opens one of every dialog family Qt ships — message boxes, input
dialogs, color/font/file pickers, a progress dialog, a custom form dialog, a
wizard, an MDI workspace, and a **Slow Dialog** that appears after a
configurable delay (1/3/5/10 seconds, or a custom value) — useful for testing
`wait_for_window` / `wait_for_element` against a dialog that arrives late.
`Help ▸ Dump Controls` shows the control inventory (class, role, accessible
name) the way pyguitest will see it.

### The Image Search tab

This is the screenshot/template-matching test area. It contains:

- a 4×3 grid of pixel-identical buttons whose only difference is their
  accessible name (`Look-alike 01` … `Look-alike 12`),
- a row of near-identical "Save…" buttons,
- a set of identical icon-only buttons, and
- a single, visually unique **CALIBRATE** target.

A picture of any look-alike matches several controls; only the calibration
target is unambiguous. This is for verifying that `locate` / `locate_image`
resolve — or honestly report — ambiguity.

### The status bar

The status bar is the app's feedback channel: **every action a control takes
is reported there** (`Clicked: Primary Action`, `Toggled: Receive
notifications = on`, `Changed: Volume = 42`, `Switched: Nested Tabs = Beta`).
A test can therefore assert that an interaction landed by reading the status
bar text instead of guessing.

## Layout

```
torture_test/     the app package (python -m torture_test)
  pages/          one module per tab page
tests/            the app's own headless self-test
drivers/          one validation driver per platform
examples/         a pyguitest-recorder output, kept verbatim
```

[AGENTS.md](AGENTS.md) carries the driver contract and the platform traps,
[VALIDATION.md](VALIDATION.md) the per-platform record, and
[examples/README.md](examples/README.md) explains why the recorded example
still matches a tab name the app no longer publishes.

## Self-test

`tests/test_app.py` instantiates the whole window headlessly (Qt's offscreen
platform, so no display is needed) and verifies the app's invariants: the
translation table is complete and used consistently, every actable control has
a stable, unambiguous name, the menus/tabs/chrome and themed lists exist, and
the status bar reports actions.

```sh
python -m unittest discover tests
```

## Driving it with pyguitest

```python
import pyguitest
from pyguitest import Capability, Role

gui = pyguitest.connect()
if not gui.supports(Capability.ELEMENT_TREE):
    raise SystemExit("element tree unavailable; see `pyguitest doctor`")

gui.button("Primary Action").click()
gui.text_field("Full Name").set_text("Ada Lovelace")
gui.dropdown("Country").choose("Sweden")
gui.checkbox("Receive notifications").click()
volume = gui.element(role=Role.SLIDER, name="Volume")
print("volume now:", volume.value)
```

`Help ▸ Dump Controls` lists the exact role and name of every control, which is
the reference for writing those lookups. Because the app names every control,
pyguitest's own `assert_no_missing_accessible_names` and
`assert_no_duplicate_accessible_names` checks should pass against it — and any
failure they report is a real gap in the app, which is the point.

## The validation drivers

`drivers/` holds one script per platform — `bsd.py`, `cosmic.py`, `debian.py`,
`linux.py`, `macos.py`, `windows.py`. Each launches the app, walks every tab
and the whole menu bar, drives every enabled control, and asserts each
interaction landed by polling the status bar.

They are not installed with the app and are not part of the distribution:
each is copied to a test box and run there, and they need
[pyguitest](https://github.com/ctrondlp/pyguitest) rather than PySide6.

A driver finds the app by deriving the repo root from its own location, so a
checkout needs no configuration. Two environment variables override that:

| Variable | Default |
|---|---|
| `TORTURE_APP_DIR` | the repo root, from the driver's own path |
| `TORTURE_APP_PYTHON` | `sys.executable` — set it where the app's interpreter is not the driver's |

Everything a driver does goes through pyguitest's own input and tree API.
Nothing in this repo uses XTEST, XRecord, Xlib, uinput, Quartz, AppKit or UIA
directly — the point is to exercise pyguitest, so reaching past it would
defeat the exercise. See [AGENTS.md](AGENTS.md) for the full contract.

## Contributing

A new control touches more files than it looks like it should, and a new
modal dialog has to be registered in every driver or it strands a whole run.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

GPL-2.0-or-later, the same as pyguitest. See [LICENSE](LICENSE).
