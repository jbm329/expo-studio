from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.normality import SHAPIRO_LARGE_SAMPLE_THRESHOLD, shapiro_normality


def test_flags_clearly_non_normal_data():
    rng = np.random.default_rng(42)
    series = pd.Series(rng.uniform(0, 100, size=200))

    statistic, p_value = shapiro_normality(series)

    assert not math.isnan(statistic)
    assert p_value < 0.001


def test_does_not_reject_clearly_normal_data():
    rng = np.random.default_rng(42)
    series = pd.Series(rng.normal(loc=50, scale=10, size=200))

    statistic, p_value = shapiro_normality(series)

    assert not math.isnan(statistic)
    assert p_value > 0.05


def test_handles_a_constant_series():
    series = pd.Series([5.0] * 50)

    statistic, p_value = shapiro_normality(series)

    assert statistic == pytest.approx(1.0)
    assert p_value == pytest.approx(1.0)


def test_handles_large_samples_without_raising():
    rng = np.random.default_rng(42)
    series = pd.Series(rng.normal(size=10_000))

    assert len(series) > SHAPIRO_LARGE_SAMPLE_THRESHOLD

    statistic, p_value = shapiro_normality(series)

    assert not math.isnan(statistic)
    assert not math.isnan(p_value)


def test_returns_nan_for_fewer_than_three_values():
    statistic, p_value = shapiro_normality(pd.Series([1.0, 2.0]))

    assert math.isnan(statistic)
    assert math.isnan(p_value)


def test_ignores_non_numeric_and_missing_values():
    rng = np.random.default_rng(42)
    values = list(rng.normal(loc=50, scale=10, size=200))
    series = pd.Series([*values, None, "not-a-number"])

    statistic, p_value = shapiro_normality(series)

    assert not math.isnan(statistic)
    assert p_value > 0.05


def test_ignores_infinite_values():
    rng = np.random.default_rng(42)
    values = list(rng.normal(loc=50, scale=10, size=200))
    series = pd.Series([*values, float("inf"), float("-inf")])

    statistic, p_value = shapiro_normality(series)

    assert not math.isnan(statistic)
    assert p_value > 0.05
