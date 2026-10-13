"""The Kitchen Sink tab: a dense, realistic form mixing many control types."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..base import Page, captioned, group, hbox, named, section
from ..i18n import tr


class KitchenSinkPage(Page):
    """A realistic form that mixes many controls on one dense page."""

    title = "Kitchen Sink"
    description = (
        "A dense, realistic form -- the closest thing here to a real "
        "application screen -- so element lookups can be exercised together."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Account details")
        full_name = named(QLineEdit(), "Account Full Name")
        full_name.setPlaceholderText(tr("Jane Doe"))
        email = named(QLineEdit(), "Account Email Address")
        email.setPlaceholderText(tr("name@example.com"))
        country = named(QComboBox(), "Account Country")
        for label in ("Norway", "Sweden", "Denmark", "Finland"):
            country.addItem(tr(label))
        age = named(QSpinBox(), "Age")
        age.setRange(0, 120)
        age.setValue(30)
        layout.addWidget(
            group(
                "Personal information",
                [
                    ("Account Full Name", full_name),
                    ("Account Email Address", email),
                    ("Account Country", country),
                    ("Age", age),
                ],
            )
        )

        newsletter = named(
            QCheckBox(tr("Subscribe to the newsletter")),
            "Subscribe to the newsletter",
        )
        newsletter.setChecked(True)
        layout.addWidget(newsletter)

        bio = named(QPlainTextEdit(), "Biography")
        bio.setPlaceholderText(tr("Tell us about yourself…"))
        layout.addWidget(captioned("Biography", bio))

        section(layout, "Actions")
        create = named(QPushButton(tr("Create Account")), "Create Account")
        create.setObjectName("primaryButton")
        cancel = named(QPushButton(tr("Cancel")), "Cancel")
        layout.addWidget(hbox(create, cancel))
