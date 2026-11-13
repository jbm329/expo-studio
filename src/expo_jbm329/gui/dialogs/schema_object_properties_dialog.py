"""Read-only presentation of a database object's catalog metadata."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.db.core.object_properties import ConstraintKind, MetadataState, SchemaObjectKind
from expo_jbm329.gui.dialogs.analysis.section_layout import ANALYSIS_TABS_STYLE
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons

if TYPE_CHECKING:
    from expo_jbm329.db.core.object_properties import MetadataValue, ObjectProperties, SchemaObjectIdentity


class SchemaObjectPropertiesDialog(QDialog):
    """Present a captured catalog snapshot without querying the database."""

    retry_requested = pyqtSignal()

    def __init__(self, parent: QWidget, identity: SchemaObjectIdentity) -> None:
        """Initialize presentation for the captured object."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._set_object_title(identity)
        self.resize(1000, 720)
        self._snapshot: ObjectProperties | None = None
        layout = QVBoxLayout(self)
        self.status = QLabel(self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        notice = QLabel(self.tr("Only metadata visible to your database user is shown."), self)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        layout.addSpacing(self.fontMetrics().height())
        self.description = QPlainTextEdit(self)
        self.description.setReadOnly(True)
        self.description.setMaximumHeight(90)
        layout.addWidget(QLabel(self.tr("Description"), self))
        layout.addWidget(self.description)
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(ANALYSIS_TABS_STYLE)
        self.columns = self._table([
            self.tr("Column"),
            self.tr("Data type"),
            self.tr("Nullable"),
            self.tr("Default"),
            self.tr("Constraints"),
            self.tr("Description"),
        ])
        self.properties = self._table([self.tr("Property"), self.tr("Value")])
        self.constraints = self._table([
            self.tr("Name"),
            self.tr("Constraints"),
            self.tr("Column"),
            self.tr("References"),
            self.tr("Definition"),
        ])
        self.tabs.addTab(self.columns, self.tr("Columns"))
        self.tabs.addTab(self.properties, self.tr("Extended properties"))
        self.tabs.addTab(self.constraints, self.tr("Constraints"))
        layout.addWidget(self.tabs)
        self.details = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)
        self.columns.itemSelectionChanged.connect(self._show_column_details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        localize_dialog_buttons(buttons)
        buttons.rejected.connect(self.reject)
        self.retry = QPushButton(self.tr("Retry"), self)
        self.retry.clicked.connect(self.retry_requested)
        buttons.addButton(self.retry, QDialogButtonBox.ButtonRole.ActionRole)
        copy = QPushButton(self.tr("Copy selected cells"), self)
        copy.clicked.connect(self._copy_selected)
        buttons.addButton(copy, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)
        self.set_loading()

    def _set_object_title(self, identity: SchemaObjectIdentity) -> None:
        template = (
            self.tr("Properties (table: {name})")
            if identity.kind == SchemaObjectKind.TABLE
            else self.tr("Properties (view: {name})")
        )
        self.setWindowTitle(template.format(name=identity.name))

    def _table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        horizontal = table.horizontalHeader()
        if horizontal is not None:
            horizontal.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            horizontal.setStretchLastSection(True)
        return table

    @staticmethod
    def _populate(table: QTableWidget, rows: list[list[str]]) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setToolTip("<qt>" + escape(value).replace("\n", "<br>") + "</qt>")
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()

    def _value[T](self, value: MetadataValue[T]) -> str:
        if value.state == MetadataState.AVAILABLE:
            if isinstance(value.value, bool):
                return self.tr("Yes") if value.value else self.tr("No")
            return str(value.value)
        return {
            MetadataState.ABSENT: self.tr("Not set"),
            MetadataState.NOT_APPLICABLE: self.tr("Not applicable"),
            MetadataState.UNSUPPORTED: self.tr("Not supported"),
            MetadataState.UNAVAILABLE: self.tr("Unavailable"),
        }[value.state]

    def _kind(self, kind: ConstraintKind) -> str:
        return {
            ConstraintKind.PRIMARY_KEY: self.tr("Primary key"),
            ConstraintKind.FOREIGN_KEY: self.tr("Foreign key"),
            ConstraintKind.UNIQUE: self.tr("Unique"),
            ConstraintKind.CHECK: self.tr("Check"),
        }[kind]

    def set_loading(self) -> None:
        """Clear any previous snapshot and present the loading state."""
        self._snapshot = None
        self.status.setText(self.tr("Loading properties..."))
        self.status.show()
        self.retry.setEnabled(False)
        self.tabs.setEnabled(False)
        self.description.clear()
        self.details.clear()
        for table in (self.columns, self.properties, self.constraints):
            table.setRowCount(0)

    def show_problem(self, message: str, *, retryable: bool = True) -> None:
        """Show a retrieval problem without changing the connection."""
        self.status.setText(message)
        self.status.show()
        self.retry.setEnabled(retryable)

    def show_connection_changed(self) -> None:
        """Invalidate the displayed snapshot and require reopening the dialog."""
        self.set_loading()
        self.show_problem(self.tr("The connection changed. Close this dialog and reopen Properties."), retryable=False)

    def show_properties(self, snapshot: ObjectProperties) -> None:
        """Display a typed snapshot without interpreting database text as HTML."""
        self._snapshot = snapshot
        self._set_object_title(snapshot.identity)
        self.status.clear()
        self.status.hide()
        self.description.setPlainText(self._value(snapshot.description))
        self.tabs.setEnabled(True)
        self.retry.setEnabled(True)
        constraints = snapshot.constraints.value or ()
        self._populate(
            self.columns,
            [
                [
                    column.name,
                    self._value(column.data_type),
                    self._value(column.nullable),
                    self._value(column.default),
                    ", ".join(self._kind(c.kind) for c in constraints if column.name in c.columns)
                    if snapshot.constraints.state == MetadataState.AVAILABLE
                    else self._value(snapshot.constraints),
                    self._value(column.description),
                ]
                for column in snapshot.columns
            ],
        )
        self._populate(
            self.properties, [[prop.name, self._value(prop.value)] for prop in snapshot.properties.value or ()]
        )
        self.tabs.setTabVisible(1, snapshot.properties.state != MetadataState.UNSUPPORTED)
        self._populate(
            self.constraints,
            [
                [
                    constraint.name or "",
                    self._kind(constraint.kind),
                    ", ".join(constraint.columns),
                    (
                        f"{constraint.referenced_object.schema}.{constraint.referenced_object.name}"
                        f" ({', '.join(constraint.referenced_columns)})"
                    )
                    if constraint.referenced_object is not None
                    else "",
                    self._value(constraint.definition),
                ]
                for constraint in constraints
            ],
        )
        if snapshot.columns:
            self.columns.selectRow(0)

    def _show_column_details(self) -> None:
        snapshot = self._snapshot
        row = self.columns.currentRow()
        if snapshot is None or row < 0 or row >= len(snapshot.columns):
            return
        column = snapshot.columns[row]
        lines = [
            column.name,
            self._value(column.description),
            f"{self.tr('Identity')}: {self._value(column.identity)}",
            f"{self.tr('Generated')}: {self._value(column.generated)}",
        ]
        lines.extend(f"{prop.name}: {self._value(prop.value)}" for prop in column.properties.value or ())
        self.details.setPlainText("\n".join(lines))

    def _copy_selected(self) -> None:
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget):
            return
        indexes = table.selectedIndexes()
        if not indexes:
            return
        selected = {(index.row(), index.column()) for index in indexes}
        rows = sorted({row for row, _column in selected})
        columns = sorted({column for _row, column in selected})
        text_rows: list[str] = []
        for row in rows:
            cells: list[str] = []
            for column in columns:
                item = table.item(row, column)
                cells.append(item.text() if item is not None and (row, column) in selected else "")
            text_rows.append("\t".join(cells))
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n".join(text_rows))
