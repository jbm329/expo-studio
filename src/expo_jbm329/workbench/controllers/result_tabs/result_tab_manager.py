"""Module for managing the result tabs in the Expo workbench.

This module provides functionality to create, manage, and interact with result tabs within the Expo workbench.
It includes classes for handling cell actions, column properties, and header context menus,
as well as integration with the GUI and data services.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP, QPoint, Qt, QThread
from PyQt6.QtGui import QAction, QFontMetrics
from PyQt6.QtWidgets import (
    QApplication,
    QHeaderView,
    QMenu,
    QStyledItemDelegate,
    QTableView,
    QTabWidget,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.gui_utils import ui_invoke
from expo_jbm329.gui.menus.result_tab_cell_context_menu import (
    ResultTabCellContextMenu,
)
from expo_jbm329.gui.menus.result_tab_column_header_context_menu import (
    ResultTabColumnHeaderContextMenu,
)
from expo_jbm329.gui.menus.result_tab_header_context import (
    ResultTabHeaderContext,
    build_header_context,
)
from expo_jbm329.services.data_profile.semantics import SeriesSemantics, infer_series_semantics
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.utils.models import DataFrameModel
from expo_jbm329.utils.visualization_models import VisualizationDatasetRef
from expo_jbm329.workbench.controllers.result_tabs.reslut_tab_header_clean_actions import (
    ResultTabHeaderCleanActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_cell_actions import (
    ResultTabCellActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_column_presentation_delegate import (
    ResultTabColumnPresentationDelegate,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_column_properties_controller import (
    ResultTabColumnPropertiesController,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_category_actions import (
    ResultTabHeaderCategoryActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_column_actions import (
    ResultTabHeaderColumnActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_dtype_actions import (
    ResultTabHeaderDtypeActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_fill_actions import (
    ResultTabHeaderFillActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_filter_actions import (
    ResultTabHeaderFilterActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_sort_actions import (
    ResultTabHeaderSortActions,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_undo_manager import (
    ResultTabUndoManager,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.busy_overlay_controller import BusyOverlayController
    from expo_jbm329.workbench.controllers.concat_controller import ConcatController
    from expo_jbm329.workbench.controllers.derived_column_controller import DerivedColumnController
    from expo_jbm329.workbench.controllers.join_controller import JoinController


# ======================================================================
# Types & Data Structures
# ======================================================================
class ResultTabState(StrEnum):
    """Lifecycle state for a result tab."""

    PENDING = "pending"
    READY = "ready"


ResultOrigin = Literal["file", "sql", "derived", "join", "concat", "unknown"]


@dataclass(slots=True)
class ResultTabRecord:
    """Internal state record for a result tab.

    This record is the new internal source of truth for tab lifecycle and
    metadata. A tab may exist in a pending state before any DataFrame has
    been loaded into it.

    Attributes:
        tab_id: Stable internal identifier for the tab.
        view: The QTableView associated with the tab.
        title: Current visible tab title.
        state: Lifecycle state for the tab.
        df: DataFrame currently associated with the tab, if any.
        job_id: Optional background job associated with the tab.
        origin_type: Logical origin of the tab content.
        remove_on_cancel: Whether the tab should be removed when the job is cancelled.
        remove_on_error: Whether the tab should be removed when the job fails.
        close_cancels_job: Whether closing the tab should request cancellation
            of the associated job when the tab is still pending.
    """

    tab_id: str
    view: QTableView
    title: str
    state: ResultTabState = ResultTabState.READY
    df: pd.DataFrame | None = None
    job_id: str | None = None
    origin_type: ResultOrigin = "unknown"
    remove_on_cancel: bool = True
    remove_on_error: bool = True
    close_cancels_job: bool = True

    @property
    def is_pending(self) -> bool:
        """Return True if the tab is currently in pending state."""
        return self.state == ResultTabState.PENDING

    @property
    def is_ready(self) -> bool:
        """Return True if the tab is currently ready."""
        return self.state == ResultTabState.READY


@dataclass(frozen=True, slots=True)
class ResultTabHandle:
    """Opaque handle returned for a managed result tab.

    Attributes:
        tab_id: Stable internal identifier for the tab.
        view: View associated with the tab.
    """

    tab_id: str
    view: QTableView


class ResultTabManager:
    """Controller for managing result tabs in the Expo workbench."""

    # --------------------------------------------------------------
    # i18n markers
    # --------------------------------------------------------------

    # Errors and exceptions
    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_COULD_NOT_READ_COLUMN = QT_TR_NOOP("Could not read column:\n{error}")
    TR_COULD_NOT_LOAD_DATA = QT_TR_NOOP("Could not load data: \n{error}")
    TR_COULD_NOT_UPDATE_DATA = QT_TR_NOOP("Could not update data: \n{error}")
    TR_COULD_NOT_PERFORM = QT_TR_NOOP("Could not perform the operation:\n{error}")

    TR_NOT_AVAILABLE = QT_TR_NOOP("Not available")
    TR_NO_DATA_AVAILABLE = QT_TR_NOOP("No data available for this view")
    TR_INVALID_INDEX = QT_TR_NOOP("Invalid column index: {column}")
    TR_COLUMN_NOT_AVAILABLE = QT_TR_NOOP("Column not available anymore.")

    # Undo
    TR_UNDO = QT_TR_NOOP("Undo")
    TR_NOTHING_TO_UNDO = QT_TR_NOOP("Nothing to undo.")
    TR_LAST_ACTION_UNDONE = QT_TR_NOOP("Last action undone")
    TR_RESTORING_STATE = QT_TR_NOOP("Restoring previous state…")

    # Tab context menu
    TR_RENAME_TAB = QT_TR_NOOP("Rename tab")
    TR_NEW_NAME = QT_TR_NOOP("New name:")
    TR_RENAME = QT_TR_NOOP("Rename…")
    TR_CLOSE = QT_TR_NOOP("Close")
    TR_CLOSE_OTHERS = QT_TR_NOOP("Close others")
    TR_DERIVED_COLUMN = QT_TR_NOOP("Derived column…")
    TR_JOIN = QT_TR_NOOP("Join…")
    TR_CONCATENATE = QT_TR_NOOP("Concatenate…")

    # Messages
    TR_PROCESSING_DATA = QT_TR_NOOP("Processing data…")
    TR_UPDATING_TABLE = QT_TR_NOOP("Updating table…")
    TR_LOADING_DATA = QT_TR_NOOP("Loading data…")
    TR_PREPARING_DATASET = QT_TR_NOOP("Preparing dataset…")
    TR_PENDING = QT_TR_NOOP("pending…")
    TR_FORMATTING_CELLS = QT_TR_NOOP("Formatting cell values…")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabManager", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("ResultTabManager", text, **kwargs)

    __slots__ = (
        "__weakref__",
        "_async_ops",
        "_busy_overlay",
        "_cancel_job",
        "_cell_actions",
        "_cell_context_menu",
        "_closing_tabs",
        "_col_profile_cache",
        "_column_properties",
        "_concat_controller",
        "_derived_column_controller",
        "_dialogs",
        "_formatting_enabled",
        "_header_category_actions",
        "_header_clean_actions",
        "_header_column_actions",
        "_header_dtype_actions",
        "_header_fill_actions",
        "_header_filter_actions",
        "_header_menu",
        "_header_sort_actions",
        "_join_controller",
        "_last_df",
        "_logger",
        "_na_rep",
        "_notify_has_data_cbs",
        "_notify_toolbar_multi_dataset_cb",
        "_parent",
        "_result_counter",
        "_set_shape",
        "_set_status",
        "_tabs",
        "_tabs_by_id",
        "_undo",
        "_update_undo_enabled",
    )

    # ==============================================================
    # CONSTRUCTOR & INITIALIZATION
    # ==============================================================
    def __init__(
        self,
        *,
        parent_widget: QWidget,
        tabs: QTabWidget,
        busy_overlay: BusyOverlayController,
        async_ops: AsyncOperationController,
        col_profile_cache: ColumnProfileCache,
        set_status: Callable[[str, int | None], None],
        dialogs: DialogService | None = None,
        set_shape: Callable[[int | None, int | None], None] | None = None,
        update_undo_enabled: Callable[[], None] | None = None,
        cancel_job: Callable[[str], bool] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize a ResultTabManager."""
        self._parent = parent_widget
        self._tabs = tabs
        self._busy_overlay = busy_overlay
        self._async_ops = async_ops
        self._col_profile_cache = col_profile_cache
        self._join_controller = None
        self._concat_controller = None
        self._derived_column_controller = None
        self._set_status = set_status
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._set_shape = set_shape if set_shape is not None else (lambda r, c: None)
        self._update_undo_enabled = update_undo_enabled
        self._cancel_job = cancel_job
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        # --- State & storage ---
        self._na_rep = ""
        self._tabs_by_id: dict[str, ResultTabRecord] = {}
        self._notify_has_data_cbs: list[Callable[[bool], None]] = []
        self._result_counter = 1
        self._last_df: pd.DataFrame | None = None
        self._closing_tabs: bool = False
        self._notify_toolbar_multi_dataset_cb: Callable[[bool], None] | None = None
        self._formatting_enabled: bool = False

        # --- Undo system ---
        self._init_undo()

        # --- UI components (menus) ---
        self._init_menus()

        # --- Controllers ---
        self._init_header_actions()
        self._init_other_controllers()

    # ==============================================================
    # INITIALIZATION
    # ==============================================================

    def _init_undo(self) -> None:
        """Initialize undo system."""
        self._undo = ResultTabUndoManager(
            logger=self._logger,
            on_state_changed=self._notify_undo_state_changed,
            undo_limit_per_tab=20,
            max_size_allow_undo_mb=100,
        )

    def _init_menus(self) -> None:
        """Initialize menus."""
        self._header_menu = ResultTabColumnHeaderContextMenu(parent=self._parent)
        self._cell_context_menu = ResultTabCellContextMenu(parent=self._parent)

    def _init_header_actions(self) -> None:
        """Initialize all header-related action controllers."""
        self._header_clean_actions = self._make_header_action(ResultTabHeaderCleanActions)
        self._header_dtype_actions = self._make_header_action(ResultTabHeaderDtypeActions)
        self._header_category_actions = self._make_header_action(ResultTabHeaderCategoryActions)
        self._header_column_actions = self._make_header_action(ResultTabHeaderColumnActions)
        self._header_sort_actions = self._make_header_action(ResultTabHeaderSortActions)

        # Special cases
        self._header_filter_actions = ResultTabHeaderFilterActions(
            parent=self._parent,
            dialogs=self._dialogs,
            logger=self._logger,
            async_ops=self._async_ops,
            resolve_df_col_series=self._resolve_df_col_series,
            get_series_semantics=self.get_series_semantics,
            apply_new_dataframe=self._apply_without_cache_invalidation,
        )

        self._header_fill_actions = ResultTabHeaderFillActions(
            parent=self._parent,
            dialogs=self._dialogs,
            logger=self._logger,
            async_ops=self._async_ops,
            resolve_df_col_series=self._resolve_df_col_series,
            get_series_semantics=self.get_series_semantics,
            apply_new_dataframe=self._apply_with_cache_invalidation,
        )

    def _init_other_controllers(self) -> None:
        """Initialize remaining controllers."""
        self._cell_actions = ResultTabCellActions(
            parent=self._parent,
            dialogs=self._dialogs,
            logger=self._logger,
            async_ops=self._async_ops,
            apply_new_dataframe=self._apply_with_cache_invalidation,
        )

        self._column_properties = ResultTabColumnPropertiesController(
            parent=self._parent,
            dialogs=self._dialogs,
            logger=self._logger,
            async_ops=self._async_ops,
            col_profile_cache=self._col_profile_cache,
            find_tab_id_for_view=self._find_tab_id_for_view,
            get_series_semantics=self.get_series_semantics,
        )

    # ==================================================================
    # Settings
    # ==================================================================

    def reload_settings(self, settings: dict) -> None:
        """Synchronize ResultTabManager with updated global settings."""
        self._undo.reload_settings(settings)

    # ==============================================================
    # PUBLIC API (ENTRY POINTS)
    # ==============================================================
    def display_dataframe(self, df: pd.DataFrame, *, title: str | None = None):
        """Display a pandas DataFrame inside a new QTableView tab.

        Args:
            df: The pandas DataFrame to display.
            title: Optional title for the new tab. If None, a default title will be generated.

        Returns:
            None
        """
        self._logger.debug(
            "ResultTabManager: request to display DataFrame (rows=%s, cols=%s, title=%s)",
            len(df) if isinstance(df, pd.DataFrame) else "?",
            len(df.columns) if isinstance(df, pd.DataFrame) else "?",
            title,
        )

        # Ensure code runs on the Qt GUI thread (thread trampoline)
        app = QApplication.instance()
        if app is not None and QThread.currentThread() is not app.thread():
            ui_invoke(self.display_dataframe, df, title=title)
            return

        # Defensive DataFrame coercion
        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
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
            ) as e:
                self._dialogs.critical(
                    self._parent,
                    self._tr(self.TR_FAILURE),
                    self._tr_fmt(self.TR_COULD_NOT_LOAD_DATA, error=str(e)),
                )
                return

        handle = self.create_pending_tab(
            title=title,
            origin_type="unknown",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )

        self._logger.debug(
            "ResultTabManager: creating DataFrame in pending tab (tab_id=%s, title=%s).",
            handle.tab_id,
            title,
        )

        self.fulfill_pending_tab(handle.tab_id, df)

        self._logger.debug("ResultTabManager: display dataframe after creating tab (tab_count=%s)", self._tabs.count())

    def apply_to_active_tab(
        self,
        df: pd.DataFrame,
        *,
        status: str,
        message: str | None = None,
        invalidate_cache: bool = True,
    ) -> None:
        """Apply a new DataFrame to the currently active tab.

        Args:
            df: DataFrame to apply to the active tab.
            status: Status message to display in the tab.
            message: Optional message to display in the tab.
            invalidate_cache: Whether to invalidate the cache for the tab.

        Returns:
            None
        """
        index = self._tabs.currentIndex()
        if index < 0:
            return

        widget = self._tabs.widget(index)
        if not isinstance(widget, QTableView):
            return

        view: QTableView = widget

        self._run_with_busy_overlay(
            view,
            lambda: self._apply_new_dataframe_to_view(
                view,
                df,
                invalidate_cache=invalidate_cache,
                status=status,
            ),
            message=message or self._tr(self.TR_UPDATING_TABLE),
        )

    def create_new_result_tab(self, df: pd.DataFrame, title: str | None = None):
        """Create a new result tab with given dataframe."""
        self.display_dataframe(df, title=title)

    def create_pending_tab(
        self,
        *,
        title: str | None,
        origin_type: ResultOrigin = "unknown",
        remove_on_cancel: bool = True,
        remove_on_error: bool = True,
        close_cancels_job: bool = True,
    ) -> ResultTabHandle:
        """Create a new pending result tab.

        A pending tab is a real result tab that exists before any DataFrame has
        been loaded into it. It can later be fulfilled or removed.

        Args:
            title: Visible base title for the tab. If None, a default title is generated.
            origin_type: Logical origin type for the tab.
            remove_on_cancel: Whether the tab should be removed on cancellation.
            remove_on_error: Whether the tab should be removed on failure.
            close_cancels_job: Whether closing the tab should cancel an associated
                pending job.

        Returns:
            A lightweight handle identifying the created pending tab.
        """
        if title is None or not str(title).strip():
            normalized_title = f"Dataset{self._result_counter}"
            self._result_counter += 1
        else:
            normalized_title = str(title).strip()

        normalized_title = self._unique_title(normalized_title)
        visible_title = self._pending_title(normalized_title)

        view = self._create_result_view()
        tab_id = uuid.uuid4().hex

        record = self._make_tab_record(
            tab_id=tab_id,
            view=view,
            title=normalized_title,
            df=None,
            state=ResultTabState.PENDING,
            job_id=None,
            origin_type=origin_type,
            remove_on_cancel=remove_on_cancel,
            remove_on_error=remove_on_error,
            close_cancels_job=close_cancels_job,
        )

        self._tabs.blockSignals(True)
        try:
            tab_index = self._tabs.addTab(view, visible_title)

            tab_bar = self._tabs.tabBar()
            if tab_bar is not None:
                tab_bar.setTabData(tab_index, tab_id)

            self._tabs_by_id[tab_id] = record
            self._undo.register_tab(tab_id)

            self._tabs.setCurrentIndex(tab_index)

        finally:
            self._tabs.blockSignals(False)

        self._last_df = None
        self._emit_shape(None)
        self._notify_undo_state_changed()
        self._emit_toolbar_data_state()
        self._emit_toolbar_multi_dataset_state()

        self._logger.info(
            "ResultTabManager: created pending tab (tab_id=%s, title=%s, origin=%s).",
            tab_id,
            normalized_title,
            origin_type,
        )

        return self._make_tab_handle(record)

    def bind_job_to_tab(self, tab_id: str, job_id: str) -> None:
        """Bind an active background job to an existing tab.

        Args:
            tab_id: Internal tab identifier.
            job_id: Active background job identifier.

        Returns:
            None
        """
        record = self._get_tab_record(tab_id)
        if record is None:
            self._logger.warning(
                "ResultTabManager: bind_job_to_tab ignored because tab was not found (tab_id=%s, job_id=%s).",
                tab_id,
                job_id,
            )
            return

        record.job_id = job_id

        self._logger.debug(
            "ResultTabManager: bound job to tab (tab_id=%s, job_id=%s, state=%s).",
            tab_id,
            job_id,
            record.state.value,
        )

    def fulfill_pending_tab(
        self,
        tab_id: str,
        df: pd.DataFrame,
    ) -> None:
        """Fill an existing pending tab with a DataFrame and mark it ready.

        Args:
            tab_id: Internal tab identifier.
            df: DataFrame to place into the tab.

        Returns:
            None
        """
        record = self._get_tab_record(tab_id)
        if record is None:
            self._logger.warning(
                "ResultTabManager: fulfill_pending_tab ignored because tab was not found (tab_id=%s).",
                tab_id,
            )
            return

        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
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
            ) as e:
                self._dialogs.critical(
                    parent=self._parent,
                    title=self._tr(self.TR_FAILURE),
                    text=self._tr_fmt(self.TR_COULD_NOT_LOAD_DATA, error=str(e)),
                )
                return

        view = record.view
        model = view.model()

        if isinstance(model, DataFrameModel):
            model.set_data_frame(df)
        else:
            self._create_dataframe_model(view, df)

        if self._should_apply_formatting(df):
            self._apply_presentation_delegate(view, df)

        self._adjust_column_widths_to_header(view, df)

        record.df = df
        record.state = ResultTabState.READY

        tab_index = self._find_tab_index_by_id(tab_id)
        if tab_index is not None:
            self._tabs.setTabText(tab_index, record.title)
            if self._tabs.currentIndex() == tab_index:
                self._last_df = df
                self._emit_shape(df)

        with contextlib.suppress(Exception):
            self._col_profile_cache.invalidate_tab(tab_id)

        self._notify_undo_state_changed()
        self._emit_toolbar_data_state()
        self._emit_toolbar_multi_dataset_state()

        self._logger.info(
            "ResultTabManager: fulfilled pending tab (tab_id=%s, title=%s, rows=%s, cols=%s).",
            tab_id,
            record.title,
            len(df),
            len(df.columns),
        )

    def remove_pending_tab(self, tab_id: str) -> None:
        """Remove an existing pending tab.

        If the tab is missing, the call is ignored.

        Args:
            tab_id: Internal tab identifier.

        Returns:
            None
        """
        record = self._get_tab_record(tab_id)
        if record is None:
            self._logger.debug(
                "ResultTabManager: remove_pending_tab ignored because tab was not found (tab_id=%s).",
                tab_id,
            )
            return

        tab_index = self._find_tab_index_by_id(tab_id)
        if tab_index is None:
            self._logger.debug(
                "ResultTabManager: remove_pending_tab ignored because tab index was not found (tab_id=%s).",
                tab_id,
            )
            return

        self._logger.info(
            "ResultTabManager: removing pending tab (tab_id=%s, title=%s, state=%s).",
            tab_id,
            record.title,
            record.state.value,
        )

        self._close_tab_internal(tab_index, request_cancel=False)

    def close_tab(self, index: int) -> None:
        """Close a tab and request cancellation for pending jobs when applicable.

        Args:
            index: Tab index to close.

        Returns:
            None
        """
        self._close_tab_internal(index, request_cancel=True)

    def rename_tab(self, index: int):
        """Renames the tab at the given index.

        Args:
            index (int): The index of the tab to rename.

        Returns:
            None
        """
        if index < 0:
            return

        current_title = self._tabs.tabText(index)
        self._logger.debug("ResultTabManager: rename tab requested (index=%s, old_title=%s).", index, current_title)
        new_title, ok = self._dialogs.prompt_text(
            parent=self._parent,
            title=self._tr(self.TR_RENAME_TAB),
            label=self._tr(self.TR_NEW_NAME),
            default=current_title,
        )

        if ok and new_title.strip():
            self._tabs.setTabText(index, new_title.strip())
            self._logger.info("ResultTabManager: renamed tab index=%s to '%s'.", index, new_title.strip())

    def current_df(self, index: int | None = None) -> pd.DataFrame | None:
        """Return the DataFrame for the current tab or a given tab index.

        Args:
            index: Tab index to return the DataFrame for. If None, the current tab is used.

        Returns:
            DataFrame for the current tab or a given tab index, or None if the tab is not found.
        """
        if index is None:
            index = self._tabs.currentIndex()

        if index is None or index < 0:
            return None

        tab_bar = self._tabs.tabBar()
        if tab_bar is None:
            return None

        tab_id = tab_bar.tabData(index)
        if not isinstance(tab_id, str):
            return None

        record = self._tabs_by_id.get(tab_id)
        if record is None:
            return None

        return record.df

    def collect_all_tabs_data(self) -> list[tuple[pd.DataFrame, str]]:
        """Returns a list of (DataFrame, title) tuples for all tabs with data.

        Used primarily for comparison profiling.
        """
        self._logger.debug("ResultTabManager: collecting DataFrames from all tabs.")
        data: list[tuple[pd.DataFrame, str]] = []

        try:
            for i in range(self._tabs.count()):
                df_i = self.current_df(i)
                if df_i is None or df_i.empty:
                    continue
                title_i = self._tabs.tabText(i).strip() or f"Dataset{i + 1}"
                data.append((df_i, title_i))
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
            pass

        return data

    def list_ready_datasets(self) -> list:
        """Return metadata for all ready datasets.

        Returns:
            A list of lightweight dataset references for all ready tabs.
        """
        datasets: list[VisualizationDatasetRef] = []

        for record in self._ready_records():
            if record.df is None:
                continue

            datasets.append(
                VisualizationDatasetRef(
                    tab_id=record.tab_id,
                    title=record.title,
                    row_count=len(record.df),
                    column_count=len(record.df.columns),
                )
            )

        return datasets

    def get_df_by_tab_id(self, tab_id: str) -> pd.DataFrame:
        """Return the DataFrame for a given tab id.

        Args:
            self: The ResultTabManager instance.
            tab_id: Stable internal tab identifier.

        Returns:
            The DataFrame associated with the tab.

        Raises:
            KeyError: If the tab does not exist or does not contain a DataFrame.
        """
        record = self._get_tab_record(tab_id)
        if record is None:
            msg = f"No tab found for tab_id='{tab_id}'"
            raise KeyError(msg)

        if record.df is None:
            msg = (
                f"Tab '{record.title}' does not currently hold a DataFrame "
                f"(tab_id={tab_id}, state={record.state.value})"
            )
            raise KeyError(msg)

        return record.df

    def active_tab_id(self) -> str | None:
        """Return the tab id for the currently active tab.

        Returns:
            The active tab id, or None if not available.
        """
        index = self._tabs.currentIndex()
        if index < 0:
            return None

        tab_bar = self._tabs.tabBar()
        if tab_bar is None:
            return None

        tab_id = tab_bar.tabData(index)
        if isinstance(tab_id, str):
            return tab_id

        return None

    # ==============================================================
    # PROPERTIES & STATE ACCESS
    # ==============================================================

    @property
    def last_df(self) -> pd.DataFrame | None:
        """Last active DataFrame (mirrored from active tab)."""
        return self._last_df

    @property
    def tabs_by_id(self) -> dict[str, ResultTabRecord]:
        """Mapping: tab_id → internal result tab record."""
        return self._tabs_by_id

    @property
    def tabs_count(self) -> int:
        """Number of tabs open."""
        return self._tabs.count()

    def active_view(self) -> QTableView | None:
        """Return the currently active result table view, if available."""
        index = self._tabs.currentIndex()
        if index < 0:
            return None

        widget = self._tabs.widget(index)
        if isinstance(widget, QTableView):
            return widget

        return None

    def ready_dataset_count(self) -> int:
        """Return the number of ready result tabs that currently hold data."""
        return len(self._ready_records())

    def can_undo_current(self) -> bool:
        """Return True if the active tab has undo snapshots."""
        try:
            idx = self._tabs.currentIndex()
            if idx < 0:
                return False

            tab_bar = self._tabs.tabBar()
            if tab_bar is None:
                return False

            tab_id = tab_bar.tabData(idx)
            if not isinstance(tab_id, str):
                return False

            return self._undo.has_undo(tab_id)

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
            return False

    def set_join_controller(self, controller: JoinController) -> None:
        """Set the join controller for the result tab manager."""
        self._join_controller = controller

    def set_concat_controller(self, controller: ConcatController) -> None:
        """Set the concatenate controller for the result tab manager."""
        self._concat_controller = controller

    def set_derived_column_controller(self, controller: DerivedColumnController) -> None:
        """Set the derived column controller for the result tab manager."""
        self._derived_column_controller = controller

    # ==============================================================
    # TOOLBAR / UI STATE NOTIFICATIONS
    # ==============================================================

    def apply_toolbar_data_state(self, cb: Callable[[bool], None]) -> None:
        """Register callback that fires whenever dataset availability changes."""
        if callable(cb):
            self._notify_has_data_cbs.append(cb)

    def apply_toolbar_multiple_dataset_state(self, cb: Callable[[bool], None]) -> None:
        """Register callback for enabling/disabling multi dataset operations (join/concat)."""
        if callable(cb):
            self._notify_toolbar_multi_dataset_cb = cb
            self._emit_toolbar_multi_dataset_state()

    def _emit_toolbar_data_state(self):
        """Emit toolbar data state change event."""
        for cb in self._notify_has_data_cbs:
            if not callable(cb):
                continue
            with contextlib.suppress(Exception):
                cb(self._has_any_data())

    def _emit_toolbar_multi_dataset_state(self) -> None:
        """Notify toolbar about whether multiple ready datasets are present.

        Pending tabs must not count as available datasets.
        """
        cb = self._notify_toolbar_multi_dataset_cb

        if cb is None:
            return

        ready_count = len(self._ready_records())
        has_multiple = ready_count > 1

        self._logger.debug(
            "ResultTabManager: emit multi-dataset state (cb_exists=%s ready_count=%s tab_count=%s has_multiple=%s)",
            True,
            ready_count,
            self._tabs.count(),
            has_multiple,
        )

        with contextlib.suppress(Exception):
            cb(has_multiple)

    # ==================================================================
    # TAB BAR CONTEXT MEN
    # ==================================================================
    def on_tabbar_context_menu(self, pos: QPoint):
        """Right-click menu on tabs.

        Args:
            pos: The position of the mouse click in the tab bar.

        Returns:
            None
        """
        tabbar = self._tabs.tabBar()
        if tabbar is None:
            return
        index = tabbar.tabAt(pos)
        self._logger.debug("ResultTabManager: tabbar context menu opened on index=%s.", index)
        if index < 0:
            return

        global_pos = tabbar.mapToGlobal(pos)

        menu = QMenu(self._parent)
        header = QAction(self._tabs.tabText(index), menu)
        menu.addAction(header)
        header.setEnabled(False)
        menu.addSeparator()

        act_rename = QAction(self._tr(self.TR_RENAME), menu)
        menu.addAction(act_rename)
        act_close = QAction(self._tr(self.TR_CLOSE), menu)
        menu.addAction(act_close)
        act_close_others = QAction(self._tr(self.TR_CLOSE_OTHERS), menu)
        menu.addAction(act_close_others)
        menu.addSeparator()

        act_derived = QAction(self._tr(self.TR_DERIVED_COLUMN), menu)
        menu.addAction(act_derived)
        act_derived.setEnabled(self._tabs.count() > 0)
        act_join = QAction(self._tr(self.TR_JOIN), menu)
        menu.addAction(act_join)
        act_join.setEnabled(self._tabs.count() > 1)
        act_concatenate = QAction(self._tr(self.TR_CONCATENATE), menu)
        menu.addAction(act_concatenate)
        act_concatenate.setEnabled(self._tabs.count() > 1)

        chosen = menu.exec(global_pos)
        if not chosen:
            return

        if chosen == act_rename:
            self.rename_tab(index)
        elif chosen == act_close:
            self.close_tab(index)
        elif chosen == act_close_others:
            self._logger.info("ResultTabManager: closing all tabs except index=%s.", index)
            for i in sorted((i for i in range(self._tabs.count()) if i != index), reverse=True):
                self.close_tab(i)

        elif chosen == act_derived:
            try:
                self._derived_column_controller.create_derived_column()
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
                self._logger.exception("Derived column failed to start.")
            return

        elif chosen == act_join:
            try:
                self._join_controller.open_join_dialog()
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
                self._logger.exception("ResultTabManager: join could not be started.")
            return
        elif chosen == act_concatenate:
            try:
                self._concat_controller.open_concat_dialog()
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
                self._logger.exception("ResultTabManager: concatenate could not be started.")
            return

    # ==================================================================
    # HEADER CONTEXT MENU
    # ==================================================================

    def _on_header_context_menu(self, view: QTableView, pos: QPoint):
        """Column header context menu.

        Args:
            view: The QTableView instance where the context menu was triggered.
            pos: The position of the mouse click in the view.

        Returns:
            None
        """
        header = view.horizontalHeader()
        if header is None:
            return
        column = header.logicalIndexAt(pos)
        if column < 0:
            return
        self._logger.debug("ResultTabManager: header context menu opened (column_index=%s).", column)

        sel_model = header.selectionModel()
        if sel_model is None:
            return
        only_one_selected = len(sel_model.selectedColumns()) < 2

        ok, df, col_name, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or not col_name:
            return

        ctx = build_header_context(
            view=view,
            df=df,
            column=column,
            column_name=col_name,
            only_one_selected=only_one_selected,
        )

        # ---------------------------
        # Main menu
        # ---------------------------
        menu, action_map = self._header_menu.build(ctx)

        global_pos = header.mapToGlobal(pos)
        chosen = menu.exec(global_pos)

        if not chosen:
            return

        action_id = action_map.get(chosen)
        if not action_id:
            return
        self._dispatch_header_action(action_id, ctx)

    def _dispatch_header_action(self, action_id: str, ctx: ResultTabHeaderContext) -> None:
        """Dispatch header context menu actions.

        This method maps action identifiers to existing handler methods.

        Args:
            action_id: Identifier of the selected action.
            ctx: Context for the header action.

        Returns:
            None
        """
        view = ctx.view
        column = ctx.column

        # ============================================================
        # Sorting
        # ============================================================
        if action_id == "sort.asc":
            self._header_sort_actions.sort_ascending(view, column)

            header = view.horizontalHeader()
            if header is None:
                return

            header.setSortIndicator(column, Qt.SortOrder.AscendingOrder)
            header.setSortIndicatorShown(True)
            return

        if action_id == "sort.desc":
            self._header_sort_actions.sort_descending(view, column)

            header = view.horizontalHeader()
            if header is None:
                return

            header.setSortIndicator(column, Qt.SortOrder.DescendingOrder)
            header.setSortIndicatorShown(True)
            return

        # ============================================================
        # Column operations
        # ============================================================
        if action_id == "column.rename":
            self._header_column_actions.rename_column(view, column)
            return

        if action_id == "column.drop":
            self._header_column_actions.remove_column(view, column)
            return

        if action_id == "column.properties":
            self._column_properties.open(view, column)
            return

        # ============================================================
        # Cleanse data
        # ============================================================
        if action_id == "clean.strip":
            self._header_clean_actions.clean_strip(view, column)
            return

        if action_id == "clean.whitespace":
            self._header_clean_actions.clean_whitespace(view, column)
            return

        if action_id == "clean.lower":
            self._header_clean_actions.clean_lower(view, column)
            return

        if action_id == "clean.upper":
            self._header_clean_actions.clean_upper(view, column)
            return

        if action_id == "clean.title":
            self._header_clean_actions.clean_title(view, column)
            return

        if action_id == "clean.first_upper":
            self._header_clean_actions.clean_capitalize(view, column)
            return

        if action_id == "clean.replace":
            self._header_clean_actions.clean_replace(view, column)
            return

        if action_id == "clean.insert":
            self._header_clean_actions.clean_insert(view, column)
            return

        if action_id == "clean.remove":
            self._header_clean_actions.clean_remove(view, column)
            return

        if action_id == "clean.regex":
            self._header_clean_actions.clean_remove_regex(view, column)
            return

        if action_id == "clean.digits":
            self._header_clean_actions.clean_keep_digits(view, column)
            return

        if action_id == "clean.letters":
            self._header_clean_actions.clean_keep_letters(view, column)
            return

        # ============================================================
        # Fill missing values
        # ============================================================
        if action_id == "fill.mean":
            self._header_fill_actions.fill_mean(view, column)
            return

        if action_id == "fill.median":
            self._header_fill_actions.fill_median(view, column)
            return

        if action_id == "fill.mode":
            self._header_fill_actions.fill_mode(view, column)
            return

        if action_id == "fill.custom":
            self._header_fill_actions.fill_custom(view, column)
            return

        # ============================================================
        # Datatype conversions
        # ============================================================
        if action_id == "dtype.to_category":
            self._header_dtype_actions.to_category(view, column)
            return

        if action_id == "dtype.to_string":
            self._header_dtype_actions.to_string(view, column)
            return

        if action_id == "dtype.to_int":
            self._header_dtype_actions.to_integer(view, column)
            return

        if action_id == "dtype.to_float":
            self._header_dtype_actions.to_float(view, column)
            return

        if action_id == "dtype.to_datetime":
            self._header_dtype_actions.to_datetime(view, column)
            return

        if action_id == "dtype.to_bool":
            self._header_dtype_actions.to_boolean(view, column)
            return

        # ============================================================
        # Category operations
        # ============================================================
        if action_id == "category.rename":
            self._header_category_actions.rename_single(view, column)
            return

        if action_id == "category.set_order":
            self._header_category_actions.set_order(view, column)
            return

        if action_id == "category.remove_unused":
            self._header_category_actions.remove_unused(view, column)
            return

        # ============================================================
        # Filtering
        # ============================================================
        if action_id == "filter.equals":
            self._header_filter_actions.filter_equals(view, column)
            return

        if action_id == "filter.contains":
            self._header_filter_actions.filter_contains(view, column)
            return

        if action_id == "filter.isna":
            self._header_filter_actions.filter_isna(view, column)
            return

        if action_id == "filter.notna":
            self._header_filter_actions.filter_notna(view, column)
            return

        if action_id == "filter.compare":
            self._header_filter_actions.filter_compare(view, column)
            return

        if action_id == "filter.between":
            self._header_filter_actions.filter_between(view, column)
            return

        # ============================================================
        # Split/Merge
        # ============================================================
        if action_id == "column.split":
            self._header_column_actions.split_column(view, column)
            return

        if action_id == "column.merge":
            self._header_column_actions.merge_columns(view, column)
            return

        # ============================================================
        # Fallback
        # ============================================================
        self._logger.warning("ResultTabManager: unhandled header action: %s", action_id)

    # ==================================================================
    # CELL CONTEXT MENU
    # ==================================================================

    def _on_cell_context_menu(self, view: QTableView, pos: QPoint):
        """Clean, modular cell context menu.

        Mirrored structure from header context menu.
        """
        ok, df, row_index, col_name, raw_value = self._cell_context_get(view, pos)
        if not ok:
            return

        menu, amap = self._cell_context_menu.build(
            column_name=col_name,
            raw_value=raw_value,
        )

        viewport = view.viewport()
        if viewport is None:
            return

        global_pos = viewport.mapToGlobal(pos)
        chosen = menu.exec(global_pos)

        if not chosen:
            return

        action = amap.get(chosen)

        try:
            # ---------------------------
            # FILTER
            # ---------------------------
            if action == "filter_keep":
                self._cell_actions.filter_keep(
                    view,
                    df,
                    column_name=col_name,
                    raw_value=raw_value,
                )
                return

            if action == "filter_remove":
                self._cell_actions.filter_remove(
                    view,
                    df,
                    column_name=col_name,
                    raw_value=raw_value,
                )
                return

            # ---------------------------
            # VALUE → REPLACE
            # ---------------------------
            if action == "value_replace":
                self._cell_actions.replace_value(
                    view,
                    df,
                    row_index=row_index,
                    column_name=col_name,
                    raw_value=raw_value,
                )
                return

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
        ) as e:
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr_fmt(self.TR_COULD_NOT_PERFORM, error=str(e)),
            )

    def _cell_context_get(self, view: QTableView, pos: QPoint):
        """Resolve cell, df, row, col_name, and raw_value.

        Args:
            view: The QTableView instance.
            pos: The QPoint position within the view.

        Returns:
            Ok, df, row_index, col_name, raw_value
        """
        index = view.indexAt(pos)
        if not index.isValid():
            return False, None, None, None, None

        model = view.model()
        if not isinstance(model, DataFrameModel):
            return False, None, None, None, None

        df = model.data_frame()
        view_col = index.column()

        try:
            col_name = str(df.columns[view_col])
            raw_value = df.iloc[index.row()][col_name]
            return True, df, index.row(), col_name, raw_value
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
            return False, None, None, None, None

    # ==================================================================
    # UNDO SYSTEM
    # ==================================================================

    def undo(self):
        """Undo the last action on the current result tab."""
        tab_idx = self._tabs.currentIndex()
        tab_bar = self._tabs.tabBar()
        if tab_bar is None:
            return
        tab_id = tab_bar.tabData(tab_idx)
        if not isinstance(tab_id, str) or not self._undo.has_undo(tab_id):
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_UNDO),
                text=self._tr(self.TR_NOTHING_TO_UNDO),
            )
            return

        stack_size_before = self._undo.stack_size(tab_id)
        self._logger.debug(
            "ResultTabManager: undo requested for tab=%s (stack size before=%d).",
            tab_id,
            stack_size_before,
        )

        prev_df = self._undo.pop_snapshot(tab_id)
        if prev_df is None:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_UNDO),
                text=self._tr(self.TR_NOTHING_TO_UNDO),
            )
            return

        widget = self._tabs.widget(tab_idx)

        if not isinstance(widget, QTableView):
            # Defensive: unexpected widget type or tab already closed
            return

        widget = self._tabs.widget(tab_idx)
        if not isinstance(widget, QTableView):
            return  # Defensive: unexpected widget type or tab already closed

        view: QTableView = widget

        self._run_with_busy_overlay(
            view,
            lambda v=view: self._apply_new_dataframe_to_view(
                v,
                prev_df,
                invalidate_cache=True,
                status=self._tr(self.TR_LAST_ACTION_UNDONE),
                push_undo=False,
            ),
            message=self._tr(self.TR_RESTORING_STATE),
        )

        self._logger.info("ResultTabManager: undo applied for tab=%s.", tab_id)

    def _notify_undo_state_changed(self):
        """Tell parent window to refresh undo-button enabled state."""
        cb = self._update_undo_enabled
        if callable(cb):
            with contextlib.suppress(Exception):
                cb()

    # ==============================================================
    # TAB CREATION & LIFECYCLE
    # ==============================================================

    def _insert_tab(
        self,
        view: QTableView,
        df: pd.DataFrame,
        title: str | None,
    ) -> None:
        """Insert a new ready tab for the given view and DataFrame.

        Args:
            view: The view for the tab.
            df: The DataFrame associated with the tab.
            title: Visible tab title, or None to generate a default title.
        """
        # --- Normalize title ---
        if title is None or not str(title).strip():
            normalized_title = f"Dataset{self._result_counter}"
            self._result_counter += 1
        else:
            normalized_title = str(title).strip()

        normalized_title = self._unique_title(normalized_title)

        # --- Create tab id and record ---
        tab_id = uuid.uuid4().hex
        record = self._make_tab_record(
            tab_id=tab_id,
            view=view,
            title=normalized_title,
            df=df,
            state=ResultTabState.READY,
            job_id=None,
            origin_type="unknown",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )

        # --- Insert tab widget ---
        self._tabs.blockSignals(True)
        try:
            tab_index = self._tabs.addTab(view, normalized_title)

            tab_bar = self._tabs.tabBar()
            if tab_bar is not None:
                tab_bar.setTabData(tab_index, tab_id)

            self._tabs_by_id[tab_id] = record
            self._undo.register_tab(tab_id)

            self._tabs.setCurrentIndex(tab_index)

        finally:
            self._tabs.blockSignals(False)

        # --- Cache & state ---
        self._col_profile_cache.invalidate_tab(tab_id)
        self._update_last_df_from_tab(self._tabs.currentIndex())
        self._last_df = df

        self._emit_shape(df)
        self._notify_undo_state_changed()
        self._emit_toolbar_data_state()
        self._emit_toolbar_multi_dataset_state()

    def _unique_title(self, base: str) -> str:
        """Ensure that tab titles are unique.

        If 'base' already exists, generate 'base (1)', 'base (2)', etc.
        """
        existing = {self._tabs.tabText(i).strip() for i in range(self._tabs.count())}

        if base not in existing:
            return base

        # Generate base (1), base (2), ...
        n = 1
        while True:
            candidate = f"{base} ({n})"
            if candidate not in existing:
                return candidate
            n += 1

    def _pending_title(self, base_title: str) -> str:
        """Return the visible title for a pending tab.

        Args:
            base_title: Logical base title for the tab.

        Returns:
            Visible pending title.
        """
        pending = self._tr(self.TR_PENDING)
        return f"{base_title} ({pending})"

    # ==============================================================
    # TAB STATE / LOOKUPS
    # ==============================================================
    def _make_tab_handle(self, record: ResultTabRecord) -> ResultTabHandle:
        """Create a lightweight public handle for a tab record.

        Args:
            record: Internal tab record.

        Returns:
            Public handle for the tab.
        """
        return ResultTabHandle(
            tab_id=record.tab_id,
            view=record.view,
        )

    def _make_tab_record(
        self,
        *,
        tab_id: str,
        view: QTableView,
        title: str,
        df: pd.DataFrame | None,
        state: ResultTabState = ResultTabState.READY,
        job_id: str | None = None,
        origin_type: ResultOrigin = "unknown",
        remove_on_cancel: bool = True,
        remove_on_error: bool = True,
        close_cancels_job: bool = True,
    ) -> ResultTabRecord:
        """Create a new internal tab record.

        Args:
            tab_id: Stable internal tab identifier.
            view: The view associated with the tab.
            title: Visible tab title.
            df: Initial dataframe for the tab, if any.
            state: Lifecycle state for the tab.
            job_id: Optional associated job id.
            origin_type: Logical origin of the tab content.
            remove_on_cancel: Whether the tab should be removed on cancellation.
            remove_on_error: Whether the tab should be removed on failure.
            close_cancels_job: Whether closing the tab should cancel an associated
                pending job.

        Returns:
            A fully initialized ResultTabRecord.
        """
        return ResultTabRecord(
            tab_id=tab_id,
            view=view,
            title=title,
            state=state,
            df=df,
            job_id=job_id,
            origin_type=origin_type,
            remove_on_cancel=remove_on_cancel,
            remove_on_error=remove_on_error,
            close_cancels_job=close_cancels_job,
        )

    def _get_tab_record(self, tab_id: str | None) -> ResultTabRecord | None:
        """Return the internal tab record for a tab id.

        Args:
            tab_id: Internal tab identifier.

        Returns:
            The matching ResultTabRecord, or None if not found.
        """
        if not isinstance(tab_id, str):
            return None
        return self._tabs_by_id.get(tab_id)

    def _get_tab_record_for_view(self, view: QTableView) -> ResultTabRecord | None:
        """Return the internal tab record associated with a view.

        Args:
            view: The view associated with a result tab.

        Returns:
            The matching ResultTabRecord, or None if not found.
        """
        tab_id = self._find_tab_id_for_view(view)
        if tab_id is None:
            return None
        return self._get_tab_record(tab_id)

    def _find_tab_index_by_id(self, tab_id: str) -> int | None:
        """Return the tab index for a tab id.

        Args:
            tab_id: Internal tab identifier.

        Returns:
            Tab index if found, otherwise None.
        """
        if not isinstance(tab_id, str):
            return None

        tab_bar = self._tabs.tabBar()
        if tab_bar is None:
            return None

        for i in range(self._tabs.count()):
            raw_tab_id = tab_bar.tabData(i)
            if raw_tab_id == tab_id:
                return i

        return None

    def _find_tab_id_for_view(self, view: QTableView) -> str | None:
        """Find the tab ID for the given view.

        Args:
            view: QTableView instance for which to find the tab ID.

        Returns:
            str | None: Tab ID if found, otherwise None.
        """
        tab_bar = self._tabs.tabBar()
        if tab_bar is None:
            return None

        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is view:
                tab_id = tab_bar.tabData(i)
                if isinstance(tab_id, str):
                    return tab_id
                return None
        return None

    def _find_tab_index_for_view(self, view: QTableView) -> int | None:
        """Find the tab index for the given view.

        Args:
            view (QTableView): The view for which to find the tab index.

        Returns:
            int | None: Tab index if found, otherwise None.
        """
        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is view:
                return i
        return None

    # ==============================================================
    # DATA APPLICATION / MODEL MANAGEMENT
    # ==============================================================

    def _apply_new_dataframe_to_view(
        self,
        view: QTableView,
        new_df: pd.DataFrame,
        *,
        invalidate_cache: bool = True,
        status: str | None = None,
        push_undo: bool = True,
    ) -> None:
        """Replace the DataFrame in an existing result tab view.

        Args:
            view: The target result view.
            new_df: The new DataFrame to apply.
            invalidate_cache: Whether to invalidate the column profile cache.
            status: Optional status message to display after success.
            push_undo: Whether to push the previous DataFrame onto the undo stack.
        """
        self._logger.debug(
            "ResultTabManager: applying new DataFrame to view (rows=%s, cols=%s, invalidate_cache=%s, push_undo=%s).",
            len(new_df),
            len(new_df.columns),
            invalidate_cache,
            push_undo,
        )

        model = view.model()
        if not isinstance(model, DataFrameModel):
            self._logger.warning("ResultTabManager: apply ignored because view model was not a DataFrameModel.")
            return

        record = self._get_tab_record_for_view(view)
        tab_id = record.tab_id if record is not None else None

        # Push previous dataframe onto undo stack before replacing it.
        if push_undo and tab_id is not None:
            try:
                old_df = model.data_frame()
                if isinstance(old_df, pd.DataFrame):
                    pushed = self._undo.push_snapshot(tab_id, old_df)
                    if pushed:
                        self._logger.debug(
                            "ResultTabManager: pushed previous DataFrame to undo stack for tab=%s.",
                            tab_id,
                        )
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
                self._logger.debug(
                    "ResultTabManager: failed to push undo snapshot for tab=%s.",
                    tab_id,
                    exc_info=True,
                )

        try:
            model.set_data_frame(new_df)
            with contextlib.suppress(Exception):
                view.setModel(model)

            if self._should_apply_formatting(new_df):
                self._apply_presentation_delegate(view, new_df)
            else:
                self._clear_presentation_delegate(view)

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
        ) as e:
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr_fmt(self.TR_COULD_NOT_UPDATE_DATA, error=str(e)),
            )
            return

        # Update internal record/state.
        if record is not None:
            record.df = new_df
            record.state = ResultTabState.READY

            if invalidate_cache:
                with contextlib.suppress(Exception):
                    self._col_profile_cache.invalidate_tab(record.tab_id)

        else:
            self._logger.warning("ResultTabManager: no tab record found while applying new DataFrame.")

        tab_idx = self._find_tab_index_for_view(view)
        if tab_idx is not None and self._tabs.currentIndex() == tab_idx:
            self._last_df = new_df
            self._emit_shape(new_df)

        if status:
            self._logger.info(
                "ResultTabManager: DataFrame updated for tab=%s.",
                tab_id,
            )
            self._set_status(status, 6000)

        self._notify_undo_state_changed()
        self._emit_toolbar_data_state()
        self._emit_toolbar_multi_dataset_state()

    def _create_dataframe_model(
        self,
        view: QTableView,
        df: pd.DataFrame,
    ) -> DataFrameModel:
        """Create and bind a DataFrameModel to the given view.

        Args:
            view: The QTableView instance to bind the model to.
            df: The pandas DataFrame to use as the model's data source.

        Returns:
            DataFrameModel: The created DataFrameModel instance.
        """
        model = DataFrameModel(
            df,
            parent=view,
            na_rep="",
        )

        # Invalidate column profile cache when DataFrame is replaced

        if isinstance(model, DataFrameModel):

            def invalidate_cache():
                tab_bar = self._tabs.tabBar()
                if tab_bar is None:
                    return

                try:
                    tab_id = self._find_tab_id_for_view(view)
                    if tab_id is not None:
                        self._col_profile_cache.invalidate_tab(tab_id)
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
                    pass

            with contextlib.suppress(Exception):
                model.data_frame_replaced.connect(invalidate_cache)

        view.setModel(model)

        return model

    def _apply_with_cache_invalidation(
        self,
        view: QTableView,
        df: pd.DataFrame,
        status: str,
    ):
        """Wrapper to enforce cache invalidation."""
        self._apply_new_dataframe_to_view(
            view,
            df,
            invalidate_cache=True,
            status=status,
        )

    def _apply_without_cache_invalidation(
        self,
        view,
        df,
        status,
    ):
        """Adapter for controllers that should not force cache invalidation."""
        self._apply_new_dataframe_to_view(
            view,
            df,
            invalidate_cache=False,
            status=status,
        )

    def _apply_presentation_delegate(
        self,
        view: QTableView,
        df: pd.DataFrame,
    ) -> None:
        """Attach or update the column presentation delegate for a view."""
        try:
            semantics_by_index: dict[int, SeriesSemantics] = {}

            for i in range(df.shape[1]):
                sem = self.get_series_semantics(view, i)
                if sem is not None:
                    semantics_by_index[i] = sem

            delegate = ResultTabColumnPresentationDelegate(
                semantics_by_column_index=semantics_by_index,
                parent=view,
            )

            view.setItemDelegate(delegate)

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
            self._logger.exception("ResultTabManager: failed to apply presentation delegate")

    def handle_format_view_toggle(self, is_checked: bool) -> None:
        """Handle toolbar toggle for enabling/disabling semantic formatting."""
        self._formatting_enabled = is_checked
        self._logger.debug("ResultTabManger: formatting toggled (enabled=%s)", is_checked)

        view = self.active_view()
        if view is None:
            return

        current_delegate = view.itemDelegate()

        if isinstance(current_delegate, ResultTabColumnPresentationDelegate):
            self._clear_presentation_delegate(view)
        else:
            if is_checked:
                active_record = self.current_df()
                if active_record is not None:
                    self._run_with_busy_overlay(
                        view,
                        lambda: self._apply_presentation_delegate(view, active_record),
                        message=self._tr(self.TR_FORMATTING_CELLS),
                    )

    def _adjust_column_widths_to_header(
        self,
        view: QTableView,
        df: pd.DataFrame,
        *,
        min_width: int = 120,
        padding: int = 24,
    ) -> None:
        """Ensure each column is at least wide enough to fit its header text."""
        header = view.horizontalHeader()
        if header is None:
            return

        fm = QFontMetrics(header.font())

        for i, col_name in enumerate(df.columns):
            text = str(col_name)
            text_width = fm.horizontalAdvance(text)
            target_width = max(min_width, text_width + padding)
            header.resizeSection(i, target_width)

    def _should_apply_formatting(self, df: pd.DataFrame) -> bool:
        _ = df
        return self._formatting_enabled

    def _clear_presentation_delegate(self, view: QTableView) -> None:
        try:
            delegate = QStyledItemDelegate(view)
            view.setItemDelegate(delegate)
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
            self._logger.exception("Failed to clear presentation delegate.")

    def _update_last_df_from_tab(self, index: int) -> None:
        """Update the cached last DataFrame from the active tab."""
        try:
            if index is None or index < 0 or self._tabs.widget(index) is None:
                self._last_df = None
                self._emit_shape(self._last_df)
                return

            tab_bar = self._tabs.tabBar()
            if tab_bar is None:
                self._last_df = None
                self._emit_shape(self._last_df)
                return

            tab_id = tab_bar.tabData(index)
            if not isinstance(tab_id, str):
                self._last_df = None
                self._emit_shape(self._last_df)
                return

            record = self._tabs_by_id.get(tab_id)
            self._last_df = record.df if record is not None else None

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
            self._last_df = None

        self._emit_shape(self._last_df)

    def _emit_shape(self, df: pd.DataFrame | None) -> None:
        """Notify host about current shape of active DataFrame.

        Passes (rows, cols) or (None, None) when no data.

        """
        try:
            if df is None:
                self._set_shape(None, None)
            else:
                self._set_shape(len(df), len(df.columns))
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
            pass

    # ==============================================================
    # VIEW / UI FACTORIES
    # ==============================================================

    def _create_result_view(self) -> QTableView:
        """Create and configure a QTableView for result display.

        Returns:
            QTableView: Configured QTableView for result display.
        """
        view = QTableView(self._parent)

        # --- Vertical header (row numbers) ---
        vheader = view.verticalHeader()
        if vheader is not None:
            vheader.setVisible(True)
            vheader.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            vheader.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            vheader.setDefaultSectionSize(32)

        # --- Sorting: disabled (controlled via context menu) ---
        view.setSortingEnabled(False)

        # --- Column-based selection (for merge/join) ---
        view.setSelectionBehavior(QTableView.SelectionBehavior.SelectColumns)
        view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)

        # --- Horizontal header ---
        header = view.horizontalHeader()
        if header is not None:
            header.setSectionsClickable(False)
            header.setSectionsMovable(False)
            header.setHighlightSections(False)
            header.setSortIndicatorShown(True)

        # --- Context menus ---
        from functools import partial

        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(partial(self._on_cell_context_menu, view))

        if header is not None:
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(partial(self._on_header_context_menu, view))

        return view

    def _make_header_action(self, cls):
        """Factory for header action controllers."""
        return cls(
            parent=self._parent,
            dialogs=self._dialogs,
            logger=self._logger,
            async_ops=self._async_ops,
            resolve_df_col_series=self._resolve_df_col_series,
            apply_new_dataframe=self._apply_with_cache_invalidation,
        )

    # ==============================================================
    # DATA ACCESS HELPERS
    # ==============================================================

    def _resolve_df_col_series(
        self, view: QTableView, column: int
    ) -> tuple[bool, pd.DataFrame | None, str | None, pd.Series | None]:
        """Resolve (DataFrame, column name, Series) from QTableView + column index.

        Assumes that all horizontal columns are data columns.

        Args:
            view (QTableView): The QTableView instance.
            column (int): The column index.

        Returns:
            tuple[bool, pd.DataFrame | None, str | None, pd.Series | None]:
                A tuple containing a boolean indicating success, the DataFrame, the column name, and the Series.
        """
        model = view.model()
        if not isinstance(model, DataFrameModel):
            self._logger.warning(
                "ResultTabManager: resolve failed - model has no DataFrame (column=%s).",
                column,
            )
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NOT_AVAILABLE),
                text=self._tr(self.TR_NO_DATA_AVAILABLE),
            )
            return False, None, None, None

        try:
            df = model.data_frame()
            if not isinstance(df, pd.DataFrame):
                msg = "Model returned non-DataFrame."
                raise TypeError(msg)

            if column < 0 or column >= df.shape[1]:
                msg_0 = f"Invalid column index: {column}"
                raise IndexError(msg_0)

            col_name = str(df.columns[column])
            s = df[col_name]

            return True, df, col_name, s

        except IndexError as e:
            self._logger.error(
                "ResultTabManager: resolve failed - invalid column index=%s: %s",
                column,
                e,
            )
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr_fmt(self.TR_INVALID_INDEX, column=str(column)),
            )
            return False, None, None, None

        except KeyError as e:
            self._logger.error(
                "ResultTabManager: resolve failed - column not found (column=%s): %s",
                column,
                e,
            )
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr(self.TR_COLUMN_NOT_AVAILABLE),
            )
            return False, None, None, None

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            self._logger.error(
                "ResultTabManager: resolve failed - unexpected error (column=%s): %s",
                column,
                e,
            )
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr_fmt(self.TR_COULD_NOT_READ_COLUMN, error=str(e)),
            )
            return False, None, None, None

    def get_series_semantics(
        self,
        view: QTableView,
        column: int,
    ) -> SeriesSemantics | None:
        """Get the inferred semantics for a series in a dataframe column.

        Returns None if the column cannot be resolved or if the series
        cannot be inferred.

        Args:
            view: The QTableView containing the dataframe.
            column: The index of the column in the dataframe.

        Returns:
            The inferred SeriesSemantics or None if not applicable.
        """
        ok, df, col_name, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or not col_name:
            return None
        return infer_series_semantics(df[col_name])

    def get_df_by_title(self, title: str) -> pd.DataFrame:
        """Return the DataFrame for a given tab title.

        Args:
            title: The visible title of the tab.

        Returns:
            The DataFrame associated with the given tab.

        Raises:
            KeyError: If no matching tab exists or if the tab has no ready DataFrame.
        """
        tab_bar = self._tabs.tabBar()
        if tab_bar is None:
            msg = "Tab bar is not available"
            raise KeyError(msg)

        target = title.strip()

        for i in range(self._tabs.count()):
            if self._tabs.tabText(i).strip() != target:
                continue

            tab_id = tab_bar.tabData(i)
            if not isinstance(tab_id, str):
                msg_0 = f"Tab '{title}' has no valid tab_id"
                raise KeyError(msg_0)

            record = self._tabs_by_id.get(tab_id)
            if record is None:
                msg_0 = f"No tab record stored for tab id={tab_id} (title='{title}')"
                raise KeyError(msg_0)

            if record.df is None:
                msg_0 = (
                    f"Tab '{title}' does not currently hold a DataFrame (tab_id={tab_id}, state={record.state.value})"
                )
                raise KeyError(msg_0)

            return record.df

        msg_0 = f"No tab with title '{title}' found"
        raise KeyError(msg_0)

    def close_tabs_by_title(self, title: str):
        """Closes all tabs whose visible title matches the given string.

        Used by FilePanelController when deleting files.
        """
        try:
            for i in reversed(range(self._tabs.count())):
                if self._tabs.tabText(i).strip() == title.strip():
                    self.close_tab(i)
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
            pass

    def _has_any_data(self) -> bool:
        """Return True if ANY tab contains a non-empty DataFrame."""
        try:
            return len(self._ready_records()) > 0
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
            return False

    def _ready_records(self) -> list[ResultTabRecord]:
        """Return all ready result-tab records that currently hold data.

        Returns:
            A list of result-tab records in READY state with a non-None DataFrame.
        """
        records: list[ResultTabRecord] = []

        for record in self._tabs_by_id.values():
            if not isinstance(record, ResultTabRecord):
                continue
            if not record.is_ready:
                continue
            if record.df is None:
                continue
            records.append(record)

        return records

    # ==============================================================
    # BUSY OVERLAY
    # ==============================================================

    def _run_with_busy_overlay(
        self,
        view: QTableView,
        fn: Callable[[], None],
        *,
        message: str | None = None,
    ):
        """Run a potentially heavy operation with a busy overlay.

        This MUST be used for operations that block the UI thread
        before DataFrame is applied.
        """
        self._busy_overlay.run(
            view,
            fn,
            message=message,
        )

    # ==============================================================
    # TAB CLOSING & CANCELLATION
    # ==============================================================

    def _close_tab_internal(self, index: int, *, request_cancel: bool) -> None:
        """Close a tab and clean up its associated state.

        Guards against Qt reentrancy issues where tabCloseRequested may be emitted
        multiple times during a single mouse click.

        Args:
            index: Tab index to close.
            request_cancel: Whether closing a pending tab should request cancellation
                of its associated job.
        """
        if self._closing_tabs:
            self._logger.debug("ResultTabManager: close_tab - reentrant call ignored.")
            return

        self._closing_tabs = True
        try:
            self._logger.debug(
                "ResultTabManager: closing tab request for index=%s (request_cancel=%s).",
                index,
                request_cancel,
            )

            widget = self._tabs.widget(index)
            if widget is None:
                return

            index = self._tabs.indexOf(widget)
            if index < 0:
                return

            tab_bar = self._tabs.tabBar()
            if tab_bar is None:
                return

            tab_id_raw = tab_bar.tabData(index)
            tab_id = tab_id_raw if isinstance(tab_id_raw, str) else None
            record = self._get_tab_record(tab_id)

            if record is not None and request_cancel:
                self._maybe_cancel_pending_tab_job(record)

            if record is not None:
                self._tabs_by_id.pop(record.tab_id, None)
                self._undo.unregister_tab(record.tab_id)
                self._logger.info("ResultTabManager: closed tab id=%s.", record.tab_id)
            else:
                self._logger.debug(
                    "ResultTabManager: closing tab with no matching record (index=%s).",
                    index,
                )

            if isinstance(widget, QTableView):
                with contextlib.suppress(Exception):
                    widget.setModel(None)

            self._tabs.removeTab(index)

            with contextlib.suppress(Exception):
                widget.deleteLater()

            if self._tabs.count() == 0:
                self._tabs_by_id.clear()
                self._undo.clear()
                self._last_df = None
            else:
                self._last_df = self.current_df()

            self._notify_undo_state_changed()
            self._emit_shape(self._last_df)
            self._emit_toolbar_data_state()
            self._emit_toolbar_multi_dataset_state()

        finally:
            ui_invoke(lambda: setattr(self, "_closing_tabs", False))

    def _maybe_cancel_pending_tab_job(self, record: ResultTabRecord) -> None:
        """Request cancellation for an associated pending job if configured.

        Args:
            record: Internal tab record for the tab being closed.
        """
        if not record.is_pending:
            return

        if not record.close_cancels_job:
            return

        job_id = record.job_id
        if not isinstance(job_id, str) or not job_id:
            return

        cancel_job = self._cancel_job
        if cancel_job is None:
            self._logger.debug(
                "ResultTabManager: pending tab close had no cancel callback (tab_id=%s, job_id=%s).",
                record.tab_id,
                job_id,
            )
            return

        try:
            cancelled = bool(cancel_job(job_id))
            self._logger.info(
                "ResultTabManager: pending tab close requested job cancellation (tab_id=%s, job_id=%s, cancelled=%s).",
                record.tab_id,
                job_id,
                cancelled,
            )
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
                "ResultTabManager: failed to cancel pending job on tab close (tab_id=%s, job_id=%s).",
                record.tab_id,
                job_id,
            )

    # ==============================================================
    # EVENTS / CALLBACKS
    # ==============================================================

    def on_tab_changed(self, index: int):
        """Active tab changed.

        Updates last_df and emits signals for toolbar state.
        """
        self._logger.debug("ResultTabManager: active tab changed to index=%s.", index)

        ui_invoke(lambda idx=index: self._update_last_df_from_tab(idx))

        self._notify_undo_state_changed()
        self._emit_toolbar_data_state()
        self._emit_toolbar_multi_dataset_state()

        view = self.active_view()
        if view is None:
            return

        current_delegate = view.itemDelegate()
        is_delegate_active = isinstance(current_delegate, ResultTabColumnPresentationDelegate)

        if self._formatting_enabled and not is_delegate_active:
            active_record = self.current_df()
            if active_record is not None:
                self._run_with_busy_overlay(
                    view,
                    lambda: self._apply_presentation_delegate(view, active_record),
                    message=self._tr(self.TR_FORMATTING_CELLS),
                )

        elif not self._formatting_enabled and is_delegate_active:
            self._clear_presentation_delegate(view)
