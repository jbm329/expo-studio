"""Controller for JOIN operations in the workbench UI.

This module coordinates the JOIN workflow by opening the configuration dialog,
collecting the selected tab data, and delegating the actual join operation to
the data-operation layer.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from typing import cast

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import QDialog, QTableView, QWidget

from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.join.join_dialog import (
    JoinDialog,
    JoinDialogResult,
)
from expo_jbm329.gui.dialogs.workflows.join.join_preview_dialog import JoinPreviewDialog
from expo_jbm329.services.data_operations.joins import (
    JoinMetadata,
    JoinRequest,
    join_dataframes,
)
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


class JoinController:
    """Controller responsible for orchestrating JOIN operations between tabs."""

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_LARGE_DATA_TITLE = QT_TR_NOOP("Large dataset detected")
    TR_LARGE_DATA_MSG = QT_TR_NOOP("⚠ This join may produce a very large dataset (~{rows} rows)")
    TR_LARGE_DATA_CONTINUE = QT_TR_NOOP("Do you want to continue?")
    TR_WARNING = QT_TR_NOOP("Warning")
    TR_WARNING_FLOAT = QT_TR_NOOP("Joining on float columns may lead to unpredictable results.")
    TR_UNSAFE_JOIN = QT_TR_NOOP("Unsafe join")
    TR_UNSAFE_JOIN_MSG = QT_TR_NOOP(
        "Joining on float columns with many-to-many cardinality is unsafe and has been blocked."
    )
    TR_JOIN_BLOCKED = QT_TR_NOOP("Join blocked")
    TR_JOIN_BLOCKED_MSG = QT_TR_NOOP("Estimated result too large.")

    TR_JOIN_OPERATION = QT_TR_NOOP("join datasets")
    TR_JOINING_DATASETS = QT_TR_NOOP("Joining datasets: {left} + {right}")
    TR_JOIN_COMPLETED = QT_TR_NOOP("Join completed: {left} + {right}")

    TR_JOIN_PREVIEW_OPERATION = QT_TR_NOOP("preview join")
    TR_JOIN_PREVIEWING = QT_TR_NOOP("Generating join preview: {left} + {right}")

    TR_JOIN_RESULT_TAB = QT_TR_NOOP("Joined data")
    TR_JOIN_CANCELLED = QT_TR_NOOP("Join cancelled.")

    TR_JOIN_TOO_LARGE_ABORTED = QT_TR_NOOP("Join too large, operation aborted")
    TR_JOIN_FAILED_TITLE = QT_TR_NOOP("Failure")
    TR_JOIN_FAILED_TEXT = QT_TR_NOOP("Could not complete join.\n{error}")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("JoinController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("JoinController", text, **kwargs)

    __slots__ = (
        "_async_ops",
        "_dialogs",
        "_get_active_title",
        "_get_active_view",
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
        get_active_view: Callable[[], QTableView | None],
        get_active_tab_title: Callable[[], str],
        list_tab_titles: Callable[[], Sequence[str]],
        get_df_for_tab: Callable[[str], pd.DataFrame],
        set_status: Callable[[str, int | None], None],
        logger: logging.Logger | None = None,
        dialogs: DialogService | None = None,
    ) -> None:
        """Initialize the JOIN controller.

        Args:
            parent_widget: Parent widget used for dialogs.
            async_ops: Controller managing async operations
            results: Controller managing result tabs.
            get_active_view: Returns active view widget.
            get_active_tab_title: Returns the title of the active tab.
            list_tab_titles: Returns the titles of all open tabs.
            get_df_for_tab: Returns the DataFrame for a tab title.
            set_status: Sets the status message and status bar.
            logger: Optional logger instance.
            dialogs: Optional dialog service instance.
        """
        self._parent = parent_widget
        self._async_ops = async_ops
        self._results = results
        self._get_active_view = get_active_view
        self._get_active_title = get_active_tab_title
        self._list_tab_titles = list_tab_titles
        self._get_df = get_df_for_tab
        self._set_status = set_status
        self._logger = logger if logger else logging.getLogger("applogger.ui")
        self._dialogs = dialogs if dialogs is not None else QtDialogService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def open_join_dialog(self) -> None:
        """Open the JOIN configuration dialog for the currently active tab."""
        left_tab = self._get_active_title()

        all_tabs = list(self._list_tab_titles())

        columns_map = {t: list(self._get_df(t).columns) for t in all_tabs}

        dfs = {t: self._get_df(t) for t in all_tabs}

        from collections import defaultdict

        joinable_map_dd: dict[tuple[str, str, str], set[str]] = defaultdict(set)

        for t1, df1 in dfs.items():
            for t2, df2 in dfs.items():
                if t1 == t2:
                    continue

                for c1 in df1.columns:
                    s1 = cast(pd.Series, df1[c1])

                    for c2 in df2.columns:
                        s2 = cast(pd.Series, df2[c2])

                        if self._are_joinable(s1, s2):
                            joinable_map_dd[(t1, c1, t2)].add(c2)

        # konvertera till vanlig dict (bra praxis)
        joinable_map = dict(joinable_map_dd)

        dlg = JoinDialog(
            parent=self._parent,
            all_tab_titles=all_tabs,
            left_initial=left_tab,
            get_columns_for_tab=columns_map,
            joinable_map=joinable_map,
        )

        # Optional: connect preview
        dlg.btn_preview.clicked.connect(
            lambda: self._on_preview(dlg)
        )

        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.build_result()
            self._run_join(result)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _run_join(self, cfg: JoinDialogResult) -> None:
        """Run JOIN according to the dialog configuration.

        Args:
            cfg: Dialog result containing JOIN settings.
        """
        self._logger.debug("JoinController: JOIN started")

        est_rows = self._precheck_join(cfg, parent=self._parent)
        if est_rows is None:
            return

        if est_rows > 5_000_000:
            proceed = self._dialogs.prompt_yes_no(
                self._parent,
                title=self._tr(self.TR_LARGE_DATA_TITLE),
                text=self._tr_fmt(self.TR_LARGE_DATA_MSG, rows=str(est_rows)),
                informative=self._tr(self.TR_LARGE_DATA_CONTINUE),
                default_yes=False,
            )
            if not proceed:
                return

        if est_rows > 100_000_000:
            self._dialogs.critical(
                self._parent,
                title=self._tr(self.TR_JOIN_BLOCKED),
                text=self._tr(self.TR_JOIN_BLOCKED_MSG),
            )
            return

        corr_id = uuid.uuid4().hex
        pending_handle = self._results.create_pending_tab(
            title=self._pending_result_title(),
            origin_type="join",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )

        pending_tab_id = pending_handle.tab_id
        pending_view = pending_handle.view

        def _work(*, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None, **_):
            _ = progress_cb
            _ = job_scope
            _ = job_id

            if cancel_cb is not None and cancel_cb():
                return None

            result_df = self._execute_join(cfg)

            if cancel_cb is not None and cancel_cb():
                return None

            filtered_df = self._filter_joined_columns(result_df, cfg)

            if cancel_cb is not None and cancel_cb():
                return None

            return filtered_df

        def _on_result(result_df: pd.DataFrame | None) -> None:
            """Handle JOIN result for the pending tab."""
            if result_df is None:
                self._logger.info(
                    "JoinController: JOIN cancelled (left=%s, right=%s, corr=%s, tab_id=%s)",
                    cfg.left_tab_title,
                    cfg.right_tab_title,
                    corr_id,
                    pending_tab_id,
                )

                self._results.remove_pending_tab(pending_tab_id)
                self._set_status(self._tr(self.TR_JOIN_CANCELLED), 6000)
                return

            if not isinstance(result_df, pd.DataFrame):
                self._logger.error(
                    "JoinController: JOIN returned non-DataFrame result "
                    "(corr=%s, tab_id=%s, type=%s)",
                    corr_id,
                    pending_tab_id,
                    type(result_df).__name__,
                )

                self._results.remove_pending_tab(pending_tab_id)
                return

            self._results.fulfill_pending_tab(pending_tab_id, result_df)

            self._set_status(
                self._tr_fmt(
                    self.TR_JOIN_COMPLETED,
                    left=cfg.left_tab_title,
                    right=cfg.right_tab_title,
                ),
                6000,
            )

            self._logger.info(
                "JoinController: JOIN completed on (%s = %s) type=%s "
                "estimated_rows=%s corr=%s tab_id=%s",
                cfg.left_on,
                cfg.right_on,
                cfg.join_type,
                est_rows,
                corr_id,
                pending_tab_id,
            )

        def _on_error(tb: str) -> None:
            """Handle JOIN worker failure for the pending tab."""
            self._results.remove_pending_tab(pending_tab_id)

            if "MemoryError" in tb:
                self._dialogs.critical(
                    parent=self._parent,
                    title=self._tr(self.TR_JOIN_BLOCKED),
                    text=self._tr(self.TR_JOIN_TOO_LARGE_ABORTED),
                )
                return

            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_JOIN_FAILED_TITLE),
                text=self._tr_fmt(self.TR_JOIN_FAILED_TEXT, error=tb),
            )

        def _on_finished() -> None:
            """Ensure no stale pending tab remains after worker completion."""
            record = self._results.tabs_by_id.get(pending_tab_id)
            if record is not None and record.is_pending:
                self._logger.debug(
                    "JoinController: removing stale pending JOIN tab on finished "
                    "(corr=%s, tab_id=%s)",
                    corr_id,
                    pending_tab_id,
                )
                self._results.remove_pending_tab(pending_tab_id)

        job = self._async_ops.run_target_overlay_operation(
            target=pending_view,
            runner="pool",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            on_finished=_on_finished,
            busy_message=self._tr_fmt(
                self.TR_JOINING_DATASETS,
                left=cfg.left_tab_title,
                right=cfg.right_tab_title,
            ),
            scope=f"join:{cfg.left_tab_title}:{cfg.right_tab_title}",
            operation_name=self._tr(self.TR_JOIN_OPERATION),
            timeout_ms=0,
            indeterminate=True,
            cancelable=True,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=True,
            corr_id=corr_id,
        )

        jobid = self._async_ops.job_mgr.get_job_id(job)
        if jobid is not None:
            self._results.bind_job_to_tab(pending_tab_id, jobid)
        else:
            self._logger.warning(
                "JoinController: could not bind JOIN job to pending tab (corr=%s, tab_id=%s)",
                corr_id,
                pending_tab_id,
            )

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _on_preview(self, dlg: JoinDialog) -> None:
        """Generate and show a preview of the join result.

        Args:
            dlg: Join configuration dialog instance.
        """
        self._logger.debug("JoinController: JOIN preview started")

        view = self._get_active_view()
        if view is None:
            self._logger.warning("JoinController: no active view available for async JOIN preview.")
            return

        cfg = dlg.build_result()

        est_rows = self._precheck_join(cfg, parent=dlg)
        if est_rows is None:
            return

        if est_rows > 5_000_000:
            proceed = self._dialogs.prompt_yes_no(
                self._parent,
                title=self._tr(self.TR_LARGE_DATA_TITLE),
                text=self._tr_fmt(self.TR_LARGE_DATA_MSG, rows=str(est_rows)),
                informative=self._tr(self.TR_LARGE_DATA_CONTINUE),
                default_yes=False,
            )
            if not proceed:
                self._logger.warning(
                    "Join preview aborted: too large (%s estimated rows)", est_rows
                )
                return

        if est_rows > 50_000_000:
            self._dialogs.critical(
                dlg,
                title=self._tr(self.TR_JOIN_BLOCKED),
                text=self._tr(self.TR_JOIN_BLOCKED_MSG),
            )
            return

        corr_id = uuid.uuid4().hex

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            _ = progress_cb
            if cancel_cb and cancel_cb():
                return None

            preview_df = self._execute_join(cfg, preview=True)

            if cancel_cb and cancel_cb():
                return None

            preview_df = self._filter_joined_columns(preview_df, cfg)

            counts = preview_df["join_status"].value_counts(normalize=True)

            metadata = JoinMetadata(
                match_rate=counts.get("both", 0.0),
                left_only=counts.get("left_only", 0.0),
                right_only=counts.get("right_only", 0.0),
                cardinality=self._classify_cardinality(cfg),
                estimated_rows=est_rows,
            )

            return preview_df, metadata

        def _show_preview(result):
            if result is None:
                return

            preview_df, metadata = result

            preview_dialog = JoinPreviewDialog(
                parent=dlg,
                df=preview_df,
                metadata=metadata,
            )
            preview_dialog.exec()

            self._logger.info(
                "JoinController: JOIN preview generated: left=%s right=%s keys=%s corr=%s",
                cfg.left_tab_title,
                cfg.right_tab_title,
                cfg.left_on,
                corr_id,
            )

        self._async_ops.run_with_overlay(
            view=view,
            runner="pool",
            work=_work,
            on_result=_show_preview,
            busy_message=self._tr_fmt(
                self.TR_JOIN_PREVIEWING,
                left=cfg.left_tab_title,
                right=cfg.right_tab_title,
            ),
            scope=f"join_preview:{cfg.left_tab_title}:{cfg.right_tab_title}",
            operation_name=self._tr(self.TR_JOIN_PREVIEW_OPERATION),
            stale_check=lambda: not dlg.isVisible(),
            corr_id=corr_id,
        )

    # noinspection PyMethodMayBeStatic
    def _filter_joined_columns(self, result_df, cfg):
        """Filter join result columns according to dialog selection."""
        left_suffix = f"_{cfg.left_tab_title}"
        right_suffix = f"_{cfg.right_tab_title}"

        keep_cols = []

        for col in result_df.columns:
            # --- JOIN KEYS (always keep) ---
            if col in cfg.left_on or col in cfg.right_on:
                keep_cols.append(col)
                continue

            # --- ALWAYS KEEP METADATA ---
            if col == "join_status":
                keep_cols.append(col)
                continue

            # --- LEFT SIDE COLUMNS ---
            if col.endswith(left_suffix):
                base = col[: -len(left_suffix)]  # remove suffix manually
                if base in cfg.left_selected_columns:
                    keep_cols.append(col)
                continue

            # --- RIGHT SIDE COLUMNS ---
            if col.endswith(right_suffix):
                base = col[: -len(right_suffix)]  # remove suffix manually
                if base in cfg.right_selected_columns:
                    keep_cols.append(col)
                continue

            # --- NON-SUFFIXED COLUMNS ---
            if col in cfg.left_selected_columns:
                keep_cols.append(col)
                continue
            if col in cfg.right_selected_columns:
                keep_cols.append(col)
                continue

        keep_cols = list(dict.fromkeys(keep_cols))

        # --- move join_status first ---
        if "join_status" in keep_cols:
            keep_cols = ["join_status"] + [c for c in keep_cols if c != "join_status"]

        return result_df[keep_cols]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_join(
        self,
        cfg: JoinDialogResult,
        *,
        preview: bool = False,
    ) -> pd.DataFrame:
        """Execute join and return result (optionally preview)."""
        left_suffix = f"_{cfg.left_tab_title}"
        right_suffix = f"_{cfg.right_tab_title}"

        left = self._get_df(cfg.left_tab_title)
        right = self._get_df(cfg.right_tab_title)

        req = JoinRequest(
            left=left,
            right=right,
            left_on=cfg.left_on,
            right_on=cfg.right_on,
            how=cfg.join_type,
            suffixes=(left_suffix, right_suffix),
        )

        df = join_dataframes(req)

        if preview:
            return df.sample(min(100, len(df)), random_state=1)

        return df

    # noinspection PyMethodMayBeStatic
    def _are_joinable(self, s1: pd.Series, s2: pd.Series) -> bool:
        """Check if two series can be joined."""
        return s1.dtype == s2.dtype

    def _classify_cardinality(self, cfg: JoinDialogResult) -> str:
        """Classify the cardinality of the join result."""
        left = self._get_df(cfg.left_tab_title)
        right = self._get_df(cfg.right_tab_title)

        left_unique = left[cfg.left_on[0]].is_unique
        right_unique = right[cfg.right_on[0]].is_unique

        if left_unique and right_unique:
            return "one-to-one"
        if left_unique:
            return "one-to-many"
        if right_unique:
            return "many-to-one"
        return "many-to-many"

    def _estimate_join_size(self, cfg: JoinDialogResult) -> int:
        left = self._get_df(cfg.left_tab_title)
        right = self._get_df(cfg.right_tab_title)

        col_l = cfg.left_on[0]
        col_r = cfg.right_on[0]

        # --- sample ---
        left_sample = left[col_l].sample(min(10_000, len(left)), random_state=1)
        right_sample = right[col_r].sample(min(10_000, len(right)), random_state=1)

        left_counts = left_sample.value_counts()
        right_counts = right_sample.value_counts()

        common = set(left_counts.index) & set(right_counts.index)

        est = 0
        for key in common:
            est += left_counts[key] * right_counts[key]

        # estimate
        scale = (len(left) / len(left_sample)) * (len(right) / len(right_sample))
        return int(est * scale)

    def _precheck_join(self, cfg: JoinDialogResult, *, parent: QWidget) -> int | None:
        left = self._get_df(cfg.left_tab_title)
        right = self._get_df(cfg.right_tab_title)

        s1 = left[cfg.left_on[0]]
        s2 = right[cfg.right_on[0]]

        if s1.dtype != s2.dtype:
            self._logger.warning("JoinController: dtype mismatch")
            return None

        if s1.dtype.kind == "f":
            self._dialogs.info(
                parent,
                title=self._tr(self.TR_WARNING),
                text=self._tr(self.TR_WARNING_FLOAT),
            )

        is_many_to_many = not s1.is_unique and not s2.is_unique

        if is_many_to_many:
            self._logger.warning("JoinController: many-to-many detected")

            if s1.dtype.kind == "f":
                self._dialogs.critical(
                    parent,
                    title=self._tr(self.TR_UNSAFE_JOIN),
                    text=self._tr(self.TR_UNSAFE_JOIN_MSG),
                )
                return None

        return self._estimate_join_size(cfg)

    def _pending_result_title(self) -> str:
        """Return the base title for a pending JOIN result tab."""
        return self._tr(self.TR_JOIN_RESULT_TAB)
