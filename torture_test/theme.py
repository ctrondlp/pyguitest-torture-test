"""Color palettes and the Qt stylesheet template that give TortureTest its look.

The two themes -- light and dark -- are produced from a single template so
they cannot drift apart. The application style is set to Fusion in ``app.main``
so the app renders identically on Windows, macOS, BSD and Linux, and the
stylesheet here restyles only the widgets that need a consistent, designed
appearance rather than the platform's own.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Template

# Colors are named by their role in the UI rather than by widget, so a color
# like `accent` reads the same in both palettes and the template stays honest.
LIGHT: dict[str, str] = {
    "window": "#f4f5f9",
    "surface": "#ffffff",
    "surface_alt": "#e9ebf2",
    "border": "#d5d8e2",
    "text": "#20212b",
    "text_dim": "#6c6f7d",
    "accent": "#2f6fed",
    "accent_hover": "#2459c8",
    "accent_text": "#ffffff",
    "hover": "#eef2fd",
    "selection": "#d7e2fb",
    "font_size": "12pt",
}

DARK: dict[str, str] = {
    "window": "#1e2029",
    "surface": "#292c37",
    "surface_alt": "#232630",
    "border": "#3d4150",
    "text": "#e9eaf0",
    "text_dim": "#9aa0b0",
    "accent": "#5b8def",
    "accent_hover": "#4a7bdc",
    "accent_text": "#ffffff",
    "hover": "#333746",
    "selection": "#3a4a6b",
    "font_size": "12pt",
}

# The stylesheet is split across two plain strings so the module stays within
# a reasonable edit size; `Template` substitutes across the concatenation.
_TEMPLATE_HEAD = """\
QWidget {
    background-color: $window;
    color: $text;
    font-size: $font_size;
    selection-background-color: $selection;
    selection-color: $text;
}
QMainWindow, QDialog { background-color: $window; }

QToolTip {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    padding: 4px 8px;
}

QMenuBar { background-color: $surface; border-bottom: 1px solid $border; }
QMenuBar::item { padding: 6px 10px; background: transparent; border-radius: 4px; }
QMenuBar::item:selected { background-color: $hover; }
QMenu { background-color: $surface; border: 1px solid $border; padding: 5px; }
QMenu::item { padding: 6px 26px 6px 22px; border-radius: 4px; }
QMenu::item:selected { background-color: $hover; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }

QToolBar {
    background-color: $surface;
    border: none;
    border-bottom: 1px solid $border;
    spacing: 4px;
    padding: 4px;
}
QToolBar QToolButton { padding: 5px; border-radius: 4px; }
QToolBar QToolButton:hover { background-color: $hover; }
QToolBar QToolButton:pressed { background-color: $selection; }

QPushButton {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 18px;
}
QPushButton:hover { background-color: $hover; }
QPushButton:pressed { background-color: $selection; }
QPushButton:disabled { color: $text_dim; background-color: $surface_alt; }
QPushButton#primaryButton {
    background-color: $accent;
    border-color: $accent;
    color: $accent_text;
    font-weight: 600;
}
QPushButton#primaryButton:hover { background-color: $accent_hover; }

QToolButton {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 5px 10px;
}
QToolButton:hover { background-color: $hover; }
QCommandLinkButton { background: transparent; border: none; color: $accent; }
QCommandLinkButton:hover { text-decoration: underline; }

QCheckBox, QRadioButton { spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked {
    background: $surface; border: 1px solid $border; border-radius: 4px;
}
QCheckBox::indicator:checked { background: $accent; border: 1px solid $accent; }
QCheckBox::indicator:indeterminate {
    background: $text_dim;
    border: 1px solid $text_dim;
}
QRadioButton::indicator:unchecked {
    background: $surface; border: 1px solid $border; border-radius: 8px;
}
QRadioButton::indicator:checked {
    background: $accent; border: 4px solid $surface; outline: 1px solid $accent;
}

QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser, QKeySequenceEdit,
QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit, QComboBox {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: $selection;
    selection-color: $text;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
    border-color: $accent;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
    background-color: $surface_alt; color: $text_dim;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border;
    selection-background-color: $selection;
}
"""

_TEMPLATE_TAIL = """\
QGroupBox {
    border: 1px solid $border;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 6px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }

QTabWidget::pane { border: 1px solid $border; border-radius: 0 6px 6px 6px; }
QTabBar::tab {
    background: $surface_alt; padding: 8px 16px; margin-right: 2px;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QTabBar::tab:selected { background: $accent; color: $accent_text; }
QTabBar::tab:!selected:hover { background: $hover; }

QTreeView, QTableView, QListView, QListWidget, QTreeWidget, QTableWidget, QColumnView {
    background-color: $surface;
    alternate-background-color: $surface_alt;
    border: 1px solid $border;
    border-radius: 6px;
    selection-background-color: $selection;
    selection-color: $text;
}
QHeaderView::section {
    background-color: $surface_alt; padding: 6px; border: none;
    border-bottom: 1px solid $border; font-weight: 600;
}
QTreeView::item, QListView::item, QTableView::item, QListWidget::item { padding: 4px; }

QSlider::groove:horizontal {
    height: 6px;
    background: $surface_alt;
    border-radius: 3px;
}
QSlider::sub-page:horizontal { background: $accent; border-radius: 3px; }
QSlider::handle:horizontal {
    width: 16px;
    margin: -5px 0;
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
}
QSlider::groove:vertical { width: 6px; background: $surface_alt; border-radius: 3px; }
QSlider::sub-page:vertical { background: $accent; border-radius: 3px; }
QSlider::handle:vertical {
    height: 16px;
    margin: 0 -5px;
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
}

QScrollBar:horizontal { background: $surface_alt; height: 12px; border-radius: 6px; }
QScrollBar::handle:horizontal {
    background: $border;
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    height: 0;
}
QScrollBar:vertical { background: $surface_alt; width: 12px; border-radius: 6px; }
QScrollBar::handle:vertical {
    background: $border;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { width: 0; height: 0; }

QProgressBar {
    background-color: $surface_alt; border: none; border-radius: 5px;
    min-height: 14px; text-align: center; color: $text;
}
QProgressBar::chunk { background-color: $accent; border-radius: 5px; }

QStatusBar { background-color: $surface; border-top: 1px solid $border; }
QStatusBar QLabel { color: $text_dim; }

QDockWidget::title {
    background: $surface_alt;
    padding: 6px 10px;
    border: 1px solid $border;
}

QSplitter::handle { background-color: $border; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }

QToolBox::tab { background: $surface_alt; padding: 6px 10px; border-radius: 4px; }
QToolBox::tab:selected { background: $accent; color: $accent_text; }

QFrame#panel {
    border: 1px solid $border;
    border-radius: 6px;
    background-color: $surface;
}
QLabel#pageTitle { font-size: 21pt; font-weight: 700; }
QLabel#pageDescription { color: $text_dim; }
QLabel#sectionHeader { font-weight: 700; color: $accent; }
QWidget#pageHeader { background-color: $surface; border-bottom: 1px solid $border; }
"""

_TEMPLATE = Template(_TEMPLATE_HEAD + _TEMPLATE_TAIL)


def stylesheet(palette: Mapping[str, str]) -> str:
    """Render the stylesheet for `palette` (see `LIGHT` and `DARK`)."""
    return _TEMPLATE.substitute(palette)
