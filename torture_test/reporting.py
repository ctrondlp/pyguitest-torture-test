"""Status-bar action reporting for TortureTest's controls.

TortureTest's status bar is its feedback channel: every control reports what
happened to it, so a pyguitest test can assert that a click or keystroke
landed by reading the status bar instead of guessing. This module holds the
mapping from widget class to the signals that mean "the user did something",
and the helpers that turn an event into a readable one-line message.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QColumnView,
    QComboBox,
    QCommandLinkButton,
    QDateEdit,
    QDateTimeEdit,
    QDial,
    QDoubleSpinBox,
    QFontComboBox,
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
    QUndoView,
    QWidget,
)

from .i18n import tr

# Widget class -> the signal(s) that fire when a user acts on it. Each is
# connected to the window's reporter, which reads the widget's name and state.
# `QProgressBar` is deliberately absent: its animated `valueChanged` is not a
# user action and would drown the status bar.
ACTION_SIGNALS: dict[type[QWidget], tuple[str, ...]] = {
    QPushButton: ("clicked",),
    QToolButton: ("clicked",),
    QCommandLinkButton: ("clicked",),
    QCheckBox: ("stateChanged",),
    QRadioButton: ("toggled",),
    QLineEdit: ("textChanged",),
    QPlainTextEdit: ("textChanged",),
    QTextEdit: ("textChanged",),
    QTextBrowser: ("textChanged",),
    QSpinBox: ("valueChanged",),
    QDoubleSpinBox: ("valueChanged",),
    QDateEdit: ("dateChanged",),
    QTimeEdit: ("timeChanged",),
    QDateTimeEdit: ("dateTimeChanged",),
    QKeySequenceEdit: ("keySequenceChanged",),
    QComboBox: ("currentIndexChanged",),
    QFontComboBox: ("currentFontChanged",),
    QListWidget: ("currentRowChanged", "itemClicked"),
    QListView: ("clicked",),
    QUndoView: ("clicked",),
    QTreeWidget: ("itemSelectionChanged", "itemClicked"),
    QTreeView: ("clicked",),
    # "currentCellChanged" alongside "cellClicked" for the same reason
    # QTreeWidget pairs "itemSelectionChanged" with "itemClicked": a real
    # mouse click is one action a test can drive, but it is not the only
    # one, and cellClicked alone never fires from keyboard-only navigation
    # (Down/Up/...) -- confirmed live (GhostBSD) driving "Data Grid" via
    # click()+Down took keyboard focus and moved the current cell
    # correctly, but nothing reported it, unlike its QTreeWidget sibling
    # "Project Tree" on the same tab, which already had this covered.
    QTableWidget: ("cellClicked", "currentCellChanged"),
    QTableView: ("clicked",),
    QColumnView: ("clicked",),
    QCalendarWidget: ("selectionChanged",),
    QSlider: ("valueChanged",),
    QDial: ("valueChanged",),
    QScrollBar: ("valueChanged",),
    QTabWidget: ("currentChanged",),
    QTabBar: ("currentChanged",),
    QToolBox: ("currentChanged",),
}

_VERBS: dict[str, str] = {
    "clicked": "Clicked",
    "toggled": "Toggled",
    "stateChanged": "Toggled",
    "textChanged": "Edited",
    "editingFinished": "Edited",
    "valueChanged": "Changed",
    "dateChanged": "Changed",
    "timeChanged": "Changed",
    "dateTimeChanged": "Changed",
    "currentIndexChanged": "Changed",
    "currentFontChanged": "Changed",
    "currentChanged": "Switched",
    "currentRowChanged": "Selected",
    "itemClicked": "Clicked item",
    "itemSelectionChanged": "Selection changed",
    "cellClicked": "Clicked cell",
    "currentCellChanged": "Selected cell",
    "keySequenceChanged": "Changed",
    "selectionChanged": "Changed",
}


def action_verb(signal_name: str) -> str:
    """Return the human verb for `signal_name`, defaulting to the name itself."""
    return tr(_VERBS.get(signal_name, signal_name))


def value_suffix(widget: QWidget) -> str:
    """Return ``" = <value>"`` describing `widget`'s current state, or empty."""
    if isinstance(widget, QCheckBox):
        partial = Qt.CheckState.PartiallyChecked
        if widget.isTristate() and widget.checkState() == partial:
            return tr(" = partial")
        return tr(" = on") if widget.isChecked() else tr(" = off")
    if isinstance(widget, QRadioButton):
        return tr(" = on") if widget.isChecked() else tr(" = off")
    if isinstance(widget, (QSpinBox, QDoubleSpinBox, QSlider, QDial, QScrollBar)):
        return f" = {widget.value()}"
    if isinstance(widget, (QDateEdit, QTimeEdit, QDateTimeEdit)):
        return f" = {widget.text()}"
    if isinstance(widget, QComboBox):
        return f" = {widget.currentText()}"
    if isinstance(widget, QLineEdit):
        text = widget.text()
        return f" = {text}" if text else ""
    if isinstance(widget, QPlainTextEdit):
        text = widget.toPlainText().strip()
        return f" = {text.splitlines()[0]}" if text else ""
    if isinstance(widget, QTextEdit):
        text = widget.toPlainText().strip()
        return f" = {text.splitlines()[0]}" if text else ""
    if isinstance(widget, (QTabWidget, QTabBar)):
        return f" = {widget.tabText(widget.currentIndex())}"
    if isinstance(widget, QKeySequenceEdit):
        sequence = widget.keySequence().toString()
        return f" = {sequence}" if sequence else ""
    if isinstance(widget, QCalendarWidget):
        return f" = {widget.selectedDate().toString('yyyy-MM-dd')}"
    return ""
