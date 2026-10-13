"""The Image Search tab: look-alike controls for screenshot/template finding.

This page exists to give image/template matching a hard time on purpose, so a
test can verify that a picture of a control resolves unambiguously (or honestly
reports ambiguity) when several controls are pixel-identical or share a similar
name.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..base import Page, hbox, named, section, standard_icon
from ..i18n import tr

# Buttons whose visible labels are near-identical: a substring or fuzzy match
# (and a template match, since they render alike) can over-match.
_SAVE_LIKE = ("Save", "Save As", "Save All", "Save Copy", "Save Draft")


class ImageSearchPage(Page):
    """Controls that are visually identical or near-identical, for image finding."""

    title = "Image Search"
    description = (
        "A test area for screenshot and template matching. The look-alike grids "
        "are pixel-identical on screen but carry distinct accessible names, and "
        "the calibration target is the one control a picture can find "
        "unambiguously."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Identical buttons (same picture, distinct names)")
        layout.addWidget(self._lookalike_grid())

        section(layout, "Similar names, similar look")
        layout.addWidget(hbox(*[self._save_like(label) for label in _SAVE_LIKE]))

        section(layout, "Identical icon buttons")
        layout.addWidget(hbox(*[self._icon_button(i) for i in range(1, 6)]))

        section(layout, "Calibration target")
        layout.addWidget(self._calibration_target())

    def _lookalike_grid(self) -> QGroupBox:
        """A 4 x 3 grid of pixel-identical buttons; only their names differ."""
        grid = QGroupBox(tr("A 4 x 3 grid of pixel-identical buttons"))
        rows = QGridLayout(grid)
        rows.setSpacing(8)
        for row in range(3):
            for col in range(4):
                index = row * 4 + col + 1
                button = QPushButton(tr("Item"))
                button.setFixedSize(96, 36)
                named(button, f"Look-alike {index:02d}")
                rows.addWidget(button, row, col)
        return grid

    def _save_like(self, label: str) -> QPushButton:
        """A plain button whose text is also its (deliberately similar) name."""
        return named(QPushButton(tr(label)), label)

    def _icon_button(self, index: int) -> QToolButton:
        """An icon button identical to its siblings, named only by index."""
        button = QToolButton()
        button.setIcon(standard_icon(QStyle.StandardPixmap.SP_FileIcon))
        button.setFixedSize(44, 36)
        return named(button, f"Icon {index}")

    def _calibration_target(self) -> QWidget:
        """The single, visually unique control a picture should find first."""
        target = QPushButton(tr("CALIBRATE"))
        target.setObjectName("calibrationTarget")
        target.setFixedSize(240, 64)
        target.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: #ffffff;"
            " font-size: 16pt; font-weight: 700; border-radius: 8px; }"
        )
        named(target, "Calibration Target")
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(QLabel(tr("The one control a picture should find first.")))
        box.addWidget(target)
        return container
