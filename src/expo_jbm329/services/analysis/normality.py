"""Shared Shapiro-Wilk normality testing helper.

Used by both the dataset-wide Descriptive Statistics analysis (per-column
normality - see `statistics.py`) and the Hypothesis Tests / Group Comparison
analysis (per-group normality - see `group_comparison.py`). The parametric
group-comparison tests (t-test/ANOVA) assume normality *within* each group,
not in the pooled column, so it must be possible to run this same test on
an arbitrary subset of values rather than only on a whole column.
"""

from __future__ import annotations

import warnings

import pandas as pd
from scipy.stats import shapiro

_NAN = float("nan")

# scipy.stats.shapiro's own documented threshold beyond which its computed
# p-value may not be accurate. Surfaced explicitly as a UI caveat (see
# gui/dialogs/analysis/statistics_view.py) instead of scipy's internal
# warning, which we deliberately suppress in `shapiro_normality`.
SHAPIRO_LARGE_SAMPLE_THRESHOLD = 5000


def shapiro_normality(series: pd.Series) -> tuple[float, float]:
    """Run the Shapiro-Wilk normality test on a set of numeric values.

    Args:
        series: The raw values to test (any dtype coercible to numeric) -
            typically a whole column, or a single group's subset of one.

    Returns:
        A ``(statistic, p_value)`` tuple. Both are NaN when scipy cannot
        compute a result (e.g. fewer than 3 valid values).
    """
    values = pd.to_numeric(series, errors="coerce").replace([float("inf"), float("-inf")], _NAN).dropna()

    with warnings.catch_warnings():
        # scipy warns about reduced accuracy for large samples and about
        # degenerate (zero-range) input. Both are surfaced explicitly as UI
        # caveats instead of as noisy warnings here.
        warnings.simplefilter("ignore")
        result = shapiro(values)

    return float(result.statistic), float(result.pvalue)
