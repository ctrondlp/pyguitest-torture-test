"""Map Qt widget classes to the accessible roles pyguitest will query them by.

Qt publishes each widget under a role in the platform accessibility tree
(AT-SPI on Linux/BSD, UIA on Windows, NSAccessibility on macOS). This module
encodes that mapping for the "Dump Controls" self-inspection, so the report
matches what pyguitest sees rather than a guess. It is a lookup table for the
classes TortureTest actually creates, not a claim about every Qt class.
"""

from __future__ import annotations

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
    QGraphicsView,
    QGroupBox,
    QKeySequenceEdit,
    QLabel,
    QLCDNumber,
    QLineEdit,
    QListView,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollBar,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
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

ROLE_BY_CLASS: dict[type[QWidget], str] = {
    QPushButton: "push button",
    QToolButton: "push button",
    QCommandLinkButton: "push button",
    QCheckBox: "check box",
    QRadioButton: "radio button",
    QLineEdit: "entry",
    QKeySequenceEdit: "entry",
    QTextEdit: "text",
    QPlainTextEdit: "text",
    QTextBrowser: "text",
    QSpinBox: "spin button",
    QDoubleSpinBox: "spin button",
    QDateEdit: "spin button",
    QTimeEdit: "spin button",
    QDateTimeEdit: "spin button",
    QComboBox: "combo box",
    QFontComboBox: "combo box",
    QSlider: "slider",
    QDial: "dial",
    QProgressBar: "progress bar",
    QScrollBar: "scroll bar",
    QListWidget: "list",
    QListView: "list",
    QUndoView: "list",
    QTreeWidget: "tree",
    QTreeView: "tree",
    QColumnView: "tree",
    QTableWidget: "table",
    QTableView: "table",
    QTabWidget: "page tab list",
    QTabBar: "page tab list",
    QToolBox: "layered pane",
    QStackedWidget: "filler",
    QGraphicsView: "filler",
    QSplitter: "split pane",
    QLabel: "label",
    QGroupBox: "group box",
    QLCDNumber: "lcd number",
    QCalendarWidget: "calendar",
}


def role_of(widget: QWidget) -> str:
    """Return the accessible role for `widget`, defaulting to a generic one."""
    return ROLE_BY_CLASS.get(type(widget), "widget")
