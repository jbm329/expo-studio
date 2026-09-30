"""Tests for the linear regression service."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor

from expo_jbm329.services.analysis.group_comparison import ColumnExclusionReason
from expo_jbm329.services.analysis.regression import (
    MAX_MODEL_TERMS,
    MAX_PREDICTORS,
    PLOT_SAMPLE_SIZE,
    CategoricalReference,
    RegressionError,
    RegressionResult,
    RegressionTerm,
    RegressionWarningReason,
    TermKind,
    analyze_regression,
    classify_predictor_columns,
    initialize_regression,
    term_name,
)


def _frame(size: int = 300, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "x1": rng.normal(size=size),
        "x2": rng.normal(size=size),
        "g": rng.choice(["a", "b", "c"], size=size, p=[0.2, 0.5, 0.3]),
        "flag": rng.choice([True, False], size=size, p=[0.3, 0.7]),
    })
    df["y"] = 1 + 2 * df["x1"] - df["x2"] + (df["g"] == "c") * 1.5 + df["flag"] * 0.3 + rng.normal(size=size)
    return df


def _term(result: RegressionResult, name: str) -> RegressionTerm:
    return next(term for term in result.terms if term_name(term) == name)


# ----------------------------------------------------------------------
# classify_predictor_columns / term_name
# ----------------------------------------------------------------------


def test_classify_predictor_columns_splits_by_kind_and_skips_datetimes():
    size = 30
    df = pd.DataFrame({
        "num": np.arange(size, dtype=float),
        "text": ["a", "b", "c"] * 10,
        "cat": pd.Categorical(["x", "y"] * 15),
        "flag": [True, False] * 15,
        "id": [str(i) for i in range(size)],
        "single": ["same"] * size,
        "when": pd.date_range("2024-01-01", periods=size),
    })

    columns = classify_predictor_columns(df)

    assert columns.numeric == ("num",)
    assert columns.categorical == ("text", "cat", "flag")
    assert [(c.name, c.reason) for c in columns.excluded] == [
        ("id", ColumnExclusionReason.TOO_MANY_VALUES),
        ("single", ColumnExclusionReason.TOO_FEW_VALUES),
    ]


def test_term_name_formats_dummies_as_column_equals_level():
    base = {"estimate": 0.0, "std_error": 0.0, "t_statistic": 0.0, "p_value": 0.0, "ci_low": 0.0, "ci_high": 0.0}

    assert term_name(RegressionTerm(TermKind.INTERCEPT, "", None, vif=math.nan, **base)) == ""
    assert term_name(RegressionTerm(TermKind.NUMERIC, "x", None, vif=1.0, **base)) == "x"
    assert term_name(RegressionTerm(TermKind.DUMMY, "g", "a", vif=1.0, **base)) == "g = a"


# ----------------------------------------------------------------------
# Fitted model
# ----------------------------------------------------------------------


def test_fit_matches_statsmodels_formula_with_treatment_coding():
    df = _frame()
    result = analyze_regression(df, "y", ["x1", "x2", "g", "flag"])
    reference = smf.ols("y ~ x1 + x2 + C(g, Treatment('b')) + C(flag, Treatment(False))", data=df).fit()

    assert result.error is None
    assert result.r_squared == pytest.approx(reference.rsquared)
    assert result.adjusted_r_squared == pytest.approx(reference.rsquared_adj)
    assert result.f_statistic == pytest.approx(reference.fvalue)
    assert result.f_p_value == pytest.approx(reference.f_pvalue)
    assert result.aic == pytest.approx(reference.aic)
    assert result.rmse == pytest.approx(math.sqrt(reference.mse_resid))
    assert result.df_model == 5
    assert result.df_residual == len(df) - 6

    expected = {
        "": "Intercept",
        "x1": "x1",
        "x2": "x2",
        "g = a": "C(g, Treatment('b'))[T.a]",
        "g = c": "C(g, Treatment('b'))[T.c]",
        "flag = True": "C(flag, Treatment(False))[T.True]",
    }
    ci = reference.conf_int()
    for name, reference_name in expected.items():
        term = _term(result, name)
        assert term.estimate == pytest.approx(reference.params[reference_name])
        assert term.std_error == pytest.approx(reference.bse[reference_name])
        assert term.t_statistic == pytest.approx(reference.tvalues[reference_name])
        assert term.p_value == pytest.approx(reference.pvalues[reference_name])
        assert term.ci_low == pytest.approx(ci.loc[reference_name, 0])
        assert term.ci_high == pytest.approx(ci.loc[reference_name, 1])


def test_terms_are_intercept_then_predictors_in_given_order():
    result = analyze_regression(_frame(), "y", ["g", "x2"])

    assert [(t.kind, t.column, t.level) for t in result.terms] == [
        (TermKind.INTERCEPT, "", None),
        (TermKind.DUMMY, "g", "a"),
        (TermKind.DUMMY, "g", "c"),
        (TermKind.NUMERIC, "x2", None),
    ]


def test_reference_level_is_the_most_frequent_level():
    result = analyze_regression(_frame(), "y", ["g", "flag"])

    assert result.references == (
        CategoricalReference("g", "b", 3),
        CategoricalReference("flag", "False", 2),
    )


def test_reference_level_ties_are_broken_by_level_order():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.5, 4.0, 5.5, 6.0], "g": ["b", "a", "b", "a", "c", "c"]})

    result = analyze_regression(df, "y", ["g"])

    assert result.references == (CategoricalReference("g", "a", 3),)


def test_vif_matches_statsmodels_and_intercept_has_none():
    df = _frame()
    result = analyze_regression(df, "y", ["x1", "x2", "g"])
    exog = smf.ols("y ~ x1 + x2 + C(g, Treatment('b'))", data=df).fit().model.exog
    # Formula order: intercept, g[a], g[c], x1, x2.
    expected = {name: variance_inflation_factor(exog, i) for i, name in enumerate(["g = a", "g = c", "x1", "x2"], 1)}

    assert math.isnan(result.terms[0].vif)
    for name, vif in expected.items():
        assert _term(result, name).vif == pytest.approx(vif)
    assert result.diagnostics is not None
    assert result.diagnostics.max_vif == pytest.approx(max(expected.values()))


def test_single_predictor_has_vif_one():
    result = analyze_regression(_frame(), "y", ["x1"])

    assert _term(result, "x1").vif == pytest.approx(1.0)


def test_listwise_deletion_counts_used_and_dropped_rows():
    df = _frame()
    df.loc[[0, 1], "x1"] = np.nan
    df.loc[2, "g"] = None
    df.loc[3, "y"] = np.inf
    df.loc[4, "x2"] = np.nan  # x2 is not a predictor: must not drop the row

    result = analyze_regression(df, "y", ["x1", "g"])

    assert result.n_used == len(df) - 4
    assert result.n_dropped == 4


def test_default_target_is_the_first_numeric_column():
    result = analyze_regression(_frame(), predictors=["x2"])

    assert result.target == "x1"
    assert result.available_targets == ("x1", "x2", "y")
    assert result.error is None


def test_diagnostics_are_computed_for_a_well_behaved_model():
    result = analyze_regression(_frame(), "y", ["x1", "x2"])

    assert result.diagnostics is not None
    assert result.diagnostics.breusch_pagan_p_value > 0.05
    assert result.diagnostics.jarque_bera_p_value > 0.05
    assert 1.5 <= result.diagnostics.durbin_watson <= 2.5
    assert result.warnings == ()


def test_warnings_flag_problems():
    rng = np.random.default_rng(2)
    size = 400
    x1 = np.sort(rng.normal(size=size))
    df = pd.DataFrame({"x1": x1, "x2": x1 + rng.normal(scale=0.01, size=size)})
    # Heteroscedastic, skewed and autocorrelated (row-ordered) errors.
    df["y"] = x1 + np.abs(x1) * rng.exponential(size=size) + np.cumsum(rng.normal(size=size))

    result = analyze_regression(df, "y", ["x1", "x2"])

    reasons = {warning.reason: warning for warning in result.warnings}
    assert set(reasons) == set(RegressionWarningReason)
    assert reasons[RegressionWarningReason.HIGH_MULTICOLLINEARITY].terms == ("x1", "x2")
    assert reasons[RegressionWarningReason.HETEROSCEDASTICITY].terms == ()


def test_input_frame_is_not_mutated():
    df = _frame()
    df.loc[0, "x1"] = np.nan
    before = df.copy()

    analyze_regression(df, "y", ["x1", "g"])

    pd.testing.assert_frame_equal(df, before)


# ----------------------------------------------------------------------
# Plot data
# ----------------------------------------------------------------------


def test_small_model_plot_data_contains_every_row():
    df = _frame()
    result = analyze_regression(df, "y", ["x1"])
    plot = result.plot

    assert plot is not None
    assert not plot.sampled
    assert len(plot.actual) == len(plot.fitted) == len(plot.residuals) == len(df)
    assert plot.actual == tuple(df["y"])
    np.testing.assert_allclose(np.array(plot.actual) - np.array(plot.fitted), plot.residuals, atol=1e-9)


def test_qq_data_is_sorted_standardized_residuals_against_normal_quantiles():
    result = analyze_regression(_frame(), "y", ["x1"])
    plot = result.plot

    assert plot is not None
    assert list(plot.qq_sample) == sorted(plot.qq_sample)
    assert list(plot.qq_theoretical) == sorted(plot.qq_theoretical)
    assert plot.qq_theoretical[0] == pytest.approx(-plot.qq_theoretical[-1])
    expected = np.sort(np.array(plot.residuals) / result.rmse)
    np.testing.assert_allclose(plot.qq_sample, expected)


def test_large_model_plot_data_is_sampled_deterministically():
    rng = np.random.default_rng(0)
    size = PLOT_SAMPLE_SIZE + 500
    df = pd.DataFrame({"x": rng.normal(size=size)})
    df["y"] = df["x"] + rng.normal(size=size)

    first = analyze_regression(df, "y", ["x"]).plot
    second = analyze_regression(df, "y", ["x"]).plot

    assert first is not None
    assert first.sampled
    assert len(first.actual) == len(first.qq_sample) == PLOT_SAMPLE_SIZE
    assert first == second


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


def _assert_error(result: RegressionResult, error: RegressionError) -> None:
    assert result.error is error
    assert result.terms == ()
    assert result.diagnostics is None
    assert result.plot is None
    assert math.isnan(result.r_squared)


def test_no_numeric_column_error():
    result = analyze_regression(pd.DataFrame({"g": ["a", "b", "a"]}))

    _assert_error(result, RegressionError.NO_NUMERIC_COLUMN)
    assert result.target == ""
    assert result.predictor_columns.categorical == ("g",)


def test_no_predictors_error_still_describes_available_columns():
    result = analyze_regression(_frame())

    _assert_error(result, RegressionError.NO_PREDICTORS_SELECTED)
    assert result.target == "x1"
    assert result.available_targets == ("x1", "x2", "y")
    assert result.predictor_columns.categorical == ("g", "flag")


def test_initialize_regression_builds_selection_metadata_without_a_model():
    result = initialize_regression(_frame())

    _assert_error(result, RegressionError.NO_PREDICTORS_SELECTED)
    assert result.target == "x1"
    assert result.predictors == ()
    assert result.available_targets == ("x1", "x2", "y")
    assert result.predictor_columns.categorical == ("g", "flag")


def test_initialize_regression_reports_when_no_numeric_target_exists():
    result = initialize_regression(pd.DataFrame({"g": ["a", "b", "a"]}))

    _assert_error(result, RegressionError.NO_NUMERIC_COLUMN)
    assert result.target == ""
    assert result.predictor_columns.categorical == ("g",)


def test_too_many_predictors_error():
    rng = np.random.default_rng(0)
    names = [f"n{i}" for i in range(MAX_PREDICTORS + 1)]
    df = pd.DataFrame({name: rng.normal(size=60) for name in [*names, "y"]})

    _assert_error(analyze_regression(df, "y", names), RegressionError.TOO_MANY_PREDICTORS)
    assert analyze_regression(df, "y", names[:MAX_PREDICTORS]).error is None


@pytest.mark.parametrize(
    ("target", "predictors"),
    [
        ("g", ["x1"]),  # non-numeric target
        ("missing", ["x1"]),
        ("y", ["missing"]),
        ("y", ["x1", "x1"]),
        ("y", ["y"]),
        ("y", ["id"]),  # excluded categorical
    ],
)
def test_invalid_column_error(target, predictors):
    df = _frame()
    df["id"] = [str(i) for i in range(len(df))]

    _assert_error(analyze_regression(df, target, predictors), RegressionError.INVALID_COLUMN)


def test_too_many_terms_error():
    rng = np.random.default_rng(0)
    size = 2_000
    df = pd.DataFrame({f"c{i}": rng.choice([f"l{j}" for j in range(20)], size=size) for i in range(3)})
    df["y"] = rng.normal(size=size)

    result = analyze_regression(df, "y", ["c0", "c1", "c2"])

    assert MAX_MODEL_TERMS < 3 * 19
    _assert_error(result, RegressionError.TOO_MANY_TERMS)
    assert result.n_used == size


def test_not_enough_observations_error():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, np.nan], "a": [1.0, 3.0, 2.0, 4.0], "b": [2.0, 1.0, 5.0, 3.0]})

    result = analyze_regression(df, "y", ["a", "b"])

    _assert_error(result, RegressionError.NOT_ENOUGH_OBSERVATIONS)
    assert result.n_used == 3
    assert result.n_dropped == 1


def test_all_rows_missing_is_not_enough_observations():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0], "a": [np.nan, np.nan, np.nan]})

    _assert_error(analyze_regression(df, "y", ["a"]), RegressionError.NOT_ENOUGH_OBSERVATIONS)


def test_constant_target_error():
    df = pd.DataFrame({"y": [2.0] * 6, "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})

    _assert_error(analyze_regression(df, "y", ["a"]), RegressionError.CONSTANT_TARGET)


@pytest.mark.parametrize("column", ["a", "g"])
def test_constant_predictor_error_names_the_column(column):
    df = pd.DataFrame({
        "y": [1.0, 2.0, 3.5, 4.0, 5.5, 6.0, 7.5],
        "a": [3.0] * 7,
        "b": [1.0, 3.0, 2.0, 5.0, 4.0, 7.0, 6.0],
        # "b" level only in the row that has y missing below.
        "g": ["x", "x", "x", "x", "x", "x", "y"],
    })
    df.loc[6, "y"] = np.nan

    result = analyze_regression(df, "y", ["b", column])

    _assert_error(result, RegressionError.CONSTANT_PREDICTOR)
    assert result.error_column == column


def test_perfect_multicollinearity_error():
    df = _frame()
    df["x3"] = 2 * df["x1"] - df["x2"]

    _assert_error(analyze_regression(df, "y", ["x1", "x2", "x3"]), RegressionError.PERFECT_MULTICOLLINEARITY)


def test_mixed_type_levels_are_sorted_as_text():
    df = pd.DataFrame({"y": [1.0, 2.5, 2.0, 4.5, 3.0, 6.5, 5.0], "g": pd.Categorical(["a", 1, "a", 1, "b", "b", "a"])})

    result = analyze_regression(df, "y", ["g"])

    assert result.error is None
    assert [term.level for term in result.terms[1:]] == ["1", "b"]
    assert result.references == (CategoricalReference("g", "a", 3),)
