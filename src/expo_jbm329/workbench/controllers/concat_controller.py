"""Controller for CONCAT operations in the workbench UI.

This module provides a thin orchestration layer that opens the CONCAT dialog,
collects the selected input tables, and delegates the actual DataFrame
concatenation to the service layer.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, cast

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP, QObject
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.gui.dialogs.workflows.concat.concat_dialog import (
    ConcatDialog,
    ConcatDialogResult,
)
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


class ConcatController:
    """Controller for CONCAT operations between open result tabs."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_CONCAT_OPERATION = QT_TR_NOOP("concatenate datasets")
    TR_CONCATENATING_DATASETS = QT_TR_NOOP("Concatenating datasets: {left} + {right}")
    TR_CONCAT_COMPLETED = QT_TR_NOOP("Concatenated datasets: {left} + {right}")
    TR_CONCAT_CANCELLED = QT_TR_NOOP("Concatenation cancelled")
    TR_CONCAT_RESULT_TAB = QT_TR_NOOP("Concatenated data")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ConcatController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt("ConcatController", text, **kwargs)

    __slots__ = (
        "_async_ops",
        "_get_active_title",
        "_get_df",
        "_list_tab_titles",
        "_logger",
        "_parent",
        "_results",
        "_set_status",
    )

    def __init__(
        self,
        *,
        parent_widget: QWidget,
        async_ops: AsyncOperationController,
        results: ResultTabManager,
        get_active_tab_title: Callable[[], str],
        list_tab_titles: Callable[[], Sequence[str]],
        get_df_for_tab: Callable[[str], pd.DataFrame],
        set_status: Callable[[str, int | None], None],
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            parent_widget: Parent widget used for dialogs.
            async_ops: Controller managing async operations.
            results: Controller managing result tabs.
            get_active_tab_title: Returns the title of the currently active tab.
            list_tab_titles: Returns the titles of all available tabs.
            get_df_for_tab: Returns the DataFrame for a given tab title.
            set_status: Sets the status text in the status bar.
            logger: Optional logger instance.
        """
        self._parent = parent_widget
        self._async_ops = async_ops
        self._results = results
        self._get_active_title = get_active_tab_title
        self._list_tab_titles = list_tab_titles
        self._get_df = get_df_for_tab
        self._set_status = set_status
        self._logger = logger or logging.getLogger("applogger.ui")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def open_concat_dialog(self) -> None:
        """Open the CONCAT configuration dialog for the active tab."""
        left_tab = self._get_active_title()
        all_tabs = list(self._list_tab_titles())

        right_tabs = [t for t in all_tabs if t != left_tab]

        if not right_tabs:
            self._logger.warning("ConcatController: no second dataset available.")
            return

        left_df = self._get_df(left_tab)
        left_cols = list(left_df.columns)

        right_cols_map: dict[str, Sequence[str]] = {tab: list(self._get_df(tab).columns) for tab in right_tabs}

        dlg = ConcatDialog(
            parent=self._parent,
            left_tab_title=left_tab,
            right_tab_titles=right_tabs,
            left_columns=left_cols,
            right_columns_map=right_cols_map,
        )

        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.build_result()
            self._run_concat(result)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _run_concat(self, cfg: ConcatDialogResult) -> None:
        """Run CONCAT according to the dialog configuration.

        Args:
            cfg: Dialog result containing CONCAT settings.
        """
        self._logger.debug("ConcatController: CONCAT started")

        corr_id = uuid.uuid4().hex
        pending_handle = self._results.create_pending_tab(
            title=self._pending_result_title(),
            origin_type="concat",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )

        pending_tab_id = pending_handle.tab_id
        pending_view = pending_handle.view

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            job_id: str | None = None,
            job_scope: str | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            del progress_cb, job_scope, job_id

            if cancel_cb is not None and cancel_cb():
                return None

            left_df = self._get_df(cfg.left_tab_title)
            right_df = self._get_df(cfg.right_tab_title)

            if cancel_cb is not None and cancel_cb():
                return None

            result_df = concat_dataframes(
                ConcatRequest(
                    left=left_df,
                    right=right_df,
                    remove_duplicates=cfg.remove_duplicates,
                )
            )

            if cancel_cb is not None and cancel_cb():
                return None

            return result_df

        def _on_result(result_df: pd.DataFrame | None) -> None:
            """Handle CONCAT result for the pending tab."""
            if result_df is None:
                self._logger.info(
                    "ConcatController: CONCAT cancelled (left=%s, right=%s, corr=%s, tab_id=%s)",
                    cfg.left_tab_title,
                    cfg.right_tab_title,
                    corr_id,
                    pending_tab_id,
                )

                self._results.remove_pending_tab(pending_tab_id)
                self._set_status(self._tr(self.TR_CONCAT_CANCELLED), 6000)
                return

            if not isinstance(result_df, pd.DataFrame):
                self._logger.error(
                    "ConcatController: CONCAT returned non-DataFrame result (corr=%s, tab_id=%s, type=%s)",
                    corr_id,
                    pending_tab_id,
                    type(result_df).__name__,
                )

                self._results.remove_pending_tab(pending_tab_id)
                return

            self._results.fulfill_pending_tab(pending_tab_id, result_df)

            self._set_status(
                self._tr_fmt(
                    self.TR_CONCAT_COMPLETED,
                    left=cfg.left_tab_title,
                    right=cfg.right_tab_title,
                ),
                6000,
            )

            self._logger.info(
                "ConcatController: CONCAT completed: %s + %s (remove_duplicates=%s corr=%s tab_id=%s)",
                cfg.left_tab_title,
                cfg.right_tab_title,
                cfg.remove_duplicates,
                corr_id,
                pending_tab_id,
            )

        def _on_finished() -> None:
            """Ensure no stale pending tab remains after worker completion."""
            record = self._results.tabs_by_id.get(pending_tab_id)
            if record is not None and record.is_pending:
                self._logger.debug(
                    "ConcatController: removing stale pending CONCAT tab on finished (corr=%s, tab_id=%s)",
                    corr_id,
                    pending_tab_id,
                )
                self._results.remove_pending_tab(pending_tab_id)

        job = self._async_ops.run_target_overlay_operation(
            target=pending_view,
            runner="pool",
            work=_work,
            on_result=_on_result,
            on_finished=_on_finished,
            busy_message=self._tr_fmt(
                self.TR_CONCATENATING_DATASETS,
                left=cfg.left_tab_title,
                right=cfg.right_tab_title,
            ),
            scope=f"concat:{cfg.left_tab_title}:{cfg.right_tab_title}",
            operation_name=self._tr(self.TR_CONCAT_OPERATION),
            timeout_ms=0,
            indeterminate=True,
            cancelable=True,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=False,
            corr_id=corr_id,
        )

        jobid = self._async_ops.job_mgr.get_job_id(cast("QObject | None", job))
        if jobid is not None:
            self._results.bind_job_to_tab(pending_tab_id, jobid)
        else:
            self._logger.warning(
                "ConcatController: could not bind CONCAT job to pending tab (corr=%s, tab_id=%s)",
                corr_id,
                pending_tab_id,
            )

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------
    def _pending_result_title(self) -> str:
        """Return the base title for a pending CONCAT result tab."""
        return self._tr(self.TR_CONCAT_RESULT_TAB)
