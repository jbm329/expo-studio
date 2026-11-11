"""Exercise downstream services with real file, SQL and REST loader outputs."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

import duckdb
import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.drivers.sa_duckdb import SqlAlchemyDuckDbDriver
from expo_jbm329.services.analysis.correlation import analyze_correlation_matrix
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.pca import analyze_pca
from expo_jbm329.services.analysis.regression import analyze_regression
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.data_io_service import DataIOService
from expo_jbm329.services.data_operations.columns import sort_dataframe
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes
from expo_jbm329.services.data_operations.fill import fillna
from expo_jbm329.services.data_operations.filter import filter_compare
from expo_jbm329.services.data_operations.joins import JoinRequest, join_dataframes
from expo_jbm329.services.data_operations.reshape_preview import (
    ReshapeFunction,
    ReshapeMetric,
    ReshapeRequest,
    compute_reshape,
)
from expo_jbm329.services.data_profile.column_data_profile import profile_series
from expo_jbm329.services.file_loader import FileLoader
from expo_jbm329.services.file_writer import FileWriter
from expo_jbm329.services.rest.models import RestRequestConfig
from expo_jbm329.services.rest.rest_job import fetch_rest_dataset

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(params=["csv", "duckdb", "rest"])
def loaded(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    """Load identical raw values without pre-casting the incoming dataframe."""
    rng = np.random.default_rng(42)
    records: list[dict[str, object]] = []
    for i in range(40):
        x, z, noise = (int(value) for value in rng.integers(1, 100, 3))
        records.append({
            "id": None if i == 2 else 2**53 + 1 + i,
            "group": "A" if i % 2 == 0 else "B",
            "x": None if i == 2 else x,
            "z": z,
            "y": None if i == 2 else 2 * x - z + noise,
            "flag": None if i == 2 else i % 2 == 0,
        })
    if request.param == "csv":
        path = tmp_path / "source.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        loader = FileLoader()
        loader.reload_settings({"csv": {"read_chunk_size_rows": 7, "sniff_delimiter": False, "default_sep": ","}})
        result = DataIOService(loader, FileWriter()).resolve_and_load_df(str(path))
        assert result.ok and isinstance(result.data, pd.DataFrame)
        frame = result.data
    elif request.param == "duckdb":
        path = tmp_path / "source.duckdb"
        with duckdb.connect(str(path)) as connection:
            connection.execute(
                'CREATE TABLE source (id BIGINT, "group" VARCHAR, x BIGINT, z BIGINT, y BIGINT, flag BOOLEAN)'
            )
            connection.executemany(
                "INSERT INTO source VALUES (?, ?, ?, ?, ?, ?)", [list(row.values()) for row in records]
            )
        driver = SqlAlchemyDuckDbDriver()
        config = ConnectionConfig(name="source", engine="duckdb", protocol="duckdb", database=str(path))
        try:
            frame = driver.execute_df(config, "SELECT * FROM source")
        finally:
            driver.dispose()
    else:

        def fetch_pages(*args: object, **kwargs: object) -> tuple[list[object], float]:
            return [{"items": records[:2]}, {"items": records[2:]}], 0.1

        monkeypatch.setattr(
            "expo_jbm329.services.rest.rest_job.fetch_json_pages",
            fetch_pages,
        )
        result = fetch_rest_dataset(
            RestRequestConfig(name="source", url="https://example.com", json_body=None, response_path="items")
        )
        assert result.ok and isinstance(result.data, pd.DataFrame)
        frame = result.data
    assert frame.dtypes.astype(str).tolist() == ["Int64", "object", "Int64", "int64", "Int64", "boolean"]
    assert frame["id"].iloc[0] == 2**53 + 1
    assert frame["id"].iloc[1] == 2**53 + 2
    return frame


def test_loaded_preparation_and_transformations_preserve_exact_values(loaded: pd.DataFrame) -> None:
    original = loaded.copy(deep=True)
    large = 2**53 + 1
    selected = filter_compare(loaded, "id", "!=", large)
    assert len(selected) == 39 and selected["id"].isna().sum() == 1
    assert filter_compare(loaded, "id", "<", large + 1)["id"].tolist() == [large]
    for ascending in (False, True):
        ordered = sort_dataframe(loaded, "id", ascending=ascending)
        expected = sorted(original["id"].dropna().tolist(), reverse=not ascending)
        assert ordered["id"].iloc[:-1].tolist() == expected
        assert pd.isna(ordered["id"].iloc[-1])
    filled = fillna(loaded, "id", 0)
    assert str(filled["id"].dtype) == "Int64"
    assert filled["id"].iloc[2] == 0
    combined = concat_dataframes(ConcatRequest(loaded, loaded.iloc[:1]))
    assert str(combined["id"].dtype) == "Int64"
    assert combined["id"].iloc[-1] == large
    joined = join_dataframes(
        JoinRequest(
            loaded,
            pd.DataFrame({"key": [large, large + 1], "label": ["first", "second"]}),
            ["id"],
            ["key"],
            how="left",
        )
    )
    assert joined["label"].iloc[:2].tolist() == ["first", "second"]
    assert joined["id"].iloc[0] == large
    reshaped = compute_reshape(
        loaded,
        ReshapeRequest(
            (1,),
            (
                ReshapeMetric("smallest_id", ReshapeFunction.MIN, 0),
                ReshapeMetric("sum_x", ReshapeFunction.SUM, 2),
            ),
        ),
    )
    assert reshaped is not None
    assert reshaped["smallest_id"].tolist() == [large, large + 1]
    assert reshaped["sum_x"].tolist() == [loaded.loc[loaded["group"] == group, "x"].sum() for group in ("A", "B")]
    pd.testing.assert_frame_equal(loaded, original)


def test_loaded_profiles_and_analysis_match_numeric_reference(loaded: pd.DataFrame) -> None:
    original = loaded.copy(deep=True)
    integer = profile_series(loaded["x"], "x")
    boolean = profile_series(loaded["flag"], "flag")
    assert integer.semantic_dtype == "int" and integer.stats["missing.n"] == 1
    assert boolean.semantic_dtype == "bool" and boolean.stats["missing.n"] == 1
    assert boolean.stats["bool.true.n"] == 19 and boolean.stats["bool.false.n"] == 20
    overview = analyze_dataset_overview(loaded)
    assert next(column for column in overview.columns if column.column == "x").missing_count == 1
    statistics = analyze_descriptive_statistics(loaded)
    x = next(column for column in statistics.columns if column.column == "x")
    assert x.count == 39 and x.missing_count == 1
    assert x.mean == pytest.approx(loaded["x"].mean())
    reference = loaded[["x", "z", "y"]].astype("float64")
    matrix = analyze_correlation_matrix(loaded, ["x", "z", "y"])
    expected_matrix = analyze_correlation_matrix(reference, ["x", "z", "y"])
    assert matrix is not None and expected_matrix is not None
    assert matrix.error is None and matrix.pairs == expected_matrix.pairs
    pca = analyze_pca(loaded, ["x", "z", "y"])
    expected_pca = analyze_pca(reference, ["x", "z", "y"])
    assert pca.error is None and expected_pca.error is None
    assert pca.rows_used == 39 and pca.rows_dropped == 1
    np.testing.assert_allclose(pca.loadings, expected_pca.loadings)
    complete = (
        loaded[["x", "z", "y", "flag"]]
        .dropna()
        .astype({
            "x": "float64",
            "z": "float64",
            "y": "float64",
            "flag": "bool",
        })
    )
    regression = analyze_regression(loaded, "y", ["x", "z", "flag"])
    expected_regression = analyze_regression(complete, "y", ["x", "z", "flag"])
    assert regression.error is None and expected_regression.error is None
    assert regression.n_used == 39 and regression.n_dropped == 1
    assert [term.estimate for term in regression.terms] == pytest.approx([
        term.estimate for term in expected_regression.terms
    ])
    pd.testing.assert_frame_equal(loaded, original)


@pytest.mark.parametrize("suffix", [".df", ".parquet", ".feather"])
def test_loaded_typed_exports_roundtrip(loaded: pd.DataFrame, tmp_path: Path, suffix: str) -> None:
    original = loaded.copy(deep=True)
    path = tmp_path / f"export{suffix}"
    FileWriter().save_datafile(loaded, path)
    restored = FileLoader().load_df_auto(str(path))
    pd.testing.assert_frame_equal(restored, original)
    pd.testing.assert_frame_equal(loaded, original)


def test_loaded_csv_export_preserves_exact_digits_and_reloads(loaded: pd.DataFrame, tmp_path: Path) -> None:
    original = loaded.copy(deep=True)
    path = tmp_path / "export.csv"
    FileWriter().save_csv(loaded, path, index=False, chunk_size_rows=7, na_rep="")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["id"] for row in rows[:3]] == [str(2**53 + 1), str(2**53 + 2), ""]
    assert [row["flag"] for row in rows[:3]] == ["True", "False", ""]
    loader = FileLoader()
    loader.reload_settings({"csv": {"sniff_delimiter": False, "default_sep": ","}})
    pd.testing.assert_frame_equal(loader.load_df_auto(str(path)), original)
    pd.testing.assert_frame_equal(loaded, original)


@pytest.mark.parametrize("streaming", [False, True])
def test_loaded_excel_export_preserves_nulls_and_booleans(
    loaded: pd.DataFrame, tmp_path: Path, streaming: bool
) -> None:
    original = loaded.copy(deep=True)
    # Excel's own numeric precision is limited; exact large IDs are checked in CSV/typed exports.
    frame = loaded.drop(columns=["id"])
    path = tmp_path / "export.xlsx"
    FileWriter().save_excel(frame, path, streaming=streaming, index=False)
    workbook = load_workbook(path)
    try:
        rows = list(workbook["Data"].values)
        assert rows[0] == tuple(frame.columns)
        assert rows[1][1] == frame["x"].iloc[0]
        assert rows[3][1] is None
        assert [row[-1] for row in rows[1:4]] == [True, False, None]
        assert workbook["Data"].cell(row=2, column=len(frame.columns)).data_type == "b"
    finally:
        workbook.close()
    pd.testing.assert_frame_equal(loaded, original)
