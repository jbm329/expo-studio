"""Thin orchestration for the Reshape configuration skeleton."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import QMessageBox

from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.utils.i18n_utils import translate

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


class ReshapeController:
    """Open an aggregation configuration bound to the active ready dataset."""

    TR_UNAVAILABLE = QT_TR_NOOP("Reshape unavailable")
    TR_READY_DATASET_REQUIRED = QT_TR_NOOP("Select a ready result dataset before opening Reshape.")

    def __init__(
        self,
        *,
        parent_widget: QWidget,
        results: ResultTabManager,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the controller with explicit workbench dependencies.

        Args:
            parent_widget: Parent for configuration and warning dialogs.
            results: Manager owning dataset readiness and identity.
            logger: Optional UI logger.
        """
        self._parent = parent_widget
        self._results = results
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

    @staticmethod
    def _tr(text: str) -> str:
        return translate("ReshapeController", text)

    def open_reshape_dialog(self) -> None:
        """Capture the active dataset's metadata and open the UI-only dialog."""
        tab_id = self._results.active_tab_id()
        record = self._results.tabs_by_id.get(tab_id) if tab_id is not None else None
        if record is None or not record.is_ready or record.df is None:
            self._logger.warning("Reshape was requested without a ready active dataset.")
            QMessageBox.warning(
                self._parent,
                self._tr(self.TR_UNAVAILABLE),
                self._tr(self.TR_READY_DATASET_REQUIRED),
            )
            return

        dataset = DatasetRef(
            tab_id=record.tab_id,
            title=record.title,
            row_count=len(record.df),
            column_count=len(record.df.columns),
        )
        dialog = ReshapeDialog(
            parent=self._parent,
            source_dataset=dataset,
            source_columns=list(record.df.columns),
        )
        dialog.exec()
