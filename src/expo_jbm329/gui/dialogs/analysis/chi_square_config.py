"""Chi-square configuration widget (row + column variable pickers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QLabel, QWidget

from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.chi_square import ChiSquareResult


class ChiSquareConfigWidget(QWidget):
    """Lets the user pick the two categorical columns to test for independence.

    Mirrors `GroupComparisonConfigWidget`: a selection change always needs
    a new background computation, which `AnalysisController` dispatches
    in response to `selection_changed`. This widget never computes
    anything itself and is never recreated by that recompute.
    """

    selection_changed = pyqtSignal(str, str)  # row_column, column_column

    def __init__(self, result: ChiSquareResult, parent: QWidget | None = None) -> None:
        """Initialize the configuration widget.

        Args:
            result: The most recently computed chi-square test, used to
                populate the column pickers and their initial selection.
                Must have at least two available columns.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._available_columns = result.available_columns
        self._excluded_columns = result.excluded_columns

        layout = QFormLayout(self)

        self._row_combo = ColumnComboBox(self)
        self._row_combo.set_columns(self._available_columns, self._excluded_columns, select=result.row_column)

        self._column_combo = ColumnComboBox(self)
        self._populate_column_combo(exclude=self._row_combo.current_column(), select=result.column_column)

        layout.addRow(QLabel(self.tr("Row variable"), self), self._row_combo)
        layout.addRow(QLabel(self.tr("Column variable"), self), self._column_combo)

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._row_combo.currentTextChanged.connect(self._on_row_changed)
        self._column_combo.currentTextChanged.connect(self._on_column_changed)

    def _populate_column_combo(self, *, exclude: str, select: str) -> None:
        """Rebuild the column combo's items, excluding `exclude` (the row variable).

        Ineligible columns are listed too, as disabled items explaining why.
        """
        self._column_combo.blockSignals(True)
        try:
            self._column_combo.set_columns(
                [column for column in self._available_columns if column != exclude],
                self._excluded_columns,
                select=select,
            )
        finally:
            self._column_combo.blockSignals(False)

    def _on_row_changed(self, _row_text: str) -> None:
        """Rebuild the column combo (excluding the new row variable) and emit."""
        row_column = self._row_combo.current_column()
        if not row_column:
            return

        current_column = self._column_combo.current_column()
        self._populate_column_combo(
            exclude=row_column,
            select=current_column if current_column != row_column else "",
        )
        self._emit_selection()

    def _on_column_changed(self, _column_column: str) -> None:
        """Emit the current selection when the column combo changes."""
        self._emit_selection()

    def _emit_selection(self) -> None:
        """Emit `selection_changed` with the current ``(row, column)`` pair, if complete."""
        selection = self.current_selection()
        if selection is not None:
            self.selection_changed.emit(*selection)

    def current_selection(self) -> tuple[str, str] | None:
        """Return the currently selected ``(row_column, column_column)`` pair.

        Returns:
            The pair, or `None` if either combo has no current selection.
        """
        row_column = self._row_combo.current_column()
        column_column = self._column_combo.current_column()
        if not row_column or not column_column:
            return None
        return row_column, column_column
