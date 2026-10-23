"""Editable aggregation UI, without transformation or preview execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from collections.abc import Sequence

    from expo_jbm329.utils.dataset_ref import DatasetRef


class ReshapeDialog(QDialog):
    """Configure dimensions and named metrics for a fixed source dataset."""

    def __init__(
        self,
        *,
        parent: QWidget | None,
        source_dataset: DatasetRef,
        source_columns: Sequence[object],
        numeric_column_positions: Sequence[int],
    ) -> None:
        """Initialize the UI-only aggregation workspace.

        Args:
            parent: Parent widget.
            source_dataset: Fixed ready dataset captured when opening the dialog.
            source_columns: Source column labels in their original positional order.
            numeric_column_positions: Positions with integer or floating-point dtypes.
        """
        super().__init__(parent)
        self._source_columns = tuple(source_columns)
        self._numeric_column_positions = frozenset(numeric_column_positions)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        self.setWindowTitle(
            self.tr("Reshape — {dataset} ({rows} rows × {columns} columns)").format(  # noqa: RUF001
                dataset=source_dataset.title,
                rows=fmt_int(source_dataset.row_count),
                columns=fmt_int(source_dataset.column_count),
            )
        )
        self.resize(1280, 900)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        notice = QLabel(self.tr("UI only. Aggregation and preview are not available yet."), self)
        notice.setWordWrap(True)
        root.addWidget(notice)

        configuration = QHBoxLayout()
        configuration.setSpacing(12)
        dimensions_box = QGroupBox(self.tr("Dimensions"), self)
        dimensions_layout = QVBoxLayout(dimensions_box)
        self.dimensions = QListWidget(dimensions_box)
        self.dimensions.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for position, column in enumerate(self._source_columns):
            item = QListWidgetItem(str(column))
            item.setData(Qt.ItemDataRole.UserRole, position)
            item.setToolTip(str(column))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.dimensions.addItem(item)
        dimensions_layout.addWidget(self.dimensions)
        configuration.addWidget(dimensions_box, 1)

        metrics_box = QGroupBox(self.tr("Metrics"), self)
        metrics_layout = QVBoxLayout(metrics_box)
        self.source_column_guidance = QLabel(
            self.tr(
                "SUM, AVG, MAX and MIN accept integer and floating-point columns only. "
                "COUNT and COUNT DISTINCT accept any column. "
                "Changing the function clears an incompatible source selection."
            ),
            metrics_box,
        )
        self.source_column_guidance.setWordWrap(True)
        metrics_layout.addWidget(self.source_column_guidance)
        self.metrics = QTableWidget(0, 4, metrics_box)
        self.metrics.setHorizontalHeaderLabels([
            self.tr("Output column name"),
            self.tr("Function"),
            self.tr("Source column"),
            self.tr("Condition (optional)"),
        ])
        self.metrics.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.metrics.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
        self.metrics.setColumnWidth(0, 220)
        self.metrics.setColumnWidth(1, 150)
        self.metrics.setColumnWidth(2, 200)
        self.metrics.setColumnWidth(3, 260)
        metrics_layout.addWidget(self.metrics)
        metric_buttons = QHBoxLayout()
        self.add_metric_button = QPushButton(self.tr("Add metric"), metrics_box)
        self.remove_metric_button = QPushButton(self.tr("Remove selected metrics"), metrics_box)
        for button in (self.add_metric_button, self.remove_metric_button):
            button.setAutoDefault(False)
            metric_buttons.addWidget(button)
        metric_buttons.addStretch()
        metrics_layout.addLayout(metric_buttons)
        configuration.addWidget(metrics_box, 3)
        root.addLayout(configuration, 3)

        preview_box = QGroupBox(self.tr("Preview (5 rows)"), self)
        preview_layout = QVBoxLayout(preview_box)
        self.preview_placeholder = QLabel(
            self.tr("A five-row output preview will be available here in a later step."), preview_box
        )
        self.preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_placeholder.setWordWrap(True)
        preview_layout.addWidget(self.preview_placeholder)
        root.addWidget(preview_box, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.apply_button = QPushButton(self.tr("Apply"), self)
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip(notice.text())
        buttons.addButton(self.apply_button, QDialogButtonBox.ButtonRole.ApplyRole)
        localize_dialog_buttons(buttons)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.add_metric_button.clicked.connect(self._add_metric)
        self.remove_metric_button.clicked.connect(self._remove_selected_metrics)
        self.metrics.itemSelectionChanged.connect(self._update_remove_button)
        self._add_metric()
        self._update_remove_button()

    def _add_metric(self) -> None:
        row = self.metrics.rowCount()
        self.metrics.insertRow(row)
        self.metrics.setItem(row, 0, QTableWidgetItem(""))

        functions = QComboBox(self.metrics)
        for function in ("SUM", "AVG", "COUNT", "COUNT DISTINCT", "MAX", "MIN"):
            functions.addItem(function, function)
        functions.setAccessibleName(self.tr("Function"))
        self.metrics.setCellWidget(row, 1, functions)

        columns = QComboBox(self.metrics)
        columns.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        columns.setAccessibleName(self.tr("Source column"))
        columns.currentTextChanged.connect(columns.setToolTip)
        self.metrics.setCellWidget(row, 2, columns)

        def update_source_columns() -> None:
            self._populate_source_columns(columns, functions.currentText())

        functions.currentIndexChanged.connect(update_source_columns)
        update_source_columns()

        condition = QTableWidgetItem("")
        condition.setToolTip(self.tr("SQL-style condition text only. Not validated or executed."))
        self.metrics.setItem(row, 3, condition)

    def _populate_source_columns(self, columns: QComboBox, function: str) -> None:
        selected_position = columns.currentData()
        columns.clear()
        columns.addItem(self.tr("Select column"), None)
        all_columns = function in {"COUNT", "COUNT DISTINCT"}
        for position, column in enumerate(self._source_columns):
            if all_columns or position in self._numeric_column_positions:
                columns.addItem(str(column), position)
                columns.setItemData(columns.count() - 1, str(column), Qt.ItemDataRole.ToolTipRole)
        if selected_position is not None:
            selected_index = columns.findData(selected_position)
            if selected_index >= 0:
                columns.setCurrentIndex(selected_index)

    def _remove_selected_metrics(self) -> None:
        rows = {index.row() for index in self.metrics.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.metrics.removeRow(row)
        self._update_remove_button()

    def _update_remove_button(self) -> None:
        self.remove_metric_button.setEnabled(bool(self.metrics.selectedIndexes()))
