from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from expo_jbm329.services.file_writer import ExportCancelled, FileWriter


@pytest.fixture
def writer() -> FileWriter:
    return FileWriter()


def test_validate_excel_sheet_name_rejects_invalid_names(writer: FileWriter):
    with pytest.raises(ValueError):
        writer._validate_excel_sheet_name("")
    with pytest.raises(ValueError):
        writer._validate_excel_sheet_name("bad:name")


def test_save_csv_writes_file(tmp_path: Path, writer: FileWriter):
    path = tmp_path / "out.csv"
    df = pd.DataFrame({"X": [1, 2]})

    result = writer.save_csv(df, path)

    assert result == path
    assert pd.read_csv(path)["X"].tolist() == [1, 2]


def test_save_csv_can_be_cancelled_before_write(tmp_path: Path, writer: FileWriter):
    path = tmp_path / "out.csv"
    df = pd.DataFrame({"X": [1]})

    with pytest.raises(ExportCancelled):
        writer.save_csv(df, path, cancel_cb=lambda: True)

