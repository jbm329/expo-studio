import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock, patch
from expo_jbm329.services.file_loader import FileLoader
from expo_jbm329.services.file_writer import FileWriter
from expo_jbm329.services.data_io_service import DataIOService

@pytest.fixture
def tmp_csv(tmp_path):
    p = tmp_path / "test.csv"
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    df.to_csv(p, index=False)
    return p

@pytest.fixture
def loader():
    return FileLoader(fmt_path=lambda x: str(x))

@pytest.fixture
def writer():
    return FileWriter(fmt_path=lambda x: str(x))

@pytest.fixture
def io_service(loader, writer):
    return DataIOService(loader, writer, fmt_path=lambda x: str(x))

def test_file_loader_resolve(loader, tmp_csv):
    # Mocking fmt_path if needed, but default might work
    path = loader.resolve(str(tmp_csv))
    assert Path(path).exists()

def test_file_loader_load_csv(loader, tmp_csv):
    df = loader.load_df_auto(str(tmp_csv))
    assert len(df) == 2
    assert "A" in df.columns

def test_file_writer_save_csv(writer, tmp_path):
    dest = tmp_path / "out.csv"
    df = pd.DataFrame({"X": [10, 20]})
    writer.save_csv(df, dest)
    assert dest.exists()
    df_loaded = pd.read_csv(dest)
    assert df_loaded["X"].iloc[0] == 10

def test_data_io_service_load(io_service, tmp_csv):
    res = io_service.resolve_and_load_df(str(tmp_csv))
    assert res.ok
    assert isinstance(res.data, pd.DataFrame)
    assert len(res.data) == 2

def test_data_io_service_export_csv(io_service, tmp_path):
    dest = tmp_path / "export.csv"
    df = pd.DataFrame({"Z": [100]})
    io_service.export_df_csv(df, dest)
    assert dest.exists()

@patch("expo_jbm329.services.data_io_service.generate_profile_report")
def test_data_io_service_export_profile(mock_gen, io_service, tmp_path):
    dest = tmp_path / "profile.html"
    df = pd.DataFrame({"A": [1]})
    mock_profile = MagicMock()
    mock_gen.return_value = mock_profile
    
    # We also need to mock writer.save_profile because it might fail if we don't
    io_service._writer = MagicMock()
    
    io_service.export_df_profile(df, dest, "My Title")
    
    mock_gen.assert_called_once()
    io_service._writer.save_profile.assert_called_once()
