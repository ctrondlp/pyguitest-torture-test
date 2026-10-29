"""Self-test for the TortureTest application.

Instantiates the full window headlessly (Qt's offscreen platform) and checks
the invariants the app is built around: the translation table is complete and
used consistently, every interactive control carries a stable, unambiguous
accessible name, the menus/tabs/chrome exist, the themed lists are populated,
and the status-bar feedback channel reports actions.

Run it with::

    python -m unittest discover tests
"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QCoreApplication, QDate, QDateTime, QEvent, QTime
    from PySide6.QtGui import QAccessible, QAction
    from PySide6.QtWidgets import (
        QApplication,
        QCalendarWidget,
        QCheckBox,
        QColumnView,
        QComboBox,
        QCommandLinkButton,
        QDateEdit,
        QDateTimeEdit,
        QDial,
        QDockWidget,
        QDoubleSpinBox,
        QErrorMessage,
        QKeySequenceEdit,
        QLineEdit,
        QListView,
        QListWidget,
        QPlainTextEdit,
        QPushButton,
        QRadioButton,
        QScrollBar,
        QSlider,
        QSpinBox,
        QTabBar,
        QTableView,
        QTableWidget,
        QTabWidget,
        QTextBrowser,
        QTextEdit,
        QTimeEdit,
        QToolBox,
        QToolButton,
        QTreeView,
        QTreeWidget,
        QWidget,
    )
except ImportError as exc:
    raise SystemExit(
        "PySide6 is not installed. Install it first: pip install PySide6"
    ) from exc

from torture_test.app import TortureTestWindow
from torture_test.base import tab_label
from torture_test.i18n import _JA, language, set_language, tr
from torture_test.pages import PAGES
from torture_test.reporting import ACTION_SIGNALS
from torture_test.roles import ROLE_BY_CLASS

# Roles that are decorative rather than acted on: their visible text may
# repeat without making a control ambiguous to a role-scoped lookup.
NON_INTERACTIVE_ROLES = frozenset({"label", "group box"})

# Every control the app exposes, as (accessible name, accessible role). This
# is the complete inventory, not a sample: test_expected_controls_are_present
# asserts each one exists, and test_expected_controls_is_complete asserts the
# app exposes nothing beyond this list. The two chrome buttons Qt adds to a
# dock widget ("Float"/"Close") are deliberately absent -- they are not app
# controls, and they carry no stable name.
EXPECTED_CONTROLS = (
    ("Accept terms and conditions", "check box"),
    ("Account Country", "combo box"),
    ("Account Email Address", "entry"),
    ("Account Full Name", "entry"),
    ("Age", "spin button"),
    ("Alarm Time", "spin button"),
    ("Animated Progress", "progress bar"),
    ("Appointment", "spin button"),
    ("Auto-complete Field", "entry"),
    ("Balance", "slider"),
    ("Biography", "text"),
    ("Calendar", "calendar"),
    ("Calibration Target", "push button"),
    ("Cancel", "push button"),
    ("Canvas", "filler"),
    ("Clear Button Field", "entry"),
    ("Colors", "list"),
    ("Column View", "tree"),
    ("Undo History", "list"),
    ("Country", "combo box"),
    ("Create Account", "push button"),
    ("Data Grid", "table"),
    ("Disabled Action", "push button"),
    ("Documentation", "text"),
    ("Download Progress", "progress bar"),
    ("Email Address", "entry"),
    ("Explore TortureTest", "push button"),
    ("Font", "combo box"),
    ("Frequency Dial", "dial"),
    ("Full Name", "entry"),
    ("Horizontal Scroll", "scroll bar"),
    ("Icon 1", "push button"),
    ("Icon 2", "push button"),
    ("Icon 3", "push button"),
    ("Icon 4", "push button"),
    ("Icon 5", "push button"),
    ("Icon Button", "push button"),
    ("Image Label", "label"),
    ("Indeterminate Busy", "progress bar"),
    ("Inner Button", "push button"),
    ("LCD Counter", "lcd number"),
    ("Look-alike 01", "push button"),
    ("Look-alike 02", "push button"),
    ("Look-alike 03", "push button"),
    ("Look-alike 04", "push button"),
    ("Look-alike 05", "push button"),
    ("Look-alike 06", "push button"),
    ("Look-alike 07", "push button"),
    ("Look-alike 08", "push button"),
    ("Look-alike 09", "push button"),
    ("Look-alike 10", "push button"),
    ("Look-alike 11", "push button"),
    ("Look-alike 12", "push button"),
    ("Masked Field", "entry"),
    ("Menu Button", "push button"),
    ("Model Table", "table"),
    ("Model Tree", "tree"),
    ("Moons", "list"),
    ("Nested Tabs", "page tab list"),
    ("Notes", "text"),
    ("Option A", "radio button"),
    ("Option B", "radio button"),
    ("Option C", "radio button"),
    ("Password", "entry"),
    ("Plan", "combo box"),
    ("Planets", "list"),
    ("Price", "spin button"),
    ("Primary Action", "push button"),
    ("Project Tree", "tree"),
    ("Quantity", "spin button"),
    ("Read Only Field", "entry"),
    ("Receive notifications", "check box"),
    ("Reset Progress", "push button"),
    ("Rich Text", "text"),
    ("Rich Text Label", "label"),
    ("Save", "push button"),
    ("Save All", "push button"),
    ("Save As", "push button"),
    ("Save Copy", "push button"),
    ("Save Draft", "push button"),
    ("Secondary Action", "push button"),
    ("Shortcut Capture", "entry"),
    ("Simple List", "list"),
    ("Splitter", "split pane"),
    ("Stack Page", "combo box"),
    ("Stacked Widget", "filler"),
    ("Standalone Tab Bar", "page tab list"),
    ("Start Date", "spin button"),
    ("Start Progress", "push button"),
    ("Static Label", "label"),
    ("Stepped", "slider"),
    ("Stop Progress", "push button"),
    ("Subscribe to the newsletter", "check box"),
    ("Toggle Me", "push button"),
    ("Tool Box", "layered pane"),
    ("Tool Button", "push button"),
    ("Tool One", "push button"),
    ("Tool Three", "push button"),
    ("Tool Two", "push button"),
    ("Toolbar Zoom", "combo box"),
    ("Tri-state option", "check box"),
    ("Tuning Dial", "dial"),
    ("Vertical Progress", "progress bar"),
    ("Vertical Scroll", "scroll bar"),
    ("Volume", "slider"),
)


class TranslationTest(unittest.TestCase):
    """The English/Japanese translation table and lookup function."""

    def tearDown(self) -> None:
        """Restore English between tests."""
        set_language("en")

    def test_every_key_has_a_nonempty_value(self) -> None:
        """No translation value may be blank."""
        empty = [key for key, value in _JA.items() if not value]
        self.assertEqual(empty, [])

    def test_table_is_substantial(self) -> None:
        """The table covers the whole interface, not a stub."""
        self.assertGreater(len(_JA), 300)

    def test_tr_returns_english_by_default(self) -> None:
        """English is the identity language."""
        set_language("en")
        self.assertEqual(tr("Primary Action"), "Primary Action")

    def test_tr_maps_to_japanese(self) -> None:
        """A lookup returns its Japanese value."""
        set_language("ja")
        self.assertEqual(tr("Primary Action"), "主要アクション")

    def test_japanese_title_is_neutral(self) -> None:
        """The Japanese app name avoids the word torture."""
        set_language("ja")
        title = tr("TortureTest")
        self.assertNotIn("拷問", title)
        self.assertEqual(title, "コントロールテスト")

    def test_tr_falls_back_to_the_key(self) -> None:
        """An unknown key degrades to English rather than vanishing."""
        set_language("ja")
        self.assertEqual(tr("Not In The Table"), "Not In The Table")

    def test_unknown_language_falls_back_to_english(self) -> None:
        """An unsupported language code selects English."""
        set_language("xx")
        self.assertEqual(language(), "en")


class WindowTest(unittest.TestCase):
    """The fully-constructed main window and its controls."""

    @classmethod
    def setUpClass(cls) -> None:
        """Build one shared offscreen application and window."""
        set_language("en")
        cls.app = QApplication.instance() or QApplication([])
        cls.window = TortureTestWindow()

    @classmethod
    def tearDownClass(cls) -> None:
        """Close the window."""
        cls.window.close()

    def setUp(self) -> None:
        """Reset to English before each test."""
        set_language("en")

    def _is_toolkit_chrome(self, widget: QWidget) -> bool:
        """Whether `widget` is Qt's own chrome rather than an app control.

        Chrome is excluded from the inventory by an explicit test, never by
        happening to fall outside `ROLE_BY_CLASS` -- see
        `test_every_named_widget_has_a_known_role` for why that distinction
        matters.
        """
        if isinstance(widget.parent(), QTabBar):
            # Qt's own tab-bar scroll buttons ("Scroll Left"/"Scroll Right")
            # are chrome, not app controls, and repeat once per tab bar --
            # they are outside the app's naming contract.
            return True
        # The two buttons Qt adds to a QDockWidget's title bar. They carry no
        # stable name (Qt sets "Float"/"Close" itself) and are not app
        # controls, which is why EXPECTED_CONTROLS has no entry for them.
        return isinstance(widget.parent(), QDockWidget)

    def _named_widgets(self) -> list[tuple[str, str]]:
        """Every app control that carries an accessible name, as (name, role)."""
        result = []
        for widget in self.window.findChildren(QWidget):
            if self._is_toolkit_chrome(widget):
                continue
            name = widget.accessibleName()
            role = ROLE_BY_CLASS.get(type(widget))
            if name and role:
                result.append((name, role))
        return result

    def test_naming_a_combo_box_with_a_description_is_refused(self) -> None:
        """`named()` refuses the one combination that silently breaks lookup.

        Qt publishes a combo box's current text as its accessible name, so
        the description carries the stable id -- a caller-supplied
        description would overwrite it and leave the control findable by
        neither. Guarded here because nothing in the app does it today, so
        only a test keeps the guard honest.
        """
        from torture_test.base import named

        box = QComboBox()
        with self.assertRaises(ValueError):
            named(box, "Country", "pick one")
        # The non-combo path still accepts a description.
        line = named(QLineEdit(), "Full Name", "as it appears on your card")
        self.assertEqual(line.accessibleName(), "Full Name")
        self.assertEqual(line.accessibleDescription(), "as it appears on your card")
        # And a combo box without one keeps its stable id in the description.
        plain = named(QComboBox(), "Country")
        self.assertEqual(plain.accessibleDescription(), "Country")

    def test_naming_a_tab_bar_puts_the_stable_id_in_the_description(self) -> None:
        """A tab bar carries its stable id in the description, like a combo.

        Qt's accessibility bridge publishes a tab bar's *selected tab* text as
        the accessible name and discards ``setAccessibleName``, so -- as for a
        combo box -- the stable identifier has to live in the description. A
        ``QTabWidget``'s page-tab-list node is its child ``QTabBar``, so the
        description lands there, and without a name: a named child would
        publish a second ``page tab list`` and duplicate the container.

        Qt's AT-SPI bridge does not in fact surface a tab bar's description
        either (see ``named``), so this guards the construction-time intent --
        the right slot, on the right node, and an explicit description refused
        -- and the macOS AX / Windows UIA backends that may read it, not an
        AT-SPI capability this cannot deliver.
        """
        from torture_test.base import named

        bar = named(QTabBar(), "Standalone Tab Bar")
        self.assertEqual(bar.accessibleName(), "Standalone Tab Bar")
        self.assertEqual(bar.accessibleDescription(), "Standalone Tab Bar")

        tabs = named(QTabWidget(), "Nested Tabs")
        self.assertEqual(tabs.accessibleName(), "Nested Tabs")
        self.assertEqual(tabs.tabBar().accessibleDescription(), "Nested Tabs")
        # No name on the child, or the inventory would count it twice.
        self.assertEqual(tabs.tabBar().accessibleName(), "")

        with self.assertRaises(ValueError):
            named(QTabBar(), "Standalone Tab Bar", "a description")
        with self.assertRaises(ValueError):
            named(QTabWidget(), "Nested Tabs", "a description")

    def test_every_named_widget_has_a_known_role(self) -> None:
        """No named app control is missing from `ROLE_BY_CLASS`.

        `_named_widgets` -- and so `test_expected_controls_is_complete`,
        which is the guard against inventory drift -- skips any widget whose
        class has no role mapping. Without this test that skip is silent: a
        new named control of an unmapped class would be invisible to the
        completeness check, pass every test, and then be missed by the
        platform drivers, which drive `EXPECTED_CONTROLS`. Role-mapped or
        explicitly chrome; nothing in between.
        """
        unmapped = sorted(
            {
                f"{type(w).__name__} {w.accessibleName()!r}"
                for w in self.window.findChildren(QWidget)
                if w.accessibleName()
                and not self._is_toolkit_chrome(w)
                and type(w) not in ROLE_BY_CLASS
            }
        )
        self.assertEqual(
            unmapped,
            [],
            "named control(s) with no ROLE_BY_CLASS entry: add the class to "
            "torture_test/roles.py, or exclude it in _is_toolkit_chrome",
        )

    def _find(self, name: str, role: str) -> QWidget | None:
        """Return the widget named `name` that also plays `role`."""
        for widget in self.window.findChildren(QWidget):
            if (
                widget.accessibleName() == name
                and ROLE_BY_CLASS.get(type(widget)) == role
            ):
                return widget
        return None

    def _flush(self) -> None:
        """Process pending events, including deferred deletions.

        `deleteLater()` defers deletion to the event loop, and
        `QApplication.processEvents()` does not deliver the deferred-delete
        event itself, so a rebuild can leave its old pages in the tree. This
        flushes them explicitly so a rebuilt window reports only the new pages.
        """
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def _act(self, widget: QWidget) -> bool:
        """Drive `widget`'s action signal, mirroring `reporting.ACTION_SIGNALS`.

        Returns False for a widget this helper does not know how to drive, so
        the caller can distinguish "not actable" from "actable but broken".
        """
        if isinstance(widget, (QPushButton, QToolButton, QCommandLinkButton)):
            if (
                isinstance(widget, QToolButton)
                and widget.menu() is not None
                and widget.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
            ):
                # An InstantPopup tool button opens its menu on click, which
                # grabs the keyboard and -- on the offscreen platform, e.g.
                # FreeBSD -- hangs. Emit the signal the reporter wires to
                # instead of opening the menu.
                widget.clicked.emit()
            else:
                widget.click()
        elif isinstance(widget, (QCheckBox, QRadioButton)):
            widget.click()
        elif isinstance(widget, QLineEdit):
            mask = widget.inputMask()
            if mask:
                # A masked field rejects characters the mask does not allow, so
                # write a value that fills every digit placeholder ("9"/"0")
                # while keeping the mask's literals.
                widget.setText("".join("1" if ch in "90" else ch for ch in mask))
            else:
                widget.setText("torture")
        elif isinstance(widget, (QPlainTextEdit, QTextEdit, QTextBrowser)):
            widget.setPlainText("torture")
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.setValue(
                widget.minimum()
                if widget.value() == widget.maximum()
                else widget.value() + 1
            )
        elif isinstance(widget, QDateEdit):
            widget.setDate(QDate(2000, 1, 1))
        elif isinstance(widget, QTimeEdit):
            widget.setTime(QTime(1, 2, 3))
        elif isinstance(widget, QDateTimeEdit):
            widget.setDateTime(QDateTime(QDate(2000, 1, 1), QTime(1, 2, 3)))
        elif isinstance(widget, QKeySequenceEdit):
            widget.setKeySequence("Ctrl+Shift+K")
        elif isinstance(widget, QComboBox):
            if not widget.count():
                return False
            widget.setCurrentIndex((widget.currentIndex() + 1) % widget.count())
        elif isinstance(widget, QListWidget):
            if not widget.count():
                return False
            widget.setCurrentRow((widget.currentRow() + 1) % widget.count())
        elif isinstance(widget, QTreeWidget):
            if not widget.topLevelItemCount():
                return False
            items = [widget.topLevelItem(i) for i in range(widget.topLevelItemCount())]
            current = widget.currentItem()
            nxt = (
                items[(items.index(current) + 1) % len(items)]
                if current in items
                else items[0]
            )
            widget.setCurrentItem(nxt)
        elif isinstance(widget, (QListView, QTreeView, QTableView, QColumnView)):
            # The model/view widgets report only their *mouse* `clicked`
            # signal, which a programmatic selection does not emit -- so emit
            # it directly, to exercise the reporting wiring.
            model = widget.model()
            if model is None or not model.rowCount():
                return False
            widget.clicked.emit(model.index(0, 0))
        elif isinstance(widget, QTableWidget):
            if not (widget.rowCount() and widget.columnCount()):
                return False
            widget.cellClicked.emit(0, 0)
        elif isinstance(widget, QCalendarWidget):
            widget.setSelectedDate(QDate(2000, 1, 1))
        elif isinstance(widget, (QSlider, QDial, QScrollBar)):
            widget.setValue(
                widget.minimum()
                if widget.value() == widget.maximum()
                else widget.value() + 1
            )
        elif isinstance(widget, (QTabWidget, QTabBar, QToolBox)):
            if not widget.count():
                return False
            widget.setCurrentIndex((widget.currentIndex() + 1) % widget.count())
        else:
            return False
        return True

    def test_window_title(self) -> None:
        """The window title comes from the translation table."""
        self.assertEqual(self.window.windowTitle(), tr("TortureTest"))

    def test_all_pages_are_present(self) -> None:
        """Every tab page is created with its translated title."""
        tabs = self.window._tabs
        self.assertEqual(tabs.count(), len(PAGES))
        for index, page_cls in enumerate(PAGES):
            # The label carries doubled ampersands; `tab_label` says why.
            self.assertEqual(tabs.tabText(index), tab_label(tr(page_cls.title)))

    def test_the_error_message_dialog_is_offered_and_is_the_stateful_kind(
        self,
    ) -> None:
        """Tools offers `QErrorMessage`, and it is the dialog it claims to be.

        It sits beside the `QMessageBox` family and would be redundant with
        it but for one thing: it is *stateful*, carrying its own "Show this
        message again" check box that suppresses the exact message string
        for the rest of the process once unticked. That check box is the
        whole reason the fixture contains this dialog, so the test asserts
        it is there rather than just that a dialog appeared.

        Also asserts it reappears when shown repeatedly. The drivers re-click
        a menu item once when the first click produced no dialog, and a
        suppressed second showing would read as "dialog never appeared" --
        a false failure. Dismissing leaves the box ticked, so it does not.
        """
        actions = [
            a
            for a in self.window.findChildren(QAction)
            if "Error Message" in (a.text() or "")
        ]
        self.assertEqual(
            len(actions), 1, "expected exactly one Error Message menu action"
        )

        try:
            for attempt in (1, 2):
                self.window._error_message()
                self.app.processEvents()
                shown = [
                    w
                    for w in QApplication.topLevelWidgets()
                    if isinstance(w, QErrorMessage) and w.isVisible()
                ]
                self.assertEqual(
                    len(shown), 1, f"attempt {attempt}: expected one visible dialog"
                )
                dialog = shown[0]
                self.assertTrue(
                    dialog.isModal(),
                    "it must be modal, like the QMessageBox family beside it",
                )
                self.assertTrue(
                    dialog.findChildren(QCheckBox),
                    "no 'show this message again' check box, which is the "
                    "only thing distinguishing this from a QMessageBox",
                )
                self.assertIn(
                    "Error message shown", self.window._status_message.text()
                )
                dialog.close()
                self.app.processEvents()
        finally:
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QErrorMessage):
                    w.close()
            self.app.processEvents()

    def test_tab_accessible_names_keep_their_ampersands(self) -> None:
        """A tab publishes the accessible name its title declares.

        Queries the *accessible interface* rather than
        `QWidget.accessibleName()`, which is the only way to see this:
        Qt reads a single `&` in visible text as a mnemonic marker and
        strips it from the published name, while `tabText()` goes on
        reporting the ampersand. Four tab titles contain one, so before
        `tab_label` existed every one of them published a name with the
        ampersand gone and a doubled space in its place -- a string whose
        defect is invisible on review, and which pyguitest-recorder
        faithfully wrote into generated scripts on both macOS and Windows.
        """
        bar = self.window._tabs.tabBar()
        iface = QAccessible.queryAccessibleInterface(bar)
        self.assertIsNotNone(iface, "the tab bar publishes no accessible interface")
        published = {}
        for index in range(iface.childCount()):
            child = iface.child(index)
            if child is None:
                continue
            name = child.text(QAccessible.Text.Name)
            if name:
                published[name] = index
        for page_cls in PAGES:
            want = tr(page_cls.title)
            self.assertIn(
                want,
                published,
                f"tab {want!r} publishes no such accessible name; "
                f"published names are {sorted(published)}",
            )
            self.assertNotIn(
                "  ",
                want,
                "a doubled space here would mean the title itself is wrong",
            )

    def test_menu_bar_has_all_menus(self) -> None:
        """The five top-level menus are present."""
        titles = [action.text() for action in self.window.menuBar().actions()]
        for expected in ("&File", "&Edit", "&View", "&Tools", "&Help"):
            self.assertIn(tr(expected), titles)

    def test_toolbar_dock_and_status_bar_exist(self) -> None:
        """The toolbar, dock and status bar are built."""
        self.assertIsNotNone(self.window._toolbar)
        self.assertIsNotNone(self.window._dock)
        self.assertIsNotNone(self.window.statusBar())

    def test_no_ambiguous_control_names(self) -> None:
        """No two actable controls of one role share a name."""
        by_role: dict[str, list[str]] = {}
        for name, role in self._named_widgets():
            if role in NON_INTERACTIVE_ROLES:
                continue
            by_role.setdefault(role, []).append(name)
        duplicates = {
            role: sorted({name for name in names if names.count(name) > 1})
            for role, names in by_role.items()
            if len(names) != len(set(names))
        }
        self.assertEqual(duplicates, {})

    def test_control_inventory_is_comprehensive(self) -> None:
        """The app exposes a large, role-complete inventory."""
        widgets = self._named_widgets()
        self.assertGreaterEqual(len(widgets), 100)
        roles = {role for _, role in widgets}
        for expected in (
            "push button",
            "check box",
            "radio button",
            "entry",
            "text",
            "spin button",
            "combo box",
            "list",
            "tree",
            "table",
            "progress bar",
            "slider",
            "dial",
            "page tab list",
        ):
            self.assertIn(expected, roles)

    def test_expected_controls_are_present(self) -> None:
        """Every control in the inventory exists by role and name."""
        self.assertTrue(EXPECTED_CONTROLS)
        self.assertEqual(
            len(EXPECTED_CONTROLS), len(set(EXPECTED_CONTROLS)),
            "the inventory lists a control twice",
        )
        for name, role in EXPECTED_CONTROLS:
            self.assertIsNotNone(self._find(name, role), f"missing: {name}")

    def test_expected_controls_is_complete(self) -> None:
        """The inventory is exactly the controls the app exposes.

        Guards against drift in both directions: a control added to the app
        but not to EXPECTED_CONTROLS, or one listed but since removed.
        """
        actual = sorted(self._named_widgets())
        self.assertEqual(actual, sorted(EXPECTED_CONTROLS))

    def test_themed_lists_are_populated(self) -> None:
        """The color/planet/moon lists hold their items."""
        for name, expected in (("Colors", 6), ("Planets", 8), ("Moons", 6)):
            widget = self._find(name, "list")
            self.assertIsNotNone(widget, f"missing list: {name}")
            self.assertEqual(widget.count(), expected, f"{name} item count")

    def test_status_bar_reports_a_button_click(self) -> None:
        """The status bar reports a programmatic click."""
        button = self._find("Primary Action", "push button")
        self.assertIsNotNone(button)
        button.click()
        self.assertIn("Primary Action", self.window._status_message.text())

    def test_every_actable_control_reports_its_action(self) -> None:
        """Driving every actable control lands a status-bar message.

        Walks the whole window, drives each widget that `reporting.py` wires a
        signal to, and asserts the status bar echoes that widget's accessible
        name back. This is the app's whole point: a test must be able to
        assert an interaction landed by reading the status bar, for every
        control type, not just a button.
        """
        touched = 0
        missing = []
        for widget in self.window.findChildren(QWidget):
            if isinstance(widget.parent(), QTabBar):
                continue
            if type(widget) not in ACTION_SIGNALS:
                continue
            if not widget.accessibleName():
                continue
            if not widget.isEnabled():
                continue
            if not self._act(widget):
                continue
            self.app.processEvents()
            message = self.window._status_message.text()
            if widget.accessibleName() not in (message or ""):
                missing.append(
                    f"{type(widget).__name__} "
                    f"{widget.accessibleName()!r} -> {message!r}"
                )
            touched += 1
        self.assertGreaterEqual(touched, 85, f"only touched {touched} controls")
        self.assertEqual(missing, [])

    def test_language_switch_rebuilds(self) -> None:
        """Switching language rebuilds text while names stay stable."""
        self.window._set_language("ja")
        self._flush()
        self.assertEqual(self.window.windowTitle(), tr("TortureTest"))
        self.assertEqual(self.window._tabs.count(), len(PAGES))
        button = self._find("Primary Action", "push button")
        self.assertIsNotNone(button)
        self.assertEqual(button.text(), tr("Primary Action"))
        self.assertEqual(button.accessibleName(), "Primary Action")
        self.window._set_language("en")
        self._flush()
        self.assertEqual(self.window.windowTitle(), "TortureTest")


def main() -> int:
    """Run the self-test suite and return a process exit status."""
    suite = unittest.main(verbosity=2, exit=False)
    return 0 if suite.result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
