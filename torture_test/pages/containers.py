"""The Containers tab: group boxes, frames, tabs, tool box, splitter and more."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from ..base import Page, captioned, hbox, named, section
from ..i18n import tr


class ContainersPage(Page):
    """Containers and layout widgets: group boxes, frames, tabs, tool boxes."""

    title = "Containers"
    description = (
        "Group boxes (plain, checkable, flat), styled and line frames, a "
        "closable/movable tab widget, a standalone tab bar, a tool box, a "
        "stacked widget, a splitter and a scroll area."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Group boxes")
        layout.addWidget(
            hbox(self._basic_group(), self._checkable_group(), self._flat_group())
        )

        section(layout, "Frames")
        panel = QFrame()
        panel.setObjectName("panel")
        panel_box = QVBoxLayout(panel)
        panel_box.addWidget(QLabel(tr("A styled panel (QFrame).")))
        layout.addWidget(captioned("Styled Panel", panel))

        h_line = QFrame()
        h_line.setFrameShape(QFrame.Shape.HLine)
        h_line.setFrameShadow(QFrame.Shadow.Sunken)
        v_line = QFrame()
        v_line.setFrameShape(QFrame.Shape.VLine)
        v_line.setFrameShadow(QFrame.Shadow.Sunken)
        v_line.setFixedHeight(48)
        layout.addWidget(hbox(h_line, v_line))

        section(layout, "Tabs and tool box")
        layout.addWidget(captioned("Nested Tabs", self._nested_tabs()))
        layout.addWidget(captioned("Standalone Tab Bar", self._tab_bar()))
        layout.addWidget(captioned("Tool Box", self._tool_box()))

        section(layout, "Stacked widget")
        layout.addWidget(captioned("Stacked Widget", self._stacked()))

        section(layout, "Splitter and scroll area")
        layout.addWidget(captioned("Splitter", self._splitter()))
        layout.addWidget(captioned("Scrollable Region", self._scroll_area()))

    def _basic_group(self) -> QGroupBox:
        """A plain group box holding a label and a button."""
        box = QGroupBox(tr("Basic Group"))
        inner = QVBoxLayout(box)
        inner.addWidget(QLabel(tr("Content inside a plain group box.")))
        inner.addWidget(named(QPushButton(tr("Inner Button")), "Inner Button"))
        return box

    def _checkable_group(self) -> QGroupBox:
        """A group box disabled or enabled through its title checkbox."""
        box = QGroupBox(tr("Checkable Group"))
        box.setCheckable(True)
        box.setChecked(True)
        inner = QVBoxLayout(box)
        inner.addWidget(QLabel(tr("Disable via the title checkbox.")))
        return box

    def _flat_group(self) -> QGroupBox:
        """A group box with no border frame."""
        box = QGroupBox(tr("Flat Group"))
        box.setFlat(True)
        inner = QVBoxLayout(box)
        inner.addWidget(QLabel(tr("A flat group box.")))
        return box

    def _nested_tabs(self) -> QTabWidget:
        """A movable, closable tab widget nested inside the page."""
        tabs = named(QTabWidget(), "Nested Tabs")
        tabs.setMovable(True)
        tabs.setTabsClosable(True)
        tabs.tabCloseRequested.connect(tabs.removeTab)
        for label in ("Alpha", "Beta", "Gamma"):
            page = QWidget()
            body = QVBoxLayout(page)
            body.addWidget(QLabel(f"Content of the {tr(label)} tab."))
            tabs.addTab(page, tr(label))
        return tabs

    def _tab_bar(self) -> QTabBar:
        """A standalone tab bar, without the pages a tab widget would hold."""
        bar = named(QTabBar(), "Standalone Tab Bar")
        bar.addTab(tr("One"))
        bar.addTab(tr("Two"))
        bar.addTab(tr("Three"))
        return bar

    def _tool_box(self) -> QToolBox:
        """An accordion-style tool box of collapsible sections."""
        box = named(QToolBox(), "Tool Box")
        for label in ("Section One", "Section Two", "Section Three"):
            page = QWidget()
            body = QVBoxLayout(page)
            body.addWidget(QLabel(f"{tr(label)} content."))
            box.addItem(page, tr(label))
        return box

    def _stacked(self) -> QWidget:
        """A stacked widget whose page is chosen by an accompanying combo box."""
        stacked = named(QStackedWidget(), "Stacked Widget")
        switch = named(QComboBox(), "Stack Page")
        for label in ("Page 1", "Page 2", "Page 3"):
            page = QWidget()
            body = QVBoxLayout(page)
            body.addWidget(QLabel(f"Contents of {tr(label)}."))
            stacked.addWidget(page)
            switch.addItem(tr(label))
        switch.currentIndexChanged.connect(stacked.setCurrentIndex)
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(switch)
        box.addWidget(stacked)
        return container

    def _splitter(self) -> QSplitter:
        """A horizontal splitter separating two panes."""
        splitter = named(QSplitter(Qt.Orientation.Horizontal), "Splitter")
        left = QWidget()
        left_body = QVBoxLayout(left)
        left_body.addWidget(QLabel(tr("Left pane")))
        right = QWidget()
        right_body = QVBoxLayout(right)
        right_body.addWidget(QLabel(tr("Right pane")))
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([200, 200])
        return splitter

    def _scroll_area(self) -> QScrollArea:
        """A scrollable region with more content than fits."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.StyledPanel)
        area.setFixedHeight(160)
        inner = QWidget()
        body = QVBoxLayout(inner)
        for i in range(40):
            body.addWidget(QLabel(f"Line {i + 1} of scrollable content"))
        area.setWidget(inner)
        return area
