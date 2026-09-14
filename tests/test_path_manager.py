from pathlib import Path
from unittest.mock import patch
from expo_jbm329.utils.path_manager import (
    get_config_dir,
    get_log_dir,
    get_cache_dir,
    get_default_documents_dir,
    get_documents_dir,
    get_sql_dir,
    ensure_all_dirs
)

def test_fixed_dirs():
    # platformdirs handles these, so we just verify they return Path objects
    assert isinstance(get_config_dir(), Path)
    assert isinstance(get_log_dir(), Path)
    assert isinstance(get_cache_dir(), Path)

def test_get_default_documents_dir():
    # Documents/Expo should be at the end (might be "Dokument" in Swedish Windows)
    path = get_default_documents_dir()
    assert path.name == "Expo"
    # Just check it's within a user-like directory or contains some variant of Documents
    path_str = str(path).lower()
    assert "document" in path_str or "dokument" in path_str

def test_get_documents_dir_custom():
    settings = {"documents_dir": "~/CustomExpo"}
    path = get_documents_dir(settings)
    assert "CustomExpo" in str(path)

def test_get_documents_dir_default():
    settings = {}
    path = get_documents_dir(settings)
    assert path.name == "Expo"

def test_get_sql_dir():
    settings = {"documents_dir": "/tmp/expo"}
    path = get_sql_dir(settings)
    assert path == Path("/tmp/expo/sql")

@patch("pathlib.Path.mkdir")
def test_ensure_all_dirs(mock_mkdir):
    settings = {"documents_dir": "/tmp/expo"}
    paths = ensure_all_dirs(settings)
    
    assert "config_dir" in paths
    assert "sql_dir" in paths
    assert paths["sql_dir"] == Path("/tmp/expo/sql")
    
    # Verify mkdir was called multiple times
    assert mock_mkdir.called
