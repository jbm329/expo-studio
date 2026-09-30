from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis import pca
from expo_jbm329.services.analysis.pca import (
    MIN_OBSERVATIONS,
    SCATTER_SAMPLE_SIZE,
    PCAError,
    analyze_pca,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, np.nan],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0],
        "c": [3.0, 2.0, 5.0, 4.0, 7.0],
        "text": list("abcde"),
    })


def test_default_analysis_uses_all_numeric_columns_and_complete_cases():
    result = analyze_pca(_frame())

    assert result.error is None
    assert result.columns == ("a", "b", "c")
    assert result.available_columns == ("a", "b", "c")
    assert result.standardize
    assert result.total_rows == 5
    assert result.rows_used == 4
    assert result.rows_dropped == 1
    assert len(result.explained_variance) == 3
    assert len(result.loadings) == 3
    assert len(result.loadings[0]) == 3
    assert len(result.sample_pc1) == result.rows_used
    assert len(result.sample_pc2) == result.rows_used
    assert not result.sampled


def test_variance_ratios_are_complete_and_cumulative():
    result = analyze_pca(_frame())

    assert result.error is None
    assert sum(result.explained_variance_ratio) == pytest.approx(1.0)
    assert result.cumulative_variance_ratio[-1] == pytest.approx(1.0)
    assert tuple(sorted(result.cumulative_variance_ratio)) == result.cumulative_variance_ratio


def test_standardization_changes_the_scale_of_the_fit():
    df = pd.DataFrame({"small": [1.0, 2.0, 3.0, 4.0], "large": [10.0, 100.0, 1_000.0, 10_000.0]})

    standardized = analyze_pca(df, standardize=True)
    raw = analyze_pca(df, standardize=False)

    assert standardized.error is None
    assert raw.error is None
    assert standardized.standardize
    assert not raw.standardize
    assert standardized.explained_variance_ratio[0] < raw.explained_variance_ratio[0]


def test_explicit_selected_columns_keep_the_given_order():
    result = analyze_pca(_frame(), ("c", "a"))

    assert result.error is None
    assert result.columns == ("c", "a")
    assert len(result.loadings) == 2


@pytest.mark.parametrize(
    ("df", "columns", "error"),
    [
        (pd.DataFrame({"a": [1.0, 2.0]}), None, PCAError.NOT_ENOUGH_NUMERIC_COLUMNS),
        (_frame(), ("a",), PCAError.NOT_ENOUGH_SELECTED_COLUMNS),
        (_frame(), ("a", "missing"), PCAError.INVALID_COLUMN),
        (_frame(), ("a", "a"), PCAError.INVALID_COLUMN),
    ],
)
def test_invalid_selection_returns_a_structured_error(df, columns, error):
    result = analyze_pca(df, columns)

    assert result.error is error
    assert result.explained_variance == ()
    assert result.loadings == ()


def test_fewer_than_two_complete_rows_returns_an_error():
    df = pd.DataFrame({"a": [1.0, np.nan], "b": [2.0, 3.0]})

    result = analyze_pca(df)

    assert result.error is PCAError.NOT_ENOUGH_OBSERVATIONS
    assert result.rows_used == MIN_OBSERVATIONS - 1
    assert result.rows_dropped == 1


def test_all_constant_features_return_no_variation():
    result = analyze_pca(pd.DataFrame({"a": [1.0, 1.0, 1.0], "b": [2.0, 2.0, 2.0]}))

    assert result.error is PCAError.NO_VARIATION
    assert result.rows_used == 3


def test_infinite_values_are_treated_as_incomplete():
    df = pd.DataFrame({"a": [1.0, np.inf, 3.0], "b": [2.0, 4.0, 6.0]})

    result = analyze_pca(df)

    assert result.error is None
    assert result.rows_used == 2
    assert result.rows_dropped == 1


def test_large_score_set_is_sampled_deterministically():
    size = SCATTER_SAMPLE_SIZE + 1
    df = pd.DataFrame({"a": np.arange(size, dtype=float), "b": np.arange(size, dtype=float) ** 2})

    first = analyze_pca(df)
    second = analyze_pca(df)

    assert first.sampled
    assert len(first.sample_pc1) == SCATTER_SAMPLE_SIZE
    assert first.sample_pc1 == second.sample_pc1
    assert first.sample_pc2 == second.sample_pc2


def test_analysis_does_not_mutate_the_dataframe():
    df = _frame()
    before = df.copy(deep=True)

    analyze_pca(df)

    pd.testing.assert_frame_equal(df, before)


def test_missing_fitted_model_attributes_raise_a_clear_internal_error(monkeypatch):
    class BrokenPCA:
        """Minimal PCA substitute missing its fitted model attributes."""

        components_ = None
        explained_variance_ = None
        explained_variance_ratio_ = np.array([0.5, 0.5])

        def fit_transform(self, values: np.ndarray) -> np.ndarray:
            return values

    monkeypatch.setattr(pca, "PCA", BrokenPCA)

    with pytest.raises(pca._PCAFitError):  # noqa: SLF001
        analyze_pca(pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 3.0]}))


def test_initialize_pca_selects_every_numeric_column_without_fitting() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [3.0, 1.0, 2.0], "text": ["x", "y", "z"]})

    result = pca.initialize_pca(df)

    assert result.error is None
    assert result.columns == ("a", "b")
    assert result.available_columns == ("a", "b")
    assert result.standardize is True
    assert result.total_rows == 3
    assert result.explained_variance == ()
    assert result.loadings == ()
    assert result.sample_pc1 == ()


def test_initialize_pca_reports_too_few_numeric_columns() -> None:
    result = pca.initialize_pca(pd.DataFrame({"a": [1.0, 2.0], "text": ["x", "y"]}))

    assert result.error is pca.PCAError.NOT_ENOUGH_NUMERIC_COLUMNS
    assert result.available_columns == ("a",)
