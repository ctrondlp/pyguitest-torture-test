"""The Buttons tab: push buttons, tool buttons, command links and toggles."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QCommandLinkButton,
    QMenu,
    QPushButton,
    QRadioButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
)

from ..base import Page, hbox, named, section, standard_icon
from ..i18n import tr


def _tool_menu(parent: QToolButton) -> QMenu:
    """Build the popup menu shown by the menu tool button."""
    menu = QMenu(parent)
    menu.addAction(tr("First Item"))
    menu.addAction(tr("Second Item"))
    menu.addSeparator()
    menu.addAction(tr("Third Item"))
    return menu


class ButtonsPage(Page):
    """Every kind of button and toggle Qt offers."""

    title = "Buttons & Toggles"
    description = (
        "Push buttons (default, toggle, disabled), tool buttons (text, "
        "icon-only, menu), a command link, check boxes including tri-state, "
        "and radio buttons -- each with a stable accessible name."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Push buttons")
        primary = named(QPushButton(tr("Primary Action")), "Primary Action")
        primary.setObjectName("primaryButton")
        primary.setDefault(True)
        secondary = named(QPushButton(tr("Secondary Action")), "Secondary Action")
        disabled = named(QPushButton(tr("Disabled Action")), "Disabled Action")
        disabled.setEnabled(False)
        toggle = named(QPushButton(tr("Toggle Me")), "Toggle Me")
        toggle.setCheckable(True)
        layout.addWidget(hbox(primary, secondary, disabled, toggle))

        section(layout, "Tool buttons")
        tool = named(QToolButton(), "Tool Button")
        tool.setText(tr("Tool Button"))
        tool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tool.setIcon(standard_icon(QStyle.StandardPixmap.SP_FileIcon))
        icon_only = named(QToolButton(), "Icon Button")
        icon_only.setIcon(standard_icon(QStyle.StandardPixmap.SP_DirIcon))
        icon_only.setToolTip(tr("An icon-only button, named explicitly"))
        menu_button = named(QToolButton(), "Menu Button")
        menu_button.setText(tr("Menu Button"))
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_button.setMenu(_tool_menu(menu_button))
        layout.addWidget(hbox(tool, icon_only, menu_button))

        section(layout, "Command link")
        command = named(
            QCommandLinkButton(
                tr("Explore TortureTest"), tr("Open the comprehensive walkthrough")
            ),
            "Explore TortureTest",
        )
        layout.addWidget(command)

        section(layout, "Check boxes")
        terms = named(
            QCheckBox(tr("Accept terms and conditions")),
            "Accept terms and conditions",
        )
        notify = named(QCheckBox(tr("Receive notifications")), "Receive notifications")
        notify.setChecked(True)
        tri = named(QCheckBox(tr("Tri-state option")), "Tri-state option")
        tri.setTristate(True)
        tri.setCheckState(Qt.CheckState.PartiallyChecked)
        layout.addWidget(terms)
        layout.addWidget(notify)
        layout.addWidget(tri)

        section(layout, "Radio buttons")
        radio_group = QButtonGroup(self)
        option_a = named(QRadioButton(tr("Option A")), "Option A")
        option_b = named(QRadioButton(tr("Option B")), "Option B")
        option_c = named(QRadioButton(tr("Option C")), "Option C")
        option_b.setChecked(True)
        for index, radio in enumerate((option_a, option_b, option_c)):
            radio_group.addButton(radio, index)
        layout.addWidget(hbox(option_a, option_b, option_c))
