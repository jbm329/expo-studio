"""Workbench service composition for the Expo application.

This module wires together the workbench-level controllers, icon/theme services,
autocomplete, result tabs, and file handling into a single dependency container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from PyQt6.QtCore import Qt

from expo_jbm329.app.settings.config_store import read_connections
from expo_jbm329.db.base import close_connection
from expo_jbm329.gui.custom_tab_bar import CustomTabBar
from expo_jbm329.gui.gui_utils import ui_invoke
from expo_jbm329.services.file_job_service import FileJobService
from expo_jbm329.services.schema_model import build_schema_dict
from expo_jbm329.utils.dialog_state import DialogState
from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController
from expo_jbm329.workbench.controllers.busy_overlay_controller import BusyOverlayController
from expo_jbm329.workbench.controllers.concat_controller import ConcatController
from expo_jbm329.workbench.controllers.connection_controller import ConnectionController
from expo_jbm329.workbench.controllers.derived_column_controller import DerivedColumnController
from expo_jbm329.workbench.controllers.document_controller import DocumentController
from expo_jbm329.workbench.controllers.editor_panel_controller import EditorPanelController
from expo_jbm329.workbench.controllers.editor_tab_manager import EditorTabManager
from expo_jbm329.workbench.controllers.export_controller import ExportController
from expo_jbm329.workbench.controllers.file_panel_controller import FilePanelController
from expo_jbm329.workbench.controllers.join_controller import JoinController
from expo_jbm329.workbench.controllers.query_controller import QueryController
from expo_jbm329.workbench.controllers.rest_controller import RestController
from expo_jbm329.workbench.controllers.rest_panel_controller import RestPanelController
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager
from expo_jbm329.workbench.controllers.schema_controller import SchemaController
from expo_jbm329.workbench.controllers.visualization.visualization_controller import (
    VisualizationController,
)
from expo_jbm329.workbench.icon.custom_file_icon_provider import CustomFileIconProvider
from expo_jbm329.workbench.icon.icon_service import IconService
from expo_jbm329.workbench.theme.highlighter_theme_service import HighlighterThemeService
from expo_jbm329.workbench.theme.theme_service import ThemeService

if TYPE_CHECKING:
    from expo_jbm329.app.app_services import AppServices
    from expo_jbm329.services.settings_service import SettingsService
    from expo_jbm329.workbench.ui_refs import WorkbenchUIRefs


class WorkbenchServices:
    """Container for workbench controllers and UI-facing services."""

    def __init__(
        self,
        busy_overlay: BusyOverlayController,
        async_ops: AsyncOperationController,
        schema: SchemaController,
        connections: ConnectionController,
        file_panel: FilePanelController,
        rest_panel: RestPanelController,
        file_jobs: FileJobService,
        document: DocumentController,
        query: QueryController,
        export: ExportController,
        rest: RestController,
        results: ResultTabManager,
        visualization: VisualizationController,
        derived_column: DerivedColumnController,
        editor_panel: EditorPanelController,
        icon_service: IconService,
        file_icon_provider: CustomFileIconProvider,
        theme_service: ThemeService,
        highlighter_theme_service: HighlighterThemeService,
        join: JoinController,
        concat: ConcatController,
        dialog_state: DialogState,
    ) -> None:
        """Initialize the workbench service container.

        Args:
            busy_overlay: Controller for busy overlay display.
            async_ops: Controller for asynchronous operations.
            schema: Controller for schema tree behavior.
            connections: Controller for database connections.
            file_panel: Controller for the file panel.
            rest_panel: Controller for the REST panel.
            file_jobs: Service handling file-related jobs.
            document: Controller for document-related operations.
            query: Controller for SQL execution.
            export: Controller for export operations.
            rest: Controller for REST API operations.
            results: Manager for result tabs.
            visualization: Controller for visualization operations.
            derived_column: Controller for derived column operations.
            editor_panel: Controller for the editor panel.
            icon_service: Service that resolves themed icons.
            file_icon_provider: QFileIconProvider implementation for the file tree.
            theme_service: GUI theme service.
            highlighter_theme_service: Syntax-highlighter theme service.
            join: Controller for JOIN operations.
            concat: Controller for CONCAT operations.
            dialog_state: Service for managing dialog state.

        Returns:
            None
        """
        self.busy_overlay = busy_overlay
        self.async_ops = async_ops
        self.schema = schema
        self.connections = connections
        self.file_panel = file_panel
        self.file_jobs = file_jobs
        self.document = document
        self.query = query
        self.export = export
        self.rest_panel = rest_panel
        self.rest = rest
        self.results = results
        self.visualization = visualization
        self.derived_column = derived_column
        self.editor_panel = editor_panel
        self.icon_service = icon_service
        self.file_icon_provider = file_icon_provider
        self.theme_service = theme_service
        self.highlighter_theme_service = highlighter_theme_service
        self.join = join
        self.concat = concat
        self.dialog_state = dialog_state

    @classmethod
    def build(cls: type[Self], app: AppServices, ui: WorkbenchUIRefs, settings_service: SettingsService) -> Self:
        """Construct all workbench-level controllers and services.

        Args:
            app: Application-wide service container.
            ui: Workbench UI references and callbacks.
            settings_service: Settings service used to subscribe controllers.

        Returns:
            A fully wired WorkbenchServices instance.
        """
        # ---------------------------------------------
        # Themes
        # ---------------------------------------------
        theme_service = ThemeService(logger=app.log_ui)

        # ---------------------------------------------
        # SQL Highlighter
        # ---------------------------------------------
        highlighter_theme_service = HighlighterThemeService(
            theme_service=theme_service,
            logger=app.log_ui,
        )

        # ---------------------------------------------
        # Icons
        # ---------------------------------------------
        icon_service = IconService(theme_service=theme_service, logger=app.log_ui)
        file_icon_provider = CustomFileIconProvider(icon_service=icon_service, logger=app.log_ui)
        icon_service.icons_updated.connect(file_icon_provider.update_theme)
        icon_service.icons_updated.connect(lambda: ui.parent.setWindowIcon(icon_service.get("app")))
        ui.parent.setWindowIcon(icon_service.get("app"))

        # Attach to UIRefs
        ui.theme_service = theme_service
        ui.highlighter_theme_service = highlighter_theme_service
        ui.icon_service = icon_service
        ui.file_icon_provider = file_icon_provider

        # Bind icon provider to file panel
        ui.files_model.setIconProvider(file_icon_provider)

        # ============================================================
        # DIALOG STATE
        # ============================================================
        dialog_state = DialogState()

        # ============================================================
        # BUSY OVERLAY
        # ============================================================
        busy_overlay = BusyOverlayController(
            parent=ui.parent,
            dialogs=app.dialogs,
            logger=app.log_ui,
        )

        # ============================================================
        # ASYNC OPS
        # ============================================================
        async_ops = AsyncOperationController(
            parent=ui.parent,
            job_mgr=app.job_mgr,
            busy=busy_overlay,
            dialogs=app.dialogs,
            logger=app.log_ui,
        )

        # ============================================================
        # RESULT TABS
        # ============================================================
        update_undo = ui.update_undo_enabled
        results = ResultTabManager(
            parent_widget=ui.parent,
            tabs=ui.result_tabs,
            busy_overlay=busy_overlay,
            async_ops=async_ops,
            col_profile_cache=app.profile_cache,
            set_status=ui.set_status,
            dialogs=app.dialogs,
            set_shape=ui.set_shape,
            update_undo_enabled=update_undo,
            cancel_job=app.job_mgr.cancel_job,
            logger=app.log_ui,
        )

        # ============================================================
        # RESULT TABS WIRING
        # ============================================================
        result_tabs = ui.result_tabs
        result_tab_bar = CustomTabBar(icon_service, parent=result_tabs)
        result_tabs.setTabBar(result_tab_bar)

        icon_service.icons_updated.connect(result_tab_bar.update_icons)

        result_tabs.tabCloseRequested.connect(results.close_tab)
        result_tabs.tabBarDoubleClicked.connect(results.rename_tab)

        # context menu
        result_tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        result_tab_bar.customContextMenuRequested.connect(results.on_tabbar_context_menu)

        ui_invoke(result_tabs.currentChanged.connect, results.on_tab_changed)
        ui_invoke(result_tabs.currentChanged.connect, lambda _: ui.update_undo_enabled())
        # ============================================================
        # VISUALIZATION
        # ============================================================
        visualization = VisualizationController(
            results=results,
            logger=app.log_ui,
        )

        # ============================================================
        # EDITOR PANEL
        # ============================================================
        editor_tab_manager = EditorTabManager()

        def get_connection_engine(connection_name: str) -> str | None:
            """Return configured database engine key for a connection."""
            connections_data = read_connections()
            config = connections_data.get(connection_name)

            if not isinstance(config, dict):
                return None

            engine = config.get("db_type") or config.get("engine")
            return engine if isinstance(engine, str) and engine else None

        editor_panel = EditorPanelController(
            tab_manager=editor_tab_manager,
            tab_widget=ui.editor_tabs,
            icon_service=icon_service,
            highlighter_theme_service=highlighter_theme_service,
            get_cache_for=app.schema_cache.get_cache_for,
            build_schema_dict=build_schema_dict,
            get_connection_engine=get_connection_engine,
            set_status=ui.set_status,
            dialogs=app.dialogs,
            parent=ui.parent,
            logger=app.log_ui,
        )

        # ============================================================
        # EDITOR TABS WIRING
        # ============================================================
        editor_tabs = ui.editor_tabs
        editor_tab_bar = CustomTabBar(icon_service, parent=editor_tabs)
        editor_tabs.setTabBar(editor_tab_bar)

        icon_service.icons_updated.connect(editor_tab_bar.update_icons)

        editor_tabs.tabCloseRequested.connect(editor_panel.close_tab_by_index)
        editor_tabs.tabBarDoubleClicked.connect(editor_panel.rename_tab_by_index)

        # Context menu
        editor_tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        editor_tab_bar.customContextMenuRequested.connect(editor_panel.on_tab_context_menu_requested)

        # Active tab changed → editor controller
        editor_tabs.currentChanged.connect(editor_panel.on_current_tab_changed)

        # ============================================================
        # FILE JOB SERVICE
        # ============================================================
        file_jobs = FileJobService(
            parent_widget=ui.parent,
            async_ops=async_ops,
            results=results,
            set_status=ui.set_status,
            get_active_tab_title=lambda: ui.result_tabs.tabText(ui.result_tabs.currentIndex()).strip() or "export",
            resolve_and_load_df=app.data_io.resolve_and_load_df,
            display_dataframe=results.display_dataframe,
            dialogs=app.dialogs,
            logger=app.log_service,
        )

        # ============================================================
        # DOCUMENT
        # ============================================================
        document = DocumentController(
            parent=ui.parent,
            file_dialogs=app.file_dialogs,
            dialogs=app.dialogs,
            set_status=ui.set_status,
            get_active_tab=editor_panel.get_active_tab,
            get_editor_text=editor_panel.get_active_tab_text,
            set_file_path=editor_tab_manager.set_file_path,
            clear_dirty=editor_tab_manager.clear_dirty,
            update_tab_ui=editor_panel.update_tab,
            create_tab=editor_panel.create_tab,
            insert_sql_into_tab=editor_panel.insert_sql_into_tab,
            open_data_file=file_jobs.open_data_file,
            dialog_state=dialog_state,
            logger=app.log_ui,
        )

        # Late binding of file open actions to editor panel
        editor_panel.bind_file_actions(
            save_sql=document.save_sql,
            save_sql_as=document.save_sql_as,
        )

        # ============================================================
        # FILE PANEL
        # ============================================================
        file_panel = FilePanelController(
            parent_widget=ui.parent,
            files_tree=ui.files_tree,
            files_model=ui.files_model,
            open_any=document.open_any,
            close_result_tabs=results.close_tabs_by_title,
            rename_file=file_jobs.rename_file,
            set_status=ui.set_status,
            file_icon_provider=file_icon_provider,
            dialogs=app.dialogs,
            logger=app.log_ui,
        )
        icon_service.icons_updated.connect(file_panel.update_icons)
        # ============================================================
        # REST CONTROLLER
        # ============================================================
        rest = RestController(
            parent_widget=ui.parent,
            async_ops=async_ops,
            results=results,
            display_dataframe=results.display_dataframe,
            set_status=ui.set_status,
            dialogs=app.dialogs,
            logger=app.log_ui,
        )

        # ============================================================
        # REST PANEL
        # ============================================================
        rest_panel = RestPanelController(
            parent_widget=ui.parent,
            rest_tree=ui.rest_tree,
            rest_controller=rest,
            open_rest_connection_dialog=ui.open_rest_connection_dialog,
            icon_service=icon_service,
            logger=app.log_ui,
        )
        rest_panel.initialize()

        # ============================================================
        # CONNECTION CONTROLLER
        # ============================================================
        connections = ConnectionController(
            get_connection_names=lambda: read_connections().keys(),
            clear_schema_cache=app.schema_cache.clear_for,
            close_db_connection=close_connection,
            logger=app.log_ui,
        )

        editor_panel.bind_connection_provider(
            get_active_connection=lambda: connections.active_connection,
            get_connections=connections.get_connection_names,
        )

        # ============================================================
        # Orchestrate connection → editor tab state/UI updates
        # Intentionally kept here as thin wiring (can be extracted later).
        # ============================================================
        def _on_active_connection_changed(previous: str | None, current: str | None) -> None:
            """Handle active connection changes."""
            editor_tab_manager.on_active_connection_changed(
                previous=previous,
                current=current,
            )

            if current:
                editor_panel.ensure_tab_for_connection(current)

            editor_panel.on_tab_state_changed()

        connections.on_active_connection_changed(_on_active_connection_changed)
        editor_panel.on_active_tab_changed(editor_panel.update_autocomplete_for_active_tab)

        # Rebuild editor autocomplete when asynchronous schema column prefetch
        # completes. SchemaCacheManager invokes this callback with the connection
        # name whose schema changed.
        app.schema_cache.autocomplete_cb = editor_panel.update_autocomplete_for_connection

        # ============================================================
        # SCHEMA CONTROLLER
        # ============================================================
        schema = SchemaController(
            parent_widget=ui.parent,
            tree_widget=ui.schema_tree,
            schema_mgr=app.schema_cache,
            async_ops=async_ops,
            job_mgr=app.job_mgr,
            create_tab_for_connection=editor_panel.create_and_activate_tab,
            insert_sql_into_tab=editor_panel.insert_sql_into_tab,
            set_status=ui.set_status,
            icon_service=icon_service,
            connect_connection=connections.connect,
            disconnect_connection=connections.disconnect,
            get_current_connection=editor_tab_manager.get_connection_for_active_tab,
            restore_baseline_status=ui.restore_status,
            dialogs=app.dialogs,
        )

        # ============================================================
        # CONNECTION ↔ SCHEMA WIRING
        #
        # - ConnectionController owns connection state
        # - SchemaController owns schema tree rendering
        # - WorkbenchServices wire them together
        # ============================================================
        def refresh_schema_connections() -> None:
            schema.refresh_connections(connections.get_connection_names())

        # Rebuild schema tree when connection list changes
        connections.on_connection_list_changed(refresh_schema_connections)

        # Initial schema tree build (no active connection)
        refresh_schema_connections()

        connections.bind_schema_loader(loader=schema.load_schema_tree)

        # ============================================================
        # QUERY CONTROLLER
        # ============================================================
        query = QueryController(
            parent_widget=ui.parent,
            async_ops=async_ops,
            results=results,
            set_status=ui.set_status,
            get_sql=lambda use_sel: editor_panel.get_active_sql(use_selection=use_sel),
            get_current_connection=editor_tab_manager.get_connection_for_active_tab,
            dialogs=app.dialogs,
            logger=app.log_service,
        )
        # ============================================================
        # EXPORT CONTROLLER
        # ============================================================
        export = ExportController(
            parent_widget=ui.parent,
            async_ops=async_ops,
            operation_target=ui.result_tabs,
            results=results,
            set_status=ui.set_status,
            file_jobs=file_jobs,
            get_tab_title=lambda: ui.result_tabs.tabText(ui.result_tabs.currentIndex()).strip(),
            open_url=lambda uri: document.open_html_file(path=uri),
            data_io=app.data_io,
            dialogs=app.dialogs,
            file_dialogs=app.file_dialogs,
            dialog_state=dialog_state,
            logger=app.log_service,
        )

        # ============================================================
        # JOIN CONTROLLER
        # ============================================================
        join = JoinController(
            parent_widget=ui.parent,
            async_ops=async_ops,
            results=results,
            get_active_view=results.active_view,
            get_active_tab_title=lambda: ui.result_tabs.tabText(ui.result_tabs.currentIndex()).strip(),
            list_tab_titles=lambda: [ui.result_tabs.tabText(i).strip() for i in range(ui.result_tabs.count())],
            get_df_for_tab=lambda title: results.get_df_by_title(title),
            set_status=ui.set_status,
            logger=app.log_ui,
        )
        results.set_join_controller(join)

        # ============================================================
        # CONCAT CONTROLLER
        # ============================================================
        concat = ConcatController(
            parent_widget=ui.parent,
            async_ops=async_ops,
            results=results,
            get_active_tab_title=lambda: ui.result_tabs.tabText(ui.result_tabs.currentIndex()).strip(),
            list_tab_titles=lambda: [ui.result_tabs.tabText(i).strip() for i in range(ui.result_tabs.count())],
            get_df_for_tab=lambda title: results.get_df_by_title(title),
            set_status=ui.set_status,
            logger=app.log_ui,
        )
        results.set_concat_controller(concat)

        # ============================================================
        # DERIVED COLUMN
        # ============================================================
        derived_column = DerivedColumnController(
            async_ops=async_ops,
            current_df=results.current_df,
            get_active_view=results.active_view,
            apply_to_active_tab=results.apply_to_active_tab,
            dialogs=app.dialogs,
            main_window=ui.parent,
            logger=app.log_ui,
        )
        results.set_derived_column_controller(derived_column)

        # ============================================================
        # Workbench settings subscriptions
        # ============================================================
        settings_service.subscribe(theme_service.reload_settings, immediate=True)
        settings_service.subscribe(highlighter_theme_service.reload_settings, immediate=True)
        settings_service.subscribe(schema.reload_settings, immediate=True)
        settings_service.subscribe(results.reload_settings, immediate=True)
        settings_service.subscribe(file_panel.reload_settings, immediate=True)
        settings_service.subscribe(document.reload_settings, immediate=True)
        settings_service.subscribe(export.reload_settings, immediate=True)

        if hasattr(query, "reload_settings"):
            settings_service.subscribe(query.reload_settings, immediate=True)

        if hasattr(rest, "reload_settings"):
            settings_service.subscribe(rest.reload_settings, immediate=True)

        # ============================================================
        # Done
        # ============================================================
        app.log_ui.info("Workbench services initialized")
        return cls(
            busy_overlay=busy_overlay,
            async_ops=async_ops,
            schema=schema,
            connections=connections,
            file_panel=file_panel,
            rest_panel=rest_panel,
            file_jobs=file_jobs,
            document=document,
            query=query,
            export=export,
            rest=rest,
            results=results,
            visualization=visualization,
            derived_column=derived_column,
            editor_panel=editor_panel,
            icon_service=icon_service,
            file_icon_provider=file_icon_provider,
            theme_service=theme_service,
            highlighter_theme_service=highlighter_theme_service,
            join=join,
            concat=concat,
            dialog_state=dialog_state,
        )
