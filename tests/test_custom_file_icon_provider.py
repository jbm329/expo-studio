
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QFileInfo
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileIconProvider

from expo_jbm329.workbench.icon.custom_file_icon_provider import (
    CustomFileIconProvider,
    _normalize_ext,
)


@pytest.fixture
def icon_service():
    service = MagicMock()
    service.current_theme.return_value = "light"
    # Return a unique QIcon for each name to verify mapping
    service.get.side_effect = lambda name: QIcon()
    return service

@pytest.fixture
def icon_provider(icon_service):
    provider = CustomFileIconProvider(icon_service)
    provider.update_theme()
    return provider

def test_normalize_ext():
    """Verifies extension normalization logic."""
    assert _normalize_ext("sql") == ".sql"
    assert _normalize_ext(".SQL") == ".sql"
    assert _normalize_ext("  .csv  ") == ".csv"
    assert _normalize_ext("") == ""
    assert _normalize_ext(None) == ""

def test_init(icon_service):
    """Verifies initial state of the provider."""
    provider = CustomFileIconProvider(icon_service)
    assert provider._icon_service == icon_service
    assert provider._icons_by_ext == {}
    assert provider._icons_by_multi_ext == {}

def test_update_theme(icon_service):
    """Verifies that update_theme populates the icon maps."""
    provider = CustomFileIconProvider(icon_service)
    
    # Pre-check
    assert provider._icons_by_ext == {}
    
    provider.update_theme()
    
    # Verify base icons loaded
    icon_service.get.assert_any_call("folder")
    icon_service.get.assert_any_call("generic_file")
    
    # Verify extension map is populated
    assert ".sql" in provider._icons_by_ext
    assert ".csv" in provider._icons_by_ext
    assert ".xlsx" in provider._icons_by_ext
    
    # Verify multi-extension map is populated
    assert ".tar.gz" in provider._icons_by_multi_ext

def test_icon_for_type(icon_provider):
    """Verifies icon retrieval by QFileIconProvider.IconType."""
    folder_icon = icon_provider._folder_icon
    file_icon = icon_provider._file_icon
    
    assert icon_provider.icon(QFileIconProvider.IconType.Folder) == folder_icon
    assert icon_provider.icon(QFileIconProvider.IconType.File) == file_icon

def test_icon_for_directory(icon_provider, tmp_path):
    """Verifies icon for a directory QFileInfo."""
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()
    
    info = QFileInfo(str(dir_path))
    assert info.isDir()
    
    icon = icon_provider.icon(info)
    assert icon == icon_provider._folder_icon

def test_icon_for_known_extension(icon_provider, tmp_path):
    """Verifies icon for a file with a known extension."""
    sql_file = tmp_path / "query.sql"
    sql_file.write_text("SELECT 1")
    
    info = QFileInfo(str(sql_file))
    icon = icon_provider.icon(info)
    
    # Should match the icon mapped for .sql
    assert icon == icon_provider._icons_by_ext[".sql"]

def test_icon_for_multi_extension(icon_provider, tmp_path):
    """Verifies priority of multi-extension icons (e.g., .tar.gz)."""
    tar_gz_file = tmp_path / "archive.tar.gz"
    tar_gz_file.write_text("data")
    
    info = QFileInfo(str(tar_gz_file))
    icon = icon_provider.icon(info)
    
    # Should match the icon mapped for .tar.gz, not just .gz (if .gz was present)
    assert icon == icon_provider._icons_by_multi_ext[".tar.gz"]

def test_icon_for_unknown_extension(icon_provider, tmp_path):
    """Verifies fallback for unknown file extensions."""
    unknown_file = tmp_path / "data.unknown_ext"
    unknown_file.write_text("data")
    
    info = QFileInfo(str(unknown_file))
    icon = icon_provider.icon(info)
    
    # Should fallback to generic file icon
    assert icon == icon_provider._file_icon

def test_icon_for_case_insensitivity(icon_provider, tmp_path):
    """Verifies that extension matching is case-insensitive."""
    sql_file = tmp_path / "QUERY.SQL"
    sql_file.write_text("SELECT 1")
    
    info = QFileInfo(str(sql_file))
    icon = icon_provider.icon(info)
    
    assert icon == icon_provider._icons_by_ext[".sql"]

def test_icon_fallback_on_exception(icon_provider):
    """Verifies graceful fallback to super().icon() on unexpected errors."""
    # Pass something that might cause an error in our logic but is handled by QFileIconProvider
    # or just trigger an exception by mocking _icon_for_name to fail
    with patch.object(icon_provider, '_icon_for_name', side_effect=Exception("Test Error")):
        # We need a real QFileInfo to trigger Case 2
        info = QFileInfo("test.txt")
        
        # Should NOT raise, but return super().icon()
        # Since we can't easily verify it called super().icon(), we just check it returns a QIcon
        icon = icon_provider.icon(info)
        assert isinstance(icon, QIcon)

def test_update_theme_clears_previous(icon_service):
    """Verifies that update_theme clears old maps before repopulating."""
    provider = CustomFileIconProvider(icon_service)
    provider._icons_by_ext[".old"] = QIcon()
    
    provider.update_theme()
    
    assert ".old" not in provider._icons_by_ext
    assert ".sql" in provider._icons_by_ext
