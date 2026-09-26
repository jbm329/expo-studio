"""Group Comparison configuration widget (numeric + grouping column pickers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult


class GroupComparisonConfigWidget(QWidget):
    """Lets the user pick the numeric column and grouping column to compare.

    Unlike `StatisticsConfigWidget`, changing either selection here always
    requires a new background computation - which statistical tests apply,
    and their results, depend on *which* two columns are selected, unlike
    switching to a different precomputed column's histogram.
    `AnalysisController` listens for `selection_changed` and re-runs the
    analysis, replacing only the content pane; this widget never computes
    anything itself and is never recreated by that recompute.
    """

    selection_changed = pyqtSignal(str, str)  # numeric_column, grouping_column

    def __init__(self, result: GroupComparisonResult, parent: QWidget | None = None) -> None:
        """Initialize the configuration widget.

        Args:
            result: The most recently computed group comparison, used to
                populate the column pickers and their initial selection.
                Must have at least one available numeric column and one
                available grouping column.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._grouping_columns = result.available_grouping_columns

        layout = QFormLayout(self)

        self._numeric_combo = QComboBox(self)
        self._numeric_combo.addItems(list(result.available_numeric_columns))
        self._set_current(self._numeric_combo, result.numeric_column)

        self._grouping_combo = QComboBox(self)
        self._populate_grouping_combo(exclude=result.numeric_column, select=result.grouping_column)

        layout.addRow(QLabel(self.tr("Numeric column"), self), self._numeric_combo)
        layout.addRow(QLabel(self.tr("Grouping column"), self), self._grouping_combo)

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._numeric_combo.currentTextChanged.connect(self._on_numeric_changed)
        self._grouping_combo.currentTextChanged.connect(self._on_grouping_changed)

    def _populate_grouping_combo(self, *, exclude: str, select: str) -> None:
        """Rebuild the grouping combo's items, excluding `exclude` (the numeric column)."""
        self._grouping_combo.blockSignals(True)
        try:
            self._grouping_combo.clear()
            self._grouping_combo.addItems([column for column in self._grouping_columns if column != exclude])
            self._set_current(self._grouping_combo, select)
        finally:
            self._grouping_combo.blockSignals(False)

    @staticmethod
    def _set_current(combo: QComboBox, text: str) -> None:
        """Select `text` in `combo` if present, else leave the default selection."""
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _on_numeric_changed(self, numeric_column: str) -> None:
        """Rebuild the grouping combo (excluding the new numeric column) and emit."""
        if not numeric_column:
            return

        current_grouping = self._grouping_combo.currentText()
        self._populate_grouping_combo(
            exclude=numeric_column,
            select=current_grouping if current_grouping != numeric_column else "",
        )
        self._emit_selection()

    def _on_grouping_changed(self, _grouping_column: str) -> None:
        """Emit the current selection when the grouping combo changes."""
        self._emit_selection()

    def _emit_selection(self) -> None:
        """Emit `selection_changed` with the current ``(numeric, grouping)`` pair, if complete."""
        selection = self.current_selection()
        if selection is not None:
            self.selection_changed.emit(*selection)

    def current_selection(self) -> tuple[str, str] | None:
        """Return the currently selected ``(numeric_column, grouping_column)`` pair.

        Returns:
            The pair, or `None` if either combo has no current selection
            (e.g. transiently, right after the numeric column changed to a
            column that leaves no eligible grouping column).
        """
        numeric_column = self._numeric_combo.currentText()
        grouping_column = self._grouping_combo.currentText()
        if not numeric_column or not grouping_column:
            return None
        return numeric_column, grouping_column
