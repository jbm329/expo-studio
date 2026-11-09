"""Compatibility checks using actual nullable join output, not synthetic casts."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from expo_jbm329.services.analysis.clustering import ClusteringMethod, analyze_clustering
from expo_jbm329.services.analysis.correlation import analyze_correlation_matrix, analyze_correlation_pair
from expo_jbm329.services.analysis.outliers import analyze_outlier_column, analyze_outlier_summary
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.pca import analyze_pca
from expo_jbm329.services.analysis.regression import analyze_regression, classify_predictor_columns
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.data_operations.joins import JoinRequest, UnmatchedFill, join_dataframes
from expo_jbm329.services.file_writer import FileWriter

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def joined() -> pd.DataFrame:
    """Include unmatched rows and matched rows with genuine nullable values."""
    rng = np.random.default_rng(42)
    size = 40
    right = pd.DataFrame({
        "id": np.arange(2, size + 2),
        "x": rng.integers(1, 100, size),
        "z": rng.integers(1, 100, size),
        "flag": pd.Series(np.arange(size) % 2 == 0, dtype="boolean"),
    })
    right["y"] = 2 * right["x"] - right["z"] + rng.integers(-10, 11, size)
    right.loc[3, "flag"] = pd.NA
    return join_dataframes(JoinRequest(pd.DataFrame({"id": np.arange(size + 2)}), right, ["id"], ["id"], how="left"))


def test_joined_nullable_columns_in_overview_and_statistics(joined: pd.DataFrame) -> None:
    original = joined.copy(deep=True)
    assert str(joined["x"].dtype) == "Int64"
    assert str(joined["flag"].dtype) == "boolean"
    overview = analyze_dataset_overview(joined)
    columns = {column.column: column for column in overview.columns}
    assert columns["x"].missing_count == 2
    assert columns["flag"].missing_count == 3
    statistics = analyze_descriptive_statistics(joined)
    values = next(column for column in statistics.columns if column.column == "x")
    assert values.count == 40
    assert values.missing_count == 2
    assert values.mean == pytest.approx(joined["x"].mean())
    assert values.histogram_counts
    assert sum(values.histogram_counts) == 40
    pd.testing.assert_frame_equal(joined, original)


def test_joined_nullable_columns_in_correlation_and_outliers(joined: pd.DataFrame) -> None:
    original = joined.copy(deep=True)
    reference = joined[["x", "z", "y"]].astype("float64")
    matrix = analyze_correlation_matrix(joined, ["x", "z", "y"])
    expected = analyze_correlation_matrix(reference, ["x", "z", "y"])
    assert matrix is not None and expected is not None
    assert matrix.error is None
    assert matrix.pairs == expected.pairs
    pair = analyze_correlation_pair(joined, "x", "y")
    expected_pair = analyze_correlation_pair(reference, "x", "y")
    assert pair.error is None
    assert pair.pair.n == expected_pair.pair.n == 40
    assert pair.pair.coefficient == pytest.approx(expected_pair.pair.coefficient)
    assert pair.slope == pytest.approx(expected_pair.slope)
    assert pair.sample_x == expected_pair.sample_x
    assert pair.sample_y == expected_pair.sample_y
    summary = analyze_outlier_summary(joined[["x", "z", "y"]])
    assert summary == analyze_outlier_summary(reference)
    detail = analyze_outlier_column(joined[["x", "z", "y"]], "x")
    assert detail == analyze_outlier_column(reference, "x")
    pd.testing.assert_frame_equal(joined, original)


def test_joined_nullable_integer_and_boolean_regression(joined: pd.DataFrame) -> None:
    original = joined.copy(deep=True)
    predictors = classify_predictor_columns(joined)
    assert "x" in predictors.numeric
    assert "flag" in predictors.categorical
    result = analyze_regression(joined, "y", ["x", "z", "flag"])
    complete = (
        joined[["x", "z", "y", "flag"]]
        .dropna()
        .astype({
            "x": "float64",
            "z": "float64",
            "y": "float64",
            "flag": "bool",
        })
    )
    expected = analyze_regression(complete, "y", ["x", "z", "flag"])
    assert result.error is None and expected.error is None
    assert result.n_used == 39
    assert result.n_dropped == 3
    assert result.r_squared == pytest.approx(expected.r_squared)
    assert [term.estimate for term in result.terms] == pytest.approx([term.estimate for term in expected.terms])
    pd.testing.assert_frame_equal(joined, original)


def test_joined_nullable_columns_in_pca(joined: pd.DataFrame) -> None:
    original = joined.copy(deep=True)
    result = analyze_pca(joined, ["x", "z", "y"])
    expected = analyze_pca(joined[["x", "z", "y"]].astype("float64"), ["x", "z", "y"])
    assert result.error is None and expected.error is None
    assert result.rows_used == 40
    assert result.rows_dropped == 2
    assert result.explained_variance == pytest.approx(expected.explained_variance)
    np.testing.assert_allclose(result.loadings, expected.loadings)
    pd.testing.assert_frame_equal(joined, original)


@pytest.mark.parametrize("method", list(ClusteringMethod))
def test_joined_nullable_columns_in_clustering(joined: pd.DataFrame, method: ClusteringMethod) -> None:
    original = joined.copy(deep=True)
    result = analyze_clustering(joined, ["x", "z"], method=method, cluster_count=2)
    expected = analyze_clustering(joined[["x", "z"]].astype("float64"), ["x", "z"], method=method, cluster_count=2)
    assert result.error is None and expected.error is None
    assert result.rows_used == 40
    assert result.rows_dropped == 2
    assert result.sample_labels == expected.sample_labels
    assert result.clusters == expected.clusters
    pd.testing.assert_frame_equal(joined, original)


def _export_join(*, defaults: bool = False, large: bool = False) -> pd.DataFrame:
    """Create missing, false and true rows plus datetime and categorical data."""
    right = pd.DataFrame({
        "id": [2, 3],
        "value": [2**62 + 1, 2**62 + 3] if large else [10, 20],
        "flag": [False, True],
        "text": pd.Series(["hello", pd.NA], dtype="string"),
        "category": pd.Series(["a", "b"], dtype="category"),
        "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
    })
    fills = {"value": UnmatchedFill(0), "flag": UnmatchedFill(False)} if defaults else {}
    return join_dataframes(
        JoinRequest(pd.DataFrame({"id": [1, 2, 3]}), right, ["id"], ["id"], how="left", right_fill=fills)
    )


@pytest.mark.parametrize("suffix", [".df", ".feather", ".ft", ".parquet"])
@pytest.mark.parametrize("defaults", [False, True])
def test_joined_datafile_roundtrip(tmp_path: Path, suffix: str, defaults: bool) -> None:
    frame = _export_join(defaults=defaults, large=True)
    original = frame.copy(deep=True)
    path = tmp_path / f"joined{suffix}"
    assert FileWriter().save_datafile(frame, path) == path
    if suffix == ".df":
        restored = pd.read_pickle(path)
    elif suffix == ".parquet":
        restored = pd.read_parquet(path)
    else:
        restored = pd.read_feather(path)
    pd.testing.assert_frame_equal(restored, frame)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("chunk_size", [None, 1])
def test_joined_csv_preserves_large_integer_text_and_nulls(tmp_path: Path, chunk_size: int | None) -> None:
    frame = _export_join(large=True)
    original = frame.copy(deep=True)
    path = tmp_path / "joined.csv"
    FileWriter().save_csv(frame, path, chunk_size_rows=chunk_size, na_rep="")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["value"] for row in rows] == ["", str(2**62 + 1), str(2**62 + 3)]
    assert [row["flag"] for row in rows] == ["", "False", "True"]
    assert [row["join_status"] for row in rows] == ["left_only", "both", "both"]
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("defaults", [False, True])
def test_joined_excel_preserves_missing_and_false_values(
    tmp_path: Path,
    streaming: bool,
    defaults: bool,
) -> None:
    frame = _export_join(defaults=defaults)
    original = frame.copy(deep=True)
    path = tmp_path / "joined.xlsx"
    FileWriter().save_excel(frame, path, streaming=streaming, index=False)
    workbook = load_workbook(path)
    try:
        rows = list(workbook["Data"].values)
        assert rows[0] == tuple(frame.columns)
        value_index = list(frame.columns).index("value")
        flag_index = list(frame.columns).index("flag")
        assert [row[value_index] for row in rows[1:]] == ([0, 10, 20] if defaults else [None, 10, 20])
        assert [row[flag_index] for row in rows[1:]] == ([False, False, True] if defaults else [None, False, True])
        assert workbook["Data"].cell(row=3, column=flag_index + 1).data_type == "b"
        assert workbook["Data"].cell(row=4, column=flag_index + 1).data_type == "b"
        if defaults:
            assert workbook["Data"].cell(row=2, column=flag_index + 1).data_type == "b"
        assert rows[1][list(frame.columns).index("date")] is None
        assert rows[2][list(frame.columns).index("date")] == pd.Timestamp("2020-01-01").to_pydatetime()
    finally:
        workbook.close()
    pd.testing.assert_frame_equal(frame, original)
