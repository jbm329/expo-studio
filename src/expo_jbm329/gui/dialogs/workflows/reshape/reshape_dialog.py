"""Reshape configuration and bounded, asynchronously calculated output preview."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.gui.dialogs.workflows.reshape.dimension_delegate import COLUMN_NAME_ROLE, DTYPE_ROLE, DimensionDelegate
from expo_jbm329.services.data_operations.reshape_condition_lint import parse_condition
from expo_jbm329.services.data_operations.reshape_conditions import condition_columns
from expo_jbm329.services.data_operations.reshape_preview import (
    ReshapeError,
    ReshapeFunction,
    ReshapeMetric,
    ReshapePreview,
    ReshapeProblem,
    ReshapeRequest,
    validate_reshape,
)
from expo_jbm329.utils.format_utils import fmt_int
from expo_jbm329.utils.models import DataFrameModel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from expo_jbm329.utils.dataset_ref import DatasetRef


class ReshapeDialog(QDialog):
    """Configure dimensions and named metrics for a fixed source dataset."""

    condition_requested = pyqtSignal(object)  # ConditionEditor
    preview_requested = pyqtSignal(object)  # ReshapeRequest
    configuration_changed = pyqtSignal()

    def __init__(
        self,
        *,
        parent: QWidget | None,
        source_dataset: DatasetRef,
        source_columns: Sequence[object],
        source_dtypes: Sequence[str],
        numeric_column_positions: Sequence[int],
        datetime_column_positions: Sequence[int],
    ) -> None:
        """Initialize configuration controls and the preview panel.

        Args:
            parent: Parent widget.
            source_dataset: Fixed ready dataset captured when opening the dialog.
            source_columns: Source column labels in their original positional order.
            source_dtypes: Storage dtype labels in the same positional order.
            numeric_column_positions: Positions with integer or floating-point dtypes.
            datetime_column_positions: Positions with datetime dtypes.
        """
        super().__init__(parent)
        self._revision = 0
        self._preview_busy = False
        self._has_preview = False
        self.applied_request: ReshapeRequest | None = None
        self._source_dtypes = tuple(source_dtypes)
        self._source_columns = tuple(source_columns)
        self._condition_columns = condition_columns(self._source_columns, source_dtypes)
        if len(source_dtypes) != len(self._source_columns):
            message = "Source dtype metadata must match the number of source columns."
            raise ValueError(message)
        self._numeric_column_positions = frozenset(numeric_column_positions)
        self._datetime_column_positions = frozenset(datetime_column_positions)
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
        notice = QLabel(self.tr("Preview uses the full dataset. Apply creates a new result dataset."), self)
        notice.setWordWrap(True)
        root.addWidget(notice)

        configuration = QHBoxLayout()
        configuration.setSpacing(12)
        dimensions_box = QGroupBox(self.tr("Dimensions"), self)
        dimensions_layout = QVBoxLayout(dimensions_box)
        self.dimension_search = QLineEdit(dimensions_box)
        self.dimension_search.setPlaceholderText(self.tr("Search dimensions"))
        self.dimension_search.setAccessibleName(self.tr("Search dimensions"))
        self.dimension_search.setClearButtonEnabled(True)
        dimensions_layout.addWidget(self.dimension_search)
        self.dimensions = QListWidget(dimensions_box)
        self.dimensions.setItemDelegate(DimensionDelegate(self.dimensions))
        self.dimensions.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for position, (column, dtype) in enumerate(zip(self._source_columns, source_dtypes, strict=True)):
            item = QListWidgetItem(f"{column} [{dtype}]")
            item.setData(Qt.ItemDataRole.UserRole, position)
            item.setData(COLUMN_NAME_ROLE, str(column))
            item.setData(DTYPE_ROLE, dtype)
            item.setToolTip(f"{column}\n{dtype}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.dimensions.addItem(item)
        dimensions_layout.addWidget(self.dimensions)
        self.dimension_search.textChanged.connect(self._filter_dimensions)
        configuration.addWidget(dimensions_box, 1)

        metrics_box = QGroupBox(self.tr("Metrics"), self)
        metrics_layout = QVBoxLayout(metrics_box)
        self.source_column_guidance = QLabel(
            self.tr(
                "SUM and AVG accept integer and floating-point columns only. "
                "MIN and MAX also accept datetime columns. "
                "COUNT and COUNT DISTINCT accept any column. "
                "Changing the function clears an incompatible source selection."
            ),
            metrics_box,
        )
        self.source_column_guidance.setWordWrap(True)
        metrics_layout.addWidget(self.source_column_guidance)
        self.metrics = QTableWidget(0, 4, metrics_box)
        self.metrics.setHorizontalHeaderLabels([
            self.tr("Metric name"),
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
        self.preview_panel = preview_box
        preview_layout = QVBoxLayout(preview_box)
        self.preview_placeholder = QLabel(
            self.tr("Configure metrics and press Preview to calculate up to five output rows."), preview_box
        )
        self.preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_placeholder.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_placeholder.setWordWrap(True)
        preview_layout.addWidget(self.preview_placeholder)
        self.preview_table = QTableView(preview_box)
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setSortingEnabled(False)
        self.preview_table.hide()
        preview_layout.addWidget(self.preview_table)
        self.preview_model: DataFrameModel | None = None
        root.addWidget(preview_box, 1)

        button_row = QHBoxLayout()
        self.preview_button = QPushButton(self.tr("Preview"), self)
        self.preview_button.setAutoDefault(False)
        self.preview_button.clicked.connect(self._request_preview)
        button_row.addWidget(self.preview_button)
        button_row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is None:
            message = "Reshape requires an OK button."
            raise RuntimeError(message)
        self.apply_button = ok_button
        self.apply_button.setAutoDefault(False)
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip(notice.text())
        self.apply_button.clicked.connect(self._apply)
        localize_dialog_buttons(buttons)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)
        root.addLayout(button_row)

        self.add_metric_button.clicked.connect(self._add_metric)
        self.remove_metric_button.clicked.connect(self._remove_selected_metrics)
        self.metrics.itemSelectionChanged.connect(self._update_remove_button)
        self.metrics.itemChanged.connect(self._update_metric_readiness)
        self.metrics.itemChanged.connect(self._configuration_changed)
        self.dimensions.itemChanged.connect(self._configuration_changed)
        self._add_metric()
        self._update_remove_button()

    def _filter_dimensions(self, text: str) -> None:
        search = text.casefold()
        for position, column in enumerate(self._source_columns):
            item = self.dimensions.item(position)
            if item is not None:
                item.setHidden(search not in str(column).casefold())

    def _add_metric(self) -> None:
        row = self.metrics.rowCount()
        self.metrics.insertRow(row)
        name = QTableWidgetItem("")
        self.metrics.setItem(row, 0, name)

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
        functions.currentIndexChanged.connect(self._configuration_changed)
        update_source_columns()

        condition = ConditionEditor(self.metrics, self._condition_columns)
        condition.builder_requested.connect(lambda: self.condition_requested.emit(condition))
        condition.validity_changed.connect(self._update_apply_button)
        condition.text.textChanged.connect(self._configuration_changed)
        self.metrics.setCellWidget(row, 3, condition)

        def fill_default_name() -> None:
            if not name.text().strip() and columns.currentData() is not None:
                name.setText(f"{functions.currentText().capitalize()} {columns.currentText()}")

        columns.currentIndexChanged.connect(fill_default_name)
        columns.currentIndexChanged.connect(self._update_metric_readiness)
        columns.currentIndexChanged.connect(self._configuration_changed)
        self._update_metric_readiness()
        self._configuration_changed()

    @property
    def revision(self) -> int:
        """Return configuration revision for async stale-result guards."""
        return self._revision

    def _configuration_changed(self) -> None:
        self._revision += 1
        if self._has_preview or self._preview_busy:
            self.preview_table.hide()
            self.preview_placeholder.setText(self.tr("Preview is out of date. Press Preview to recalculate."))
        self._update_apply_button()
        self.configuration_changed.emit()

    def capture_request(self) -> ReshapeRequest:
        """Flush lint and capture an immutable, validated execution request."""
        if not self.validate_conditions():
            raise ReshapeError(ReshapeProblem.CONFIGURATION)
        dimensions = tuple(
            position
            for position in range(self.dimensions.count())
            if (item := self.dimensions.item(position)) is not None and item.checkState() == Qt.CheckState.Checked
        )
        metrics: list[ReshapeMetric] = []
        for row in range(self.metrics.rowCount()):
            name = self.metrics.item(row, 0)
            function = self.metrics.cellWidget(row, 1)
            source = self.metrics.cellWidget(row, 2)
            condition = self.metrics.cellWidget(row, 3)
            if (
                name is None
                or not isinstance(function, QComboBox)
                or not isinstance(source, QComboBox)
                or not isinstance(condition, ConditionEditor)
                or not isinstance(source.currentData(), int)
            ):
                raise ReshapeError(ReshapeProblem.CONFIGURATION)
            parsed = parse_condition(condition.text.text(), self._condition_columns)
            if parsed.diagnostics:
                raise ReshapeError(ReshapeProblem.CONFIGURATION)
            metrics.append(
                ReshapeMetric(
                    name.text().strip(),
                    ReshapeFunction(function.currentText()),
                    source.currentData(),
                    parsed.instructions,
                )
            )
        request = ReshapeRequest(dimensions, tuple(metrics))
        validate_reshape(request, self._condition_columns, self._source_dtypes)
        return request

    def _request_preview(self) -> None:
        try:
            request = self.capture_request()
        except ReshapeError as error:
            self.show_preview_problem(error)
            return
        self.preview_requested.emit(request)

    def _apply(self) -> None:
        if self._preview_busy:
            return
        try:
            request = self.capture_request()
        except ReshapeError as error:
            self.show_preview_problem(error)
            return
        self.applied_request = request
        self.accept()

    def set_preview_busy(self, busy: bool) -> None:
        """Update request controls without blocking configuration or Close."""
        self._preview_busy = busy
        if busy:
            self.preview_table.hide()
            self.preview_placeholder.setText(self.tr("Calculating preview..."))
        self._update_apply_button()

    def show_preview(self, result: ReshapePreview) -> None:
        """Present a worker result using the read-only dataframe model."""
        old_model = self.preview_model
        self.preview_model = DataFrameModel(result.frame, self.preview_table)
        self.preview_table.setModel(self.preview_model)
        if old_model is not None:
            old_model.deleteLater()
        self.preview_table.resizeColumnsToContents()
        self.preview_table.show()
        self.preview_placeholder.setText(
            self.tr("Showing {shown} of {total} output rows.").format(
                shown=fmt_int(len(result.frame)), total=fmt_int(result.total_rows)
            )
        )
        self._has_preview = True

    def show_preview_message(self, message: str) -> None:
        """Present cancellation/failure explicitly rather than stale results."""
        self.preview_table.hide()
        self.preview_placeholder.setText(message)
        self._has_preview = False

    def show_preview_problem(self, error: ReshapeError) -> None:
        """Translate an expected service failure on the GUI thread."""
        messages = {
            ReshapeProblem.CONFIGURATION: self.tr(
                "Complete every metric and correct condition errors before previewing."
            ),
            ReshapeProblem.OUTPUT_NAMES: self.tr("Output column names must be unique across dimensions and metrics."),
            ReshapeProblem.VALUE: self.tr("A condition value cannot be interpreted for column '{name}'."),
            ReshapeProblem.DATA: self.tr(
                "Cannot compare or aggregate the selected data for '{name}'. Check its values and types."
            ),
        }
        self.show_preview_message(messages[error.problem].format(name=error.name))

    @property
    def conditions_valid(self) -> bool:
        """Return current aggregate lint validity, treating pending checks as invalid."""
        return all(
            isinstance(editor := self.metrics.cellWidget(row, 3), ConditionEditor) and editor.condition_valid
            for row in range(self.metrics.rowCount())
        )

    def validate_conditions(self) -> bool:
        """Flush pending checks before a future execution dispatch."""
        for row in range(self.metrics.rowCount()):
            editor = self.metrics.cellWidget(row, 3)
            if isinstance(editor, ConditionEditor):
                editor.validate_now()
        return self.conditions_valid

    def _update_apply_button(self) -> None:
        names = [
            str(self._source_columns[position])
            for position in range(self.dimensions.count())
            if (item := self.dimensions.item(position)) is not None and item.checkState() == Qt.CheckState.Checked
        ]
        ready = self.metrics.rowCount() > 0 and self.conditions_valid
        for row in range(self.metrics.rowCount()):
            name = self.metrics.item(row, 0)
            source = self.metrics.cellWidget(row, 2)
            ready = (
                ready
                and name is not None
                and bool(name.text().strip())
                and isinstance(source, QComboBox)
                and source.currentData() is not None
            )
            if name is not None:
                names.append(name.text().strip())
        unique = len(set(names)) == len(names)
        self.preview_button.setEnabled(ready and unique and not self._preview_busy)
        self.apply_button.setEnabled(ready and unique and not self._preview_busy)
        self.apply_button.setToolTip(
            self.tr("Correct condition errors before applying.")
            if not self.conditions_valid
            else self.tr("Apply creates a new result dataset.")
        )
        self.preview_button.setToolTip(
            self.tr("Output column names must be unique across dimensions and metrics.")
            if not unique
            else self.tr("Calculate up to five output rows from the full dataset.")
        )

    def _update_metric_readiness(self) -> None:
        all_ready = True
        for row in range(self.metrics.rowCount()):
            name = self.metrics.item(row, 0)
            columns = self.metrics.cellWidget(row, 2)
            condition = self.metrics.cellWidget(row, 3)
            ready = (
                name is not None
                and bool(name.text().strip())
                and isinstance(columns, QComboBox)
                and columns.currentData() is not None
            )
            if isinstance(condition, ConditionEditor):
                condition.button.setEnabled(ready)
            all_ready = all_ready and ready
        self.add_metric_button.setEnabled(all_ready)
        self._update_apply_button()

    def _populate_source_columns(self, columns: QComboBox, function: str) -> None:
        selected_position = columns.currentData()
        columns.clear()
        columns.addItem(self.tr("Select column"), None)
        all_columns = function in {"COUNT", "COUNT DISTINCT"}
        allow_datetime = function in {"MIN", "MAX"}
        for position, column in enumerate(self._source_columns):
            if (
                all_columns
                or position in self._numeric_column_positions
                or (allow_datetime and position in self._datetime_column_positions)
            ):
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
        self._update_metric_readiness()
        self._configuration_changed()

    def _update_remove_button(self) -> None:
        self.remove_metric_button.setEnabled(bool(self.metrics.selectedIndexes()))
