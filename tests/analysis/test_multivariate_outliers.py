from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis import multivariate_outliers
from expo_jbm329.services.analysis.multivariate_outliers import (
    DEFAULT_CONTAMINATION,
    DEFAULT_LOF_NEIGHBORS,
    MAX_LOF_NEIGHBORS,
    PLOT_SAMPLE_SIZE,
    MultivariateOutlierError,
    MultivariateOutlierMethod,
    analyze_multivariate_outliers,
    initialize_multivariate_outliers,
)


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(8)
    normal = rng.normal(size=(100, 2))
    values = np.vstack((normal, [[8.0, 8.0], [-8.0, -8.0]]))
    return pd.DataFrame({"x": values[:, 0], "y": values[:, 1], "text": ["a"] * len(values)})


@pytest.mark.parametrize("method", list(MultivariateOutlierMethod))
def test_methods_screen_complete_rows_and_rank_extremes(method):
    result = analyze_multivariate_outliers(_frame(), method=method, lof_neighbors=10)

    assert result.error is None
    assert result.method is method
    assert result.columns == ("x", "y")
    assert result.standardize
    assert result.contamination == DEFAULT_CONTAMINATION
    assert result.rows_used == 102
    assert result.rows_dropped == 0
    assert result.outlier_count > 0
    assert result.inlier_count + result.outlier_count == result.rows_used
    assert result.extremes[0].score >= result.extremes[-1].score
    assert result.extremes[0].row_number in {101, 102}
    assert len(result.sample_pc1) == result.rows_used


def test_standardization_can_be_disabled():
    result = analyze_multivariate_outliers(_frame(), standardize=False)

    assert result.error is None
    assert not result.standardize


def test_missing_and_infinite_rows_are_dropped_as_complete_case_analysis():
    df = _frame()
    df.loc[0, "x"] = np.nan
    df.loc[1, "y"] = np.inf

    result = analyze_multivariate_outliers(df)

    assert result.error is None
    assert result.rows_used == 100
    assert result.rows_dropped == 2


def test_local_outlier_factor_rejects_neighbors_not_less_than_complete_rows():
    result = analyze_multivariate_outliers(
        pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [1.0, 3.0, 2.0]}),
        method=MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR,
        lof_neighbors=3,
    )

    assert result.error is MultivariateOutlierError.INVALID_LOF_NEIGHBORS
    assert result.rows_used == 3


@pytest.mark.parametrize(
    ("df", "columns", "kwargs", "error"),
    [
        (pd.DataFrame({"x": [1.0, 2.0, 3.0]}), None, {}, MultivariateOutlierError.NOT_ENOUGH_NUMERIC_COLUMNS),
        (_frame(), ("x",), {}, MultivariateOutlierError.NOT_ENOUGH_SELECTED_COLUMNS),
        (_frame(), ("x", "missing"), {}, MultivariateOutlierError.INVALID_COLUMN),
        (_frame(), ("x", "x"), {}, MultivariateOutlierError.INVALID_COLUMN),
        (_frame(), None, {"contamination": 0.0}, MultivariateOutlierError.INVALID_CONTAMINATION),
        (_frame(), None, {"contamination": 0.6}, MultivariateOutlierError.INVALID_CONTAMINATION),
        (_frame(), None, {"lof_neighbors": 1}, MultivariateOutlierError.INVALID_LOF_NEIGHBORS),
        (_frame(), None, {"lof_neighbors": MAX_LOF_NEIGHBORS + 1}, MultivariateOutlierError.INVALID_LOF_NEIGHBORS),
    ],
)
def test_invalid_requests_return_structured_errors(df, columns, kwargs, error):
    result = analyze_multivariate_outliers(df, columns, **kwargs)

    assert result.error is error
    assert result.extremes == ()


def test_too_few_complete_rows_and_no_variation_return_errors():
    too_few = analyze_multivariate_outliers(pd.DataFrame({"x": [1.0, np.nan], "y": [2.0, 3.0]}))
    constant = analyze_multivariate_outliers(pd.DataFrame({"x": [1.0, 1.0, 1.0], "y": [2.0, 2.0, 2.0]}))

    assert too_few.error is MultivariateOutlierError.NOT_ENOUGH_OBSERVATIONS
    assert constant.error is MultivariateOutlierError.NO_VARIATION


def test_projection_sampling_is_deterministic():
    size = PLOT_SAMPLE_SIZE + 1
    x = np.arange(size, dtype=float)
    df = pd.DataFrame({"x": x, "y": x**2})

    first = analyze_multivariate_outliers(df)
    second = analyze_multivariate_outliers(df)

    assert first.sampled
    assert len(first.sample_pc1) == PLOT_SAMPLE_SIZE
    assert first.sample_pc1 == second.sample_pc1
    assert first.sample_outliers == second.sample_outliers


def test_analysis_does_not_mutate_the_dataframe():
    df = _frame()
    before = df.copy(deep=True)

    analyze_multivariate_outliers(df)

    pd.testing.assert_frame_equal(df, before)


def test_algorithm_errors_are_not_silently_suppressed(monkeypatch):
    def _raise(*_args, **_kwargs):
        message = "intentional fitting failure"
        raise RuntimeError(message)

    monkeypatch.setattr(multivariate_outliers, "_fit_labels_and_scores", _raise)

    with pytest.raises(RuntimeError, match="intentional fitting failure"):
        analyze_multivariate_outliers(_frame())


def test_defaults_are_exposed_in_the_result():
    result = analyze_multivariate_outliers(_frame())

    assert result.lof_neighbors == DEFAULT_LOF_NEIGHBORS


def test_initialize_multivariate_outliers_uses_defaults_without_fitting():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4, 5, 6], "t": list("xyz")})

    result = initialize_multivariate_outliers(df)

    assert result.method is MultivariateOutlierMethod.ISOLATION_FOREST
    assert result.columns == ("a", "b")
    assert result.available_columns == ("a", "b")
    assert result.standardize is True
    assert result.contamination == DEFAULT_CONTAMINATION
    assert result.lof_neighbors == DEFAULT_LOF_NEIGHBORS
    assert result.total_rows == 3
    assert result.rows_used == 0
    assert result.extremes == ()
    assert result.error is None


def test_initialize_multivariate_outliers_with_one_numeric_column_reports_the_error():
    result = initialize_multivariate_outliers(pd.DataFrame({"a": [1.0, 2.0], "t": ["x", "y"]}))

    assert result.columns == ("a",)
    assert result.error is MultivariateOutlierError.NOT_ENOUGH_NUMERIC_COLUMNS
