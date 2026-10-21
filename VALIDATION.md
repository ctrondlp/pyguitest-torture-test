# Validation status

Tracks the cross-platform validation effort: driving this app through
pyguitest's own API (never raw XTEST/XRECORD — see AGENTS.md) across the
target fleet, one platform at a time, fixing real bugs as they're found. The
[Platform matrix](#platform-matrix) below is the current per-platform
status — now well past the original five targets — and the dated sections
after it are the per-run history behind it. Prior history before 2026-10-11
lived in a private, non-repo file (`~/pyguitest-validation-state.md`); from
2026-10-11 on it lives here.

## Scale of the fixture

Measured from the live widget tree on 2026-10-13 (`QT_QPA_PLATFORM=offscreen`,
walking `TortureTestWindow`'s `QWidget` descendants):

| Measure | Count |
|---|---|
| Live `QWidget` instances | **702** |
| Distinct Qt widget classes | **61** |
| `QAction`s (menu bar + toolbar) | **95** |
| Tab pages | **9** |
| Uniquely-named controls in `EXPECTED_CONTROLS` | **105** |

The two numbers to be careful not to conflate: the app *contains* 702 widgets
across 61 classes, and the drivers *individually drive and status-bar-verify*
the 105 uniquely-named controls plus the whole menu bar, on every platform
below. Quote 702 as the size of the fixture and 105 as the size of the
verified inventory — never 702 as "controls verified".

(Measured at 693/60/93/104 earlier the same day, before `QUndoView` and
`QErrorMessage` were added — see the coverage audit below.)

## 2026-10-13: made ready to push, and three bugs found doing it

The directory became a git repository and was restructured for publication.
Nothing about the validated drive sequences changed; what changed is layout,
packaging and hygiene.

**Structure.** The app is now an importable package, `torture_test/`, with
`tests/`, `drivers/` and `examples/` beside it. The directory used to be
hyphenated and therefore un-importable, which had forced two near-identical
`importlib.util.spec_from_file_location` bootstraps (one in `__main__.py`,
one in the self-test) to register it under a synthetic name. Both are gone;
`python -m torture_test` and `python -m unittest discover tests` work
directly. Added `pyproject.toml` (builds and passes `twine check`),
`.gitignore`, and `LICENSE` (GPL-2.0-or-later, matching pyguitest).

**Hard-coded local paths removed.** Every driver had an `APP_DIR` and
`APP_PYTHON` pinned to one machine's home directory, including a Windows
`C:\Users\<user>\...` and a macOS `/Users/<user>/...`. Each now derives
the repo root from its own location, with `TORTURE_APP_DIR` /
`TORTURE_APP_PYTHON` as overrides. Two superseded drivers (the private-Xvfb
BSD template and the pointer-driven Debian attempt) were moved out of the
repo entirely -- both duplicated a live driver almost line for line, both
leaked local paths, and one still described an XTEST/xrecord approach the
project has since ruled out.

**Re-verified live on two boxes (2026-10-13).** Deployed to a *scratch*
directory on each (never into a checkout), so `APP_DIR` derived from the
driver's own location with no configuration -- which is the new default path
doing its job. Windows 11 and macOS 26.7 both: self-test 21/21, driver
`all controls verified`, `EXIT=0`, and no process or window left behind.
Windows went through the interactive-session Scheduled Task as usual
(`Logon Mode: Interactive only` confirmed). One cmd.exe trap worth recording:
`set QT_QPA_PLATFORM=offscreen && ...` captures the trailing space into the
value, and Qt then cannot find a plugin named `"offscreen "` -- quote it
(`set "VAR=value"`) or let the self-test set it itself, which it does.
GhostBSD, COSMIC and Debian remain un-re-verified; nothing about their drive
sequences changed, but the launch path did.

**Launch path changed with the layout**, which is the one functional change
to the drivers: they used to run `python <APP_DIR>/__main__.py` as a file,
which relative imports no longer allow, so they now run
`python -m torture_test` with `cwd=APP_DIR` (`-m` puts the cwd on
`sys.path`, which is what makes it resolve). The macOS wrapper script now
quotes both interpolated paths, so a checkout directory containing a space
no longer splits into two shell words. **Not yet re-verified on any box** --
every AT-SPI test box was unreachable when this was done.

**XTEST/XRecord audit.** Swept every file for raw platform input and
accessibility APIs. Result: clean. The full import set across the project is
PySide6, pyguitest, pyguitest-recorder and the standard library -- no Xlib,
ctypes, Quartz, AppKit, comtypes, evdev, pyautogui or pynput anywhere. Every
remaining textual mention of XTEST or xrecord is in a comment explaining why
the project does not use them, plus pyguitest-recorder's own generated header
in `examples/`, which is the documented exception.

**Lint.** `ruff` with pyguitest's own rule selection: 298 findings down to
zero. The app package and the self-test pass the full strict set with no
per-file exemptions. The drivers keep every correctness rule (F, B, UP, C4,
RET) and are exempted from four prose/structure rules plus `D205`/`E501`,
each with its reason recorded in `pyproject.toml` -- their docstrings carry
live-verified platform findings that would lose detail if squeezed into a
one-line summary. Verified separately that no *code* line in `drivers/`
exceeds 88 columns, so that exemption covers prose only.

### The three bugs

1. **`named()` could silently un-name a combo box.** Qt publishes a combo
   box's current text as its accessible name and discards
   `setAccessibleName`, so the stable id travels in the accessible
   *description*. `named()` set the description for a combo box and then
   overwrote it with a caller-supplied `description`, leaving the control
   findable by neither name nor description -- and `Session.dropdown()`
   tries exactly those two. Latent: nothing in the app passes a description
   today. It now raises `ValueError` at construction instead, which is the
   whole point -- the alternative surfaces as an unexplained miss in a
   driver run on some other platform.

2. **The inventory completeness test had a blind spot by construction.**
   `_named_widgets()` collected widgets with *both* a name and a known
   `ROLE_BY_CLASS` entry, so `test_expected_controls_is_complete` -- the
   guard against inventory drift -- could not see a named control whose
   class had no role mapping. A new control of an unmapped class would have
   passed every test and then been missed by the drivers, which drive
   `EXPECTED_CONTROLS`. Measured: the only two widgets hidden today are a
   `QDockWidget`'s "Float"/"Close" chrome buttons, which are *meant* to be
   excluded -- but they were excluded by accident, through the same missing
   mapping, rather than deliberately. Chrome exclusion is now an explicit
   `_is_toolkit_chrome()` test, and a new
   `test_every_named_widget_has_a_known_role` fails loudly otherwise.
   Confirmed the new test actually catches it: removing `QDial` from
   `ROLE_BY_CLASS` fails with
   `["QDial 'Frequency Dial'", "QDial 'Tuning Dial'"] != []`.

3. **A driver could strand the app on the desktop.** Cleanup ran
   `app.terminate()` then `app.wait(timeout=5)` inside
   `try/except Exception: pass`, so a timeout was swallowed and the process
   left running -- which is how a run leaves a window behind, and a dozen
   runs leave a dozen. The five `Popen`-based drivers now escalate to
   `app.kill()`. Verified against a process with `SIGTERM` set to
   `SIG_IGN`: 5s timeout, then reaped with returncode -9.

   The macOS driver deliberately does **not** escalate, and the reasoning
   is recorded in the code: its app is not a child of the driver (launched
   via `open -a`, so launchd owns it and its pid was found by window
   title), so it cannot be `wait()`ed on, and `os.kill(pid, 0)` does not
   substitute -- that call still succeeds for a process that has died but
   not been reaped, so a poll-then-SIGKILL loop escalates even when SIGTERM
   worked. Measured exactly that while writing it. Worse, if the pid has
   been reaped and reused by then, the SIGKILL lands on an unrelated
   process.

Two checked and found *not* to be bugs, recorded so they are not
re-investigated: `_new_window()` holds its new `TortureTestWindow` only in a
local, which is the classic PySide6 premature-collection trap -- measured,
the window survives `gc.collect()` on PySide6 6.x. And
`_wire_action_reporting()` is genuinely idempotent: wiring three times still
reports one message per click, so the `WeakSet` is doing its job.

## Qt control coverage: what the fixture does and does not contain

Audited 2026-10-13 against PySide6 6.12. `PySide6.QtWidgets` ships **72**
`QWidget` subclasses, and after the two additions below the fixture accounts
for **68** of them:

| Group | Count | Classes |
|---|---|---|
| Present in the window at rest | 50 | including the newly added `QUndoView` |
| Abstract bases -- every concrete subclass *is* present | 4 | `QAbstractItemView`, `QAbstractScrollArea`, `QAbstractSlider`, `QAbstractSpinBox` |
| Built on demand by the Tools menu, which the drivers walk | 13 | `QDialog`, `QDialogButtonBox`, `QMessageBox`, `QInputDialog`, `QColorDialog`, `QFontDialog`, `QFileDialog`, `QProgressDialog`, `QWizard`, `QWizardPage`, `QMdiArea`, `QMdiSubWindow`, and the newly added `QErrorMessage` |
| The main window's own base class | 1 | `QMainWindow` (`TortureTestWindow` is one) |
| **Deliberately absent** | 4 | `QRubberBand`, `QSplashScreen`, `QFocusFrame`, `QRhiWidget` |

**Added as a result of this audit:**

- **`QUndoView`** on the Trees & Tables tab, as "Undo History" (role `list`,
  being a `QListView` subclass). It is the only item view here driven by a
  *command* model rather than a `QStandardItemModel` -- its rows come from a
  `QUndoStack` with three pushed commands. Needed a `ROLE_BY_CLASS` entry, an
  `ACTION_SIGNALS` entry, a place in `_VIEW_ONLY_CLASSES`, an
  `EXPECTED_CONTROLS` row and six Japanese strings.
- **`QErrorMessage`** on the Tools ▸ Message Boxes submenu, as
  "&Error Message". Distinct from the `QMessageBox` family beside it because
  it is *stateful*: it carries its own "Show this message again" check box,
  and unticking it makes Qt suppress that exact message string for the rest
  of the process.

`test_every_named_widget_has_a_known_role` -- added earlier the same day --
caught the missing `QUndoView` role mapping on the first run, and
`test_expected_controls_is_complete` then caught the missing inventory row.
Both failed exactly as designed, which is the first real evidence either
guard works on a change that was not contrived to test them.

One measured quirk, documented in `_undo_view`'s docstring and left alone:
`QUndoView` reports its selection to the status bar **twice** where the other
item views report once, because the view and its stack are bound two ways
(selection moves the stack index, and the stack moving its index sets the
selection). A driver polls the status bar for the control's *name*, so two
identical messages read the same as one. The alternatives were worse:
dropping it from the selection wiring would stop it reporting keyboard
navigation at all -- the exact gap `QTableWidget` needed `currentCellChanged`
to close -- and de-duplicating messages app-wide would hide a real
double-fire somewhere a test wanted to see one.

**A bug caused by the addition itself** -- the fourth of the day, after the
three in the tidy-up section above. The first Windows re-run
after adding these died mid-walk with `Last Result: -1073741510`
(`STATUS_CONTROL_C_EXIT`) and **leaked the app** -- `pythonw.exe` still on the
desktop, because the driver died before its own cleanup ran. Cause: each
driver keeps a `MENU_DIALOG_ITEMS` set naming the menu entries that open a
dialog, and only those entries get the
wait-for-window / `focus_window` / Escape / wait-for-close treatment.
"Error Message" was not in it, so the driver clicked the item, never
dismissed the dialog, and -- since `QErrorMessage` here is
*application-modal* -- every subsequent menu click was blocked by a dialog
nothing was going to close.

Adding a modal dialog to a menu the drivers walk therefore means editing
`MENU_DIALOG_ITEMS` in all six drivers, which is now done, with the reason
recorded inline so the next person adding one does not repeat it.
**Re-verified after the fix**: Windows `all controls verified`, `EXIT=0`,
empty stderr, no leaked `python.exe`/`pythonw.exe`, run 8:23:41→8:31:09;
macOS `all controls verified`, exit 0. Scheduled Task deleted and both
scratch directories removed afterwards. Worth
noting macOS passed the same run: its menu walk tolerated the stray dialog
where Windows did not, so a single green platform was *not* enough to show
the addition was complete -- exactly the argument for re-running every
platform after an inventory change.

**The four remaining absences are a deliberate list, not an oversight:**

- **`QRubberBand`** is a transient selection overlay: no accessible name, no
  action, nothing for a driver to find or assert.
- **`QSplashScreen`** would be *actively harmful* here -- it appears before
  the main window and is gone by the time a driver connects, so all it could
  do is race the drivers' window detection.
- **`QFocusFrame`** is decoration and publishes nothing.
- **`QRhiWidget`** needs a working 3D graphics backend, which is exactly the
  thing that varies across the VMs and headless sessions this fixture has to
  run on -- adding it would trade coverage for flakiness.

## 2026-10-13 (later): recorder round-trip, and two more bugs

### Recorder round-trip run on Windows and macOS -- a first

pyguitest-recorder 0.8.3 deployed to a scratch dir with `PYTHONPATH`
(Windows had a stale 0.8.2 checkout; macOS had no recorder at all), then a
scripted session: launch the app, arm the recorder, drive four controls
through pyguitest, stop with the recorder's own Escape-Escape, inspect the
output. **Both platforms produced a working script.** `--regenerate` is
byte-identical on a second pass (an apparent difference was a flag mismatch
on this side -- `--suppress-atspi-chatter` passed to the recording but not
the regenerate).

The two outputs differ instructively:

| | macOS | **Fully clean — zero known bugs** (2026-10-15, pyguitest 0.17.1, twice in a row, ~110 s) — the day's two "dialog never closed" failures were macOS's own `View > Enter Full Screen` menu item: not a dialog, it put the app into native full screen before the walk reached Tools, and everything after ran against that. The driver now drives it as a toggle — enter, verify the item flipped to `Exit Full Screen`, leave, verify it flipped back — re-reading the menu bar fresh for the check, because the children list captured at walk start keeps reporting the old name. macOS's AutoFill/dictation/emoji items (its own, in the app's Edit menu, opening system UI in other processes) are skipped. `Undo History` (the 2026-10-14 gap) did not recur | Dedicated test box (VM); Quick Note hot corner disabled. **A locked or sleeping Mac looks exactly like a broken driver** — check `pmset -g powerstate IODisplayWrangler` first |
|---|---|---|
| Button / check box | `gui.button(...).click()` / `gui.checkbox(...).click()` | same |
| Tab | `element(role=Role.RADIO_BUTTON, ...).click()` | `element(role=Role.PAGE_TAB, ...).select()` |
| Text-field click | coordinate fallback | named `.click()` |
| `set_text` | named | named |
| connect preamble | `backend=["macquartz", "macos"]` | bare `connect()` |

macOS's coordinate fallback carried its own reason in the generated script
("'Full Name' was named, but offered the Accessibility API no click or press
action"), which is the documented degradation path working rather than a
defect. The `macquartz` preamble is what the generator's own docstring says
it emits on a Mac and why -- confirmed live here.

Windows also emitted a note that **12 keystrokes were injected by another
process rather than typed**. That is a true positive: the harness injected
them through `SendInput`, which Windows flags. Any driver-injected recording
on Windows will carry it; the note's suggested cause (a keep-awake or macro
tool) is just the common case. macOS emitted no equivalent.

### Bug: Qt strips ampersands from accessible names

Both recordings matched the tab as `"Text  Numbers"` -- **double space,
ampersand gone**. Qt reads a single `&` in visible text as a mnemonic marker
and strips it from the published accessible name. Measured through the
accessible interface:

    tabText='Text & Numbers'   -> accessible 'Text  Numbers'
    tabText='Text && Numbers'  -> accessible 'Text & Numbers'

Four tab titles were affected: Buttons & Toggles, Text & Numbers, Trees &
Tables, Sliders & Ranges. This defeats the fixture's own contract -- a
control a test can find by name -- and the defect is *invisible* on review,
since the only trace is a doubled space. Neither `tabText()` nor
`accessibleName()` shows it: both report what was set, not what the platform
publishes.

Fixed with a `tab_label()` helper that doubles the ampersand, applied to the
label only and never to `Page.title`, which is also the translation key.
New `test_tab_accessible_names_keep_their_ampersands` queries the accessible
interface -- the only way to see this -- and fails with all four damaged
names when the fix is removed. **Re-verified**: Windows and macOS both
`all controls verified`, exit 0, self-test 22/22, nothing leaked.

### Bug: QActions accumulated on every language switch

Found by the new `QErrorMessage` test, which looked up its menu action by
text and found **two**. Cause: `_make_action` parents every action to the
*window* rather than to the menu showing it (the same action can appear in a
menu, the toolbar and an action group at once), so `menuBar().clear()` drops
the menus and leaves the actions alive while `_build_menus()` builds a fresh
set. Measured: 95 QActions on a fresh window, 189 after one language switch,
283 after the second.

`_rebuild_ui` now snapshots the actions and action groups before rebuilding
and collects them afterwards, each `deleteLater()` guarded with
`contextlib.suppress(RuntimeError)` -- clearing the menu bar and deleting
the old toolbar and dock already take some of them, and PySide6 raises
rather than no-ops on an already-destroyed C++ object. Count is now stable
at 99 across any number of switches instead of growing by 94 each time.

**Not re-run on the boxes for this one, deliberately**: every driver has
`MENU_SKIP_SUBMENUS = {"Language"}`, so `_rebuild_ui` is never in the driven
path and the runs above neither exercised nor validated it. It is covered by
the self-test (`test_language_switch_rebuilds` plus the new error-message
test, 23/23 locally).

## Omarchy / Hyprland: the first wlroots compositor (2026-10-13)

Hyprland and niri were both on record as never having met a live compositor.
This closes that: a full `all controls verified` run on Omarchy (Arch),
Hyprland on Wayland, with **pyguitest needing no changes whatsoever**.
`connect()` composed
`hyprland+atspi+input:wtype+capture:grim+clipboard:wl-copy+imagesearch:compare`
on its own, every window capability -- list, state, activate, minimize,
geometry, placement, resize, **pid**, at-point -- served by `hyprland`.
`pyguitest` with no subcommand already printed `compositor wlroots
(Hyprland)` and listed `hyprctl`; `hints.py` already knew Arch's package
names. Nothing in the library had to be taught about this platform.

`drivers/cosmic.py` runs here **unmodified**, which is why there is no
`drivers/hyprland.py`. COSMIC matches windows by title because its protocol
carries no pid; Hyprland does carry one, so title matching is merely less
precise, not wrong. One driver covering both wlroots-family compositors is
the point.

**Pointer injection is a permission here, not a protocol.** `/dev/uinput`
exists but is root-owned and the login account is not in the `input` group, so
`POINTER_MOVE`/`POINTER_BUTTON` are absent and the pointer-free strategy
applies. Unlike COSMIC and Debian -- where no permission change can help --
`sudo usermod -aG input <user>` plus a re-login would unlock the full
pointer-driven strategy. pyguitest diagnoses this unprompted, in those
words.

### Resolution turned out to be load-bearing

The VBox adapter's `preferred` mode is 1024x768, and Omarchy sets
`scale = "auto"` with `GDK_SCALE=2`. At that size most of the fixture fell
outside the window: the driver reached **7** actable controls on the first
tab against **17** at 1920x1080. A run at the default would have reported
"all controls verified" having checked a fraction of them -- the exact
shape of a misleading pass, so the first run was discarded rather than
recorded. `scale = 1` matters separately: pyguitest skips its rectangle
checks on a scaled screen, because AT-SPI extents and window geometry stop
sharing units.

`hyprctl keyword` cannot set this. Omarchy uses Hyprland's new **Lua**
config, which is what "keyword can't work with non-legacy parsers" means.
The mode goes in `~/.config/hypr/monitors.lua` as
`hl.monitor({ output = "VGA-1", mode = "1920x1080@60", position = "0x0",
scale = 1 })`, then `hyprctl reload`.

### The two driver fixes

1. **`Rich Text` was never driven at all.** A `QTextEdit` publishing only a
   `Set Focus` action, and not reachable by Tab -- 70 presses never focused
   it -- so `seek_focus` failed and the branch did nothing. The first
   instinct was `do_action("Set Focus")`, but that reaches past the library:
   measured on the box, pyguitest's own `Element.focus()` sets focus just as
   well (`focused=True` for both `Rich Text` and `Notes`). So the fallback
   uses the primitive, and *verifies* focus before typing -- because on
   COSMIC and the local GNOME desktop `focus()` was measured **not** to move
   real keyboard focus, which is why `seek_focus` exists and still runs
   first. That platform difference is worth remembering.
2. **`Tool Box` could not have reported however it was clicked.** The
   `QToolBox` container publishes no actions, and the application reports
   `currentChanged` for one -- so a click on the container switches no page
   and fires nothing, pointer or not. Its section headers are real push
   buttons (`Section One/Two/Three`, each offering `Press`), and pressing one
   is what a *user* does to switch pages. The driver clicks the **last**
   header, because the first is already the open page.

## 2026-10-15: pyguitest 0.17.1 green on all eight boxes

Every box was up at once for the first time, a new Ubuntu box joined, and
the round ended with **`all controls verified` on all eight** — including
the first full widget-level run ever on niri. Everything ran the bumped
(still uncommitted) 0.17.1 / 0.9.1 trees, deployed to `/tmp/tt-run` and
reached through `PYTHONPATH`, no box's own checkout touched.

| Box | Result |
|---|---|
| GhostBSD .77 | `all controls verified`, 2254 unit tests, full recorded-session replay |
| Omarchy .82 (Hyprland) | `all controls verified`, twice — first clean runs since 2026-10-13 |
| Debian .78 (GNOME Wayland) | `all controls verified`, twice |
| COSMIC .79 | `all controls verified`, twice |
| Windows .18 | `all controls verified`, twice (Scheduled Task into session 1) |
| macOS .36 | `all controls verified`, twice — full screen driven, not skipped |
| KaOS/niri .83 | `all controls verified` — first ever on niri |
| Ubuntu 26.10 .88 | `all controls verified` — new box, provisioned bare-to-green same day |

**Environmental, found and routed around (now in AGENTS.md):** Omarchy's
"no window ever takes keyboard focus" was its shell's 300 s idle session
lock, invisible to `hyprctl` and `loginctl` alike; and running over ssh
without `XDG_CURRENT_DESKTOP` makes the doctor read `compositor other`, so
no compositor backend joins and on Wayland `ELEMENT_GEOMETRY` silently
goes missing — the verdict then reads "NO CONTROLS FOUND" with the fixture
publishing hundreds of elements. `scripts/run-box-tests.sh` now takes the
whole session environment from the compositor's own process (procstat on
FreeBSD), and finds `NIRI_SOCKET`/`SWAYSOCK` from their socket files.

**Fixed in pyguitest (one change):** `extents()` returned `None` when an
element's window had no position to absolutize against — every caller
unpacking a rectangle then died with `TypeError: cannot unpack non-iterable
NoneType object`. Measured on niri, where the compositor reports no
position for tiled windows at all. It now raises `CapabilityUnsupported`
naming the cause and the way forward; the two unit tests that pinned the
old `None` were updated to pin the refusal.

**Fixed in the drivers:**

- *macOS* — `View > Enter Full Screen` (macOS's own menu item) is driven as
  a toggle instead of being clicked and abandoned, which had left the app
  full-screen for the rest of the walk and was the whole cause of the two
  "dialog never closed" failures (both dialogs pass in isolation). The
  check re-reads the menu bar fresh: the stale children list never shows
  the name flip. AutoFill/dictation/emoji system items are skipped.
- *All six* — the whole `Slow Dialog` submenu and `Help > Dump Controls`
  joined `MENU_DIALOG_ITEMS`: each opens an application-modal dialog
  (delayed, for the Slow ones), and five drivers were passing with them
  unlisted by luck.
- *AT-SPI drivers* — a control whose window has no screen position is kept
  and driven (actions + real-focus keys need no coordinates) instead of
  being dropped by the extents filter; the tab bar is found by grouping on
  its containing tab list when there is no `y` to rank by; and
  `seek_focus` sends Ctrl+Tab every 25th press, because a `QTextEdit`
  consumes Tab as input and the walk otherwise never leaves it.
- *AT-SPI drivers* — spin button, combo box, slider and dial got the same
  `_focus_via_api` fallback the entry branch already had: on KaOS the five
  spin buttons sit after the Notes text area in the tab order, so the Tab
  walk could not reach them at all, and `Element.focus()` could. Those
  five were the last failures between an 84-control run and a clean one.
- *cosmic/debian/linux* — `seek_focus` declines immediately when the
  window never took keyboard focus (a locked Omarchy turned every keyboard
  control into a 60-press timeout), and the periodic
  `faulthandler.dump_traceback_later(25, repeat=True)` is gone: its
  GIL-less frame walk eventually lands on a thread being born — pyguitest's
  atspi backend starts one per bounded call — and segfaulted a run
  (coredumpctl: crashing thread = the watchdog, inside libpython).
  `faulthandler.enable()` + `SIGUSR1` replaces it; `kill -USR1 <pid>`
  dumps once, on request.

**Scripts added** (`scripts/`): `run-box-tests.sh` (deploy-and-run with the
session env taken from the compositor process), `deploy-box.sh`,
`run-macos-tests.sh`, `win-run.bat`, `disable-idle-lock.sh` /
`disable-idle-lock.cmd` (verified on Omarchy, GhostBSD, niri; best-effort
branches for the rest).

## 2026-10-18: the Wayland drivers share one core, and focus-seeking is a ring walk

The three pointer-free Wayland drivers (`linux.py`, `debian.py`, `cosmic.py`)
were near-identical ~1000-line copies of one strategy — `debian.py` differed
from `linux.py` by *docstrings only*, `cosmic.py` by title-vs-pid window
matching plus a progress print. They are now thin platform files (a
`Platform` config plus each box's live-verified findings) over a shared
`drivers/driver_core.py`, which meets the app package's full correctness
lint standard. `bsd.py` keeps its pointer-driven X11 strategy and imports
only the shared fixture constants; `macos.py` and `windows.py` are untouched
and still carry full private copies — migrating their shared constants needs
their boxes up to validate the changed deployment (both were down today),
recorded here as open. The `MENU_DIALOG_ITEMS`-must-change-in-six-places
trap is now a two-place trap (core + each of macos/windows).

**The one behavioral change: `seek_focus` no longer re-walks the Tab ring
per control.** The old shape pressed Tab up to 60 times *per keyboard
control*, checking only that control's `focused` state — O(n²) presses per
page, and the direct cause of the 900 s campaign timeouts seen 2026-10-17 on
KaOS/niri and Omarchy/Hyprland, where the key path is slow. The new shape
walks the ring **once per page**: after each press it asks which pending
target took focus (early-exit scan in enumeration order, which tracks Qt's
tab order), drives that control right there with the same role key
sequences, and verifies the same status-bar report. The walk ends when
nothing pending has taken focus for 60 straight presses or at a per-page
scaled backstop. Controls the ring never reaches — QScrollBar, QTableView,
QUndoView are never Tab-reachable at all — go to the same per-role fallbacks
as before (`Element.focus()`, child action clicks), behind a full 60-press
confirmation seek. Scroll bars moved out of the focus path entirely (their
`Increase` action never needed focus). Failure semantics are unchanged: a
ring-driven control whose report never shows goes back through `drive_one`'s
fresh-element retry and is recorded against the same failure list.

**The ring's patience is tuned, not guessed — a mid-work flake set it.** A
tab is switched by an AT-SPI action click, which moves no keyboard focus, so
when the ring starts pressing Tab on a freshly-shown page focus is wherever
the previous page left it — often on a now-hidden widget, and the first
Ctrl+Tab escape (every 25 presses) is what cycles it back into the visible
page. A first cut set the fruitless limit to 35 (one escape) and shortened
the post-ring fallback seek to 10 presses on the false premise that a ring
miss proved a control unreachable. Measured live on the Fedora box, the
Choosers tab: on one run focus re-entered within 35 and all 12 controls went
through the ring at ~1 s each; on the very next run it did not, the ring gave
up with zero hits, and all 12 fell to the shortened fallback at 10–16 s each
— flaky, because 35 was marginal for getting focus into a page. The fix is
above: fruitless limit 60 (two escapes, matching the old per-control seek's
persistence at entering a page) and the fallback seek restored to the full
60, so a control the ring missed still gets a real seek and the worst case
(focus never enters a page) degrades to the old behaviour, never to a new
failure.

**Validated live, same day (the final tuned code):**

- This maintainer's Fedora box (GNOME 51 Wayland, the `linux.py` platform):
  `all controls verified`, exit 0 — 22 controls via the ring, 6 via the
  fallback, zero failures, and the Choosers tab driven through the ring
  (~1–2 s each), confirming the fruitless-limit fix. An earlier run on the
  pre-fix code had passed too (516 s, same 22/6 split) but only because that
  run happened not to hit the focus-entry flake.
- Ubuntu .88 (GNOME 51 Wayland, the `debian.py` platform): the pre-fix code
  drove the same Choosers controls cleanly via the ring (~0.6–1.4 s each) on
  its one captured run before the campaign was stopped; the old (per-control
  seek) driver had passed the full fixture in **773 s** earlier the same day.
  **A full `.88` campaign on the final tuned code has NOT been run** — the
  box was rebooted mid-session — so .88 on this code is unverified-pending,
  recorded here honestly rather than claimed.

**New, unvalidated:** `drivers/sway.py` + `scripts/run-sway-headless.sh` —
the first wlroots-family driver, for the one pyguitest-validated desktop
with no torture coverage. The runner boots a private headless sway,
discovers its sockets, and **refuses to run without `wtype`**: a headless
sway has no seat, so pyguitest's uinput fallback would attach to the live
desktop's libinput and type into the user's own session. A bootstrap smoke
test ran today (sway up, fixture launched inside it, view listed with a pid
in sway's tree); the driver itself has not — this box has no `wtype`
(install needs root). Two findings from the smoke are already encoded:
backend auto-selection inside a nested compositor picks the *outer* desktop
(measured: `windows()` answered with the GNOME session's windows despite
`SWAYSOCK` and `XDG_CURRENT_DESKTOP=sway`), so `Platform` grew a `backends`
override and `sway.py` forces `("sway", "atspi", "input")`; and
`python -m torture_test` must be launched with the repo as its cwd.

## Platform matrix

| Platform | Status | Notes |
|---|---|---|
| Linux (Wayland, this maintainer's desktop) | **Partially unblocked, 4 bugs fixed, not re-verified** (2026-10-12) — pointer is broken but keyboard works (same split as COSMIC/Debian); a pointer-free driver + 3 interact() fixes exist but the fixed version has not been re-run here, per explicit instruction to stop testing this box — see below | Live desktop — do not run without explicit go-ahead each time |
| GhostBSD/FreeBSD (X11) | **Fully clean — zero known bugs** (re-verified 2026-10-15 on pyguitest 0.17.1: `all controls verified`, 2254 unit tests green, a recorded session replayed end to end) (2026-10-12) — every tab and the entire menu bar walked with `all controls verified`, no failures at all, confirmed on 2 consecutive runs after a 10-run/12-failures-every-time baseline; reconfirmed clean again after the pyguitest hang-hardening fix was synced over | Dedicated test box |
| Pop!_OS 24.04 / COSMIC | **Fully clean — zero known bugs** (re-verified 2026-10-15 on pyguitest 0.17.1: `all controls verified`, exit 0, 423 s, 7 controls clipped by screen size) (2026-10-12) — pointer-free driver (AT-SPI action clicks + Tab-seek real-focus keyboard), `all controls verified` on 2 consecutive full runs | Dedicated test box; slow (repeated bounded AT-SPI stalls during menu walking) but correct |
| Debian 13 (Wayland) | **Fully clean — zero known bugs** (re-verified 2026-10-15 on pyguitest 0.17.1: `all controls verified`, exit 0, 474 s, nothing clipped; doctor reads `mutter (GNOME)`) (2026-10-12) — pointer-free driver (same strategy as COSMIC), `all controls verified` on 2 consecutive full runs after fixing 3 real bugs — see below | Dedicated test box |
| macOS | **One control short — a driver gap, not a pyguitest bug** (2026-10-14) — 16 controls found and driven, `Undo History` the only failure: its rows do not move the undo stack through the AX API, so the interaction reports nothing. Clean twice on 2026-10-13 before that. 7 real bugs fixed along the way, incl. the driver clicking the Dock's Notes icon (which stole keyboard focus and made whole runs look like hangs) and 2 genuine pyguitest bugs — see below | Dedicated test box (VM); Quick Note hot corner had to be disabled. **A locked or sleeping Mac looks exactly like a broken driver**: Quartz keeps listing windows while the AX tree returns nothing, so a run reports zero controls — check `pmset -g powerstate IODisplayWrangler` before debugging code |
| Omarchy / Hyprland (Arch) | **Fully clean — zero known bugs** (2026-10-15, pyguitest 0.17.1) — `all controls verified`, exit 0, 740 s. The long-standing "Hyprland grants no window keyboard focus" block was **the session being locked**: Omarchy's shell locks after 300 s idle through its own PAM-backed `ext-session-lock`, and Hyprland refuses `focusWindow` outright while a lock is up, while every dispatch still replies `ok`, `hyprctl layers` lists no lock surface and `loginctl` says `LockedHint=no`. Unlocked at the console + `omarchy-toggle-idle stay-awake`, the same tree passed first time. Ask the shell before debugging focus: `OMARCHY_PATH=/usr/share/omarchy omarchy-shell lock isLocked` | Dedicated test box (VBox); keep it unlocked and awake — `scripts/disable-idle-lock.sh`. Pointer injection is still a *permission* away (`/dev/uinput` root-only, no ACL), not needed for a pass |
| KaOS / niri | **Fully clean — zero known bugs** (2026-10-15, pyguitest 0.17.1) — `all controls verified`, the first full widget-level run ever on niri, closing the last compositor gap in the matrix. Getting there took one provisioning step (`gtk3`, root — KaOS ships no GTK and dogtail's `utils.py` requires the Gtk-3.0 typelib at import), one package repair (`pip install pyside6` into `~/tt-venv`: KaOS had `pyside6 6.12.0` against `qt6-base 6.11.2`, so system PySide6 could not even import QtCore; the wheel bundles its own Qt), and `NIRI_SOCKET` exported from the socket file (niri does not carry it in its own environment, and without it the niri backend never joins the composite). niri reports no position for a tiled window (`tile_pos_in_workspace_view` null even on screen), so there are no screen coordinates there at all — pyguitest now refuses `extents()` with a typed `CapabilityUnsupported` instead of returning `None`, and the drivers keep such controls and drive them through actions and real-focus keys, which need no coordinates | Dedicated test box (VM). `scripts/run-box-tests.sh` handles the env; the box's venv is `~/tt-venv` |
| Ubuntu 26.10 (GNOME Wayland) | **Fully clean — zero known bugs** (2026-10-15, pyguitest 0.17.1) — `all controls verified`, exit 0, 873 s, on a box provisioned from bare that same day: no pip, no ensurepip, no virtualenv, no curl, no gcc, so the venv was built `--system-site-packages --without-pip` and pip bootstrapped with urllib; PySide6/dogtail/pytest from PyPI on top of the system `gi`. Needed beyond that: the pyguitest GNOME Shell extension (user-level install + a log out/in — Wayland cannot reload the Shell), `toolkit-accessibility` true (was false, same as Debian), and uinput (`python3-evdev` via apt + an ACL on `/dev/uinput`; pip cannot build evdev there and libei answered `BackendUnavailable` on this session). All of it is `~/setup-pyguitest-ubuntu.sh` and `~/fix-pyguitest-ubuntu.sh` on the box, both idempotent. Unit suite: 2243 passed there | New (eighth) box, `ssh paulsden@192.168.1.88` |
| Windows 11 | **Fully clean — zero known bugs** (re-verified 2026-10-15 on pyguitest 0.17.1 via a Scheduled Task into session 1: `all controls verified`, driver-exit 0, 3 controls clipped; re-verified 2026-10-13 after the restructure, then again after `QUndoView`/`QErrorMessage` — 21/21 self-test, `all controls verified`, `EXIT=0`, empty stderr, nothing leaked; the intermediate failure and its cause are below) — brand-new driver, `all controls verified` on 2 consecutive full runs on the first attempt | Dedicated test box; must run via a Scheduled Task bound to the interactive session, not plain SSH — see below |
| Windows 10 (22H2, build 19045) | **Fully clean — zero known bugs** (2026-10-19, pyguitest with the drag/region fixes) — 23/23 self-test, `all controls verified`, `EXIT=0`, 17 actable controls visible, nothing leaked. First torture run on Windows 10, same `uia`+`win32`/Scheduled-Task path as Windows 11 (here the composite was `win32` alone). Needed only Python installed from scratch (python.org 3.12.10 — winget is absent over SSH) and `pip install PySide6 comtypes` | New (tenth) box, `ssh paulsden@192.168.1.89` (user `paulsden`, VirtualBox guest "winny"). A mid-install SSH drop left a null-byte-corrupted PySide6 once — `pip install --force-reinstall --no-cache-dir` fixed it |
| Fedora 19 (GNOME 3.8, Xorg, 2013) | **Torture test impossible — not a pyguitest limit** (2026-10-19) — the app itself cannot run: no PySide6 wheel exists for glibc 2.17 (Qt 6's floor is glibc 2.28) and no GI/AT-SPI bindings for a modern interpreter. pyguitest *itself* was validated here separately (drag/region fixes green, 71 unit tests, recorder record→replay round trip on gedit) on a portable CPython 3.12 — see pyguitest's own `docs/validation.md`. Recorded here only so the gap is deliberate, not an untried box | Legacy box, `ssh paulsden@192.168.1.91` (needs an ECDSA key — its sshd 6.2 predates ed25519) |

## 2026-10-19: Windows 10 added, and Fedora 19's hard floor

Two new boxes came online while validating a pair of pyguitest fixes (`drag()`
releasing its button even when the glide raises, and `check_region()` covering
fractional regions instead of truncating them — both live in pyguitest's own
`docs/validation.md`). The torture app itself was run where it could run.

**Windows 10 (22H2, build 19045) — fully clean, first attempt.** The box had
no Python at all; python.org 3.12.10 installed quietly over SSH (winget does
not exist in an SSH session), then `PySide6` and `comtypes`. The driver ran
through the same Scheduled-Task-into-session-1 path as Windows 11 — a plain
SSH session is Session 0 and sees no desktop — and reported 23/23 self-test,
`all controls verified`, `EXIT=0`, 17 actable controls visible, with no
process or window left behind. The composite here was `win32` alone (Windows
11's is `uia`+`win32`), which is the honest difference between the two boxes,
not a failure. One operational scar worth keeping: a mid-install SSH drop
left PySide6 half-written and importing it failed with "source code string
cannot contain null bytes" — a corrupted install masquerading as a code bug;
`pip install --force-reinstall --no-cache-dir` was the fix, and a
file-based import probe is what told a real `ModuleNotFoundError` apart from
a corrupt one over a connection that mangles inline Python.

**Fedora 19 (2013) — the app cannot run there, and that is the finding.**
This is the oldest system in the fleet: GNOME 3.8 on Xorg 1.14, glibc 2.17,
system Python 3.3. The torture fixture is PySide6/Qt 6, and Qt 6's own glibc
floor is 2.28 — pip finds *no* wheel, and there are no GI/AT-SPI bindings for
a modern interpreter on the box either, so element automation is out
regardless. The torture test is therefore impossible here, and that is a
property of a thirteen-year-old userland, not of pyguitest. pyguitest itself
was validated on the box separately on a portable CPython 3.12 (the drag and
region fixes, 71 unit tests, and a full recorder record→generate→replay round
trip against gedit on the live desktop), recorded in pyguitest's own
`docs/validation.md`. The row is in the matrix above so the gap reads as
deliberate rather than as a box nobody tried.

## 2026-10-11 session

### AGENTS.md: no-XTEST/XRECORD rule made explicit

Added an explicit, unambiguous rule to `AGENTS.md`: nothing in this app or
its driver scripts may use XTEST, XRECORD, or any other raw platform input/
capture API — every interaction goes through pyguitest's own API. The one
documented exception is pyguitest-recorder's own internal use of XRecord to
*capture* a session, which is the recorder's job, not the app's or a
driver's. (The codebase already complied; this was a documentation gap, not
a code fix.)

### Housekeeping: synced latest pyguitest/pyguitest-recorder/this app to BSD

BSD's checkouts of `pyguitest` and `pyguitest-recorder` were stale (behind
by several merged PRs, including the COSMIC backend and an already-merged
`click_via` feature) and also had their own *separate*, independently
uncommitted `click_via`-shaped WIP sitting in the working tree — apparently
written directly on the box at some earlier point, in violation of the
project's own "never write into a test box's checkout" rule. That WIP
turned out to be superseded by what already landed on `main` (same feature,
independently implemented), so no work was lost; the stale/uncommitted
state was simply overwritten with current `main`'s source via `scp -r`
(not `rsync --delete`, not `git pull` — these boxes are reached by copying
files, not git state, by long-standing convention).

Also renamed BSD's `~/code/torture-test` to `~/code/pyguitest-torture-test`
(was carrying a legacy, pre-rename directory name) and fixed the `APP_DIR`
path in the BSD driver (now `drivers/bsd.py`) to match. (That hard-coded
`APP_DIR` is gone as of the 2026-10-13 tidy-up -- the drivers derive the
repo root from their own location now.)

Self-test (`python3 test.py`, headless Qt) ran clean, 19/19, after the sync.

### BLOCKED: BSD's X11 session is not delivering synthetic input at all right now

A live full-driver run (`drivers/bsd.py`) hung indefinitely
after the very first control. Instrumented diagnosis (temporary print
statements, then a series of minimal standalone repro scripts) traced this
all the way down to the X server itself, not to any pyguitest or
torture-test code:

- `gui.click()` via pyguitest's `x11` backend on a correctly-positioned,
  correctly-focused "Primary Action" button: **no effect** (status bar
  never updates).
- A **plain `xdotool click`** at the identical screen coordinate, same
  window, same focus state, entirely bypassing pyguitest: **also no
  effect**.
- **Keyboard** input (`xdotool key Tab` then `key space`, which should
  focus and activate a button): **also no effect**.
- `xdotool type` into a plain Terminal window (not Qt, not this app, not
  pyguitest at all) that `xdotool getactivewindow` confirms is focused:
  **also no effect** — the typed command never appeared.
- AT-SPI reads (element tree, extents, window list, status bar text) all
  work normally throughout — only input delivery is affected.
- Screenshots throughout show the right window, right tab, right layout;
  nothing visibly wrong, no stray dialog or window sitting on top.
- The accessible-action route (`element.click()`, which calls the
  AT-SPI/dogtail action directly rather than injecting a real pointer
  event) **does** work — that's why earlier isolated AT-SPI checks in this
  session looked healthy before the input-specific tests ran.

**Conclusion**: this is a GhostBSD/X11 session-level problem (XTEST/input
event delivery broken desktop-wide), not a pyguitest, torture-test, or
driver-script bug. It reproduces identically for a brand-new, never-
automated Terminal window, ruling out anything specific to Qt, AT-SPI, or
this app. Likely needs the X session restarted (or the box rebooted) to
clear, which was not done unilaterally here since it would disrupt the
live desktop session on that box.

All test processes and diagnostic scripts from this investigation were
cleaned up (confirmed via `ps`/`wmctrl`); nothing was left running or
orphaned on the box.

**Next step on resume**: once the BSD box's input is confirmed working
again (a quick `xdotool click`/`xdotool type` sanity check against a
throwaway window is enough to confirm before re-running anything real),
resume from the known-good "run 5" state described in the pre-2026-10-11
history below — tabs+menus walk end-to-end; the one still-open item is the
9-menu-dialog detection gap (see below).

**Update, later the same day**: input recovered on its own (or was fixed
on the box from outside this effort — never diagnosed further, since
the blocker cleared and `xdotool type`/`click` against a throwaway Terminal
window were confirmed working again). Validation resumed from there; see
the next section for what followed.

### RESOLVED: a real pyguitest hang, found, fixed, and fixed in pyguitest itself

With input working again, a full driver run reliably hung anyway —
indefinitely, zero progress, same shape as the earlier "Model Tree" symptom
but now reproducing on *different* widgets/tabs run to run, not always the
same one. Root-caused with `faulthandler.dump_traceback_later` (far faster
and more conclusive than continued print-statement bisection — see the
stack traces it produced): a single underlying AT-SPI call
(`dogtail`'s `_find_all_descendants` → `get_role_name`/`get_child_at_index`,
several frames deep) can simply never return on this platform, with no
exception and nothing to catch. Every `wait_for_*`/`wait_until` timeout
anywhere in the calling driver was powerless against it, since each only
checks its own deadline *between* calls to a function that itself never
hands control back to Python at all.

Two approaches were tried at the driver-script level first and both turned
out to be dead ends:
- A `signal.alarm`-based watchdog in the driver script: confirmed live to
  **not** interrupt this specific hang at all — the call is stuck inside a
  blocking native (GI/D-Bus) call that never returns control to the
  interpreter loop, and CPython only delivers a pending signal between
  bytecode instructions, so a truly wedged native call defeats a
  signal-based timeout outright.
- Chasing individual unguarded call sites one at a time in the driver
  script: the hang kept recurring at a *different* point each time a given
  one was worked around (property reads, not just `find_elements`), because
  the real exposure is pervasive across pyguitest's own AT-SPI backend, not
  a handful of call sites in this driver.

**The real fix went into pyguitest itself**, on branch
`P2-atspi-call-timeout` (`~/code/pyguitest`, not committed — the maintainer
commits their own work; full gate green, 7/7, ready for review): a new
`BackendCallTimeout` error, and `atspi.py`'s `find_elements`/`extents`/every
`Element` property now run their underlying dogtail call in a worker thread
bounded by `join(timeout)` (default 20s, configurable via
`backend_options={"atspi": {"call_timeout": ...}}`) instead of calling it
directly. It cannot stop the stuck call — nothing in Python can force
another thread to abort a blocking C/D-Bus call — but it reliably lets the
*caller* move on instead of hanging forever. Confirmed live: a run that
previously made zero progress for the full budget now makes continuous,
bounded progress throughout — a 180s diagnostic run reached tab 7 of 9
(previously 3-4 was the ceiling, ever, on this box) with no permanent
stalls, just individual slow calls that each eventually completed or
cleanly timed out.

The driver script's own `signal.alarm`-based watchdog and the
`drive_items()`-abandons-its-own-batch-on-a-miss gap (see below, carried
over from before) were both fixed properly in this pass: the signal
watchdog was removed (dead weight now that pyguitest bounds its own calls,
and actively harmful — it could cut off a call that was merely slow, not
hung, before pyguitest's own 20s budget gave it a fair chance), and
`drive_items()` now continues through the rest of its batch on any miss,
including a caught `BackendCallTimeout`.

**Follow-up, same session: root cause of the slowness found and fixed too.**
A full run still didn't finish even with a 600s budget — not a hang
(`BackendCallTimeout` was confirmed not firing), just genuinely slow AT-SPI.
Checked the actual AT-SPI session bus process and found the real cause:
the login session's AT-SPI `dbus-daemon` had accumulated **7 minutes 44
seconds of CPU time** over the ~5.5-hour test session (compare: its sibling
`at-spi2-registryd`, sitting at a normal 4 seconds). That daemon routes
every single AT-SPI message; something about it degrades under sustained
AT-SPI traffic over a long session, driving per-call cost from the
documented ~5s baseline up to 10-20s+.

**Fix**: killed the three AT-SPI processes belonging to the logged-in
user's session
(`at-spi-bus-launcher`, its `dbus-daemon`, `at-spi2-registryd`) — cleared
with the maintainer first, since it's a live desktop session even on a
dedicated test box. They respawn automatically via AT-SPI's own on-demand activation
the moment a client reconnects (confirmed: `a11y_bus_reachable()` → `True`,
a real `connect()` + tree walk succeeded immediately after). A direct
timing probe right after confirmed `find_elements()` back down to 4.37s —
exactly the documented baseline. Nothing else in the desktop session was
touched; this only affects accessibility-bus traffic.

### MILESTONE: first full end-to-end pass on BSD (2026-10-11)

With the bus fresh, `drive()` (all 9 tabs) completed cleanly in ~165s —
itself a first; no run before today had ever gotten through more than 3-4
tabs. `drive_menus()` (the full menu bar — discovery pass, then every safe
leaf clicked, ~46 leaves including 18 dialog-verified ones) took
substantially longer, ~435s, which pushed the *first* attempt at this past
a 600s budget with no visible failure (just not yet done — the production
driver prints nothing between start and its final summary, so this needed
a lightly-instrumented copy with milestone prints to see where time was
actually going, rather than guessing again). A 900s run then completed in
full:

```
STATUS CHECK FAILED: 12 interaction(s) did not report
  - Model Tree (tree) -> 'Selection changed: Project Tree'
  - Data Grid (table) -> 'Selection changed: Project Tree'
  - Model Table (table) -> 'Selection changed: Project Tree'
  - Tools/Color Picker… (menu item) -> dialog never appeared
  - Tools/Font Picker… (menu item) -> dialog never appeared
  - Tools/File Dialog… (menu item) -> dialog never appeared
  - Tools/Progress Dialog… (menu item) -> dialog never appeared
  - Tools/Custom Dialog… (menu item) -> dialog never appeared
  - Tools/Wizard… (menu item) -> dialog never appeared
  - Tools/MDI Workspace… (menu item) -> dialog never appeared
  - Help/About TortureTest… (menu item) -> dialog never appeared
  - Help/About Qt… (menu item) -> dialog never appeared
```

Exit code 2 (the script's own "ran clean, found N known failures" signal,
not a crash). Process cleanup confirmed (`ps`/`wmctrl`, nothing left
running or open). **Every one of these 12 failures is already documented
above as a known, pre-existing gap — zero new failures.** The tree/table
misclick (previously documented against "Model Tree" alone) now shows the
same symptom on three widgets at once (Model Tree, Data Grid, Model Table
all report "Selection changed: Project Tree") — a broader manifestation of
the same undiagnosed root cause, not three new bugs. The 9 dialog-detection
items are exactly the previously-documented set (see "Known gap" below) —
notably, the *other* 9 `MENU_DIALOG_ITEMS` (Information/Warning/Critical/
Question/Get Text/Get Integer/Get Item/the 1-second Slow Dialog) all
**passed** this run, so the gap is specifically these 9, not dialogs in
general.

This closes out tonight's BSD work: the driver is correct, the pyguitest
fix is correct, and the only things standing between this and a clean run
are the two already-known, already-documented, previously-deprioritized
gaps (tree/table misclick, 9-dialog detection). A 10x campaign to check
run-to-run stability, and investigating either known gap, are both
reasonable next steps whenever picked back up — neither is urgent tonight.

### 10x stability campaign on BSD (2026-10-11/12)

Same driver, same app, run 10 times back to back with the AT-SPI session
bus restarted before each run (it degrades under sustained AT-SPI traffic
within a single run — see above — so restarting between runs keeps
conditions comparable across the whole campaign rather than letting later
runs get progressively slower for reasons unrelated to the app/driver).
Each run given a 900s budget. Results, updated as runs complete:

| Run | Exit | Duration | Failures |
|---|---|---|---|
| 1 | 2 | 725s | 12 — the known set |
| 2 | 2 | 712s | 12 — identical |
| 3 | 2 | 720s | 12 — identical (first run with the status-bar-as-plain-QLabel app fix below; unaffected, confirming it's safe on BSD too) |
| 4 | 2 | 713s | 12 — identical |
| 5 | 2 | 707s | 12 — identical |
| 6 | 2 | 689s | 12 — identical |
| 7 | 2 | 696s | 12 — identical |
| 8 | 2 | 698s | 12 — identical |
| 9 | 2 | 690s | 12 — identical |
| 10 | 2 | 702s | 12 — identical |

**10 for 10.** Every run exit 2, every run exactly the same 12 pre-existing,
already-documented failures, zero flakiness, zero new failures. Campaign
finished 2026-10-12 07:13 CDT. This fully validates the driver and the
`BackendCallTimeout` fix under repeated load — see the next section for
what happened to those 12 failures.

### MILESTONE: all 12 known BSD failures fixed — zero known bugs (2026-10-12)

A fair challenge raised after the 10x campaign: *why are the failures not
being fixed?* The two gaps behind all 12 failures had been investigated
hard earlier and explicitly deprioritized at the time, and the focus up to
that point had been on reaching a complete run at all (never done before)
plus proving stability, not on these two specific items. Revisited
both properly and found real, fixable root causes for all of them — four
small, targeted fixes, two in this app and two in the BSD driver:

**Bug A — `Model Tree`/`Model Table` never reported keyboard-driven
selection changes.** Root cause: `reporting.py`'s `ACTION_SIGNALS` wires
`QTreeView`/`QTableView`/`QListView`/`QColumnView` (the model/view-only
widget classes) to `clicked` alone — a real mouse-click signal that never
fires from keyboard-only navigation (`Down`/`Up`/...). Their
`QTreeWidget`/`QTableWidget` siblings don't have this gap because they
*also* wire `itemSelectionChanged`/similar directly on the widget; the
plain view classes only expose an equivalent one layer down, on
`.selectionModel()`, which `ACTION_SIGNALS` (keyed by widget type, one
`getattr(widget, signal_name)` per entry) had no way to reach. Confirmed
live (GhostBSD): clicking "Model Tree" correctly took keyboard focus and
`Down` correctly moved the current row — nothing was broken in the
driving — but nothing fired, so the status bar kept showing whatever the
*previously*-driven control's own report was, surfacing as "Model Tree ->
'Selection changed: Project Tree'" (confirmed as a result of the ordering
controls are driven in, not a true mix-up).

**Fix**: `app.py`'s `_wire_action_reporting` now also connects
`widget.selectionModel().selectionChanged` for exactly
`(QTreeView, QTableView, QListView, QColumnView)` — `type(widget) in
(...)`, not `isinstance`, since `QTreeWidget`/`QTableWidget` *inherit from*
`QTreeView`/`QTableView` in Qt and must not be double-wired.

**Bug B — `Data Grid` (`QTableWidget`) had the same gap, for a different
reason.** Not caught by Bug A's fix since it's a Widget-based class, which
should have already been covered the way `QTreeWidget` is — except
`QTableWidget`'s own `ACTION_SIGNALS` entry was *only* `("cellClicked",)`,
also mouse-only, with no keyboard-friendly pair the way `QTreeWidget` has
`itemSelectionChanged` alongside `itemClicked`. A real, separate gap in
the same family, not a consequence of Bug A.

**Fix**: added `"currentCellChanged"` (a real signal `QTableWidget` already
has, firing on keyboard-driven current-cell changes) alongside
`"cellClicked"` in `ACTION_SIGNALS`, plus a `_VERBS` entry ("Selected
cell") for it.

**Bug C/D — 9 menu items under Tools/Help (all direct, depth-1 children of
their top-level menu) clicked at the right coordinate but never fired.**
The dialog genuinely never opened — this is the same symptom a prior
session already confirmed via live trace (ruling out wrong coordinates,
timeout margin, and the click mechanism itself in isolation). Revisited
with two independent fixes, both needed together (confirmed live: the
settle delay alone closed the gap in an isolated single-leaf repro but did
**not** hold up in the context of a full run, where AT-SPI is under far
more sustained load by the time `drive_menus()` reaches Tools/Help):

- `open_path()` now sleeps 0.5s after a menu level's `wait_for_element`
  succeeds, before trusting that level's item extents — `wait_for_element`
  only confirms *a* menu-role element exists, not that the whole level
  (Tools has 10 direct entries, the largest menu in the app) has finished
  rendering.
- Each menu-leaf dialog click now gets one retry — fresh `open_path` +
  re-click — if the dialog doesn't appear on the first attempt, mirroring
  the retry shape `drive_one()` already uses for an ordinary control. These
  specific leaves are a one-shot miss, not a structurally unreachable
  target: a second, independent attempt is a real second chance.

**Result, confirmed live, twice in a row**: `all controls verified`, `EXIT=0`,
zero failures — the first fully clean run this app has ever had, on any
platform. **BSD has zero known outstanding bugs.**

`app.py`/`reporting.py` (Bugs A/B — this app's own code, platform-agnostic)
synced to Debian's checkout too, ready for whenever its separate input
blocker (below) is resolved; Bugs C/D's fixes are BSD-driver-specific
(`drivers/bsd.py`) and will need porting to the other drivers
once their own platforms are unblocked/reached.

### Debian: thought BLOCKED, actually fixable — see "Debian 13: fully clean" below (2026-10-11/12)

Ported the same driver fixes BSD got (menu walking, `drive_items()`
batch-continue, `BackendCallTimeout`-aware exception handling) to
`the archived debian_pointer driver` — turned out to be a much smaller diff than
expected, since this script already had menu-walking and the top-level
`drive()` fix from an earlier (pre-2026-10-10) round; only the narrower
`drive_items()`-abandons-its-own-batch gap needed porting. `pyguitest-
torture-test`'s legacy `~/code/torture-test` directory on the Debian box was
also renamed to match, same as BSD.

**A real, separate app-level bug found and fixed along the way**: the first
full run reported 16 failures, every single one showing a *stale* status
message — reading back the *previous* control's report, or just the
permanent "controls: N" counter, never the real one. Root-caused (not a
timing issue, confirmed by raising the verification timeout 3x with zero
change in the failure list): Qt's `QStatusBar.showMessage()`/
`currentMessage()` mechanism is not exposed to accessibility *at all* on
this Debian/Qt/Wayland build — `udevadm`-style introspection via AT-SPI
showed its internal temporary-message widget as `role="unknown"`, with
empty name, description, and text, even immediately after a real message
was shown. The adjacent "controls: N" counter (a plain `QLabel` added via
`addPermanentWidget`) read back perfectly the whole time, which is what
pointed at the fix: `app.py`'s `_build_status_bar`/`_report` now write into
an ordinary `QLabel` the app owns directly (`self._status_message`) instead
of relying on `QStatusBar`'s own built-in mechanism. `test.py`'s self-test
updated to match (`window._status_message.text()` instead of `window.
statusBar().currentMessage()`) — the old self-test used Qt's own API, which
works fine internally, so it could never have caught an *accessibility*-
only gap like this one. Deployed to BSD too (confirmed harmless there,
see the campaign above).

**The real blocker, found while re-testing the status-bar fix**: synthetic
input — pointer *and* keyboard — does not reach the application at all on
this box, confirmed via direct probing, not an app or driver bug:

- Raw kernel events are delivered correctly: reading `pyguitest`'s own
  `/dev/input/eventN` node directly (bypassing Mutter entirely) after a
  click showed the exact expected `EV_ABS`/`EV_KEY`/`SYN` sequence.
- `udevadm info` showed the device correctly tagged `seat` at the
  `/sys/class/input/inputN` level (the level `loginctl seat-status`
  actually tracks) — matching the real keyboard exactly. An initial read
  that seemed to show it *missing* a seat tag, and missing from
  `loginctl seat-status` entirely, turned out to be a timing race (checked
  too soon after device creation); a few seconds' buffer showed it correctly
  tagged and listed every time.
- Declared capabilities briefly looked implicated: the device's keyboard-
  range sweep included `KEY_POWER` (116), which `udevadm info` showed
  tagging the whole device `power-switch` at the `/dev/input/eventN` level
  (a *different*, additional classification from the `seat`-tagged parent
  node above). Excluded it in `uinput.py` as a real, defensible fix either
  way — no GUI test needs a hardware power-button key, and this tag could
  plausibly cause trouble on a system that *does* gate `uaccess` on it even
  though this one, confirmed, does not. **This did not fix the blocker**:
  identical failure before and after.
- Screen/coordinate calibration checked out: `gnomeshell`'s own
  `gui.screens()` reports `1280x800 'Virtual-1'`, exactly matching the
  `uinput` backend's own axis declaration.
- A longer (5s) warm-up delay between device creation and the first input
  event made no difference, ruling out a device-registration race on
  Mutter's side.
- **Decisive test**: a bare-minimum `evdev` device — one button, two
  absolute axes, nothing else, built directly with no code from this
  project at all — clicked the identical target and had the identical zero
  effect. This rules out anything about pyguitest's own device declaration;
  *no* uinput-created device can deliver input to this login session right now,
  regardless of its capabilities.
- AT-SPI's own accessible-action route (`element.click()`, which never
  touches `uinput` — it calls GNOME's AT-SPI action interface directly)
  **works perfectly**: confirmed live, "Clicked: Primary Action" reported
  correctly and immediately. The desktop session itself is healthy; this is
  specific to the `uinput` → libinput/Mutter input-delivery path.
- A full reboot (done between finding this and re-confirming it) did not
  change the outcome — this is a deterministic configuration issue on this
  box, not transient session drift the way BSD's AT-SPI slowness was.

**Conclusion**: a real, thoroughly-isolated, system-level block on this
specific Debian VM's ability to accept any uinput-injected input at all,
most likely a libinput/seat configuration issue below what's diagnosable
without root (`sudo` on this box prompts for a password the automated run
does not have; `libinput-tools`, which would give a direct, authoritative answer
via `libinput debug-events`, is not installed and could not be installed
without one). Not a pyguitest bug, not a driver bug, not an app bug (the
one real app bug found along the way — the status-bar accessibility gap —
is fixed and confirmed independently on BSD). Needs the maintainer's own access
to this box to resolve (check `libinput debug-events` once installed, or
compare against a known-working Debian/GNOME/Wayland box's `libinput`
device list for what's different). The `KEY_POWER` fix and the status-bar
fix are both real and kept regardless of this blocker — see pyguitest's
`CHANGELOG.md` and this app's `app.py`/`test.py`.

### This maintainer's own Linux desktop: thought BLOCKED, superseded below (2026-10-12)

Driver ported (same `drive_items`/`BackendCallTimeout`/menu-settle-and-retry
fixes as Debian and BSD), a working venv set up (`~/code/.venv`, system
Python 3.15's own `gi`/AT-SPI bindings via `--system-site-packages`, plus a
pip-installed PySide6 wheel — the same box's dedicated venvs were each
missing one half of the pair), and a real `NO_AT_BRIDGE=1` gotcha fixed
(`app_environment()` now explicitly unsets it — the shell this work ran in
sets it, which would have silently kept the Qt app off the accessibility
bus entirely). The live run itself hit the exact same symptom as Debian:
every control's status stayed on "Ready", pointer
clicks landing nowhere, confirmed via the same isolated probe (window
correctly focused and active, `element.click()` via the accessible-action
route works perfectly, raw pointer clicks have zero effect). The
`pyguitest` uinput device is correctly `seat`-tagged and listed in
`loginctl seat-status` here too (confirmed with the same several-seconds
settle the Debian investigation needed to rule out a timing race). Same conclusion: a real, system-level libinput/Mutter block on
synthetic input from uinput-created devices, not diagnosable further
without root. A one-off sudo grant for `libinput debug-events` was
offered and turned out to be unusable: piping a password into `sudo` is
blocked by the tooling's own permission system even with explicit
authorization given in response to being asked. Maintainer's call: leave
this box blocked for now, same as Debian, and move on to other
platforms.

**Superseded the same day**, after COSMIC's pointer-free driver proved the
"blocked" conclusion was only half right (see below): re-tested this box's
keyboard path in isolation and found `gui.tap_key("Tab")` genuinely moves
real AT-SPI-visible focus and `gui.type_text()` lands real characters —
only *pointer* injection is dead here, not input generally. Wrote a new
pointer-free driver (`drivers/linux.py`, pid-based window matching
since this box's `gnomeshell` backend populates `Window.pid` correctly,
unlike COSMIC's) and found 4 real bugs, all later confirmed and fixed via
Debian (see "Debian 13" below for the full root-cause writeup — identical
symptoms, identical fixes). The fixed driver has **not been re-run on this
box**: testing here was called off partway through the live investigation,
so the fix is ported into `drivers/linux.py` but
unverified here. This box's status is "probably fixed, confirm before
relying on it" — not "fully clean" until a clean run is actually observed.

### Pop!_OS 24.04 / COSMIC: fully clean, 2x confirmed (2026-10-12)

A new driver, `drivers/cosmic.py`, written from scratch rather
than ported — COSMIC needed a different interaction strategy on two
independent axes, both confirmed by live probing before any driver code was
written:

- **Window matching is by title, never pid.** `Window.pid` from the
  `cosmic` backend is always `None` — verified directly against the real
  `zcosmic_toplevel_info_v1` protocol XML (cosmic-protocols, through v3):
  no pid-bearing event exists at any version, a permanent protocol
  limitation, not a missing feature. (This is also what the
  `_window_offset` title-fallback fix below exists for.) AT-SPI's own
  `Element.pid` is unaffected — confirmed live, it comes from
  `get_process_id()` on the accessible node itself — so every `app_frame`-
  scoped element lookup stays pid-filtered exactly like every other
  platform's driver; only direct `gui.windows()` matches switch to title.
- **Pointer injection never reaches the app**, confirmed via the same
  isolated-probe method used on Debian/this maintainer's box: window
  correctly focused, `element.click()` (AT-SPI action) works, raw pointer
  clicks have zero effect. Unlike those two boxes, this one was not treated
  as blocked — COSMIC's keyboard path (`wtype`-backed) is independently
  confirmed live to work, which Debian's and the other Linux box's did not
  get to, so a pointer-free driver was possible here. Two live findings
  shaped it:
  - `Element.click()` reliably fires the real action for buttons, tabs, and
    menu items — confirmed by more than the AT-SPI `selected` state flipping:
    clicking a page tab via its action made a Text-&-Numbers-only control
    (`entry.visible`) actually become `True`, i.e. the real Qt page changed.
  - `Element.click()` and `grabFocus()` do **not** reliably move real
    keyboard focus — confirmed live: text typed with `gui.type_text()`
    right after either landed nowhere (`entry.text` stayed `""`). Real
    focus only moved via actual Tab key presses; `seek_focus()` in the
    driver walks Tab presses checking `Element.focused` (an AT-SPI state,
    confirmed accurate) until the target reports focused, bounded to 60
    presses.

  Driving split accordingly: push buttons/checkboxes/radio buttons/page
  tabs/menu items go through `Element.click()` alone; entries, spin
  buttons, sliders/dials/scroll bars, lists/trees/tables/calendars, and
  combo boxes go through `seek_focus()` + real keyboard input (a focused
  `QComboBox` changes its current index directly on a plain Down press, no
  popup needed — simpler than the pointer-driven open-popup-then-select
  dance every other platform's driver uses, and avoids relying on a
  popup's own click-to-open working here).

**A real pyguitest bug found and fixed along the way**: `Element.click()`'s
`doActionNamed` call was not bounded the way every other AT-SPI round trip
in `atspi.py` already was (`find_elements`/`extents`/`Element.pid`/etc., all
wrapped in `_run_bounded` since the BSD `BackendCallTimeout` work earlier
in this effort). Confirmed live here: a `doActionNamed` call genuinely hung
mid-run, surviving even a plain `timeout`-sent `SIGTERM` (the call is stuck
in a native GI/D-Bus call that never hands control back to the interpreter —
the same root cause class `_run_bounded`'s own docstring already describes —
and only died to `SIGKILL`). Rather than patch just `click()`, audited the
whole of `atspi.py` for every other direct, unbounded dogtail/GI call and
wrapped each one the same way: `Element.alive`/`focus`/`set_text`/
`do_action`/`select`/`_toggle_expansion`/`choose`/`find`/`is_ancestor_of`/
`_click_by_coordinate`, the `element_at` hit-testing walk (`_at_point`,
`_hits_in`, `_past_a_container`, and `element_at` itself), and the
`AtspiBackend` window methods `windows()`/`active_window()`/
`is_window_viewable()`/`activate_window()`/`geometry()`, plus the
previously-unwrapped `_frame_pid()` helper (which duplicates `Element.pid`'s
own already-bounded read, without the bound). All 135 `test_atspi.py` tests
and the full 2260-test/35058-subtest suite pass after the audit. Parked,
uncommitted, on `P2-atspi-call-timeout` alongside the earlier BSD fixes —
the maintainer reviews and commits once every platform is done.

**A real, repeated AT-SPI stall found but not yet root-caused**: once a
`QMenu` is open, `gui.find_elements(role=MENU_ROLES, ...)` genuinely hangs
inside dogtail's recursive `find_all_descendants` walk, repeatedly, during
both menu discovery and menu-leaf clicking — confirmed via
`faulthandler.dump_traceback_later(25, repeat=True)`, the same
authoritative instrument the original BSD hang was root-caused with. Not
`at-spi2-registryd` CPU bloat (checked live: `0:00` CPU, healthy) the way
BSD's slowdown was — something specific to walking an *open* QMenu's
subtree on this Qt/Wayland/COSMIC build. With the `click()` bounding fix
above, each stall now costs one bounded `BackendCallTimeout` (`self.
_call_timeout`, 20s) instead of hanging forever, and the driver's existing
retry/failure-recording logic absorbs it like any other miss — the run
still reaches a clean, zero-failure result, just slowly (a full run took
somewhere between ~7 and ~25 minutes, dominated by repeated 20s menu
stalls). Left as a known, bounded quirk rather than chased further; nothing
in this app or driver correctness depends on it being fast.

**Result**: `all controls verified`, exit 0, confirmed on 2 consecutive
full runs (every top-level control, all 9 tabs, the entire menu bar).
Driver lives at `~/code/drivers/cosmic.py` (not in any repo,
same convention as the other platform drivers).

### Debian 13: fully clean, 2x confirmed — the "BLOCKED" verdict above was wrong (2026-10-12)

Re-tested after COSMIC proved a box can have broken pointer injection
*and* working keyboard injection at the same time: isolated the two paths
on Debian directly and found exactly that split, confirmed live —
`gui.move_mouse()`+`gui.click()` on "Primary Action" still does nothing
(status stays "Ready", matching the original BLOCKED finding exactly), but
`gui.tap_key("Tab")` genuinely moves real focus (`Element.focused` flips
True after 2 presses) and `gui.type_text()` right after lands real
characters (`entry.text` -> `"hello"`). The original diagnostic work
that led to "BLOCKED" (raw kernel events, udev seat tagging, screen
calibration, a bare-minimum `evdev` device all checking out — see above)
never actually isolated *keyboard* injection from *pointer* injection; it
tested pointer clicks failing and reasonably generalized to "no synthetic
input," which the COSMIC work showed was the wrong
generalization for a libinput/Mutter block of this specific shape.

New driver written, `drivers/debian.py` (pid-based
window matching, like `drivers/linux.py` and unlike COSMIC's
title-based one — this box's `gnomeshell` backend does populate a real
`Window.pid`), porting COSMIC's pointer-free strategy (AT-SPI action
clicks for buttons/tabs/menu items, Tab-seek real-focus keyboard for
everything else) directly. First full run surfaced 4 real failures —
reproduced identically on this maintainer's own Fedora box the same day,
confirming they are genuine, platform-independent bugs in the pointer-free
interaction strategy, not environment flakiness:

- **`QScrollBar` is never reachable via Tab at all** (`seek_focus`
  exhausts its full 60-press budget) — confirmed on both "Horizontal
  Scroll" and "Vertical Scroll", both left showing whatever the
  previously-driven control's stale message was, since no keypress had any
  effect. Fix: skip keyboard entirely for `role == "scroll bar"` and call
  `Element.do_action("Increase")` directly — confirmed live it publishes
  `['Decrease', 'Increase']` and needs no focus at all.
- **A freshly-loaded `QTreeWidget` is collapsed to one root row** — a lone
  `Down` has nothing else to select and never fires a report, confirmed
  live on "Project Tree" (seek_focus *does* succeed here, unlike scroll
  bars — this is a navigation gap, not a focus gap). Fix: send `Right`
  (expand) before `Down`.
- **`role == "table"` covers two widget types with opposite keyboard
  behavior.** A `QTableWidget` (eg "Data Grid") focuses normally via Tab
  and plain `Down` already worked — confirmed by it being absent from the
  original failure list. A `QTableView` (eg "Model Table") is never
  reachable via Tab at all, same symptom as the scroll bars, confirmed via
  `seek_focus` exhausting its budget there specifically. An over-broad
  first fix (unconditional child-cell click for every list/tree/table/
  calendar) silently broke 3 previously-passing `list` controls
  ("Colors"/"Planets"/"Moons") and "Data Grid" by preferring the click path
  even where keyboard already worked — caught by the very next full run,
  not assumed fixed from the isolated probe alone. The real, scoped fix:
  try `seek_focus` first; only when it genuinely fails does `table` fall
  back to finding a child with a published action (a "table cell") and
  clicking it directly — confirmed live this fires the real
  selection-changed signal for "Model Table" with no focus needed at all.
  `list`/`calendar` stay on the original seek_focus+Down path unchanged.

All three fixes are in `interact()`, scoped by the actual discriminating
signal (`seek_focus`'s own success/failure for table, a role-specific key
sequence for tree, a role-specific action for scroll bar) rather than by
role name alone, since role name alone does not reliably predict keyboard
behavior for these three cases. Ported into
`drivers/linux.py` (Fedora — not re-verified there, see above) and
`drivers/cosmic.py` (COSMIC — the changes are a safe superset
of its prior, already-passing behavior: an unconditional `do_action` where
a focus-based path worked fine before, and an extra `Right` press before
`Down` for tree; not yet re-run to confirm neither changed anything there).

**Result**: `all controls verified`, exit 0, confirmed on 2 consecutive
full runs after the fix (every top-level control, all 9 tabs, the entire
menu bar). Driver lives at `~/code/drivers/debian.py`
(not in any repo); the original `the archived debian_pointer driver` (pointer-
based, written when this box was believed blocked) is now superseded and
can be retired.

### Windows: fully clean, 2x confirmed, first attempt (2026-10-12)

A brand-new driver, `drivers/windows.py`, written from scratch —
the old `drivers/windows.py` on the box was coupled to pyguitest-
recorder (capture + script generation, not a plain drive-and-verify
contract) and pre-dated most of the fixes above (its last real
result: 1-9/104 "resemblance", against a stale 104-control app checkout).
App source was stale there too (660-line `app.py` vs the current
729-line one) — synced current, same as every other platform.

**The one platform-specific obstacle, solved before any driver code was
needed**: a plain SSH session cannot drive or even see the real desktop
at all. Confirmed live: `(Get-Process -Id $PID).SessionId` from an SSH
shell answers `0` (the non-interactive "Background"/services session),
while `query session` shows the real interactive desktop as session `1`
(the logged-in user, `Active`). `gui.windows()` run directly over SSH returns
nothing. The fix, found and confirmed live: a **Scheduled Task** created
with `/ru <user>` and *no* `/rp` password forces "Logon Mode: Interactive
only", which correctly lands the launched process in session 1 — `(Get-
Process -Id $PID).SessionId` read back from a process started this way
answers `1`. Every run in this suite therefore goes through
`schtasks /create ... /ru <user> /f` (`/tr` pointing at a small `.bat`
wrapper, not an inline command -- `schtasks /tr` with a quoted, piped
inline command was confirmed live to occasionally kill the whole task
with `STATUS_CONTROL_C_EXIT` before a single line of output; a `.bat`
file read via `/tr "<path-to-bat>"` did not) then `schtasks /run /tn
...`, polling the `.bat`'s own output file over SSH afterward. Re-running
the *same* already-completed one-time task was flaky (killed the app
mid-run, twice); deleting and recreating the task fresh before each run
was reliable both times it was tried.

Structurally, UIA turned out much closer to BSD/Linux's AT-SPI model than
macOS's AX was: `role="menu bar"` is the app's own embedded, window-child
menu bar (not a separate system-wide one, confirmed live by its children
being `File`/`Edit`/`View`/`Tools`/`Help` `"menu item"`s); `role="status
bar"` and `role="page tab"` both work directly with real text via
`.name`; a combo box's stable name is `.name` itself, with `.description`
empty (the opposite of Qt's AT-SPI bridge on Linux/BSD, where the stable
id lives in `.description` instead). `drivers/windows.py` is
consequently a close, direct port of `drivers/bsd.py`'s
structure (pointer+keyboard `interact()`, the same two-pass
discover-then-click `drive_menus()`), not a from-scratch redesign the way
COSMIC's or macOS's pointer-free/AX-specific drivers were.

**One real bug, the same one every other platform already has a fix
for**: "Read Only Field" (`setReadOnly(True)`, by design never reports a
change) was still in the driven set on the very first run, the only
failure out of the whole app — fixed by adding the same `READ_ONLY_FIELDS`
name-exclusion every other platform's driver already carries.

**Result**: `all controls verified`, exit 0, confirmed on 2 consecutive
full runs (the first full run, before the one-line fix above, already
had exactly one failure out of the entire app). Driver lives at
`~/code/drivers/windows.py` (not in any repo); the old recorder-
coupled `drivers/windows.py` is now superseded.

### macOS: fully clean — and a long chase after the wrong suspect (2026-10-13)

Driver written from scratch at `~/code/drivers/macos.py` (the old
`drivers/macos.py` was a primitive, pre-fix script with no
status verification at all). This platform took by far the most
investigation of the five, almost all of it spent on a symptom whose real
cause was somewhere else entirely, so the order below is the order it
actually unfolded — the wrong turns are the useful part.

**The symptom**: whole runs looked like the app had hung. Text fields
stopped reporting partway through, dialogs piled up unclosed on screen,
and the app stayed responsive to *clicks* while ignoring everything typed.

**The wrong suspect** (hours): macOS native panels. A plain SSH session
really does land in launchd's `"Background"` domain rather than `"Aqua"`
(confirmed: `launchctl managername`), and launching the app via `open -a`
really does move it into the Aqua session (confirmed the same way). That
fix is real and is kept -- but it was *not* what made runs fail. Nor was
the stray mounted OpenCore boot CD-ROM, which an earlier reading of
`CarbonCore`/`FileProvider` errors in `log stream` pointed at: those
errors were incidental, the volume is needed to boot this VM, and
`stat`-ing every mounted volume showed none of them matched the device id
the errors named.

**The actual cause**, found by screenshotting the VM mid-run after the
user pointed out that the torture-test app was not even frontmost:

```
'Rich Text': rect=(160,724,883,80) click=(601,764)
    element_at(601,764) -> role='dock item' name='Notes'
```

"Rich Text" is a `QTextEdit` near the bottom of its page. Against an app
window of `(0, 31, 1080, 704)` only 11 pixels of it are visible, and its
*centre* -- the point every driver in this suite clicks -- lands at
y=764, below the window and on top of the **Dock**. `element_at`
resolved that point to the Dock's **Notes** icon. So the driver was
clicking Notes in the Dock: Notes launched, took keyboard focus, and from
that moment every `type_text` went into a Note and every `Escape` meant
for a dialog went to Notes instead, which is why dialogs accumulated and
why the app looked hung while actually being perfectly healthy. A real
Note on that machine had filled up with the word "torture".

Two things made this hard to see, and both are worth remembering:

- `NSWorkspace.frontmostApplication()` and pyguitest's own
  `active_window()` both kept reporting the torture-test app, because the
  *window* was still frontmost and AX tracks windows. Neither answers
  "where do typed keys go", which is a question about the frontmost
  **application's key window**. Every focus check written against those
  two said "fine" while the keys went elsewhere.
- A genuinely separate landmine was found on the way and corrected: this
  box had the bottom-right **hot corner set to Quick Note**
  (`wvous-br-corner = 14`). Measured directly: a pointer move to
  (1279, 799) spawns a `LinkedNotesUIService` panel at window layer 25
  that captures typed text *without* changing the frontmost application.
  It was not what the driver was hitting, but no GUI automation can share
  a machine with it, so it is now disabled (`-int 0`; restore with
  `-int 14`).

**Seven real fixes**, all confirmed live:

1. Status text lives in `.text` on this backend, not `.name`/`.value`/
   `.description` -- every `QLabel` reports empty for all three, including
   the always-populated "controls: N" counter. `Element.text`'s own
   docstring already says so; the first draft reached for `.name` out of
   habit from the Linux/BSD drivers.
2. The main tab bar reports tabs as `role="radio button"` inside a
   `"page tab list"` container -- `role="page tab"` matches nothing here.
3. Spin buttons, sliders and scroll bars never take real keyboard focus
   from a synthetic click (`.focused` stays False), so a following arrow
   key lands nowhere; each publishes `increment`/`decrement` AX actions
   that work with no focus at all.
4. Tree/table/list containers publish only `'raise'` themselves; their
   row/item children carry the real action, so a child click is what fires
   the selection-changed signal.
5. **The Dock click above**: a new `_clickable()` guard clips every click
   point to the app window's own rectangle. This is the direct form of the
   `clip_bottom` guard the Linux and BSD drivers already carry, and it
   also caught five spin buttons on "Text & Numbers" whose centres were at
   y=1004..1156 on an 800px display (scrolled below the fold, clamped by
   `CGEventPost` onto the screen edge).
6. New-window detection now diffs on window **handles**, not
   `(title, pid)` pairs. The three `QMessageBox` leaves
   (Warning/Critical/Question) open dialogs whose title is the empty
   string, back to back, and `windows()` caches the window-server list for
   0.25s -- long enough for a just-dismissed `('', pid)` to still be in
   the "before" set, so the next identical dialog never looked new. Those
   three plus the leaf after them were the last four failures in the run
   before this fix, and every one of them passed in isolation, where the
   extra delay let the cache turn over.
7. `QFileDialog`/`QColorDialog`/`QFontDialog` now pass
   `DontUseNativeDialog` on macOS only (`app.py`), so these exercise Qt's
   own dialogs rather than the XPC-serviced native panels. Kept because it
   is a legitimate app-level choice that keeps every dialog fully testable
   here; Linux/BSD/Windows already use Qt's own dialogs and are untouched.

**Two genuine pyguitest bugs found and fixed** (see its CHANGELOG):

- `macos.activate_window()` ran `AXRaise` and, when that succeeded, never
  called the AppKit application activation. `AXRaise` only reorders a
  window *within* its application; it does not make the application
  frontmost or give it the key window, which is where
  `CGEventPost(kCGHIDEventTap, ...)` actually delivers keys. Both routes
  now run.
- `macos.windows()` dropped any window not at CoreGraphics layer 0, which
  silently excluded every modal dialog: a Qt `QFileDialog` opened app-modal
  reports layer 8 (`NSModalPanelWindowLevel`), on screen, with a real AX
  counterpart. Layer 8 is now accepted alongside 0.

**Result**: `all controls verified`, exit 0. Driver lives at
`~/code/drivers/macos.py` (not in any repo).

## Carried-over history (pre-2026-10-11, from the old private notes)

### Bugs fixed (BSD, proven across multiple full runs)

1. **A single miss used to abort the entire rest of the walk.** `drive()`'s
   tab loop was gated on success; one miss anywhere aborted every
   subsequent tab. Fixed: every `drive_items(...)` call is unconditional,
   failures are recorded but driving continues. *(Note: a narrower version
   of this same bug existed inside `drive_items()` itself — see "RESOLVED"
   below.)*
2. **Menus were never driven at all, on any platform, ever.** New
   `drive_menus()` walks the real menu bar, skips anything that would
   corrupt the harness (Exit, Language, visibility toggles, etc.), and
   verifies dialog-opening leaves the same way toolbar buttons already are.
3. **AT-SPI/dogtail on X11 reports stale, nonzero extents for hidden menu
   items.** Caused a live, real UI-language switch to Japanese mid-run
   before being caught. Fixed with a `_is_showing()` check against AT-SPI's
   own SHOWING state, plus defense-in-depth at the click site.

### RESOLVED: `drive_items()` no longer aborts its own batch on a miss

Re-reading the current driver during today's diagnosis: the top-level fix
(bug 1 above) stopped a miss in one tab from aborting *later* tabs, but
`drive_items()` itself still did `if not drive_one(...): return False`
inside its own loop — so a miss on the *first* control handed to it in any
one batch still abandoned the rest of *that* batch (that tab's, or the
initial pre-tab batch's, remaining controls). Observed live: tab 1's very
first control ("Primary Action") missed while input was broken, and none of
tab 1's other 12 controls were ever attempted as a result. Fixed later the
same session (see "RESOLVED: a real pyguitest hang" above):
`drive_items()` now attempts every item in its batch regardless of an
earlier miss, recording each failure rather than abandoning the rest.

### RESOLVED: 9 menu dialogs never detected (BSD)

Color Picker, Font Picker, File Dialog, Progress/Custom/Wizard/MDI dialogs,
and both About boxes used to consistently report "dialog never appeared"
in a full run — all real leaves, correctly reached and clicked (confirmed
in a live trace). Timeout, pointer dwell, and the click mechanism itself
were each ruled out via isolated tests that succeeded where the full run
failed. A plausible lead (File's "Open…"/"Save As…" leaves skip the
focus-aware dialog dismissal every other dialog leaf gets) was never
actually tested correctly at the time — the attempted fix compared against
the wrong string (`"Open"` vs the real `"Open…"`) and was reverted after
causing a 600s hang regression. **Fixed 2026-10-12** — see "MILESTONE: all
12 known BSD failures fixed" above: all 9 of these were depth-1 direct
children of their top-level menu (unlike the passing dialog items, one
level deeper in a submenu), fixed with a menu-render settle delay plus a
retry-on-miss for the dialog-opening click.

### RESOLVED: Other known gaps

- **BSD "Model Tree"/"Project Tree" misclick**: fixed 2026-10-12, see
  "MILESTONE" above — not a misclick at all; the click and keyboard
  navigation were both landing correctly, but `QTreeView`'s only wired
  signal (`clicked`) never fires from keyboard navigation, so the status
  bar kept showing whatever the previously-driven control last reported.
- **Linux/Debian "Primary Action" first-pointer-click miss**: confirmed
  deterministic pre-tab-fix; not re-tested since, since no live run has
  completed on either box since.
- **macOS "Save As" dialog detection**: `_wait_new_app_window` doesn't see
  the NSSavePanel sheet as a new top-level `AXWindow`. Confirmed safe (no
  orphaned process), just unexercised.
- **Windows `win_loop.py` result-extraction regex**: doesn't match the
  actual driver's stdout/stderr shape, so per-run pass/fail detail isn't
  readable even though the campaign itself runs to completion. Cosmetic,
  not a correctness bug.

## 2026-10-14: recorded and replayed, and what that cost

The fixture was driven on five platforms again, and for the first time the
runs were *recorded* with pyguitest-recorder and the recordings *replayed*.
Recording is only possible where the recorder has a capture backend -- `x11`,
`win32`, `macos` -- so COSMIC, Omarchy and niri cannot be recorded even in
principle, and their drivers click through AT-SPI actions, which emit no
input events for a recorder to see.

| Platform | Driven | Recorded | Replayed |
|---|---|---|---|
| Debian 13 / GNOME | **all controls verified** (17 on tab 1) | n/a | n/a |
| GhostBSD / X11 | all controls verified (13 on tab 1) | 376 events | reached line 576 of 908 |
| Pop!_OS / COSMIC | all controls verified (7 on tab 1) | n/a | n/a |
| Windows 11 / UIA | all controls verified (14 on tab 1) | 771 events | reached line 261 of 1991 |
| macOS 26 / AX | 1 control short | 182 events | not attempted |
| Omarchy / Hyprland | **failed**, 27 interactions | n/a | n/a |

### The verdict line was hiding how much of the fixture ran

Three platforms printed the same `all controls verified` over very different
amounts of the fixture: 17 actable controls on the first tab at 1920x1080,
13 at 1024x768 (GhostBSD, whose X server offers no higher mode), 7 at
1280x800 (COSMIC). `enumerate_controls` drops any expected control whose
rectangle falls below the status bar -- correctly, since a control that is
not on screen cannot be clicked -- and the verdict then covered only what was
left. Five drivers now print `PARTIAL COVERAGE: N expected control(s) are
outside the visible window` beside the count. `drivers/macos.py` structures
that skip differently and was left alone rather than patched blind.

### Omarchy's failure was pyguitest's, and is fixed

27 interactions reported nothing, every one a control reached by Tab-seeking,
each showing the status line of the *previous* control. The cause was one
rung down: Hyprland now parses `hyprctl dispatch` as Lua and rejects the
long-standing `focuswindow address:0x...` form, so `activate_window` had been
failing silently, no window ever held focus, and every key `wtype` sent went
nowhere. pyguitest now speaks the Lua dispatcher API
(`hl.dsp.focus({ window = ... })`) and discovers which form a daemon wants.
Focus was still unobtainable on that session for a separate reason that is
not pyguitest's: **the session was locked.** Omarchy's shell (quickshell)
locks after 300 s idle through its own PAM-backed `ext-session-lock`, and
Hyprland refuses `focusWindow` outright while a session lock is up -- every
`hl.dsp.focus` reply is `ok`, `move` and `resize` through the same channel
work, the window is mapped, visible and `acceptsInput`, and `hyprctl
activewindow` still answers `Invalid`. Nothing in Hyprland's IPC shows the
lock (`hyprctl layers` lists no lock surface, Hyprland's own log is off by
default and only aquamarine's renderer chatter reaches the file) and
`loginctl` reports `LockedHint=no` because quickshell never sets it. The
shell answers directly: `OMARCHY_PATH=/usr/share/omarchy omarchy-shell lock
isLocked`. Same lesson as the Mac -- a locked box looks exactly like a
broken driver -- in a Hyprland costume.

Two driver findings fell out of running against that locked session
(2026-10-15), both fixed in `cosmic.py`, `debian.py` and `linux.py`:

- **`seek_focus` now declines at once when `wait_window_focus` said no.**
  Before, every keyboard-driven control still Tab-walked 60 presses through
  `wtype`, and the run died at the 900 s timeout inside `Choosers`; now it
  finishes in ~9 min with the one WARNING up front and an honest
  `did not report` per keyboard control (28 of them, plus `Save As`, whose
  dialog an unreachable Escape cannot close).
- **The periodic `faulthandler.dump_traceback_later(25, repeat=True)` is
  gone.** It segfaulted the driver: `coredumpctl` put the crashing thread in
  the watchdog, inside libpython, while the main thread sat in
  `pthread_create` -- pyguitest's atspi backend starts a worker thread per
  bounded call, dozens a second, and a GIL-less frame walk on a timer
  eventually lands on one being born (Python 3.14.7; the sixth dump of a
  150 s run; yesterday's run survived 31 by luck). The drivers now
  `faulthandler.enable()` and register `SIGUSR1`, so a run that looks hung
  gets `kill -USR1 <pid>` -- one dump, on request.

**Every driver now acts on `wait_window_focus`'s answer.** It returns a bool
and always had; all six discarded it. Checking it turns this exact condition
from 27 scattered failures into one line saying the window never took
keyboard focus.

### macOS: one control short

`all controls verified` except `Undo History`, which reported the previous
control's status line. The container route is right -- a `QUndoView`
publishes only "raise" and never takes focus -- but clicking its rows does
not move the undo stack through macOS's AX. The driver now skips the row the
selection already sits on (clicking it can emit nothing, which
`drivers/linux.py` learned on the same control); that did not resolve it, and
the remaining cause is unisolated because the control exists only after the
tab walk reaches "Trees & Tables".

### What the recordings proved about the fixture

Checked against `EXPECTED_CONTROLS` and the fixture's source: **no fabricated
names in any of the three recordings.** GhostBSD named 29 distinct things (11
verified controls), Windows 84 (40), macOS 70 (49). The handful that matched
neither list all resolve -- a tab's own description string, Windows' `System`
window menu, two table-cell coordinates, and `Academy Engraved LET`, a font
the macOS font chooser offered. That is a direct, independent check that the
fixture's accessible names are what it claims they are.

### The replays found three real bugs in the recorder

Scopes anchored to a tab bar's name (which Qt publishes as its *selected
tab*), lookups emitted unscoped (so `gui.menu_item("Help")` resolved into
`mate-panel` rather than the fixture), and a window binding that silently
reassigned a scope binding. All three are fixed upstream. Two further
findings were recorded rather than fixed: an accessible-action click on a
modal-opening control deadlocks (AT-SPI "Did not receive a reply";
UIA `0x80131505`), and **a recording made from a machine-speed driver carries
timings too tight to replay** -- the recorder inserts the waits it observed,
and a driver clicking as fast as it can leaves none to observe. Worth knowing
before recording a driver instead of a person.
