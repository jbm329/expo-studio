"""Controller for the Advanced Analysis workspace dialog."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QT_TR_NOOP, QTimer

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog
from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.services.analysis.overview import DatasetOverviewResult
    from expo_jbm329.services.analysis.statistics import DescriptiveStatisticsResult
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import (
        ResultTabManager,
    )


@dataclass(frozen=True, slots=True)
class _CategoryHandler:
    """Pairs a category's background computation with its GUI rendering.

    Kept as two separate callables because Qt widgets must only ever be
    created on the GUI thread, while `compute` runs on a background pool
    thread via JobManager/AsyncOperationController.

    Attributes:
        compute: Background-safe callable turning a DataFrame into a plain
            (non-Qt) result object.
        render: GUI-thread callable turning that result object into the
            `QWidget` to display.
    """

    compute: Callable[[pd.DataFrame], object]
    render: Callable[[object], QWidget]


class AnalysisController:
    """Controller responsible for the Advanced Analysis workspace workflow.

    Each analysis category is backed by a `_CategoryHandler`. Computation
    always runs as a background job (JobManager, via
    AsyncOperationController) with a busy overlay shown over the dialog's
    result pane, so large datasets never freeze the GUI thread. Categories
    without a registered handler fall back to the not-implemented
    placeholder.
    """

    TR_NOT_IMPLEMENTED = QT_TR_NOOP("This analysis is not implemented yet.")
    TR_ANALYSIS_ERROR = QT_TR_NOOP("An error occurred while generating this analysis.")
    TR_RUNNING_ANALYSIS = QT_TR_NOOP("Running analysis…")
    TR_ANALYSIS_OPERATION = QT_TR_NOOP("generate analysis")

    @staticmethod
    def _tr(text: str) -> str:
        """Translate a UI string for this controller."""
        return tr("AnalysisController", text)

    def __init__(
        self,
        *,
        results: ResultTabManager,
        async_ops: AsyncOperationController,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the analysis controller.

        Args:
            results: ResultTabManager instance.
            async_ops: Controller running analyses as background jobs.
            logger: Optional logger instance.
        """
        self._results = results
        self._async_ops = async_ops
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        self._category_handlers: dict[AnalysisCategory, _CategoryHandler] = {
            AnalysisCategory.OVERVIEW: _CategoryHandler(
                compute=analyze_dataset_overview,
                render=self._render_overview,
            ),
            AnalysisCategory.STATISTICS: _CategoryHandler(
                compute=analyze_descriptive_statistics,
                render=self._render_statistics,
            ),
        }

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
            self._refresh_content(dialog)

        def _handle_dataset_changed(_tab_id: str) -> None:
            self._refresh_content(dialog)

        dialog.category_changed.connect(_handle_category_changed)
        dialog.dataset_changed.connect(_handle_dataset_changed)

        # Overview is already selected by the time the dialog is constructed
        # (see AnalysisDialog), but that self-emission happens before the
        # connections above exist. Deferred by one event-loop tick so the
        # dialog is already shown (and correctly sized) once the initial
        # busy overlay is created - showing an overlay on a not-yet-shown
        # widget would compute its geometry against a stale/default size.
        QTimer.singleShot(0, lambda: self._refresh_content(dialog))

        dialog.exec()

    # ------------------------------------------------------------------
    # Renderers (GUI thread only)
    # ------------------------------------------------------------------

    def _render_overview(self, result: object) -> QWidget:
        """Render the Dataset Overview view. Must run on the GUI thread."""
        return OverviewView(cast("DatasetOverviewResult", result))

    def _render_statistics(self, result: object) -> QWidget:
        """Render the Descriptive Statistics view. Must run on the GUI thread."""
        return StatisticsView(cast("DescriptiveStatisticsResult", result))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _refresh_content(self, dialog: AnalysisDialog) -> None:
        """Rebuild the content panel for the currently selected category/dataset.

        The actual computation always runs as a background job with a busy
        overlay shown over the dialog's result pane, so large datasets or
        heavier analyses never freeze the GUI thread.

        Args:
            dialog: Active Advanced Analysis dialog.
        """
        category = dialog.selected_category()
        if category is None:
            return

        handler = self._category_handlers.get(category)
        if handler is None:
            dialog.show_placeholder(self._tr(self.TR_NOT_IMPLEMENTED))
            return

        tab_id = dialog.selected_dataset_tab_id()
        if tab_id is None:
            # Defensive only: open_dialog() never opens without a dataset,
            # so the combo box always has a selection in practice.
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))
            return

        try:
            df = self._results.get_df_by_tab_id(tab_id)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.exception(
                "AnalysisController: failed to load dataset for category '%s' (tab_id=%s).",
                category,
                tab_id,
            )
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))
            return

        self._run_analysis(dialog, category, handler, tab_id, df)

    def _run_analysis(
        self,
        dialog: AnalysisDialog,
        category: AnalysisCategory,
        handler: _CategoryHandler,
        tab_id: str,
        df: pd.DataFrame,
    ) -> None:
        """Run a category's computation in the background with a busy overlay."""
        corr_id = uuid.uuid4().hex

        def _is_stale() -> bool:
            """Discard results once the user has moved on to something else."""
            return dialog.selected_category() != category or dialog.selected_dataset_tab_id() != tab_id

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> object:
            del progress_cb
            if cancel_cb is not None and cancel_cb():
                return None
            return handler.compute(df)

        def _on_result(result: object) -> None:
            if result is None:
                return
            widget = handler.render(result)
            dialog.set_content_widget(widget)

        def _on_error(_traceback: str) -> None:
            if _is_stale():
                return
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))

        self._async_ops.run_target_overlay_operation(
            target=dialog.content_panel(),
            runner="pool",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=self._tr(self.TR_RUNNING_ANALYSIS),
            scope=f"analysis:{category.value}",
            operation_name=self._tr(self.TR_ANALYSIS_OPERATION),
            stale_check=_is_stale,
            corr_id=corr_id,
        )
