"""App services module.

This module provides the AppServices dataclass, which serves as a dependency
injection container for the application's core services and infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from expo_jbm329.app.logging.logging_manager import LoggingManager
from expo_jbm329.app.settings.config_store import read_rest_connections
from expo_jbm329.bootstrap.rest_samples import load_rest_samples
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.file.file_dialog_service import QtFileDialogService
from expo_jbm329.i18n.translation_service import TranslationService
from expo_jbm329.services.data_io_service import DataIOService
from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
from expo_jbm329.services.file_loader import FileLoader
from expo_jbm329.services.file_writer import FileWriter
from expo_jbm329.services.job_manager import JobManager
from expo_jbm329.services.rest.registry import rest_registry
from expo_jbm329.services.schema_cache import SchemaCacheManager
from expo_jbm329.services.settings_service import SettingsService
from expo_jbm329.utils.format_utils import fmt_path


@dataclass
class AppServices:
    """Infrastructure-level service container.

    This dataclass serves as a dependency injection root for the application,
    containing all core services and infrastructure components.

    Attributes:
        settings: Core application settings loaded from configuration.
        logging_manager: Manager for logging configuration and logger instances.
        log_ui: Logger for UI-related messages.
        log_service: Logger for service layer messages.
        log_jobs: Logger for job-related messages.
        log_db: Logger for database-related messages.
        log_system: Logger for system-level messages.
        settings_service: Service for managing application settings with pub/sub.
        loader: File loader for data import operations.
        writer: File writer for data export operations.
        data_io: Combined data IO service for loader and writer.
        job_mgr: Manager for background job execution.
        schema_cache: Cache for database schema information.
        profile_cache: Cache for column profile data.
        dialogs: Service for displaying Qt dialogs.
        file_dialogs: Service for Qt file selection dialogs.
    """

    # Core static data
    settings: dict

    # Logging
    logging_manager: LoggingManager
    log_ui: Any
    log_service: Any
    log_jobs: Any
    log_db: Any
    log_system: Any  # applogger

    # Settings
    settings_service: SettingsService

    # IO
    loader: FileLoader
    writer: FileWriter
    data_io: DataIOService

    # Background infra
    job_mgr: JobManager
    schema_cache: SchemaCacheManager
    profile_cache: ColumnProfileCache

    # Dialog services
    dialogs: QtDialogService
    file_dialogs: QtFileDialogService

    # Translation service
    translation_service: TranslationService

    # ==================================================================
    # Factory
    # ==================================================================
    @classmethod
    def build(cls, settings: dict) -> AppServices:
        """Builds the full application infrastructure layer.

        This factory method initializes and configures all core services,
        including logging, settings, data IO, job management, caches, and dialogs.
        It must be called once during application startup.

        Args:
            settings: Dictionary of application settings from configuration.

        Returns:
            An initialized AppServices instance with all services ready.
        """
        # -------------------------
        # 1) Logging
        # -------------------------
        logging_manager = LoggingManager()
        logging_manager.setup()

        log_ui = logging_manager.ui_logger
        log_service = logging_manager.service_logger
        log_jobs = logging_manager.jobs_logger
        log_db = logging_manager.db_logger
        log_system = logging_manager.system_logger

        # -------------------------
        # 2) Settings (pub/sub)
        # -------------------------
        settings_service = SettingsService(
            initial_settings=settings,
            dispatcher=None,  # UI dispatcher set later in SqlEditor
            logger=log_service,
        )

        # -------------------------
        # 3) Data IO (loader/writer)
        # -------------------------
        loader = FileLoader(logger=log_service)
        writer = FileWriter(logger=log_service)
        data_io = DataIOService(loader, writer, logger=log_service)

        # -------------------------
        # 4) Background infrastructure
        # -------------------------
        job_mgr = JobManager(logger=log_jobs)  # UI parent injected later
        schema_cache = SchemaCacheManager(
            status_cb=None,
            progress_cb=None,
            autocomplete_cb=None,
            logger=log_service
        )
        profile_cache = ColumnProfileCache(capacity=256)

        # -------------------------
        # 5) Dialogs (Qt)
        # -------------------------
        dialogs = QtDialogService()
        file_dialogs = QtFileDialogService()

        # -------------------------
        # 6) Internationalization
        # -------------------------
        translation_service = TranslationService(logger=log_ui)

        # -------------------------
        # 7) Persistent resources bootstrap
        # -------------------------
        # REST connections (persistent)
        rest_registry.load_user_connections(read_rest_connections())

        # REST Samples (runtime only)
        rest_registry.load_samples(load_rest_samples())

        # ============================================================
        # Backend settings subscriptions
        # ============================================================
        settings_service.subscribe(data_io.reload_settings, immediate=True)
        settings_service.subscribe(schema_cache.reload_settings, immediate=True)
        settings_service.subscribe(translation_service.reload_settings, immediate=True)

        # -------------------------
        # Done
        # -------------------------
        log_service.info("AppServices initialized.")

        return cls(
            settings=settings,
            logging_manager=logging_manager,
            log_ui=log_ui,
            log_service=log_service,
            log_jobs=log_jobs,
            log_db=log_db,
            log_system=log_system,
            settings_service=settings_service,
            loader=loader,
            writer=writer,
            data_io=data_io,
            job_mgr=job_mgr,
            schema_cache=schema_cache,
            profile_cache=profile_cache,
            dialogs=dialogs,
            file_dialogs=file_dialogs,
            translation_service=translation_service,
        )
