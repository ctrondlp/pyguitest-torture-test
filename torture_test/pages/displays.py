"""The Displays tab: labels, an LCD number, progress bars and a calendar."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCalendarWidget,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QLCDNumber,
    QProgressBar,
    QVBoxLayout,
)

from ..base import Page, captioned, group, named, section
from ..i18n import tr


def _circle_pixmap() -> QPixmap:
    """Draw a small filled circle so the image label needs no asset file."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#2f6fed"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 60, 60)
    painter.end()
    return pixmap


def _demo_scene() -> QGraphicsScene:
    """Build a two-shape scene for the graphics view."""
    scene = QGraphicsScene()
    scene.addRect(
        QRectF(0, 0, 100, 100), QPen(QColor("#2f6fed")), QBrush(QColor("#eef2fd"))
    )
    scene.addEllipse(
        QRectF(40, 40, 20, 20), QPen(QColor("#c0392b")), QBrush(QColor("#c0392b"))
    )
    return scene


class DisplaysPage(Page):
    """Read-only widgets: labels, an LCD number, progress bars and a calendar."""

    title = "Displays"
    description = (
        "Plain, rich and image labels, an LCD number, determinate, "
        "indeterminate and vertical progress bars, a calendar, and a graphics "
        "view."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Labels")
        plain = named(QLabel(tr("A plain text label")), "Static Label")
        rich = QLabel(
            "<b>Bold</b> and <i>italic</i> and <a href='https://example.com'>a link</a>"
        )
        rich.setTextFormat(Qt.TextFormat.RichText)
        named(rich, "Rich Text Label")
        image = named(QLabel(), "Image Label")
        image.setPixmap(_circle_pixmap())
        layout.addWidget(
            group(
                "Labels",
                [
                    ("Static Label", plain),
                    ("Rich Text Label", rich),
                    ("Image Label", image),
                ],
            )
        )

        section(layout, "LCD number")
        lcd = named(QLCDNumber(3), "LCD Counter")
        lcd.display(42)
        layout.addWidget(captioned("LCD Counter", lcd))

        section(layout, "Progress bars")
        download = named(QProgressBar(), "Download Progress")
        download.setRange(0, 100)
        download.setValue(64)
        busy = named(QProgressBar(), "Indeterminate Busy")
        busy.setRange(0, 0)
        vertical = named(QProgressBar(), "Vertical Progress")
        vertical.setOrientation(Qt.Orientation.Vertical)
        vertical.setRange(0, 100)
        vertical.setValue(30)
        layout.addWidget(
            group(
                "Progress",
                [
                    ("Download Progress", download),
                    ("Indeterminate Busy", busy),
                    ("Vertical Progress", vertical),
                ],
            )
        )

        section(layout, "Calendar")
        calendar = named(QCalendarWidget(), "Calendar")
        layout.addWidget(captioned("Calendar", calendar))

        section(layout, "Graphics view")
        canvas = named(QGraphicsView(_demo_scene()), "Canvas")
        canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas.setFixedHeight(140)
        layout.addWidget(captioned("Canvas", canvas))
