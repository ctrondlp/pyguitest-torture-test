"""The Trees & Tables tab: tree, table and column item views."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QColumnView,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QUndoView,
    QVBoxLayout,
)

from ..base import Page, captioned, hbox, named, section
from ..i18n import tr


class ItemViewsPage(Page):
    """Tree, table and column views, both widget- and model-driven."""

    title = "Trees & Tables"
    description = (
        "A multi-column checkable tree, a table grid, a column view, and "
        "their model/view counterparts -- each named for element lookup."
    )

    def _populate(self, layout: QVBoxLayout) -> None:
        section(layout, "Trees")
        layout.addWidget(
            hbox(
                captioned("Project Tree", self._tree_widget()),
                captioned("Model Tree", self._tree_view()),
            )
        )

        section(layout, "Tables")
        layout.addWidget(
            hbox(
                captioned("Data Grid", self._table_widget()),
                captioned("Model Table", self._table_view()),
            )
        )

        section(layout, "Column view")
        layout.addWidget(
            hbox(
                captioned("Column View", self._column_view()),
                captioned("Undo History", self._undo_view()),
            )
        )

    def _undo_view(self) -> QUndoView:
        """A `QUndoView` listing a populated `QUndoStack`.

        The one item view here driven by a *command* model rather than a
        `QStandardItemModel`: `QUndoView` subclasses `QListView` and takes
        its rows from a `QUndoStack`, so each row is a pushed command and
        clicking one moves the stack's index. Named for lookup like every
        other control; the stack is parented to the view so it outlives
        this call.

        It reports its selection to the status bar *twice*, where the other
        item views report once -- measured, and left alone deliberately.
        The cause is the view's two-way binding with its stack: changing the
        selection moves the stack's index, and the stack moving its index
        sets the selection again, so `selectionChanged` genuinely fires
        twice. Suppressing the second would mean either dropping this view
        out of the selection-reporting wiring -- which would stop it
        reporting keyboard navigation at all, the exact gap `QTableWidget`
        needed `currentCellChanged` to close -- or de-duplicating messages
        app-wide, which would hide a real double-fire somewhere a test
        wanted to see one. A driver polls the status bar for the control's
        name, so two identical messages read the same as one.
        """
        view = named(QUndoView(), "Undo History")
        stack = QUndoStack(view)
        for label in ("Typed heading", "Inserted table", "Resized column"):
            stack.push(QUndoCommand(tr(label)))
        view.setStack(stack)
        return view

    def _tree_widget(self) -> QTreeWidget:
        """A multi-column, checkable `QTreeWidget` with nested items."""
        tree = named(QTreeWidget(), "Project Tree")
        tree.setHeaderLabels([tr("Name"), tr("Size"), tr("Type")])
        tree.setColumnCount(3)
        root = QTreeWidgetItem(["Project", "", "Folder"])
        source = QTreeWidgetItem(["src", "12 KB", "Folder"])
        source.addChild(QTreeWidgetItem(["main.py", "3 KB", "Python"]))
        source.addChild(QTreeWidgetItem(["util.py", "2 KB", "Python"]))
        readme = QTreeWidgetItem(["README.md", "1 KB", "Markdown"])
        for item in (root, source, readme):
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
        root.addChild(source)
        root.addChild(readme)
        root.setExpanded(True)
        tree.addTopLevelItem(root)
        return tree

    def _tree_view(self) -> QTreeView:
        """A `QTreeView` backed by a `QStandardItemModel`."""
        view = named(QTreeView(), "Model Tree")
        model = QStandardItemModel(view)
        model.setHorizontalHeaderLabels([tr("Name"), tr("Value")])
        parent = QStandardItem(tr("Parent"))
        parent.appendRow([QStandardItem(tr("Child A")), QStandardItem("1")])
        parent.appendRow([QStandardItem(tr("Child B")), QStandardItem("2")])
        model.appendRow(parent)
        view.setModel(model)
        view.expandAll()
        return view

    def _table_widget(self) -> QTableWidget:
        """An editable `QTableWidget` with a checkable cell column."""
        grid = named(QTableWidget(4, 3), "Data Grid")
        grid.setHorizontalHeaderLabels([tr("Name"), tr("Quantity"), tr("In Stock")])
        rows = [
            ("Widget", "3", True),
            ("Gadget", "7", False),
            ("Gizmo", "12", True),
            ("Doodad", "1", False),
        ]
        for row, (name, quantity, in_stock) in enumerate(rows):
            grid.setItem(row, 0, QTableWidgetItem(name))
            grid.setItem(row, 1, QTableWidgetItem(quantity))
            check = QTableWidgetItem()
            check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked if in_stock else Qt.CheckState.Unchecked
            )
            grid.setItem(row, 2, check)
        return grid

    def _table_view(self) -> QTableView:
        """A `QTableView` backed by a `QStandardItemModel`."""
        view = named(QTableView(), "Model Table")
        model = QStandardItemModel(3, 3, view)
        model.setHorizontalHeaderLabels(["A", "B", "C"])
        for row in range(3):
            for col in range(3):
                model.setItem(row, col, QStandardItem(f"{row},{col}"))
        view.setModel(model)
        return view

    def _column_view(self) -> QColumnView:
        """A `QColumnView` showing a hierarchical model one column at a time."""
        view = named(QColumnView(), "Column View")
        model = QStandardItemModel(view)
        root = QStandardItem(tr("Root"))
        for name in ("Alpha", "Beta", "Gamma"):
            child = QStandardItem(tr(name))
            child.appendRow(QStandardItem(f"{tr(name)} detail"))
            root.appendRow(child)
        model.appendRow(root)
        view.setModel(model)
        return view
