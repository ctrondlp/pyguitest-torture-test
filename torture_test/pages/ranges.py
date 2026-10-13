"""The Sliders & Ranges tab: sliders, dials, scroll bars and an animated bar."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDial,
    QProgressBar,
    QPushButton,
    QScrollBar,
    QSlider,
    QVBoxLayout,
)

from ..base import Page, captioned, group, hbox, named, section
from ..i18n import tr


class RangesPage(Page):
    """Sliders, dials, scroll bars and an animated progress bar."""

    title = "Sliders & Ranges"
    description = (
        "Horizontal and vertical sliders (with ticks), dials, standalone scroll "
        "bars, and a timer-driven progress bar with start/stop/reset."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Sliders")
        volume = named(QSlider(Qt.Orientation.Horizontal), "Volume")
        volume.setRange(0, 100)
        volume.setValue(40)
        volume.setTickPosition(QSlider.TickPosition.TicksBelow)
        volume.setTickInterval(10)

        stepped = named(QSlider(Qt.Orientation.Horizontal), "Stepped")
        stepped.setRange(0, 10)
        stepped.setValue(3)
        stepped.setTickPosition(QSlider.TickPosition.TicksBothSides)
        stepped.setTickInterval(1)
        stepped.setPageStep(2)

        balance = named(QSlider(Qt.Orientation.Vertical), "Balance")
        balance.setRange(-100, 100)
        balance.setValue(0)

        layout.addWidget(
            group(
                "Sliders",
                [
                    ("Volume", volume),
                    ("Stepped", stepped),
                    ("Balance", balance),
                ],
            )
        )

        section(layout, "Dials")
        tuning = named(QDial(), "Tuning Dial")
        tuning.setRange(0, 100)
        tuning.setValue(25)
        frequency = named(QDial(), "Frequency Dial")
        frequency.setNotchesVisible(True)
        frequency.setRange(0, 100)
        frequency.setValue(50)
        layout.addWidget(hbox(tuning, frequency))

        section(layout, "Scroll bars")
        h_scroll = named(QScrollBar(Qt.Orientation.Horizontal), "Horizontal Scroll")
        h_scroll.setRange(0, 100)
        h_scroll.setValue(30)
        v_scroll = named(QScrollBar(Qt.Orientation.Vertical), "Vertical Scroll")
        v_scroll.setRange(0, 100)
        v_scroll.setValue(60)
        layout.addWidget(captioned("Horizontal Scroll", h_scroll))
        layout.addWidget(captioned("Vertical Scroll", v_scroll))

        section(layout, "Animated progress")
        self._progress = named(QProgressBar(), "Animated Progress")
        self._progress.setRange(0, 100)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._advance)
        start = named(QPushButton(tr("Start")), "Start Progress")
        start.clicked.connect(lambda: self._timer.start())
        stop = named(QPushButton(tr("Stop")), "Stop Progress")
        stop.clicked.connect(lambda: self._timer.stop())
        reset = named(QPushButton(tr("Reset")), "Reset Progress")
        reset.clicked.connect(self._reset_progress)
        layout.addWidget(self._progress)
        layout.addWidget(hbox(start, stop, reset))

    def _advance(self) -> None:
        """Step the progress bar forward, wrapping at the end."""
        value = self._progress.value() + 1
        if value > self._progress.maximum():
            value = self._progress.minimum()
        self._progress.setValue(value)

    def _reset_progress(self) -> None:
        """Stop the timer and return the bar to zero."""
        self._timer.stop()
        self._progress.setValue(0)
