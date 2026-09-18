from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from expo_jbm329.services.file_loader import FileLoader, OperationCancelledError

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def loader() -> FileLoader:
    return FileLoader()


def test_load_df_auto_reads_csv(tmp_path: Path, loader: FileLoader):
    path = tmp_path / "test.csv"
    pd.DataFrame({"A": [1, 2]}).to_csv(path, index=False)

    df = loader.load_df_auto(str(path))

    assert df.shape[0] == 2
    assert df.shape[1] >= 1


def test_load_df_auto_rejects_unknown_suffix(tmp_path: Path, loader: FileLoader):
    path = tmp_path / "test.xyz"
    path.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        loader.load_df_auto(str(path))


def test_load_df_auto_can_be_cancelled_before_read(tmp_path: Path, loader: FileLoader):
    path = tmp_path / "test.csv"
    pd.DataFrame({"A": [1]}).to_csv(path, index=False)

    with pytest.raises(OperationCancelledError):
        loader.load_df_auto(str(path), cancel_cb=lambda: True)


def test_load_df_auto_sets_index_col(tmp_path: Path, loader: FileLoader):
    path = tmp_path / "test.json"
    pd.DataFrame({"id": [1, 2], "value": [10, 20]}).to_json(path, orient="records")

    df = loader.load_df_auto(str(path), index_col="id")

    assert list(df.index) == [1, 2]
    assert list(df.columns) == ["value"]
