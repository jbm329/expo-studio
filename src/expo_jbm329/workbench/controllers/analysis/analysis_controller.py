"""Controller for the Advanced Analysis workspace dialog."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import (
        ResultTabManager,
    )


class AnalysisController:
    """Controller responsible for the Advanced Analysis workspace workflow.

    This currently only owns the dialog lifecycle and the not-implemented
    placeholder shown for every analysis category. Each analysis category
    will get its own handler as its implementation step lands.
    """

    TR_NOT_IMPLEMENTED = QT_TR_NOOP("This analysis is not implemented yet.")

    @staticmethod
    def _tr(text: str) -> str:
        """Translate a UI string for this controller."""
        return tr("AnalysisController", text)

    def __init__(
        self,
        *,
        results: ResultTabManager,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the analysis controller.

        Args:
            results: ResultTabManager instance.
            logger: Optional logger instance.
        """
        self._results = results
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

    def open_dialog(self, parent: QWidget) -> None:
        """Open the Advanced Analysis dialog.

        Args:
            parent: Parent widget for the dialog.
        """
        datasets = self._results.list_ready_datasets()
        if not datasets:
            return

        dialog = AnalysisDialog(
            parent=parent,
            datasets=datasets,
            active_tab_id=self._results.active_tab_id(),
        )

        def _handle_category_changed(_category_value: str) -> None:
            self._on_category_changed(dialog)

        dialog.category_changed.connect(_handle_category_changed)

        dialog.exec()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_category_changed(self, dialog: AnalysisDialog) -> None:
        """Show the not-implemented placeholder for the selected category.

        Args:
            dialog: Active Advanced Analysis dialog.
        """
        dialog.show_placeholder(self._tr(self.TR_NOT_IMPLEMENTED))
