"""The Choosers tab: combo boxes, a font picker and themed list widgets."""

from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFontComboBox,
    QListView,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QVBoxLayout,
)

from ..base import Page, captioned, group, hbox, named, section, standard_icon
from ..i18n import tr

# Themed list data: (English key, representative color) for each item.
_COLORS = (
    ("Red", "#e74c3c"),
    ("Orange", "#e67e22"),
    ("Yellow", "#f1c40f"),
    ("Green", "#2ecc71"),
    ("Blue", "#3498db"),
    ("Purple", "#9b59b6"),
)
_PLANETS = (
    ("Mercury", "#b5a7a2"),
    ("Venus", "#e8c07a"),
    ("Earth", "#5b8def"),
    ("Mars", "#d97a5a"),
    ("Jupiter", "#d9a36a"),
    ("Saturn", "#e8d0a0"),
    ("Uranus", "#7fd4d4"),
    ("Neptune", "#5a7fd9"),
)
_MOONS = (
    ("Moon", "#c0c0c8"),
    ("Phobos", "#a8a8b0"),
    ("Deimos", "#b8b8c0"),
    ("Titan", "#d0c8a8"),
    ("Europa", "#c8d0d8"),
    ("Ganymede", "#b0b8c0"),
)


def _swatch(color: str) -> QIcon:
    """A square swatch icon filled with `color`."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def _disc(color: str) -> QIcon:
    """A small circular disc icon filled with `color`."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QIcon(pixmap)


class ChoosersPage(Page):
    """Combo boxes, a font picker and themed list widgets."""

    title = "Choosers"
    description = (
        "Editable and read-only combo boxes, a font picker, and lists themed "
        "around colors, planets and moons -- with single, checkable and "
        "multi-selection, plus a model/view list."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Combo boxes")
        country = named(QComboBox(), "Country")
        country.setEditable(True)
        for label in ("Norway", "Sweden", "Denmark", "Finland", "Iceland"):
            country.addItem(tr(label))
        country.setCurrentText(tr("Norway"))

        plan = named(QComboBox(), "Plan")
        for label in ("Free", "Pro", "Enterprise"):
            plan.addItem(standard_icon(QStyle.StandardPixmap.SP_FileIcon), tr(label))

        font = named(QFontComboBox(), "Font")

        layout.addWidget(
            group(
                "Combo boxes",
                [
                    ("Country", country),
                    ("Plan", plan),
                    ("Font", font),
                ],
            )
        )

        section(layout, "Lists")
        colors = named(QListWidget(), "Colors")
        for label, color in _COLORS:
            colors.addItem(QListWidgetItem(_swatch(color), tr(label)))

        planets = named(QListWidget(), "Planets")
        for label, color in _PLANETS:
            item = QListWidgetItem(_disc(color), tr(label))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            planets.addItem(item)

        moons = named(QListWidget(), "Moons")
        moons.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for label, color in _MOONS:
            moons.addItem(QListWidgetItem(_disc(color), tr(label)))

        simple = named(QListView(), "Simple List")
        simple.setModel(QStringListModel([tr(label) for label, _ in _PLANETS], simple))

        layout.addWidget(
            hbox(
                captioned("Colors", colors),
                captioned("Planets", planets),
                captioned("Moons", moons),
            )
        )
        layout.addWidget(captioned("Simple List (model/view)", simple))
