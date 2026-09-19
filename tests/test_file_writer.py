from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from expo_jbm329.services.file_writer import ExportCancelledError, FileWriter

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def writer() -> FileWriter:
    return FileWriter()


def test_validate_excel_sheet_name_rejects_invalid_names(writer: FileWriter) -> None:
    with pytest.raises(ValueError):
        writer._validate_excel_sheet_name("")
    with pytest.raises(ValueError):
        writer._validate_excel_sheet_name("bad:name")


def test_save_csv_writes_file(tmp_path: Path, writer: FileWriter) -> None:
    path = tmp_path / "out.csv"
    df = pd.DataFrame({"X": [1, 2]})

    result = writer.save_csv(df, path)

    assert result == path
    assert pd.read_csv(path)["X"].tolist() == [1, 2]


def test_save_csv_can_be_cancelled_before_write(tmp_path: Path, writer: FileWriter) -> None:
    path = tmp_path / "out.csv"
    df = pd.DataFrame({"X": [1]})

    with pytest.raises(ExportCancelledError):
        writer.save_csv(df, path, cancel_cb=lambda: True)
