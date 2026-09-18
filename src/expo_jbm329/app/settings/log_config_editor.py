"""Log configuration editor dialog for managing logconfig.json.

This module provides the LogConfigEditor class, which is a dedicated dialog
for configuring logging settings, including log levels, file handlers,
and console output. It pulls defaults from DEFAULT_LOG_CONFIG and
interacts with logconfig.json.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.logging.logging_manager import BUILTIN_FORMATTERS as LM_BUILTIN_FORMATTERS
from expo_jbm329.app.settings.config_store import (
    DEFAULT_LOG_CONFIG,
    read_log_config,
    write_log_config,
)
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.path_manager import get_log_path

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.icon.icon_service import IconService

# =============================================================================
# Helper utilities
# =============================================================================


def _is_frozen() -> bool:
    """Checks if the application is running in a frozen state (e.g., PyInstaller).

    Returns:
        True if frozen, False otherwise.
    """
    return bool(getattr(sys, "frozen", False))


def _builtin_formatter_names() -> list[str]:
    """Returns a list of names for all built-in log formatters.

    Returns:
        A list of formatter name strings.
    """
    return list(LM_BUILTIN_FORMATTERS.keys())


LOGLEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


NAMESPACE_LOGGERS: list[str] = [
    "applogger.ui",
    "applogger.service",
    "applogger.jobs",
    "applogger.db",
]

# =============================================================================
# Dialog
# =============================================================================


class LogConfigEditor(QDialog):
    """Dedicated dialog for editing logconfig.json.

    Supports configuring the root log level, file handler, console handler
    (if not frozen), and specific namespace loggers. Includes a reset
    functionality to restore default settings.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        dialogs: DialogService | None = None,
        icon_service: IconService | None = None,
    ) -> None:
        """Initializes the LogConfigEditor dialog.

        Args:
            parent: The parent widget.
            dialogs: Service for showing dialog boxes. Defaults to QtDialogService if None.
            icon_service: Service for retrieving icons.
        """
        super().__init__(parent)

        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._icon_service = icon_service

        self.setWindowTitle(self.tr("Log settings"))
        self.setFixedSize(500, 500)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # IconService-driven icon (theme-aware)
        self._update_icon()
        if self._icon_service:
            self._icon_service.icons_updated.connect(self._update_icon)

        # Current config
        self.log_cfg: dict = read_log_config() or {}

        # Widgets declared here; instantiated in _build_ui
        self.lbl_logfile: QLabel
        self.cb_logger_level: QComboBox
        self.cb_thirdparty_level: QComboBox

        self.chk_file_enabled: QCheckBox
        self.cb_file_level: QComboBox
        self.cb_file_formatter: QComboBox
        self.spin_file_maxbytes: QSpinBox
        self.spin_file_backup: QSpinBox

        self.gb_console: QGroupBox
        self.chk_console_enabled: QCheckBox
        self.cb_stdout_level: QComboBox
        self.cb_stdout_formatter: QComboBox

        self.ns_widgets: dict[str, tuple[QCheckBox, QComboBox]] = {}

        # Build and populate
        self._build_ui()
        self._populate()

    # -------------------------------------------------------------------------
    # Update icon
    # -------------------------------------------------------------------------
    def _update_icon(self) -> None:
        """Updates the window icon using the IconService or a fallback path."""
        if self._icon_service:
            icon = self._icon_service.get("logging")
        else:
            icon = QIcon(":/icons/dark/themes/dark/logging.png")
        self.setWindowIcon(icon)

    # -------------------------------------------------------------------------
    # UI Builder
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Constructs the user interface for the logging configuration dialog."""
        main_layout = QVBoxLayout(self)

        # ------------------------------
        # Top: logfile path + root level
        # ------------------------------
        form_top = QFormLayout()
        self.lbl_logfile = QLabel(self)
        self.lbl_logfile.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form_top.addRow(self.tr("Log file:"), self.lbl_logfile)

        self.cb_logger_level = QComboBox(self)
        self.cb_logger_level.addItems(LOGLEVELS)
        self.cb_logger_level.setFixedWidth(140)  # ← SMALARE SOM DU VILL
        form_top.addRow(self.tr("Root log level:"), self.cb_logger_level)

        self.cb_thirdparty_level = QComboBox(self)
        self.cb_thirdparty_level.addItems(LOGLEVELS)
        self.cb_thirdparty_level.setFixedWidth(140)
        form_top.addRow(self.tr("Third party log level:"), self.cb_thirdparty_level)

        main_layout.addLayout(form_top)

        # ==============================
        # Two-column handler layout
        # ==============================
        cols = QHBoxLayout()

        def bind_enable(chk: QCheckBox, widgets: list[QWidget]) -> None:
            def _apply() -> None:
                e = chk.isChecked()
                for w in widgets:
                    w.setEnabled(e)

            chk.stateChanged.connect(_apply)
            _apply()

        # ------------------------------------------------------------------
        # FILE HANDLER
        # ------------------------------------------------------------------
        gb_file = QGroupBox(self.tr("File"), self)
        form_file = QFormLayout(gb_file)

        self.chk_file_enabled = QCheckBox(self.tr("Activate"), self)
        form_file.addRow(self.chk_file_enabled)

        self.cb_file_level = QComboBox(self)
        self.cb_file_level.addItems(LOGLEVELS)
        form_file.addRow(self.tr("Level:"), self.cb_file_level)

        self.cb_file_formatter = QComboBox(self)
        self.cb_file_formatter.addItems(_builtin_formatter_names())
        form_file.addRow(self.tr("Formatting:"), self.cb_file_formatter)

        self.spin_file_maxbytes = QSpinBox(self)
        self.spin_file_maxbytes.setRange(1_000, 2_000_000_000)
        self.spin_file_maxbytes.setSingleStep(100_000)
        form_file.addRow(self.tr("Max size (bytes):"), self.spin_file_maxbytes)

        self.spin_file_backup = QSpinBox(self)
        self.spin_file_backup.setRange(0, 50)
        form_file.addRow(self.tr("Backup:"), self.spin_file_backup)

        bind_enable(
            self.chk_file_enabled,
            [self.cb_file_level, self.cb_file_formatter, self.spin_file_maxbytes, self.spin_file_backup],
        )

        cols.addWidget(gb_file, 1)

        # ------------------------------------------------------------------
        # CONSOLE HANDLER
        # ------------------------------------------------------------------
        self.gb_console = QGroupBox(self.tr("Console"), self)
        form_console = QFormLayout(self.gb_console)

        self.chk_console_enabled = QCheckBox(self.tr("Activate"), self)
        form_console.addRow(self.chk_console_enabled)

        self.cb_stdout_level = QComboBox(self)
        self.cb_stdout_level.addItems(LOGLEVELS)
        form_console.addRow(self.tr("Level:"), self.cb_stdout_level)

        self.cb_stdout_formatter = QComboBox(self)
        self.cb_stdout_formatter.addItems(_builtin_formatter_names())
        form_console.addRow(self.tr("Formatting:"), self.cb_stdout_formatter)

        bind_enable(self.chk_console_enabled, [self.cb_stdout_level, self.cb_stdout_formatter])

        if _is_frozen():
            self.gb_console.hide()

        cols.addWidget(self.gb_console, 1)

        main_layout.addLayout(cols)

        # ------------------------------------------------------------------
        # NAMESPACE LOGGERS
        # ------------------------------------------------------------------

        gb_ns = QGroupBox(self.tr("Namespace loggers"), self)
        form_ns = QFormLayout(gb_ns)

        for lname in NAMESPACE_LOGGERS:
            row_w = QWidget(self)
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)

            chk = QCheckBox(self.tr("Activate"), self)
            cb = QComboBox(self)
            cb.addItems(LOGLEVELS)
            cb.setFixedWidth(120)

            # Styr enable/disable på nivålådan
            def bind_ns_enable(_chk: QCheckBox, _cb: QComboBox) -> None:
                def _apply() -> None:
                    _cb.setEnabled(_chk.isChecked())

                _chk.stateChanged.connect(_apply)
                _apply()

            bind_ns_enable(chk, cb)

            # Lägg i layout
            row_l.addWidget(chk)
            row_l.addSpacing(8)
            row_l.addWidget(QLabel(self.tr("Level:"), self))
            row_l.addSpacing(4)
            row_l.addWidget(cb, 1)
            row_l.addStretch(1)

            form_ns.addRow(lname + ":", row_w)

            # Spara referenser
            self.ns_widgets[lname] = (chk, cb)

        main_layout.addWidget(gb_ns)

        # ------------------------------
        # ACTION BUTTONS
        # ------------------------------
        row = QHBoxLayout()
        row.addStretch(1)

        btn_reset = QPushButton(self.tr("Reset defaults"), self)
        btn_reset.clicked.connect(self._on_reset_defaults)
        btn_cancel = QPushButton(self.tr("Cancel"), self)
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton(self.tr("Save"), self)
        btn_save.clicked.connect(self._on_save)

        row.addWidget(btn_reset)
        row.addSpacing(10)
        row.addWidget(btn_cancel)
        row.addWidget(btn_save)

        main_layout.addLayout(row)

    # -------------------------------------------------------------------------
    # Populate UI
    # -------------------------------------------------------------------------

    def _ensure_custom_formatter(self, name: str | None) -> None:
        """Ensures the UI combo boxes include a custom formatter name if it exists.

        Args:
            name: The name of the formatter to check and potentially add.
        """
        if name and name not in _builtin_formatter_names():
            self.cb_file_formatter.addItem(name)
            self.cb_stdout_formatter.addItem(name)

    def _populate(self) -> None:
        """Populates the UI fields from the current log configuration.

        Uses default fallbacks from DEFAULT_LOG_CONFIG if values are missing.
        """
        self.lbl_logfile.setText(str(get_log_path()))

        # Root
        root_level = self.log_cfg.get("logger_level", DEFAULT_LOG_CONFIG["logger_level"])
        self.cb_logger_level.setCurrentText(root_level)

        # Third-party (wildcard) level
        tp_level = self.log_cfg.get("third_party_log_level", DEFAULT_LOG_CONFIG.get("third_party_log_level", "WARNING"))
        self.cb_thirdparty_level.setCurrentText(str(tp_level).upper())

        # Handlers
        handlers = self.log_cfg.get("handlers", {}) or {}

        # --- FILE ---
        file_def = DEFAULT_LOG_CONFIG["handlers"]["file"]
        h_file = handlers.get("file", {})
        self._ensure_custom_formatter(h_file.get("formatter"))

        self.chk_file_enabled.setChecked(bool(h_file))
        self.cb_file_level.setCurrentText(h_file.get("level", file_def["level"]))
        self.cb_file_formatter.setCurrentText(h_file.get("formatter", file_def["formatter"]))
        self.spin_file_maxbytes.setValue(int(h_file.get("maxBytes", file_def["maxBytes"])))
        self.spin_file_backup.setValue(int(h_file.get("backupCount", file_def["backupCount"])))

        # --- STDOUT ---
        out_def = DEFAULT_LOG_CONFIG["handlers"]["stdout"]
        h_out = handlers.get("stdout", {})
        self._ensure_custom_formatter(h_out.get("formatter"))

        self.chk_console_enabled.setChecked(bool(h_out) and not _is_frozen())
        self.cb_stdout_level.setCurrentText(h_out.get("level", out_def["level"]))
        self.cb_stdout_formatter.setCurrentText(h_out.get("formatter", out_def["formatter"]))

        # --- NAMESPACE LOGGERS ---

        ns_cfg = self.log_cfg.get("loggers", {}) or {}

        ns_def = DEFAULT_LOG_CONFIG.get("loggers", {}) or {}
        for lname, (chk, cb) in self.ns_widgets.items():
            spec = ns_cfg.get(lname, {})
            if not spec and lname in ns_def:
                spec = ns_def.get(lname, {})
            enabled = bool(spec)
            chk.setChecked(enabled)
            cb.setCurrentText(str(spec.get("level", "INFO")).upper())

    # -------------------------------------------------------------------------
    # Reset to defaults
    # -------------------------------------------------------------------------

    def _on_reset_defaults(self) -> None:
        """Resets only the logging configuration to DEFAULT_LOG_CONFIG."""
        import copy

        self.log_cfg = copy.deepcopy(DEFAULT_LOG_CONFIG)
        self._populate()
        self._dialogs.info(
            parent=self,
            title=self.tr("Reset defaults"),
            text=self.tr("Log configuration has been reset to default values."),
        )

    # -------------------------------------------------------------------------
    # Save handler
    # -------------------------------------------------------------------------

    def _on_save(self) -> None:
        """Persists the current UI state to logconfig.json."""
        new_log = dict(self.log_cfg)
        handlers: dict = {}

        # Root
        new_log["logger_level"] = self.cb_logger_level.currentText()

        # Third party
        new_log["third_party_log_level"] = self.cb_thirdparty_level.currentText()

        # FILE
        if self.chk_file_enabled.isChecked():
            handlers["file"] = {
                "level": self.cb_file_level.currentText(),
                "formatter": self.cb_file_formatter.currentText(),
                "maxBytes": int(self.spin_file_maxbytes.value()),
                "backupCount": int(self.spin_file_backup.value()),
            }

        # STDOUT
        if not _is_frozen() and self.chk_console_enabled.isChecked():
            handlers["stdout"] = {
                "level": self.cb_stdout_level.currentText(),
                "formatter": self.cb_stdout_formatter.currentText(),
            }

        new_log["handlers"] = handlers

        # NAMESPACE LOGGERS
        loggers: dict[str, dict] = {}
        for lname, (chk, cb) in self.ns_widgets.items():
            if chk.isChecked():
                # Vår enkla modell: bara level; propagate=True styrs i config/manager
                loggers[lname] = {
                    "level": cb.currentText(),
                    "propagate": True,
                }
        if loggers:
            new_log["loggers"] = loggers
        else:
            # inga aktiverade namespaces → rensa nyckeln
            new_log.pop("loggers", None)

        try:
            write_log_config(new_log)
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
            title = self.tr("Failure")
            msg = self.tr("Could not save log configuration:\n{error}").format(error=str(e))
            self._dialogs.critical(parent=self, title=title, text=msg)
            return

        self._dialogs.info(
            parent=self, title=self.tr("Log configuration saved"), text=self.tr("Log configuration has been saved.")
        )
        self.accept()
