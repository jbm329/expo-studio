"""Join-facing adapters for shared typed column-default editors."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from expo_jbm329.gui.dialogs.workflows.column_fill_editor import (
    FILL_COLUMN_ROLE,
    FILL_VALUE_ROLE,
    ColumnFillDelegate,
    ColumnFillValueDialog,
)
from expo_jbm329.gui.dialogs.workflows.column_fill_editor import display_fill as display_join_fill
from expo_jbm329.utils.i18n_utils import translate

if TYPE_CHECKING:
    from PyQt6.QtCore import QLocale
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.services.data_operations.column_defaults import ColumnFill, FillColumn

__all__ = ["FILL_COLUMN_ROLE", "FILL_VALUE_ROLE", "JoinFillDelegate", "JoinFillValueDialog", "display_join_fill"]


class JoinFillValueDialog(ColumnFillValueDialog):
    """Keep the join picker API and canonical operation-specific wording."""

    def __init__(
        self,
        parent: QWidget | None,
        column: FillColumn,
        initial: ColumnFill,
        dialogs: DialogService,
        *,
        numeric_locale: QLocale | None = None,
    ) -> None:
        """Create a shared picker using the established join translations."""
        super().__init__(
            parent,
            column,
            initial,
            dialogs,
            title=translate("JoinFillValueDialog", "If no match"),
            object_hint=translate(
                "JoinFillValueDialog",
                "Text defaults require text-only source values. This is checked when the join runs.",
            ),
            numeric_locale=numeric_locale,
        )


class JoinFillDelegate(ColumnFillDelegate):
    """Retain the join delegate constructor and lazy picker creation."""

    def __init__(self, parent: QWidget, dialogs: DialogService) -> None:
        """Capture join-specific wording before opening any editor."""
        super().__init__(
            parent,
            dialogs,
            title=translate("JoinFillValueDialog", "If no match"),
            object_hint=translate(
                "JoinFillValueDialog",
                "Text defaults require text-only source values. This is checked when the join runs.",
            ),
        )

    @override
    def _create_dialog(self, column: FillColumn, initial: ColumnFill) -> JoinFillValueDialog:
        return JoinFillValueDialog(
            self._parent_widget,
            column,
            initial,
            self._dialogs,
            numeric_locale=self._numeric_locale,
        )
