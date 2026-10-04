from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from expo_jbm329.app.settings.config_store import (
    DEFAULT_SETTINGS,
    load_settings,
    save_settings,
)
from expo_jbm329.app.settings.settings_editor import SettingsEditor


@pytest.fixture
def mock_dialogs():
    return MagicMock()


@pytest.fixture
def mock_file_dialogs():
    return MagicMock()


@pytest.fixture
def mock_highlighter_service():
    mock = MagicMock()
    mock.available_themes_with_labels.return_value = [
        ("system", "System"),
        ("dark_modern", "Dark Modern"),
        ("light_modern", "Light Modern"),
    ]
    return mock


def test_settings_editor_gui_theme_disabled_and_system(mock_dialogs, mock_file_dialogs, mock_highlighter_service):
    dialog = SettingsEditor(
        dialogs=mock_dialogs,
        file_dialogs=mock_file_dialogs,
        highlighter_theme_service=mock_highlighter_service,
    )
    assert dialog.cmb_theme.isEnabled() is False
    assert dialog.cmb_theme.currentText() == "system"


def test_settings_editor_init_populates_controls(tmp_path, mock_dialogs, mock_file_dialogs, mock_highlighter_service):
    custom_docs = str(tmp_path / "MyDocs")
    custom_settings = {
        "documents_dir": custom_docs,
        "workbench": {
            "language": "sv",
            "theme": "system",
            "highlighter_theme": "dark_modern",
            "gen_top_n": 500,
            "undo_limit_per_tab": 15,
            "max_size_allow_undo_mb": 200,
        },
        "csv": {
            "read_chunk_size_rows": 50000,
            "write_chunk_size_rows": 60000,
            "default_encoding": "latin-1",
            "sniff_delimiter": False,
            "default_sep": ";",
        },
        "excel": {
            "chunk_size_rows": 10000,
            "max_rows_per_sheet": 500000,
            "streaming": False,
        },
        "schema_cache": {
            "prefetch_limit": 300,
            "prefetch_batch_size": 50,
            "ttl_seconds": 600,
        },
    }
    save_settings(custom_settings)

    dialog = SettingsEditor(
        dialogs=mock_dialogs,
        file_dialogs=mock_file_dialogs,
        highlighter_theme_service=mock_highlighter_service,
    )

    # Workbench
    assert dialog.cmb_language.currentData() == "sv"
    assert dialog.cmb_theme.currentText() == "system"
    assert dialog.cmb_highlighter.currentText() == "Dark Modern"
    assert dialog.txt_documents_dir.text() == custom_docs
    assert dialog.spin_undo_limit.value() == 15
    assert dialog.spin_undo_max_mb.value() == 200
    assert dialog.spin_editor_topn.value() == 500

    # CSV
    assert dialog.spin_csv_read_chunksize.value() == 50000
    assert dialog.spin_csv_write_chunk_size.value() == 60000
    assert dialog.cmb_csv_encoding.currentText() == "latin-1"
    assert dialog.chk_csv_sniff.isChecked() is False
    assert dialog.cmb_csv_default_sep.currentData() == ";"
    assert dialog.cmb_csv_default_sep.isEnabled() is True

    # Excel
    assert dialog.spin_excel_chunk_size.value() == 10000
    assert dialog.spin_excel_max_rows.value() == 500000
    assert dialog.chk_excel_streaming.isChecked() is False

    # Schema Cache
    assert dialog.spin_schema_limit.value() == 300
    assert dialog.spin_schema_batch.value() == 50
    assert dialog.spin_schema_ttl.value() == 600


def test_settings_editor_save_updates_all_settings(tmp_path, mock_dialogs, mock_file_dialogs, mock_highlighter_service):
    dialog = SettingsEditor(
        dialogs=mock_dialogs,
        file_dialogs=mock_file_dialogs,
        highlighter_theme_service=mock_highlighter_service,
    )

    updated_docs = str(tmp_path / "UpdatedDocs")

    # Update workbench settings
    sv_index = dialog.cmb_language.findData("sv")
    dialog.cmb_language.setCurrentIndex(sv_index)
    dialog.cmb_highlighter.setCurrentText("Dark Modern")
    dialog.txt_documents_dir.setText(updated_docs)
    dialog.spin_undo_limit.setValue(25)
    dialog.spin_undo_max_mb.setValue(300)
    dialog.spin_editor_topn.setValue(2000)

    # Update CSV settings
    dialog.spin_csv_read_chunksize.setValue(80000)
    dialog.spin_csv_write_chunk_size.setValue(90000)
    dialog.cmb_csv_encoding.setCurrentText("utf-8-sig")
    dialog.chk_csv_sniff.setChecked(False)
    dialog.cmb_csv_default_sep.setCurrentIndex(dialog.cmb_csv_default_sep.findData(";"))

    # Update Excel settings
    dialog.spin_excel_chunk_size.setValue(30000)
    dialog.spin_excel_max_rows.setValue(800000)
    dialog.chk_excel_streaming.setChecked(False)

    # Update Schema Cache settings
    dialog.spin_schema_limit.setValue(400)
    dialog.spin_schema_batch.setValue(80)
    dialog.spin_schema_ttl.setValue(900)

    # Save
    dialog._on_save()

    assert mock_dialogs.info.call_count == 1
    saved = load_settings()

    assert saved["documents_dir"] == updated_docs
    assert saved["workbench"]["language"] == "sv"
    assert saved["workbench"]["theme"] == "system"
    assert saved["workbench"]["highlighter_theme"] == "dark_modern"
    assert saved["workbench"]["gen_top_n"] == 2000
    assert saved["workbench"]["undo_limit_per_tab"] == 25
    assert saved["workbench"]["max_size_allow_undo_mb"] == 300

    assert saved["csv"]["read_chunk_size_rows"] == 80000
    assert saved["csv"]["write_chunk_size_rows"] == 90000
    assert saved["csv"]["default_encoding"] == "utf-8-sig"
    assert saved["csv"]["sniff_delimiter"] is False
    assert saved["csv"]["default_sep"] == ";"

    assert saved["excel"]["chunk_size_rows"] == 30000
    assert saved["excel"]["max_rows_per_sheet"] == 800000
    assert saved["excel"]["streaming"] is False

    assert saved["schema_cache"]["prefetch_limit"] == 400
    assert saved["schema_cache"]["prefetch_batch_size"] == 80
    assert saved["schema_cache"]["ttl_seconds"] == 900


def test_settings_editor_reset_defaults(tmp_path, mock_dialogs, mock_file_dialogs, mock_highlighter_service):
    dialog = SettingsEditor(
        dialogs=mock_dialogs,
        file_dialogs=mock_file_dialogs,
        highlighter_theme_service=mock_highlighter_service,
    )

    # Modify values away from defaults
    dialog.cmb_language.setCurrentIndex(dialog.cmb_language.findData("sv"))
    dialog.spin_undo_limit.setValue(35)
    dialog.spin_undo_max_mb.setValue(400)
    dialog.spin_csv_read_chunksize.setValue(5000)
    dialog.chk_csv_sniff.setChecked(False)
    dialog.chk_excel_streaming.setChecked(False)
    dialog.spin_schema_limit.setValue(999)

    # Reset defaults
    dialog._reset_defaults()

    assert mock_dialogs.info.call_count == 1

    wb_defaults = DEFAULT_SETTINGS["workbench"]
    csv_defaults = DEFAULT_SETTINGS["csv"]
    excel_defaults = DEFAULT_SETTINGS["excel"]
    sc_defaults = DEFAULT_SETTINGS["schema_cache"]

    assert dialog.cmb_language.currentData() == wb_defaults["language"]
    assert dialog.cmb_theme.currentText() == "system"
    assert dialog.cmb_highlighter.currentText() == "System"
    assert dialog.spin_undo_limit.value() == wb_defaults["undo_limit_per_tab"]
    assert dialog.spin_undo_max_mb.value() == wb_defaults["max_size_allow_undo_mb"]
    assert dialog.spin_editor_topn.value() == wb_defaults["gen_top_n"]

    assert dialog.spin_csv_read_chunksize.value() == csv_defaults["read_chunk_size_rows"]
    assert dialog.spin_csv_write_chunk_size.value() == csv_defaults["write_chunk_size_rows"]
    assert dialog.cmb_csv_encoding.currentText() == csv_defaults["default_encoding"]
    assert dialog.chk_csv_sniff.isChecked() == csv_defaults["sniff_delimiter"]

    assert dialog.spin_excel_chunk_size.value() == excel_defaults["chunk_size_rows"]
    assert dialog.spin_excel_max_rows.value() == excel_defaults["max_rows_per_sheet"]
    assert dialog.chk_excel_streaming.isChecked() == excel_defaults["streaming"]

    assert dialog.spin_schema_limit.value() == sc_defaults["prefetch_limit"]
    assert dialog.spin_schema_batch.value() == sc_defaults["prefetch_batch_size"]
    assert dialog.spin_schema_ttl.value() == sc_defaults["ttl_seconds"]


def test_settings_editor_documents_dir_selection(tmp_path, mock_dialogs, mock_file_dialogs, mock_highlighter_service):
    dialog = SettingsEditor(
        dialogs=mock_dialogs,
        file_dialogs=mock_file_dialogs,
        highlighter_theme_service=mock_highlighter_service,
    )

    selected_dir = str(tmp_path / "ChosenDocs")
    mock_file_dialogs.get_existing_directory.return_value = selected_dir

    dialog._pick_documents_dir()
    assert dialog.txt_documents_dir.text() == selected_dir

    # When file dialog is cancelled (returns None or empty)
    mock_file_dialogs.get_existing_directory.return_value = None
    dialog._pick_documents_dir()
    assert dialog.txt_documents_dir.text() == selected_dir


def test_settings_editor_sniff_toggle_updates_separator_enabled(
    mock_dialogs, mock_file_dialogs, mock_highlighter_service
):
    dialog = SettingsEditor(
        dialogs=mock_dialogs,
        file_dialogs=mock_file_dialogs,
        highlighter_theme_service=mock_highlighter_service,
    )

    dialog.chk_csv_sniff.setChecked(True)
    assert dialog.cmb_csv_default_sep.isEnabled() is False

    dialog.chk_csv_sniff.setChecked(False)
    assert dialog.cmb_csv_default_sep.isEnabled() is True


def test_settings_editor_save_handles_error(monkeypatch, mock_dialogs, mock_file_dialogs, mock_highlighter_service):
    dialog = SettingsEditor(
        dialogs=mock_dialogs,
        file_dialogs=mock_file_dialogs,
        highlighter_theme_service=mock_highlighter_service,
    )

    def _fail_save(*args, **kwargs):
        msg = "Permission denied"
        raise OSError(msg)

    monkeypatch.setattr("expo_jbm329.app.settings.settings_editor.save_settings", _fail_save)

    dialog._on_save()
    assert mock_dialogs.critical.call_count == 1
