from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from expo_jbm329.services.data_io_service import DataIOService
from expo_jbm329.services.file_loader import FileLoader
from expo_jbm329.services.file_writer import FileWriter


@pytest.fixture
def tmp_csv(tmp_path: Path) -> Path:
    path = tmp_path / "test.csv"
    pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}).to_csv(path, index=False)
    return path


@pytest.fixture
def loader() -> FileLoader:
    return FileLoader()


@pytest.fixture
def writer() -> FileWriter:
    return FileWriter()


@pytest.fixture
def io_service(loader: FileLoader, writer: FileWriter) -> DataIOService:
    return DataIOService(loader, writer)


def test_file_loader_load_csv(loader: FileLoader, tmp_csv: Path):
    df = loader.load_df_auto(str(tmp_csv))

    assert len(df) == 2
    assert list(df.columns) == ["A", "B"]


def test_file_writer_save_csv(writer: FileWriter, tmp_path: Path):
    dest = tmp_path / "out.csv"
    df = pd.DataFrame({"X": [10, 20]})

    writer.save_csv(df, dest)

    assert dest.exists()
    assert pd.read_csv(dest)["X"].tolist() == [10, 20]


def test_data_io_service_load(io_service: DataIOService, tmp_csv: Path):
    res = io_service.resolve_and_load_df(str(tmp_csv))

    assert res.ok is True
    assert isinstance(res.data, pd.DataFrame)
    assert list(res.data.columns) == ["A", "B"]


def test_data_io_service_load_missing_file_returns_failure(io_service: DataIOService):
    res = io_service.resolve_and_load_df("missing.csv")

    assert res.ok is False
    assert res.cancelled is False
    assert res.data is None
    assert "missing.csv" in res.error


def test_data_io_service_export_csv(io_service: DataIOService, tmp_path: Path):
    dest = tmp_path / "export.csv"
    df = pd.DataFrame({"Z": [100]})

    res = io_service.export_df_csv(df, dest)

    assert res.ok is True
    assert dest.exists()


def test_data_io_service_export_profile(io_service: DataIOService, tmp_path: Path):
    dest = tmp_path / "profile.html"
    df = pd.DataFrame({"A": [1]})
    mock_profile = MagicMock()

    with patch("expo_jbm329.services.data_io_service.generate_profile_report", return_value=mock_profile) as mock_gen:
        io_service._writer = MagicMock()
        res = io_service.export_df_profile(df, dest, "My Title")

    assert res.ok is True
    mock_gen.assert_called_once()
    io_service._writer.save_profile.assert_called_once_with(mock_profile, str(dest), corr_id=None)


def test_data_io_service_export_comparison_profile(io_service: DataIOService, tmp_path: Path):
    dest = tmp_path / "compare.html"
    data = [(pd.DataFrame({"A": [1]}), "One"), (pd.DataFrame({"A": [2]}), "Two")]
    mock_report = MagicMock()

    with patch(
        "expo_jbm329.services.data_io_service.generate_comparison_profile_report",
        return_value=mock_report,
    ) as mock_gen:
        io_service._writer = MagicMock()
        res = io_service.export_dfs_profile(data, dest)

    assert res.ok is True
    mock_gen.assert_called_once_with(data, corr_id=None)
    io_service._writer.save_profile.assert_called_once_with(mock_report, str(dest), corr_id=None)
