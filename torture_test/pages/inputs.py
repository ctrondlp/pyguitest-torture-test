"""The Text & Numbers tab: line edits, text views, spin boxes and dates."""

from __future__ import annotations

from PySide6.QtCore import QDate, QDateTime, QRegularExpression, Qt, QTime
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCompleter,
    QDateEdit,
    QDateTimeEdit,
    QDoubleSpinBox,
    QKeySequenceEdit,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QTextBrowser,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
)

from ..base import Page, captioned, group, named, section
from ..i18n import tr


class InputsPage(Page):
    """Text, number, date and key-sequence entry widgets."""

    title = "Text & Numbers"
    description = (
        "Line edits with validation, masking, completion and echo modes; "
        "multi-line and rich text views; spin boxes; date/time editors; and a "
        "key-sequence capture field."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Line edits")
        full_name = named(QLineEdit(), "Full Name")
        full_name.setPlaceholderText(tr("Jane Doe"))

        email = named(QLineEdit(), "Email Address")
        email.setPlaceholderText(tr("name@example.com"))
        email.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
            )
        )

        password = named(QLineEdit(), "Password")
        password.setEchoMode(QLineEdit.EchoMode.Password)
        password.setPlaceholderText("••••••••")

        read_only = named(QLineEdit(tr("Read-only value")), "Read Only Field")
        read_only.setReadOnly(True)

        clearable = named(QLineEdit(), "Clear Button Field")
        clearable.setPlaceholderText(tr("Type to reveal the clear button"))
        clearable.setClearButtonEnabled(True)

        masked = named(QLineEdit(), "Masked Field")
        masked.setInputMask("(999) 000-0000")

        autocomplete = named(QLineEdit(), "Auto-complete Field")
        autocomplete.setPlaceholderText(tr("Fruit names"))
        completer = QCompleter(["Apple", "Banana", "Cherry", "Date", "Elderberry"])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        autocomplete.setCompleter(completer)

        layout.addWidget(
            group(
                "Single-line fields",
                [
                    ("Full Name", full_name),
                    ("Email Address", email),
                    ("Password", password),
                    ("Read Only Field", read_only),
                    ("Clear Button Field", clearable),
                    ("Masked Field", masked),
                    ("Auto-complete Field", autocomplete),
                ],
            )
        )

        section(layout, "Multi-line text")
        notes = named(QPlainTextEdit(), "Notes")
        notes.setPlaceholderText(tr("Write notes here…"))
        rich = named(QTextEdit(), "Rich Text")
        rich.setPlaceholderText(tr("Rich text…"))
        browser = named(QTextBrowser(), "Documentation")
        browser.setPlainText(
            "This is a read-only documentation view (QTextBrowser).\n"
            "Use it for help pages and other non-editable rich text."
        )
        layout.addWidget(captioned("Notes", notes))
        layout.addWidget(captioned("Rich Text", rich))
        layout.addWidget(captioned("Documentation", browser))

        section(layout, "Numbers and dates")
        quantity = named(QSpinBox(), "Quantity")
        quantity.setRange(0, 999)
        quantity.setValue(1)
        quantity.setSuffix(" pcs")

        price = named(QDoubleSpinBox(), "Price")
        price.setRange(0.0, 100_000.0)
        price.setDecimals(2)
        price.setPrefix("$ ")
        price.setValue(9.99)

        start_date = named(QDateEdit(), "Start Date")
        start_date.setCalendarPopup(True)
        start_date.setDate(QDate.currentDate())

        alarm = named(QTimeEdit(), "Alarm Time")
        alarm.setTime(QTime(7, 30))

        appointment = named(QDateTimeEdit(), "Appointment")
        appointment.setDateTime(QDateTime.currentDateTime())

        shortcut = named(QKeySequenceEdit(), "Shortcut Capture")

        layout.addWidget(
            group(
                "Spinners and editors",
                [
                    ("Quantity", quantity),
                    ("Price", price),
                    ("Start Date", start_date),
                    ("Alarm Time", alarm),
                    ("Appointment", appointment),
                    ("Shortcut Capture", shortcut),
                ],
            )
        )
