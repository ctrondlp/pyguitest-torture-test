"""Shared scaffolding for the TortureTest tab pages.

Every tab is a `Page`: a titled, described header above a scrollable body. The
helpers here keep each page's construction readable and the accessibility
naming consistent -- which is the point of the application, since a control
without a stable name is one pyguitest can only reach by coordinate.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr

_Widget = TypeVar("_Widget", bound=QWidget)


def named(widget: _Widget, name: str, description: str | None = None) -> _Widget:
    """Set `widget`'s accessible name (and optional description) and return it.

    The accessible name is what an assistive technology -- and therefore
    pyguitest -- reads back, so it must be stable and unique within the
    window. For text-bearing controls the visible text already serves, but
    setting it here makes the contract explicit and covers icon-only controls.

    A combo box is the one exception Qt's accessibility bridge makes: it
    publishes the box's *current text* as the accessible name and discards
    ``setAccessibleName`` entirely (verified live through AT-SPI), so the
    stable name travels in the accessible description instead, which Qt does
    not overwrite.

    That makes `description` and a combo box mutually exclusive: the
    description is the combo box's only stable identifier, so overwriting it
    would leave the control reachable by neither name nor description --
    `Session.dropdown()` tries exactly those two, in that order. Raising
    here is deliberate. The alternative is a control that silently cannot be
    found, which is the one failure this whole application exists to catch,
    and it would surface as an unexplained miss in a driver run on some
    other platform rather than as an error at construction.
    """
    widget.setAccessibleName(name)
    if isinstance(widget, QComboBox):
        if description is not None:
            raise ValueError(
                f"{name!r}: a combo box cannot carry a description -- Qt "
                "publishes its current text as the accessible name, so the "
                "description is the only stable identifier it has"
            )
        widget.setAccessibleDescription(name)
    elif description is not None:
        widget.setAccessibleDescription(description)
    return widget


def tab_label(title: str) -> str:
    """`title` with its ampersands escaped, for a tab, button or menu label.

    Qt reads a single ``&`` in a widget's visible text as a mnemonic marker
    and **strips it from the accessible name** it publishes. Measured
    directly against a `QTabBar`: a tab added as ``"Text & Numbers"``
    publishes the accessible name ``"Text  Numbers"`` -- ampersand gone and
    a double space left where it was -- while ``tabText()`` still reports
    the ampersand, so Qt's own property does not show the loss. Doubling it
    (``"Text && Numbers"``) renders one literal ``&`` and publishes
    ``"Text & Numbers"``, which is the name a test is written against.

    Found by recording a session with pyguitest-recorder on both macOS and
    Windows: each generated script matched the tab on ``"Text  Numbers"``,
    a string whose doubled space is invisible on review. The app's self-test
    could not catch it, because `QWidget.accessibleName()` returns what was
    *set* rather than what the platform publishes after mnemonic stripping;
    `test_tab_accessible_names_keep_their_ampersands` queries the accessible
    interface instead, which is the only way to see it.

    Applied to the label only, never to `Page.title` itself: the title is
    also the translation key and the page's identity.
    """
    return title.replace("&", "&&")


def standard_icon(pixmap: QStyle.StandardPixmap) -> QIcon:
    """Return the platform's standard icon for `pixmap` (no asset files)."""
    return QApplication.style().standardIcon(pixmap)


class Page(QWidget):
    """One torture-test tab: a header (title + description) over a scroll body.

    Subclasses set the `title` and `description` class attributes -- the tab's
    label and its header text -- and implement `_populate`, which receives the
    body layout to fill with controls.
    """

    title: str = ""
    description: str = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Assemble the header and scrollable body, then populate the body."""
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        """Lay out the header and scroll area, then hand the body to `_populate`."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("pageHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(24, 18, 24, 14)
        head.setSpacing(4)
        title = QLabel(tr(self.title))
        title.setObjectName("pageTitle")
        description = QLabel(tr(self.description))
        description.setObjectName("pageDescription")
        description.setWordWrap(True)
        head.addWidget(title)
        head.addWidget(description)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 14, 24, 28)
        layout.setSpacing(14)
        self._populate(layout)
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    def _populate(self, layout: QVBoxLayout) -> None:
        """Fill `layout` with the page's controls; subclasses override this."""
        raise NotImplementedError


def section(layout: QVBoxLayout, title: str) -> None:
    """Add a small, styled section heading to `layout`."""
    label = QLabel(tr(title))
    label.setObjectName("sectionHeader")
    layout.addWidget(label)


def group(title: str, rows: Iterable[tuple[str, QWidget]]) -> QGroupBox:
    """Build a titled group box pairing each caption with a control.

    ``QFormLayout.addRow(caption, widget)`` also associates the caption label
    as the control's buddy, which is how Qt publishes the label/field
    relationship to the accessibility tree -- a test can then attribute a label
    to its field rather than matching on text alone.
    """
    box = QGroupBox(tr(title))
    form = QFormLayout(box)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    for caption, widget in rows:
        form.addRow(tr(caption), widget)
    return box


def hbox(*widgets: QWidget) -> QWidget:
    """Arrange `widgets` side by side, left-aligned, in a horizontal container."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return container


def captioned(caption: str, widget: QWidget) -> QWidget:
    """Stack a buddy label above `widget`, associating the two for accessibility.

    `QLabel.setBuddy` publishes the caption as the control's label in the
    accessibility tree, so a test can attribute "Notes" to its editor rather
    than matching on placeholder text alone.
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    label = QLabel(tr(caption))
    label.setBuddy(widget)
    layout.addWidget(label)
    layout.addWidget(widget)
    return container
