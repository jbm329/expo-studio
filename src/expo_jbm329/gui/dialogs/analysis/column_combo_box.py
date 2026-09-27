"""Column picker combo box that shows ineligible columns as disabled choices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import QComboBox, QWidget

from expo_jbm329.services.analysis.group_comparison import MAX_GROUPS, MIN_GROUPS, ColumnExclusionReason
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from collections.abc import Sequence

    from expo_jbm329.services.analysis.group_comparison import ExcludedColumn


def exclusion_tooltip(column: ExcludedColumn) -> str:
    """Return the translated explanation of why a categorical `column` can't be chosen.

    Args:
        column: The excluded column and the reason for its exclusion.

    Returns:
        Translated tooltip text.
    """
    if column.reason is ColumnExclusionReason.TOO_FEW_VALUES:
        return QCoreApplication.translate(
            "ColumnComboBox",
            "Not available: {count} distinct values (at least {minimum} are needed).",
        ).format(count=fmt_int(column.distinct_count), minimum=fmt_int(MIN_GROUPS))
    return QCoreApplication.translate(
        "ColumnComboBox",
        "Not available: {count} distinct values (at most {maximum} are allowed).",
    ).format(count=fmt_int(column.distinct_count), maximum=fmt_int(MAX_GROUPS))


class ColumnComboBox(QComboBox):
    """A column picker listing eligible columns first, then excluded ones.

    Excluded columns are listed below a separator as disabled items whose
    tooltip explains why they can't be chosen, so the user can see that
    a column exists but is not suitable, rather than wondering where it
    went. Disabled items and the separator can't be selected by the user
    (Qt skips them for mouse, keyboard and wheel input), and
    `current_column` never reports one even if selected programmatically.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize an empty column combo box.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._eligible_count = 0

    def set_columns(
        self,
        eligible: Sequence[str],
        excluded: Sequence[ExcludedColumn] = (),
        *,
        select: str = "",
    ) -> None:
        """Replace all items with `eligible` columns followed by disabled `excluded` ones.

        Does not block signals; callers that must not react to the rebuild
        should wrap this call in ``blockSignals``.

        Args:
            eligible: Selectable column names, in display order.
            excluded: Columns shown as disabled items with an explanatory
                tooltip, below a separator. No separator is added when empty.
            select: Eligible column to select. Falls back to the first
                eligible column, or to no selection when there is none.
        """
        self.clear()
        self.addItems(list(eligible))
        self._eligible_count = len(eligible)

        if excluded:
            self.insertSeparator(self.count())
            model = self._standard_model()
            for column in excluded:
                self.addItem(column.name)
                index = self.count() - 1
                self.setItemData(index, exclusion_tooltip(column), Qt.ItemDataRole.ToolTipRole)
                item = model.item(index)
                if item is None:
                    msg = f"ColumnComboBox: missing model item at index {index}."
                    raise RuntimeError(msg)
                item.setEnabled(False)

        self.setCurrentIndex(self._eligible_index(select))

    def current_column(self) -> str:
        """Return the currently selected eligible column, or ``""`` if there is none."""
        index = self.currentIndex()
        if not 0 <= index < self._eligible_count:
            return ""
        return self.itemText(index)

    def eligible_columns(self) -> tuple[str, ...]:
        """Return the selectable column names, in display order."""
        return tuple(self.itemText(index) for index in range(self._eligible_count))

    def _eligible_index(self, column: str) -> int:
        """Return the index of eligible `column`, else of the first eligible item, else -1."""
        if self._eligible_count == 0:
            return -1
        index = self.findText(column)
        if 0 <= index < self._eligible_count:
            return index
        return 0

    def _standard_model(self) -> QStandardItemModel:
        """Return the combo box's item model, which must support per-item flags."""
        model = self.model()
        if not isinstance(model, QStandardItemModel):
            msg = "ColumnComboBox requires the default QStandardItemModel."
            raise TypeError(msg)
        return model
