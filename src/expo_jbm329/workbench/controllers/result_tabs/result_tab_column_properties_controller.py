"""Controller for handling column properties dialogs in result tabs.

This controller owns:
  • cache lookup
  • async profile orchestration
  • dialog opening

Async execution and overlay lifecycle are delegated to
AsyncOperationController.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.utils.models import DataFrameModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QTableView, QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class ResultTabColumnPropertiesController:
    """Controller for column properties dialogs."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_COULD_NOT_PERFORM = QT_TR_NOOP("Could not perform the operation:\n{error}")

    TR_PROFILING_OPERATION = QT_TR_NOOP("profile column")
    TR_PROFILING_COLUMN = QT_TR_NOOP("Profiling column: {column_name}")

    # ------------------------------------------------------------------
    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabColumnPropertiesController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("ResultTabColumnPropertiesController", text, **kwargs)

    # ------------------------------------------------------------------
    __slots__ = (
        "_async_ops",
        "_cache",
        "_dialogs",
        "_find_tab_id",
        "_get_series_semantics",
        "_logger",
        "_parent",
    )

    def __init__(
        self,
        *,
        parent: QWidget,
        dialogs: DialogService,
        logger: logging.Logger,
        async_ops: AsyncOperationController,
        col_profile_cache: ColumnProfileCache,
        find_tab_id_for_view: Callable[[QTableView], str | None],
        get_series_semantics: Callable[[QTableView, int], SeriesSemantics | None],
    ):
        """Initialize the controller.

        Args:
            parent: Parent widget for dialogs.
            dialogs: DialogService instance.
            logger: Logger instance.
            async_ops: Controller instance for managing async operations.
            col_profile_cache: ColumnProfileCache instance.
            find_tab_id_for_view: Callable resolving tab_id from a QTableView.
            get_series_semantics: Callable to infer series semantics.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._cache = col_profile_cache
        self._find_tab_id = find_tab_id_for_view
        self._get_series_semantics = get_series_semantics

    # ==================================================================
    # Public API
    # ==================================================================

    def open(self, view: QTableView, column: int) -> None:
        """Open the column properties dialog for a given view and column.

        Args:
            view: QTableView instance for which to open the dialog.
            column: Index of the column for which to open the dialog.

        Returns:
            None
        """
        if view is None or column < 0:
            return

        model = view.model()
        if not isinstance(model, DataFrameModel):
            return

        df = model.data_frame()
        if not isinstance(df, pd.DataFrame):
            return

        if column >= df.shape[1]:
            return

        col_name = str(df.columns[column])
        self._logger.debug(
            "ColumnPropertiesController: open requested for column '%s'.",
            col_name,
        )

        tab_id = self._find_tab_id(view) or "unknown"
        key = (tab_id, col_name)

        # --------------------------------------------------------------
        # Cache fast-path
        # --------------------------------------------------------------
        cached = self._cache.get(key)
        if cached is not None:
            self._logger.debug(
                "ColumnPropertiesController: cache hit (key=%s).", key
            )
            try:
                from expo_jbm329.gui.dialogs.column_properties_dialog import ColumnPropertiesDialog

                sem = self._get_series_semantics(view, column)

                dlg = ColumnPropertiesDialog(
                    parent=self._parent,
                    profile=cached,
                    semantics=sem)
                dlg.show()

            except Exception as e:
                self._fail(e)
            return

        # --------------------------------------------------------------
        # Async profiling path
        # --------------------------------------------------------------
        self._run_async_profile(
            view=view,
            df=df,
            column=column,
            col_name=col_name,
            cache_key=key,
        )

    # ==================================================================
    # Internal helpers
    # ==================================================================
    def _run_async_profile(
        self,
        *,
        view: QTableView,
        df: pd.DataFrame,
        column: int,
        col_name: str,
        cache_key: tuple[str, str],
    ) -> None:
        """Run async column profiling."""
        corr_id = uuid.uuid4().hex

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            from expo_jbm329.services.data_operations.analytics import (
                get_column_profile,
            )

            if cancel_cb and cancel_cb():
                return None

            return get_column_profile(df, col_name)

        def _apply_result(profile):
            if profile is None:
                return

            self._cache.set(cache_key, profile)

            from expo_jbm329.gui.dialogs.column_properties_dialog import (
                ColumnPropertiesDialog,
            )

            sem = self._get_series_semantics(view, column)

            self._logger.info(
                "ColumnPropertiesController: column profile generated for column '%s' (corr=%s).",
                col_name,
                corr_id,
            )

            dlg = ColumnPropertiesDialog(
                parent=self._parent,
                profile=profile,
                semantics=sem,
            )
            dlg.show()

        self._async_ops.run_with_overlay(
            view=view,
            runner="pool",
            work=_work,
            on_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_PROFILING_COLUMN,
                column_name=col_name,
            ),
            scope=f"profile:{col_name}",
            operation_name=self._tr(self.TR_PROFILING_OPERATION),
            stale_check=lambda: self._find_tab_id(view) is None,
            corr_id=corr_id,
        )

    def _fail(self, exc: Exception) -> None:
        """Standard failure handler."""
        self._logger.error(
            "ColumnPropertiesController: operation failed: %s",
            exc,
        )
        self._dialogs.critical(
            parent=self._parent,
            title=self._tr(self.TR_FAILURE),
            text=self._tr_fmt(
                self.TR_COULD_NOT_PERFORM,
                error=str(exc),
            ),
        )
