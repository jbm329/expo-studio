"""Settings editor dialog for managing general application settings.

This module provides the SettingsEditor class, which is a comprehensive dialog
for editing Expo user settings (settings.json). It handles configurations for
themes, documents directory, undo limits, CSV/Excel processing, and schema cache.

The user interface text is in Swedish, while comments and docstrings
follow Google-style English conventions.
"""

from __future__ import annotations

import contextlib
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
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.settings.config_store import (
    DEFAULT_SETTINGS,
    load_settings,
    save_settings,
)
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.file.file_dialog_service import (
    DirectoryRequest,
    FileDialogService,
    QtFileDialogService,
)
from expo_jbm329.utils.path_manager import (
    ensure_all_dirs,
    get_documents_dir,
)

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.icon.icon_service import IconService
    from expo_jbm329.workbench.theme.highlighter_theme_service import HighlighterThemeService

THEMES = ["system"]

CSV_ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]


LANGUAGES = [
    ("Svenska", "sv"),
    ("English", "en"),
]


class SettingsEditor(QDialog):
    """Dedicated dialog for modifying general Expo settings (settings.json).

    Supports configuring core application behavior, including UI themes,
    file paths, undo history, data import/export parameters, and database
    metadata caching.

    The UI text is Swedish, while comments and docstrings are in English.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        dialogs: DialogService | None = None,
        file_dialogs: FileDialogService | None = None,
        highlighter_theme_service: HighlighterThemeService | None = None,
        icon_service: IconService | None = None,
    ):
        """Initializes the SettingsEditor dialog.

        Args:
            parent: The parent widget.
            dialogs: Service for showing dialog boxes. Defaults to QtDialogService if None.
            file_dialogs: Service for file and directory selection.
            highlighter_theme_service: Service for managing syntax highlighting themes.
            icon_service: Service for retrieving icons.
        """
        super().__init__(parent)

        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._file_dialogs = file_dialogs if file_dialogs is not None else QtFileDialogService()
        self._icon_service = icon_service

        self.setWindowTitle(self.tr("Settings"))
        self.setFixedSize(750, 600)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Set icon via IconService
        self._update_icon()
        if self._icon_service:
            self._icon_service.icons_updated.connect(self._update_icon)

        # Load user settings
        self.settings: dict = load_settings()
        self.highlighter_theme_service = highlighter_theme_service

        # Build UI + populate fields
        self._build_ui()
        self._populate()

    # -------------------------------------------------------------------------
    # Update icon
    # -------------------------------------------------------------------------
    def _update_icon(self):
        """Updates the window icon using the IconService or a fallback path."""
        if self._icon_service:
            icon = self._icon_service.get("settings")
        else:
            icon = QIcon(":/icons/dark/themes/dark/settings.png")  # fallback

        if not icon.isNull():
            self.setWindowIcon(icon)

    # -------------------------------------------------------------------------
    # UI Builder
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Constructs the user interface for the settings editor dialog."""
        main_layout = QVBoxLayout(self)

        # ================================================================
        # GROUP: Basic settings
        # ================================================================
        box_top = QGroupBox(self.tr("Basic settings"), self)
        form_top = QFormLayout(box_top)

        row_theme = QHBoxLayout()

        # Language selector (FIRST)
        row_theme.addWidget(QLabel(self.tr("Language:"), self))

        self.cmb_language = QComboBox(self)
        self.cmb_language.setFixedWidth(125)

        for label, code in LANGUAGES:
            self.cmb_language.addItem(label, code)

        row_theme.addWidget(self.cmb_language)

        row_theme.addSpacing(20)

        # GUI-Theme (light/dark/system)
        row_theme.addWidget(QLabel(self.tr("GUI theme:"), self))

        self.cmb_theme = QComboBox(self)
        self.cmb_theme.setEnabled(False)
        self.cmb_theme.setFixedWidth(125)
        self.cmb_theme.addItems(["system", "light", "dark"])
        row_theme.addWidget(self.cmb_theme)

        # Highlighter-theme
        row_theme.addSpacing(20)
        row_theme.addWidget(QLabel(self.tr("Highlighter theme:"), self))
        self.cmb_highlighter = QComboBox(self)
        self.cmb_highlighter.setFixedWidth(125)
        row_theme.addWidget(self.cmb_highlighter)

        row_theme.addStretch(1)

        # One single row label
        form_top.addRow(row_theme)

        # --- Documents dir (row with line edit + picker) ---
        row_path = QHBoxLayout()
        self.txt_documents_dir = QLineEdit(self)
        btn_pick = QPushButton(self.tr("Select directory…"), self)
        btn_pick.clicked.connect(self._pick_documents_dir)
        row_path.addWidget(self.txt_documents_dir, 1)
        row_path.addWidget(btn_pick, 0)
        form_top.addRow(self.tr("Documents directory:"), row_path)

        # Undo settings row (same row for both parameters) ---
        row_undo = QHBoxLayout()

        # undo_limit_per_tab
        lbl_undo_limit = QLabel(self.tr("Max undo steps/tab:"), self)
        self.spin_undo_limit = QSpinBox(self)
        self.spin_undo_limit.setRange(0, 50)
        self.spin_undo_limit.setSingleStep(1)
        self.spin_undo_limit.setFixedWidth(90)

        # spacing
        row_undo.addWidget(lbl_undo_limit)
        row_undo.addWidget(self.spin_undo_limit)
        row_undo.addSpacing(20)

        # max_size_allow_undo_mb
        lbl_undo_maxmb = QLabel(self.tr("Max undo size (MB):"), self)
        self.spin_undo_max_mb = QSpinBox(self)
        self.spin_undo_max_mb.setRange(100, 5000)
        self.spin_undo_max_mb.setSingleStep(100)
        self.spin_undo_max_mb.setFixedWidth(100)

        row_undo.addWidget(lbl_undo_maxmb)
        row_undo.addWidget(self.spin_undo_max_mb)
        row_undo.addStretch(1)

        # Add the combined row under document dir
        form_top.addRow(row_undo)

        main_layout.addWidget(box_top)

        # ================================================================
        # GROUPS: CSV and Excel
        # ================================================================
        row_csv_excel = QHBoxLayout()

        # ---- CSV ----
        box_csv = QGroupBox(self.tr("CSV settings"), self)
        form_csv = QFormLayout(box_csv)

        self.spin_csv_read_chunksize = QSpinBox(self)
        self.spin_csv_read_chunksize.setRange(1, 50_000_000)
        self.spin_csv_read_chunksize.setSingleStep(50_000)
        form_csv.addRow(self.tr("Read bit size (rows):"), self.spin_csv_read_chunksize)

        self.spin_csv_write_chunk_size = QSpinBox(self)
        self.spin_csv_write_chunk_size.setRange(1, 50_000_000)
        self.spin_csv_write_chunk_size.setSingleStep(50_000)
        form_csv.addRow(self.tr("Write bit size (rows):"), self.spin_csv_write_chunk_size)

        self.cmb_csv_encoding = QComboBox(self)
        self.cmb_csv_encoding.addItems(CSV_ENCODINGS)
        form_csv.addRow(self.tr("Standard encoding:"), self.cmb_csv_encoding)

        self.chk_csv_sniff = QCheckBox(self.tr("Identify delimiter automatically"), self)
        self.chk_csv_sniff.setToolTip(
            self.tr("When this is on the reader tries to guess the delimiter, ex. ',' ';' '\\t' '|'.")
        )
        form_csv.addRow("", self.chk_csv_sniff)

        self.cmb_csv_default_sep = QComboBox(self)

        self.cmb_csv_default_sep.addItem(self.tr("Automatic"), None)
        self.cmb_csv_default_sep.addItem(",", ",")
        self.cmb_csv_default_sep.addItem(";", ";")
        self.cmb_csv_default_sep.addItem("\\t", "\t")
        self.cmb_csv_default_sep.addItem("|", "|")
        self.cmb_csv_default_sep.setToolTip(
            self.tr("Standard delimiter used when sniff is disabled or as fallback on failure.")
        )

        form_csv.addRow(self.tr("Standard delimiter:"), self.cmb_csv_default_sep)

        self.chk_csv_sniff.toggled.connect(self._sync_csv_sep_enabled)
        self._sync_csv_sep_enabled()

        # ---- Excel ----
        box_excel = QGroupBox(self.tr("Excel settings"), self)
        form_excel = QFormLayout(box_excel)

        self.spin_excel_chunk_size = QSpinBox(self)
        self.spin_excel_chunk_size.setRange(1, 5_000_000)
        self.spin_excel_chunk_size.setSingleStep(5_000)
        form_excel.addRow(self.tr("Read/write bit size (rows):"), self.spin_excel_chunk_size)

        self.spin_excel_max_rows = QSpinBox(self)
        self.spin_excel_max_rows.setRange(1, 1_500_000)
        self.spin_excel_max_rows.setSingleStep(10_000)
        form_excel.addRow(self.tr("Max rows per sheet:"), self.spin_excel_max_rows)

        self.chk_excel_streaming = QCheckBox(self.tr("Excel streaming"), self)
        form_excel.addRow("", self.chk_excel_streaming)

        row_csv_excel.addWidget(box_csv, 1)
        row_csv_excel.addWidget(box_excel, 1)

        main_layout.addLayout(row_csv_excel)

        # ================================================================
        # GROUP: Schema-cache
        # ================================================================
        row_schema = QHBoxLayout()

        # -------------------------
        # VÄNSTER: Schema-cache
        # -------------------------
        box_sc = QGroupBox(self.tr("Schema cache"), self)
        form_sc = QFormLayout(box_sc)

        self.spin_schema_limit = QSpinBox(self)
        self.spin_schema_limit.setRange(0, 50_000)
        self.spin_schema_limit.setSingleStep(100)
        form_sc.addRow(self.tr("Max objects preload:"), self.spin_schema_limit)

        self.spin_schema_batch = QSpinBox(self)
        self.spin_schema_batch.setRange(1, 10_000)
        self.spin_schema_batch.setSingleStep(10)
        form_sc.addRow(self.tr("Batch size:"), self.spin_schema_batch)

        self.spin_schema_ttl = QSpinBox(self)
        self.spin_schema_ttl.setRange(1, 86400)
        self.spin_schema_ttl.setSingleStep(10)
        form_sc.addRow(self.tr("TTL (seconds):"), self.spin_schema_ttl)

        row_schema.addWidget(box_sc, 1)

        # -------------------------
        # HÖGER: Editor
        # -------------------------
        box_editor = QGroupBox(self.tr("SQL editor"), self)
        form_editor = QFormLayout(box_editor)

        self.spin_editor_topn = QSpinBox(self)
        self.spin_editor_topn.setRange(0, 1_000_000)  # allow 0 = no limit
        self.spin_editor_topn.setSingleStep(1000)
        form_editor.addRow(self.tr("SELECT TOP N value (0 = no limit):"), self.spin_editor_topn)

        row_schema.addWidget(box_editor, 1)

        main_layout.addLayout(row_schema)

        # ================================================================
        # ACTION BUTTONS
        # ================================================================
        row = QHBoxLayout()
        row.addStretch(1)

        btn_reset = QPushButton(self.tr("Reset defaults"), self)
        btn_reset.clicked.connect(self._reset_defaults)
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

    def _populate(self) -> None:
        """Populates the UI fields from the current application settings.

        Uses default fallbacks from DEFAULT_SETTINGS if values are missing.
        """
        s = self.settings

        editor_defaults = DEFAULT_SETTINGS.get("workbench", {})
        editor = s.get("workbench", editor_defaults)
        if editor is None:
            msg = "Workbench settings are unavailable."
            raise RuntimeError(msg)

        # Language
        current_lang = editor.get("language", editor_defaults.get("language", "en"))

        found = False
        for i in range(self.cmb_language.count()):
            if self.cmb_language.itemData(i) == current_lang:
                self.cmb_language.setCurrentIndex(i)
                found = True
                break

        if not found:
            self.cmb_language.setCurrentIndex(0)

        # Theme
        self.cmb_theme.setCurrentText(editor.get("theme", editor_defaults.get("theme", "system")))

        # Highlighter theme (dynamic list)
        if self.highlighter_theme_service is None:
            msg = "Highlighter theme service is not configured."
            raise RuntimeError(msg)
        pairs = self.highlighter_theme_service.available_themes_with_labels()

        self.cmb_highlighter.clear()
        self._theme_key_map = {}  # friendly_text -> key

        for key, friendly in pairs:
            self.cmb_highlighter.addItem(friendly)
            self._theme_key_map[friendly] = key

        # Select current theme (from settings)
        current_key = editor.get("highlighter_theme", "system")
        for friendly, key in self._theme_key_map.items():
            if key == current_key:
                self.cmb_highlighter.setCurrentText(friendly)
                break

        # Documents dir
        self.txt_documents_dir.setText(str(get_documents_dir(s)))

        # Undo settings
        self.spin_undo_limit.setValue(
            int(editor.get("undo_limit_per_tab", editor_defaults.get("undo_limit_per_tab", 20)))
        )
        self.spin_undo_max_mb.setValue(
            int(editor.get("max_size_allow_undo_mb", editor_defaults.get("max_size_allow_undo_mb", 100)))
        )

        # CSV settings
        csv = s.get("csv", DEFAULT_SETTINGS["csv"])
        self.spin_csv_read_chunksize.setValue(
            csv.get("read_chunk_size_rows", DEFAULT_SETTINGS["csv"]["read_chunk_size_rows"])
        )
        self.spin_csv_write_chunk_size.setValue(
            csv.get("write_chunk_size_rows", DEFAULT_SETTINGS["csv"]["write_chunk_size_rows"])
        )
        self.cmb_csv_encoding.setCurrentText(csv.get("default_encoding", DEFAULT_SETTINGS["csv"]["default_encoding"]))

        sniff_default = DEFAULT_SETTINGS["csv"].get("sniff_delimiter", True)
        self.chk_csv_sniff.setChecked(bool(csv.get("sniff_delimiter", sniff_default)))
        self._sync_csv_sep_enabled()

        # Map 'default_sep' from settings -> combobox index
        default_sep_default = DEFAULT_SETTINGS["csv"].get("default_sep", ",")
        sep_val = csv.get("default_sep", default_sep_default)

        # Normalize None / "" → "Auto"
        index = self.cmb_csv_default_sep.findData(sep_val)
        if index == -1:
            index = self.cmb_csv_default_sep.findData(None)

        self.cmb_csv_default_sep.setCurrentIndex(index)

        # Excel settings
        excel = s.get("excel", DEFAULT_SETTINGS["excel"])
        self.spin_excel_chunk_size.setValue(excel.get("chunk_size_rows", DEFAULT_SETTINGS["excel"]["chunk_size_rows"]))
        self.spin_excel_max_rows.setValue(
            excel.get("max_rows_per_sheet", DEFAULT_SETTINGS["excel"]["max_rows_per_sheet"])
        )
        self.chk_excel_streaming.setChecked(excel.get("streaming", DEFAULT_SETTINGS["excel"]["streaming"]))

        # schema cache
        sc = s.get("schema_cache", DEFAULT_SETTINGS["schema_cache"])
        self.spin_schema_limit.setValue(sc.get("prefetch_limit", DEFAULT_SETTINGS["schema_cache"]["prefetch_limit"]))
        self.spin_schema_batch.setValue(
            sc.get("prefetch_batch_size", DEFAULT_SETTINGS["schema_cache"]["prefetch_batch_size"])
        )
        self.spin_schema_ttl.setValue(sc.get("ttl_seconds", DEFAULT_SETTINGS["schema_cache"].get("ttl_seconds", 300)))

        # (workbench - remaining)
        self.spin_editor_topn.setValue(editor.get("gen_top_n", editor_defaults.get("gen_top_n", 10)))

    # -------------------------------------------------------------------------
    # Reset button
    # -------------------------------------------------------------------------

    def _reset_defaults(self) -> None:
        """Resets all general settings to their default values."""
        self.settings = DEFAULT_SETTINGS.copy()
        self._populate()
        self._dialogs.info(self, self.tr("Reset defaults"), self.tr("Settings have been reset to default values."))

    # -------------------------------------------------------------------------
    # File picking
    # -------------------------------------------------------------------------

    def _pick_documents_dir(self) -> None:
        """Opens a directory picker to select the documents root directory."""
        base = self.txt_documents_dir.text().strip()
        req = DirectoryRequest(self.tr("Select documents root (Expo)"), base)
        picked = self._file_dialogs.get_existing_directory(self, req)
        if picked:
            self.txt_documents_dir.setText(picked)

    # -------------------------------------------------------------------------
    # Save to settings.json
    # -------------------------------------------------------------------------

    def _on_save(self) -> None:
        """Persists the current UI state to settings.json."""
        new_s = dict(self.settings)

        # documents
        new_s["documents_dir"] = self.txt_documents_dir.text().strip() or None

        # csv
        # • Save sniff + default sep (mapped from combo)
        default_sep_value = self.cmb_csv_default_sep.currentData()

        new_s["csv"] = {
            "read_chunk_size_rows": int(self.spin_csv_read_chunksize.value()),
            "write_chunk_size_rows": int(self.spin_csv_write_chunk_size.value()),
            "default_encoding": self.cmb_csv_encoding.currentText(),
            "sniff_delimiter": bool(self.chk_csv_sniff.isChecked()),
            "default_sep": default_sep_value,
        }

        # excel
        new_s["excel"] = {
            "chunk_size_rows": int(self.spin_excel_chunk_size.value()),
            "max_rows_per_sheet": int(self.spin_excel_max_rows.value()),
            "streaming": bool(self.chk_excel_streaming.isChecked()),
        }

        # schema cache
        new_s["schema_cache"] = {
            "prefetch_limit": int(self.spin_schema_limit.value()),
            "prefetch_batch_size": int(self.spin_schema_batch.value()),
            "ttl_seconds": int(self.spin_schema_ttl.value()),
        }

        # workbench settings
        # NOTE: Keep all workbench-related values together
        editor_defaults = DEFAULT_SETTINGS.get("workbench", {})
        editor_existing = dict(new_s.get("workbench", {}))

        label = self.cmb_highlighter.currentText()
        key = self._theme_key_map.get(label, "system")

        editor_updated = {
            # From top row (Language, Theme, Highlighter)
            "language": self.cmb_language.currentData(),
            "theme": self.cmb_theme.currentText(),
            "highlighter_theme": key,
            # Core workbench features
            "gen_top_n": int(self.spin_editor_topn.value()),
            "undo_limit_per_tab": int(self.spin_undo_limit.value()),
            "max_size_allow_undo_mb": int(self.spin_undo_max_mb.value()),
        }

        # Merge to preserve any other workbench keys users/config may have
        editor_existing.update(editor_updated)
        new_s["workbench"] = editor_existing or editor_defaults

        try:
            save_settings(new_s)
            ensure_all_dirs(new_s)
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
            msg = self.tr("Could not save settings:\n%1").replace("%1", str(e))
            self._dialogs.critical(self, title, msg)
            return

        self._dialogs.info(self, self.tr("Saved settings"), self.tr("Settings have been saved."))
        self.accept()

    # =============================================================================
    # Helper
    # =============================================================================

    def _sync_csv_sep_enabled(self) -> None:
        """Updates the enabled state of the CSV separator combo based on the sniff toggle."""
        with contextlib.suppress(Exception):
            self.cmb_csv_default_sep.setEnabled(not self.chk_csv_sniff.isChecked())
