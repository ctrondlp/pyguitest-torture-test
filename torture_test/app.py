"""The TortureTest main window: menus, toolbar, status bar, dock and dialogs.

This module assembles the window that hosts every tab page, and wires the
menus, toolbar, status bar, dock widget and demo dialogs around them. The
result is a complete, if deliberately pointless, desktop application whose
only job is to be found and driven by pyguitest.
"""

from __future__ import annotations

import contextlib
import os
import sys
import weakref

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QColumnView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QErrorMessage,
    QFileDialog,
    QFontDialog,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMdiArea,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QStyle,
    QTableView,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QToolButton,
    QTreeView,
    QUndoView,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from .base import standard_icon, tab_label
from .i18n import language, set_language, tr
from .pages import PAGES
from .reporting import ACTION_SIGNALS, action_verb, value_suffix
from .roles import role_of
from .theme import DARK, LIGHT, stylesheet


class TortureTestWindow(QMainWindow):
    """The TortureTest application window."""

    def __init__(self) -> None:
        """Assemble the window: menus, toolbar, status bar, dock and dialogs."""
        super().__init__()
        self.setWindowTitle(tr("TortureTest"))
        self.resize(1080, 760)
        self._dark = False
        self._point_size = 12
        self._show_status = True
        self._show_toolbar = True
        self._show_dock = True
        self._wired: weakref.WeakSet = weakref.WeakSet()
        # Widgets whose action signals are already connected to the reporter.
        # Weak by object identity, deliberately not a set of id(): Python
        # reuses id() once a deleted widget's wrapper is collected, so an
        # id-keyed set could silently skip wiring a *new* control whose
        # address collided with a dead one's -- measured live, a button click
        # after a language-switch rebuild intermittently reported nothing.
        self._build_central()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._build_dock()
        # Deferred for two reasons, both measured. It used to be counted
        # inside _build_status_bar, which runs before _build_dock, so the
        # dock's own widgets were never included and the figure read 693
        # where findChildren() said 701. Counting here instead fixed that
        # but still read 700: a widget or two is not constructed until the
        # event loop has turned once. A zero-timer counts after it has.
        QTimer.singleShot(0, self._refresh_status_count)
        self._apply_theme()
        self._wire_action_reporting()
        self._status_message.setText(tr("Ready"))

    # -- assembly ----------------------------------------------------------

    def _build_central(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setObjectName("mainTabs")
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)
        for page_cls in PAGES:
            self._tabs.addTab(page_cls(), tab_label(tr(page_cls.title)))

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("&File"))
        file_menu.addAction(
            self._make_action(
                "&New Window", self._new_window, QKeySequence.StandardKey.New
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(
            self._make_action("&Open…", self._file_open, QKeySequence.StandardKey.Open)
        )
        file_menu.addAction(
            self._make_action(
                "&Save As…", self._file_save_as, QKeySequence.StandardKey.SaveAs
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(
            self._make_action("E&xit", self.close, QKeySequence.StandardKey.Quit)
        )

        edit_menu = menubar.addMenu(tr("&Edit"))
        edit_menu.addAction(
            self._make_action(
                "&Undo", lambda: self._edit("undo"), QKeySequence.StandardKey.Undo
            )
        )
        edit_menu.addAction(
            self._make_action(
                "&Redo", lambda: self._edit("redo"), QKeySequence.StandardKey.Redo
            )
        )
        edit_menu.addSeparator()
        edit_menu.addAction(
            self._make_action(
                "Cu&t", lambda: self._edit("cut"), QKeySequence.StandardKey.Cut
            )
        )
        edit_menu.addAction(
            self._make_action(
                "&Copy", lambda: self._edit("copy"), QKeySequence.StandardKey.Copy
            )
        )
        edit_menu.addAction(
            self._make_action(
                "&Paste", lambda: self._edit("paste"), QKeySequence.StandardKey.Paste
            )
        )
        edit_menu.addSeparator()
        edit_menu.addAction(
            self._make_action(
                "Select &All",
                lambda: self._edit("selectAll"),
                QKeySequence.StandardKey.SelectAll,
            )
        )

        view_menu = menubar.addMenu(tr("&View"))
        view_menu.addAction(
            self._make_action(
                "&Reset Demo Controls", self._reset_pages, QKeySequence("Ctrl+R")
            )
        )
        view_menu.addSeparator()
        self._status_action = self._make_action(
            "Show &Status Bar",
            self._toggle_status_bar,
            checkable=True,
            checked=self._show_status,
        )
        self._toolbar_action = self._make_action(
            "Show &Tool Bar",
            self._toggle_toolbar,
            checkable=True,
            checked=self._show_toolbar,
        )
        self._dock_action = self._make_action(
            "Show &Tool Palette",
            self._toggle_dock,
            checkable=True,
            checked=self._show_dock,
        )
        self._dark_action = self._make_action(
            "&Dark Theme", self._set_dark, checkable=True, checked=self._dark
        )
        view_menu.addAction(self._status_action)
        view_menu.addAction(self._toolbar_action)
        view_menu.addAction(self._dock_action)
        view_menu.addAction(self._dark_action)
        view_menu.addSeparator()
        view_menu.addAction(
            self._make_action(
                "Zoom &In", self._zoom_in, QKeySequence.StandardKey.ZoomIn
            )
        )
        view_menu.addAction(
            self._make_action(
                "Zoom &Out", self._zoom_out, QKeySequence.StandardKey.ZoomOut
            )
        )
        view_menu.addAction(
            self._make_action("&Reset Zoom", self._reset_zoom, QKeySequence("Ctrl+0"))
        )
        view_menu.addSeparator()
        language_menu = view_menu.addMenu(tr("Language"))
        lang_en = self._make_action(
            "English",
            lambda: self._set_language("en"),
            checkable=True,
            checked=(language() == "en"),
        )
        lang_ja = self._make_action(
            "日本語",
            lambda: self._set_language("ja"),
            checkable=True,
            checked=(language() == "ja"),
        )
        lang_group = QActionGroup(self)
        lang_group.addAction(lang_en)
        lang_group.addAction(lang_ja)
        language_menu.addAction(lang_en)
        language_menu.addAction(lang_ja)

        tools_menu = menubar.addMenu(tr("&Tools"))
        messages = tools_menu.addMenu(tr("Message &Boxes"))
        messages.addAction(
            self._make_action(
                "&Information", lambda: self._message_box(QMessageBox.Icon.Information)
            )
        )
        messages.addAction(
            self._make_action(
                "&Warning", lambda: self._message_box(QMessageBox.Icon.Warning)
            )
        )
        messages.addAction(
            self._make_action(
                "&Critical", lambda: self._message_box(QMessageBox.Icon.Critical)
            )
        )
        messages.addAction(
            self._make_action(
                "&Question", lambda: self._message_box(QMessageBox.Icon.Question)
            )
        )
        messages.addSeparator()
        messages.addAction(self._make_action("&Error Message", self._error_message))
        inputs = tools_menu.addMenu(tr("&Input Dialogs"))
        inputs.addAction(
            self._make_action("Get &Text", lambda: self._input_dialog("text"))
        )
        inputs.addAction(
            self._make_action("Get &Integer", lambda: self._input_dialog("int"))
        )
        inputs.addAction(
            self._make_action("Get &Item", lambda: self._input_dialog("item"))
        )
        tools_menu.addSeparator()
        tools_menu.addAction(self._make_action("&Color Picker…", self._color_dialog))
        tools_menu.addAction(self._make_action("&Font Picker…", self._font_dialog))
        tools_menu.addAction(self._make_action("&File Dialog…", self._file_open))
        tools_menu.addSeparator()
        tools_menu.addAction(
            self._make_action("&Progress Dialog…", self._progress_dialog)
        )
        tools_menu.addAction(self._make_action("&Custom Dialog…", self._custom_dialog))
        tools_menu.addAction(self._make_action("&Wizard…", self._wizard))
        tools_menu.addAction(self._make_action("&MDI Workspace…", self._mdi_workspace))
        tools_menu.addSeparator()
        slow_menu = tools_menu.addMenu(tr("Slow &Dialog"))
        slow_menu.addAction(self._make_action("1 second", lambda: self._slow_dialog(1)))
        slow_menu.addAction(
            self._make_action("3 seconds", lambda: self._slow_dialog(3))
        )
        slow_menu.addAction(
            self._make_action("5 seconds", lambda: self._slow_dialog(5))
        )
        slow_menu.addAction(
            self._make_action("10 seconds", lambda: self._slow_dialog(10))
        )
        slow_menu.addAction(self._make_action("Custom…", self._slow_dialog_custom))

        help_menu = menubar.addMenu(tr("&Help"))
        help_menu.addAction(self._make_action("&About TortureTest…", self._about))
        help_menu.addAction(self._make_action("About &Qt…", self._about_qt))
        help_menu.addSeparator()
        help_menu.addAction(self._make_action("&Dump Controls", self._dump_controls))

    def _build_toolbar(self) -> None:
        self._toolbar = QToolBar(tr("Main Toolbar"), self)
        self._toolbar.setObjectName("mainToolbar")
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)

        new_action = self._make_action("New Window", self._new_window)
        new_action.setIcon(standard_icon(QStyle.StandardPixmap.SP_FileIcon))
        open_action = self._make_action("Open…", self._file_open)
        open_action.setIcon(standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton))
        save_action = self._make_action("Save As…", self._file_save_as)
        save_action.setIcon(standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton))
        reset_action = self._make_action("Reset Demo Controls", self._reset_pages)
        reset_action.setIcon(standard_icon(QStyle.StandardPixmap.SP_BrowserReload))
        about_action = self._make_action("About TortureTest", self._about)
        about_action.setIcon(
            standard_icon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        )

        self._toolbar.addAction(new_action)
        self._toolbar.addAction(open_action)
        self._toolbar.addAction(save_action)
        self._toolbar.addSeparator()
        self._toolbar.addAction(reset_action)
        self._toolbar.addSeparator()
        self._toolbar_combo = QComboBox()
        self._toolbar_combo.setAccessibleName("Toolbar Zoom")
        # Qt's accessibility bridge publishes a combo box's *current text* as
        # its accessible name and discards setAccessibleName -- see base.py's
        # named() helper. Every other combo box in the app goes through that
        # helper and gets setAccessibleDescription("...") for free; this one
        # is built inline and was missing it, leaving "Toolbar Zoom"
        # unreachable over AT-SPI.
        self._toolbar_combo.setAccessibleDescription("Toolbar Zoom")
        self._toolbar_combo.addItems(["100%", "125%", "150%"])
        self._toolbar_combo.currentIndexChanged.connect(self._toolbar_zoom)
        self._toolbar.addWidget(self._toolbar_combo)
        self._toolbar.addSeparator()
        self._toolbar.addAction(about_action)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        # A plain QLabel we own and update directly, not QStatusBar's own
        # showMessage()/currentMessage() mechanism. Confirmed live (Debian
        # 13, GNOME/Wayland): the widget showMessage() paints its temporary
        # text into is not exposed to accessibility at all on this Qt build
        # -- it reports role "unknown" with an empty name, description, and
        # text, even immediately after a real message was shown. A test
        # reading Qt's own currentMessage() (as this app's former self-test
        # did) never caught this, since that API works fine internally; only
        # the *accessible* exposure of that same text was broken. A plain
        # QLabel added normally is a completely ordinary accessible widget
        # -- the adjacent "controls: N" counter label already proved this,
        # reporting correctly as role "label" with a real name throughout.
        self._status_message = QLabel()
        self._status_message.setObjectName("statusMessage")
        bar.addWidget(self._status_message, 1)
        self._status_count = QLabel()
        self._status_count.setObjectName("statusControlCount")
        bar.addPermanentWidget(self._status_count)

    def _build_dock(self) -> None:
        self._dock = QDockWidget(tr("Tool Palette"), self)
        self._dock.setObjectName("toolPalette")
        self._dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        palette = QWidget()
        box = QVBoxLayout(palette)
        for label in ("Tool One", "Tool Two", "Tool Three"):
            button = QToolButton()
            button.setText(tr(label))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIcon(standard_icon(QStyle.StandardPixmap.SP_FileIcon))
            button.setAccessibleName(label)
            box.addWidget(button)
        box.addStretch(1)
        self._dock.setWidget(palette)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock)

    def _make_action(
        self,
        text: str,
        slot: object,
        shortcut: QKeySequence | QKeySequence.StandardKey | None = None,
        checkable: bool = False,
        checked: bool = False,
    ) -> QAction:
        action = QAction(tr(text), self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.setCheckable(checkable)
        if checkable:
            action.setChecked(checked)
        action.triggered.connect(slot)
        return action

    def _refresh_status_count(self) -> None:
        """Update the status bar's live control count.

        Flushes pending deletions before counting, rather than trusting a
        timer to have outlasted them. `removeTab()`/`deleteLater()` and the
        stale-object sweep in `_rebuild_ui` both defer their deletions to
        the event loop, and `findChildren()` happily counts an object that
        is queued for deletion but not yet gone -- measured at 1354 against
        a true 701 immediately after a rebuild, and still eight to ten over
        when read from a zero-timer. Draining the queue first makes the
        figure deterministic instead of a race.
        """
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        count = len(self.findChildren(QWidget))
        self._status_count.setText(f"{tr('controls')}: {count}")

    # -- status-bar feedback ------------------------------------------------

    def _report(self, message: str) -> None:
        """Show `message` in the status bar."""
        self._status_message.setText(message)

    # The model/view-only widgets (as opposed to their QTreeWidget/
    # QTableWidget/QListWidget siblings, which inherit from these and are
    # NOT meant to match here -- exact type below, not isinstance).
    # ACTION_SIGNALS wires each one to "clicked" alone, a real mouse click
    # that never fires from keyboard-only navigation (Down/Up/...): a tree
    # widget's own "itemSelectionChanged" and a table widget's own
    # "cellClicked" both exist directly on the widget, but the plain view
    # classes expose the equivalent only one layer down, on their
    # *selection model* -- QAbstractItemView has no such signal of its own
    # to put in ACTION_SIGNALS. Confirmed live (GhostBSD): "Model Tree"
    # correctly took keyboard focus after being clicked, and Down correctly
    # moved its current row, but nothing reported it -- the status bar kept
    # showing whatever the previously-driven control's own report was.
    _VIEW_ONLY_CLASSES = (QTreeView, QTableView, QListView, QColumnView, QUndoView)

    def _wire_action_reporting(self) -> None:
        """Connect every control's action signals to the status-bar reporter."""
        for widget in self.findChildren(QWidget):
            if widget in self._wired:
                continue
            for signal_name in ACTION_SIGNALS.get(type(widget), ()):
                getattr(widget, signal_name).connect(
                    lambda *_, w=widget, s=signal_name: self._report_action(w, s)
                )
            if type(widget) in self._VIEW_ONLY_CLASSES:
                selection_model = widget.selectionModel()
                if selection_model is not None:
                    selection_model.selectionChanged.connect(
                        lambda *_, w=widget: self._report_action(w, "selectionChanged")
                    )
            self._wired.add(widget)

    def _report_action(self, widget: QWidget, signal_name: str) -> None:
        """Write a one-line description of the action to the status bar."""
        name = widget.accessibleName()
        if not name:
            # Internal chrome Qt builds around a named control -- the tab bar
            # inside a QTabWidget, the line edit inside an editable combo -- is
            # unnamed, and its own signals firing would drown the named control
            # it belongs to. Only the app's named controls report.
            return
        self._report(f"{action_verb(signal_name)}: {name}{value_suffix(widget)}")

    # -- view state --------------------------------------------------------

    def _apply_theme(self) -> None:
        palette = dict(DARK if self._dark else LIGHT)
        palette["font_size"] = f"{self._point_size}pt"
        QApplication.instance().setStyleSheet(stylesheet(palette))

    def _set_dark(self, checked: bool) -> None:
        self._dark = checked
        self._apply_theme()
        self._report(tr(f"Theme: {'dark' if checked else 'light'}"))

    def _toggle_status_bar(self, checked: bool) -> None:
        self._show_status = checked
        self.statusBar().setVisible(checked)
        self._report(tr(f"Status bar: {'shown' if checked else 'hidden'}"))

    def _toggle_toolbar(self, checked: bool) -> None:
        self._show_toolbar = checked
        self._toolbar.setVisible(checked)
        self._report(tr(f"Tool bar: {'shown' if checked else 'hidden'}"))

    def _toggle_dock(self, checked: bool) -> None:
        self._show_dock = checked
        self._dock.setVisible(checked)
        self._report(tr(f"Tool palette: {'shown' if checked else 'hidden'}"))

    def _zoom_in(self) -> None:
        self._set_point_size(self._point_size + 1)

    def _zoom_out(self) -> None:
        self._set_point_size(self._point_size - 1)

    def _reset_zoom(self) -> None:
        self._set_point_size(12)

    def _set_point_size(self, size: int) -> None:
        self._point_size = max(8, min(20, size))
        self._apply_theme()
        self._report(tr("Zoom: {}pt").format(self._point_size))

    def _toolbar_zoom(self, index: int) -> None:
        sizes = {0: 12, 1: 15, 2: 18}
        self._set_point_size(sizes.get(index, 12))

    # -- window-level actions ----------------------------------------------

    def _new_window(self) -> None:
        window = TortureTestWindow()
        window.show()
        self._report(tr("Opened a new window"))

    def _reset_pages(self) -> None:
        self._rebuild_pages()
        self._report(tr("Demo controls reset"))

    def _rebuild_pages(self) -> None:
        current = self._tabs.currentIndex()
        while self._tabs.count():
            page = self._tabs.widget(0)
            self._tabs.removeTab(0)
            page.deleteLater()
        for page_cls in PAGES:
            self._tabs.addTab(page_cls(), tab_label(tr(page_cls.title)))
        self._tabs.setCurrentIndex(min(current, self._tabs.count() - 1))
        self._wire_action_reporting()
        # Deferred: removeTab() + deleteLater() does not free the old pages
        # until the event loop runs, so counting now sees both generations
        # at once -- measured at 1354 against a true 701. A zero-timer puts
        # the count after those deletions instead.
        QTimer.singleShot(0, self._refresh_status_count)

    def _edit(self, method: str) -> None:
        widget = QApplication.focusWidget()
        fn = getattr(widget, method, None)
        if callable(fn):
            fn()
            self._report(tr("Edit: {}").format(method))
        else:
            self._report(tr("Edit: {} (no focused editor)").format(method))

    # -- demo dialogs ------------------------------------------------------

    def _message_box(self, icon: QMessageBox.Icon) -> None:
        label = {
            QMessageBox.Icon.Information: tr("Information"),
            QMessageBox.Icon.Warning: tr("Warning"),
            QMessageBox.Icon.Critical: tr("Critical"),
            QMessageBox.Icon.Question: tr("Question"),
        }[icon]
        if icon == QMessageBox.Icon.Information:
            QMessageBox.information(
                self, label, tr("This is an information message box.")
            )
        elif icon == QMessageBox.Icon.Warning:
            QMessageBox.warning(self, label, tr("This is a warning message box."))
        elif icon == QMessageBox.Icon.Critical:
            QMessageBox.critical(self, label, tr("This is a critical message box."))
        else:
            QMessageBox.question(self, label, tr("This is a question message box."))
        self._report(tr("Message box: {}").format(label))

    def _input_dialog(self, kind: str) -> None:
        if kind == "text":
            value, ok = QInputDialog.getText(self, tr("Input"), tr("Name:"))
        elif kind == "int":
            value, ok = QInputDialog.getInt(
                self, tr("Input"), tr("Age:"), 30, 0, 120, 1
            )
        else:
            value, ok = QInputDialog.getItem(
                self,
                tr("Input"),
                tr("Plan:"),
                [tr("Free"), tr("Pro"), tr("Enterprise")],
                0,
                False,
            )
        if ok:
            self._report(tr("Input dialog: {}").format(value))
        else:
            self._report(tr("Input dialog: cancelled"))

    def _color_dialog(self) -> None:
        options = (
            QColorDialog.ColorDialogOption.DontUseNativeDialog
            if sys.platform == "darwin"
            else QColorDialog.ColorDialogOption(0)
        )
        color = QColorDialog.getColor(
            QColor("#2f6fed"), self, tr("Choose a color"), options
        )
        if color.isValid():
            self._report(tr("Color chosen: {}").format(color.name()))

    def _font_dialog(self) -> None:
        # macOS's native color/font/file panels run in a separate,
        # XPC-serviced helper process (com.apple.appkit.xpc.*) that, on at
        # least one real box (a VM, confirmed live via `log stream`:
        # the helper launches and starts normal AppKit window-restoration
        # logic but never actually shows a window, repeatably, across many
        # reproductions), never renders at all -- hanging this app
        # indefinitely on first use, since the call blocks waiting for a
        # panel the user can never interact with. Qt's own, non-native
        # implementation of these same dialogs needs no such service and
        # is already confirmed working on this exact box (QMessageBox,
        # never native, opens and closes normally) -- using it here on
        # macOS specifically keeps every one of these dialogs fully
        # testable (they still really open, still really report) without
        # depending on a system service this environment cannot run.
        # Linux/BSD/Windows already use Qt's own dialogs by default and
        # are untouched.
        options = (
            QFontDialog.FontDialogOption.DontUseNativeDialog
            if sys.platform == "darwin"
            else QFontDialog.FontDialogOption(0)
        )
        font, ok = QFontDialog.getFont(
            self.font(), self, tr("Choose a font"), options=options
        )
        if ok:
            self._report(
                tr("Font chosen: {} {}pt").format(font.family(), font.pointSize())
            )

    def _file_open(self) -> None:
        options = (
            QFileDialog.Option.DontUseNativeDialog
            if sys.platform == "darwin"
            else QFileDialog.Option(0)
        )
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Open File"), "", "All Files (*)", options=options
        )
        if path:
            self._report(tr("Open: {}").format(path))

    def _file_save_as(self) -> None:
        options = (
            QFileDialog.Option.DontUseNativeDialog
            if sys.platform == "darwin"
            else QFileDialog.Option(0)
        )
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Save File"), "untitled.txt", "Text Files (*.txt)", options=options
        )
        if path:
            self._report(tr("Save As: {}").format(path))

    def _error_message(self) -> None:
        """Show a `QErrorMessage`, the one dialog that remembers dismissals.

        Distinct from the `QMessageBox` family above it, and worth having
        for that reason: it carries its own "Show this message again" check
        box, and unticking it makes Qt suppress that exact message string
        for the rest of the process. A test that drove it twice and asserted
        on the second appearance would be asserting on the check box's
        state, not on this method -- which is the kind of stateful dialog a
        fixture should contain rather than hide.
        """
        dialog = QErrorMessage(self)
        dialog.setWindowTitle(tr("Error Message"))
        dialog.setModal(True)
        dialog.showMessage(tr("Something went wrong, but it is only a demo."))
        self._report(tr("Error message shown"))

    def _progress_dialog(self) -> None:
        dialog = QProgressDialog(tr("Working…"), tr("Cancel"), 0, 100, self)
        dialog.setWindowTitle(tr("Progress"))
        dialog.setAutoClose(True)
        dialog.setAutoReset(True)
        dialog.setMinimumDuration(0)
        dialog.show()
        timer = QTimer(self)
        timer.setInterval(30)

        def step() -> None:
            dialog.setValue(dialog.value() + 1)
            if dialog.value() >= dialog.maximum() or dialog.wasCanceled():
                timer.stop()
                self._report(tr("Progress dialog finished"))

        timer.timeout.connect(step)
        timer.start()
        self._report(tr("Progress dialog started"))

    def _custom_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Preferences"))
        form = QFormLayout(dialog)
        name = QLineEdit()
        name.setAccessibleName("Dialog Name")
        notify = QCheckBox(tr("Enable notifications"))
        notify.setAccessibleName("Dialog Notifications")
        form.addRow(tr("Name"), name)
        form.addRow("", notify)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            self._report(tr("Dialog accepted: {}").format(name.text()))
        else:
            self._report(tr("Dialog cancelled"))

    def _wizard(self) -> None:
        wizard = QWizard(self)
        wizard.setWindowTitle(tr("Setup Wizard"))
        welcome = QWizardPage()
        welcome.setTitle(tr("Welcome"))
        welcome.setSubTitle(tr("This is the first page."))
        wizard.addPage(welcome)
        config = QWizardPage()
        config.setTitle(tr("Configuration"))
        layout = QFormLayout(config)
        server = QLineEdit()
        server.setAccessibleName("Wizard Server")
        layout.addRow(tr("Server"), server)
        wizard.addPage(config)
        if wizard.exec() == QWizard.DialogCode.Accepted:
            self._report(tr("Wizard finished"))
        else:
            self._report(tr("Wizard cancelled"))

    def _mdi_workspace(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("MDI Workspace"))
        dialog.resize(640, 420)
        area = QMdiArea()
        box = QVBoxLayout(dialog)
        box.addWidget(area)
        for i in range(3):
            editor = QTextEdit()
            editor.setPlainText(f"Contents of document {i + 1}.")
            sub = area.addSubWindow(editor)
            sub.setWindowTitle(f"Document {i + 1}")
        area.tileSubWindows()
        dialog.exec()
        self._report(tr("MDI workspace closed"))

    def _about(self) -> None:
        QMessageBox.about(
            self,
            tr("About TortureTest"),
            tr(
                "<b>TortureTest</b> is a desktop app stuffed with every Qt "
                "control, built to give pyguitest a worst-case test target."
            ),
        )
        self._report(tr("Showed About TortureTest"))

    def _about_qt(self) -> None:
        QMessageBox.aboutQt(self, tr("About Qt"))
        self._report(tr("Showed About Qt"))

    def _dump_controls(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Control Inventory"))
        dialog.resize(620, 520)
        box = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(self._controls_report())
        box.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        dialog.exec()
        self._report(tr("Dumped control inventory"))

    def _slow_dialog(self, seconds: int) -> None:
        self._report(tr("Slow dialog scheduled ({}s)").format(seconds))
        QTimer.singleShot(seconds * 1000, lambda: self._show_slow_dialog(seconds))

    def _slow_dialog_custom(self) -> None:
        value, ok = QInputDialog.getInt(
            self, tr("Slow Dialog"), tr("Delay (seconds):"), 2, 1, 60, 1
        )
        if ok:
            self._slow_dialog(value)

    def _show_slow_dialog(self, seconds: int) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Slow Dialog"))
        box = QVBoxLayout(dialog)
        box.addWidget(
            QLabel(tr("This dialog appeared after a {} second delay.").format(seconds))
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        self._report(tr("Slow dialog shown"))
        dialog.exec()
        self._report(tr("Slow dialog closed"))

    def _set_language(self, lang: str) -> None:
        set_language(lang)
        self._rebuild_ui()
        label = "Language: English" if lang == "en" else "Language: 日本語"
        self._report(tr(label))

    def _rebuild_ui(self) -> None:
        # Every QAction is parented to the *window* rather than to the menu
        # that shows it, because the same action can appear in a menu, the
        # toolbar and an action group at once. `menuBar().clear()` therefore
        # does not free them: it drops the menus, and the actions behind
        # them stay alive as children of the window while `_build_menus()`
        # creates a fresh set. Measured before this was collected: a window
        # went from 95 QActions to 189 after one language switch and 283
        # after the second, and a lookup for an action by text then found
        # two of it. Snapshot first, delete after the rebuild, so nothing
        # still in use is dropped out from under a live menu.
        stale: list[QObject] = [
            *self.findChildren(QAction),
            *self.findChildren(QActionGroup),
            # QMenus too, and for a separate reason: `menuBar().clear()`
            # removes the *actions* from the bar, but each QMenu that
            # `addMenu()` created is parented to the bar and outlives the
            # clear. Measured before this was collected: QMenu count went
            # 12 -> 59 across five language switches, about nine per
            # switch, which is the number `_build_menus` creates.
            *self.findChildren(QMenu),
        ]
        self.setWindowTitle(tr("TortureTest"))
        self.menuBar().clear()
        self._build_menus()
        toolbar = self._toolbar
        self.removeToolBar(toolbar)
        toolbar.deleteLater()
        self._build_toolbar()
        self.removeDockWidget(self._dock)
        self._dock.deleteLater()
        self._build_dock()
        self._rebuild_pages()
        self._apply_theme()
        for obj in stale:
            # RuntimeError means already gone: clearing the menu bar and
            # deleting the old toolbar and dock takes some of these with
            # them, and PySide6 raises rather than no-ops once the
            # underlying C++ object is destroyed. The snapshot cannot know
            # which, so the ones it still owns are collected here and the
            # rest were already handled.
            with contextlib.suppress(RuntimeError):
                obj.deleteLater()

    def _controls_report(self) -> str:
        header = f"{'Widget class':<24} {'Accessible role':<18} Accessible name"
        rows = [header, "-" * len(header)]
        for widget in sorted(self.findChildren(QWidget), key=_control_sort_key):
            name = widget.accessibleName()
            if not name:
                continue
            rows.append(
                f"{widget.metaObject().className():<24} {role_of(widget):<18} {name}"
            )
        return "\n".join(rows)


def _control_sort_key(widget: QWidget) -> str:
    return widget.accessibleName()


def main(argv: list[str] | None = None) -> int:
    """Start the Qt event loop and return its exit code."""
    args = list(sys.argv if argv is None else argv)
    filtered = [args[0]]
    index = 1
    while index < len(args):
        if args[index] == "--lang" and index + 1 < len(args):
            set_language(args[index + 1])
            index += 2
        else:
            filtered.append(args[index])
            index += 1
    os.environ.setdefault("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", "1")
    app = QApplication(filtered)
    app.setApplicationName("TortureTest")
    app.setOrganizationName("pyguitest")
    app.setStyle("Fusion")
    window = TortureTestWindow()
    window.show()
    return app.exec()
