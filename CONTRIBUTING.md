# Contributing to pyguitest-torture-test

This repository is a **test fixture**, not a product. Everything in it exists
to give [pyguitest](https://github.com/ctrondlp/pyguitest) and
[pyguitest-recorder](https://github.com/ctrondlp/pyguitest-recorder) a
worst-case target to be driven against. That shapes what a useful
contribution looks like here, so it is worth reading this before opening a
pull request.

For what the app contains and how to run it, see [README.md](README.md). For
the conventions the validation drivers are built around — and the platform
gotchas that cost real time — see [AGENTS.md](AGENTS.md). For the
per-platform record of what has actually been driven clean, see
[VALIDATION.md](VALIDATION.md).

## The one rule that matters most

**Nothing in this repository may reach past pyguitest to a lower-level
input or accessibility API.** No XTEST, no XRecord, no raw Xlib, no direct
`uinput`, no Quartz/AppKit, no UIA. Every interaction — `move_mouse`,
`click`, `tap_key`, `type_text`, window lookups, waits — goes through
pyguitest's own API.

The point of this fixture is to prove those APIs work. If pyguitest cannot
do something, that is a pyguitest gap to fix there, not a reason to reach
around it here. A driver that works by bypassing the library under test
proves nothing.

(The single documented exception is pyguitest-recorder's own internal use of
XRecord to *capture* a session. That lives inside the recorder, not in this
app or its drivers.)

## Ways to contribute

- **A new control.** The most directly useful change: a widget family the
  fixture does not yet contain. See [Adding a control](#adding-a-control) —
  it touches more files than it looks like it should.
- **A new platform driver.** A desktop, compositor or OS nobody here has
  driven. The existing drivers in `drivers/` are the template.
- **Fixing an accessibility gap in the app.** A control that cannot be
  found by name, or whose action the status bar does not report, is a real
  bug in this fixture — that is precisely what it exists to expose.
- **Documentation.** Especially a platform finding written down. Most of
  the value in `AGENTS.md` and `VALIDATION.md` is prose nobody could have
  guessed from the code.

## Setting up

```sh
git clone https://github.com/ctrondlp/pyguitest-torture-test
cd pyguitest-torture-test
python -m venv .venv && . .venv/bin/activate
pip install PySide6
python -m torture_test
```

Python 3.10 or newer. PySide6 is the app's only dependency.

To work on a driver you also need pyguitest on the *driving* side — which
is often a different interpreter from the app's, since the app needs PySide6
and the driver needs pyguitest:

```sh
pip install -e ".[drivers]"
```

## Running the self-test

```sh
python -m unittest discover tests
```

Fully headless (Qt's offscreen platform), so no display is needed, and it
needs nothing beyond PySide6. It checks the invariants the whole fixture
rests on: every actable control has a stable, unambiguous accessible name,
the translation table is complete and consistently used, the menus, tabs and
chrome exist, and the status bar reports actions.

It also owns `EXPECTED_CONTROLS`, the `(name, role)` inventory every driver
drives against. Two of its tests exist specifically to tell you what you
forgot after adding a control.

## Lint

```sh
ruff check .
```

The rule selection in `pyproject.toml` is deliberately the same one
pyguitest uses, so moving between the two repositories means meeting one
style rather than two. Every per-file relaxation is justified in a comment
beside it; `drivers/` is held to a looser *prose* standard than the app
package, but every correctness rule stays on.

`ruff format` is **not** enforced here, and running it over `drivers/` is
not an improvement: it reflows hundreds of lines of hand-wrapped commentary
in files whose value is being readable top to bottom.

## Adding a control

A new control is more than a new widget, because six drivers drive against
the inventory. In order:

1. Add the widget to the right page module in `torture_test/pages/`, naming
   it through `named()` from `torture_test/base.py`.
2. Add its class to `ROLE_BY_CLASS` in `torture_test/roles.py`.
3. Add its action signal to `ACTION_SIGNALS` in `torture_test/reporting.py`,
   so the status bar reports it.
4. Add its row to `EXPECTED_CONTROLS` in `tests/test_app.py`.
5. Add its Japanese strings to `torture_test/i18n.py`.

`test_every_named_widget_has_a_known_role` and
`test_expected_controls_is_complete` will each tell you which of those you
missed.

**If the control opens a modal dialog, it must also be added to
`MENU_DIALOG_ITEMS` — once in `drivers/driver_core.py` (which serves the
Wayland drivers and `bsd.py`), and again in `macos.py` and `windows.py`,
which still carry their own copies.** Only the entries listed there get the
wait-for-window / focus / Escape / wait-for-close treatment. Adding a modal
dialog without listing it killed a whole Windows run mid-walk and left the
app stranded on the desktop: the driver clicked the item, never dismissed
it, and an application-modal dialog then blocked every later menu click.
One platform tolerating the stray dialog does not prove the change is
complete.

**Adding a control invalidates every platform's "all controls verified"
result**, because it changes the inventory all six drivers drive against.
That is expected; note it in the pull request rather than quietly leaving
`VALIDATION.md` claiming more than it covers.

## Working on a driver

The drivers are standalone scripts copied to a test box and run there — not
library code, and not installed with the app. The pointer-free Wayland
family (`linux.py`, `debian.py`, `cosmic.py`) shares its whole strategy
through `drivers/driver_core.py` — those drivers are now a platform config
plus the box's live-verified findings, and `driver_core.py` must be
deployed next to them (the scripts under `scripts/` do). `bsd.py` keeps its
own pointer-driven X11 strategy and imports only the shared fixture
constants; `macos.py` and `windows.py` still carry full private copies,
each a long linear drive sequence readable end to end on the platform it
documents.

- **Never hard-code a path.** Each driver derives the repository root from
  its own location; `TORTURE_APP_DIR` and `TORTURE_APP_PYTHON` are the
  overrides.
- **Record a miss and keep going.** One failure must not abort the walk —
  an early miss used to leave the rest of the app unexercised and hid how
  much was actually broken.
- **Verify by reading the status bar**, never by assuming an interaction
  landed.
- **Re-run the whole batch after a fix, not an isolated probe.** A fix
  rescoped for one platform's `table` handling silently regressed three
  `list` controls; only a full re-run surfaced it.

`AGENTS.md` carries the full contract and a long list of platform-specific
traps. Read it before spending time on a driver.

## Pull requests

- One logical change per pull request.
- Say which platforms you actually ran it on, and which you did not. "Not
  re-verified" is a perfectly good thing to write down; a claim of coverage
  that was never run is not.
- Run `python -m unittest discover tests` and `ruff check .` first.
- Conventional-Commits-style subject lines (`feat:`, `fix:`, `docs:`), one
  line, no body.

## License

By contributing you agree your work is licensed under GPL-2.0-or-later, the
same terms as the rest of the project. See [LICENSE](LICENSE).
