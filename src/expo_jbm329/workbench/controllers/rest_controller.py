"""REST controller for loading datasets from REST APIs."""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Protocol

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import QWidget

from expo_jbm329.app.settings.config_store import (
    read_rest_connections,
    write_rest_connections,
)
from expo_jbm329.gui.gui_utils import ui_invoke
from expo_jbm329.services.job_result import JobResult
from expo_jbm329.services.rest.models import RestRequestConfig
from expo_jbm329.services.rest.registry import rest_registry
from expo_jbm329.services.rest.rest_job import fetch_rest_dataset
from expo_jbm329.utils.format_utils import fmt_shape, fmt_time
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


class DisplayDataFrameProtocol(Protocol):
    """Protocol for displaying a DataFrame in results tab."""
    def __call__(self, df: pd.DataFrame, *, title: str | None) -> None:
        """Display a DataFrame in results tab."""
        ...


class RestController:
    """Controller for loading datasets from REST APIs.

    This controller is responsible for orchestrating REST-based data loading,
    including job scheduling, status updates, error handling, and displaying
    results in the workbench.
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_FETCH_STARTED = QT_TR_NOOP("Fetching data from API {name}…")
    TR_FETCH_DONE = QT_TR_NOOP("Completed: {rows} rows, {cols} columns from {name} ({elapsed_time})")
    TR_FETCH_FAILED = QT_TR_NOOP("Failed to fetch data from API {name}")
    TR_FETCH_CANCELLED = QT_TR_NOOP("API request was cancelled")

    TR_DIALOG_ERROR_TITLE = QT_TR_NOOP("REST API error")
    TR_DIALOG_ERROR_TEXT = QT_TR_NOOP("Could not load data from API:\n{error}")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("RestController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("RestController", text, **kwargs)

    _SCOPE_LOAD_REST = "load:rest"

    __slots__ = (
        "__weakref__",
        "_async_ops",
        "_dialogs",
        "_display_dataframe",
        "_logger",
        "_parent",
        "_results",
        "_set_status",
    )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def __init__(
        self,
        *,
        parent_widget: QWidget,
        async_ops: AsyncOperationController,
        results: ResultTabManager,
        display_dataframe: DisplayDataFrameProtocol,
        set_status: Callable[[str, int | None], None],
        dialogs,
        logger: logging.Logger | None = None,
    ):
        """Initialize RestController.

        Args:
            parent_widget: Parent widget for dialogs.
            async_ops: AsyncOperationController instance.
            results: ResultTabManager instance.
            display_dataframe: Callback to display dataframe.
            set_status: Callback to set status messages.
            dialogs: Dialog service.
            logger: Optional logger instance.
        """
        self._parent = parent_widget
        self._async_ops = async_ops
        self._results = results
        self._display_dataframe = display_dataframe
        self._set_status = set_status
        self._dialogs = dialogs
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

    # ==================================================================
    # Public API
    # ==================================================================
    def load_from_api(self, *, config: RestRequestConfig) -> None:
        """Load data from a REST API into a pending result tab.

        Args:
            config: REST request configuration.
        """
        corr = uuid.uuid4().hex
        scope = self._SCOPE_LOAD_REST

        self._logger.info(
            "RestController: REST load requested (corr=%s, name=%s, url=%s)",
            corr,
            config.name,
            config.url,
        )

        started_msg = self._tr_fmt(self.TR_FETCH_STARTED, name=config.name)

        pending_handle = self._results.create_pending_tab(
            title=config.name,
            origin_type="unknown",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )

        pending_tab_id = pending_handle.tab_id
        pending_view = pending_handle.view

        def _work(*, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None, **_):
            if cancel_cb is not None and cancel_cb():
                return JobResult(
                    ok=False,
                    cancelled=True,
                    error=None,
                    corr_id=corr,
                    elapsed=0.0,
                    data=None,
                )

            return fetch_rest_dataset(
                config,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
                corr_id=corr,
            )

        def _on_result(payload: object) -> None:
            """Handle REST result for the pending tab."""
            self._on_rest_loaded(
                payload,
                config.name,
                corr=corr,
                pending_tab_id=pending_tab_id,
            )

        def _on_error(err: str) -> None:
            """Handle REST error for the pending tab."""
            self._on_rest_error(
                err,
                config.name,
                corr=corr,
                pending_tab_id=pending_tab_id,
            )

        job = self._async_ops.run_target_overlay_operation(
            target=pending_view,
            runner="thread",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=started_msg,
            scope=scope,
            operation_name=self._tr_fmt(self.TR_FETCH_FAILED, name=config.name),
            timeout_ms=0,
            indeterminate=True,
            cancelable=True,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=True,
            corr_id=corr,
        )

        jobid = self._async_ops.job_mgr.get_job_id(job)
        if jobid is not None:
            self._results.bind_job_to_tab(pending_tab_id, jobid)
        else:
            self._logger.warning(
                "RestController: could not bind REST job to pending tab "
                "(corr=%s, name=%s, tab_id=%s)",
                corr,
                config.name,
                pending_tab_id,
            )

    def load_preset(self, preset_name: str) -> None:
        """Load a REST dataset from a named preset (user or sample)."""
        entry = rest_registry.get(preset_name)
        
        if not entry:
            self._logger.error("RestController: REST preset not found: %s", preset_name)
            return

        config = entry.request

        try:
            config.validate()
            self.load_from_api(config=config)

        except Exception as exc:
            self._logger.exception(
                "Failed to load REST preset '%s': %s",
                preset_name,
                exc,
            )
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_DIALOG_ERROR_TITLE),
                text=self._tr_fmt(
                    self.TR_DIALOG_ERROR_TEXT,
                    error=str(exc),
                ),
            )

    def copy_preset(self, preset_name: str) -> str | None:
        """Clone a preset into user connections and return the new name.

        Args:
            preset_name: Name of the preset to copy.

        Returns:
            The new connection name, or None if the operation failed or was cancelled.
        """
        entry = rest_registry.get(preset_name)
        if not entry:
            self._logger.error("RestController: copy_preset — preset not found: %s", preset_name)
            return None

        # Build a unique default name
        base = f"{preset_name} (copy)"
        candidate = base
        counter = 2
        while rest_registry.exists(candidate):
            candidate = f"{base} {counter}"
            counter += 1

        new_name, ok = self._dialogs.prompt_text(
            parent=self._parent,
            title=self._tr("Copy connection"),
            label=self._tr("Name for the new connection:"),
            default=candidate,
        )
        if not ok or not new_name or not new_name.strip():
            return None

        new_name = new_name.strip()
        if rest_registry.exists(new_name):
            self._dialogs.warn(
                parent=self._parent,
                title=self._tr("Name already exists"),
                text=self._tr("A connection named '{name}' already exists.").format(name=new_name),
            )
            return None

        # Serialize the source config and write it as a new user connection
        cfg = entry.request
        connections = read_rest_connections()
        connections[new_name] = {
            "url": cfg.url,
            "method": cfg.method,
            "response_path": cfg.response_path or "",
            "headers": cfg.headers or {},
            "query_params": cfg.query_params or {},
            "auth": {
                "type": cfg.auth.type if cfg.auth else "none",
                **({"token": cfg.auth.token} if cfg.auth and cfg.auth.token else {}),
            },
            **({"json_body": cfg.json_body} if cfg.json_body is not None else {}),
        }
        write_rest_connections(connections)
        rest_registry.reload_user_connections(read_rest_connections())

        self._logger.info(
            "RestController: preset '%s' copied to user connection '%s'",
            preset_name,
            new_name,
        )
        return new_name

    # ==================================================================
    # Internal handlers
    # ==================================================================
    def _on_rest_loaded(
        self,
        payload: object,
        name: str,
        *,
        corr: str | None = None,
        pending_tab_id: str | None = None,
    ) -> None:
        """Handle REST data load result for a pending tab."""
        if payload is None:
            self._logger.info(
                "RestController: REST load returned no payload (corr=%s, name=%s, tab_id=%s)",
                corr,
                name,
                pending_tab_id,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            self._set_status(self._tr(self.TR_FETCH_CANCELLED), 6000)
            return

        if not isinstance(payload, JobResult):
            self._logger.error(
                "RestController: REST result is not JobResult "
                "(corr=%s, name=%s, tab_id=%s, type=%s)",
                corr,
                name,
                pending_tab_id,
                type(payload).__name__,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            self._set_status(self._tr_fmt(self.TR_FETCH_FAILED, name=name), 8000)
            return

        if payload.cancelled:
            self._logger.info(
                "RestController: REST load cancelled (corr=%s, name=%s, tab_id=%s)",
                corr,
                name,
                pending_tab_id,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            self._set_status(self._tr(self.TR_FETCH_CANCELLED), 6000)
            return

        if not payload.ok or payload.data is None:
            err = payload.error or self._tr_fmt(self.TR_FETCH_FAILED, name=name)

            self._logger.error(
                "RestController: REST load failed (corr=%s, name=%s, tab_id=%s): %s",
                corr,
                name,
                pending_tab_id,
                err,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            self._set_status(str(err), 8000)
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_DIALOG_ERROR_TITLE),
                text=self._tr_fmt(self.TR_DIALOG_ERROR_TEXT, error=str(err)),
            )
            return

        df_obj = payload.data
        if not isinstance(df_obj, pd.DataFrame):
            self._logger.error(
                "RestController: REST load returned non-DataFrame payload "
                "(corr=%s, name=%s, tab_id=%s, type=%s)",
                corr,
                name,
                pending_tab_id,
                type(df_obj).__name__,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            self._set_status(self._tr_fmt(self.TR_FETCH_FAILED, name=name), 8000)
            return

        df = df_obj

        if pending_tab_id is not None:
            self._results.fulfill_pending_tab(pending_tab_id, df)
        else:
            self._display_dataframe(df, title=name)

        elapsed_value = payload.elapsed if isinstance(payload.elapsed, float) else 0.0
        rows, cols = fmt_shape(df)
        elapsed_time = fmt_time(elapsed_value)

        status = self._tr_fmt(
            self.TR_FETCH_DONE,
            name=name,
            rows=rows,
            cols=cols,
            elapsed_time=elapsed_time,
        )
        ui_invoke(self._set_status, status, 10000)

        self._logger.info(
            "RestController: REST load completed (corr=%s, name=%s, tab_id=%s, rows=%s, cols=%s)",
            corr,
            name,
            pending_tab_id,
            rows,
            cols,
        )

    def _on_rest_error(
            self,
            err: str | JobResult,
            name: str,
            *,
            corr: str | None = None,
            pending_tab_id: str | None = None,
    ) -> None:
        """Handle REST job error for a pending result tab."""
        if pending_tab_id is not None:
            self._results.remove_pending_tab(pending_tab_id)

        self._logger.error(
            "RestController: REST load error (corr=%s, name=%s, tab_id=%s): %s",
            corr,
            name,
            pending_tab_id,
            err,
        )

        msg = self._tr_fmt(self.TR_FETCH_FAILED, name=name)
        self._set_status(msg, 8000)

        self._dialogs.critical(
            parent=self._parent,
            title=self._tr(self.TR_DIALOG_ERROR_TITLE),
            text=self._tr_fmt(self.TR_DIALOG_ERROR_TEXT, error=str(err)),
        )
