"""Group Comparison hypothesis tests.

Compares a numeric column's central tendency across the groups defined by
another column's distinct values. Runs Welch's t-test and Mann-Whitney U
for exactly two groups, or one-way ANOVA and Kruskal-Wallis for more than
two groups - both the parametric and non-parametric result are always
computed and returned together (never auto-selected), alongside each
group's own Shapiro-Wilk normality check, so the caller can judge which
result to trust rather than have that judgment hidden from them. This
mirrors `expo_jbm329.services.analysis.statistics`'s Shapiro-Wilk usage,
but tests normality *within* each group rather than on a whole column -
the parametric tests' normality assumption is about each group's own
distribution, not the pooled column.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd
from scipy.stats import f_oneway, kruskal, mannwhitneyu, ttest_ind

from expo_jbm329.services.analysis.normality import shapiro_normality
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

_NUMERIC_DTYPES = frozenset({SemanticDType.INT, SemanticDType.FLOAT})
_NAN = float("nan")
_CONFIDENCE_LEVEL = 0.95

# A group needs at least this many observations for a standard deviation
# (and any confidence interval/effect size derived from it) to be defined.
_MIN_OBSERVATIONS_FOR_VARIANCE = 2

# scipy.stats.shapiro's own minimum sample size; below this it returns NaN.
_MIN_OBSERVATIONS_FOR_NORMALITY = 3

# A grouping column needs at least this many distinct values to compare -
# otherwise there is nothing to compare against.
MIN_GROUPS = 2

# A grouping column with more distinct values than this is rejected: with
# too many groups, the comparison stops being meaningful (e.g. an ID-like
# column) and the underlying computation would be needlessly expensive.
MAX_GROUPS = 20


class GroupComparisonError(StrEnum):
    """Reasons a group comparison could not be computed.

    Kept UI-text-free (a plain reason code) so the GUI layer owns
    translation, matching `expo_jbm329.services.analysis.categories`.
    """

    NO_NUMERIC_COLUMN = "no_numeric_column"
    NO_GROUPING_COLUMN = "no_grouping_column"
    TOO_FEW_GROUPS = "too_few_groups"
    TOO_MANY_GROUPS = "too_many_groups"


class GroupWarningReason(StrEnum):
    """Reasons a per-group caveat is surfaced to the user.

    Kept UI-text-free for the same reason as `GroupComparisonError`.
    """

    TOO_FEW_FOR_VARIANCE = "too_few_for_variance"
    TOO_FEW_FOR_NORMALITY = "too_few_for_normality"


@dataclass(frozen=True, slots=True)
class GroupComparisonWarning:
    """A single non-blocking caveat about one group's data.

    Attributes:
        group_label: The affected group's label.
        reason: Structured reason code; translated by the GUI layer.
    """

    group_label: str
    reason: GroupWarningReason


@dataclass(frozen=True, slots=True)
class GroupSummary:
    """Descriptive summary and normality check for one group in a comparison.

    Attributes:
        label: The group's value (from the grouping column), as text.
        count: Number of valid (non-null) numeric observations in this
            group.
        mean: Arithmetic mean of the group's numeric values.
        std: Sample standard deviation. NaN when `count` < 2.
        minimum: Minimum value.
        q1: 25th percentile.
        median: Median (50th percentile).
        q3: 75th percentile.
        maximum: Maximum value.
        shapiro_statistic: Shapiro-Wilk test statistic (W) for this group
            alone. NaN when it could not be computed (fewer than 3 valid
            values).
        shapiro_p_value: Shapiro-Wilk p-value for this group alone. See
            `shapiro_statistic`.
    """

    label: str
    count: int
    mean: float
    std: float
    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    shapiro_statistic: float
    shapiro_p_value: float


@dataclass(frozen=True, slots=True)
class PairwiseComparisonResult:
    """Two-group comparison: Welch's t-test and Mann-Whitney U.

    `mean_difference` and its confidence interval are computed as
    ``mean(first group) - mean(second group)``, using `groups`' order.

    Attributes:
        t_statistic: Welch's t-test statistic (does not assume equal
            variances between the two groups).
        t_p_value: Two-sided p-value for the t-test.
        t_degrees_of_freedom: Welch-Satterthwaite degrees of freedom.
        mean_difference: Difference between the two groups' means.
        mean_difference_ci_low: Lower bound of the confidence interval for
            `mean_difference` (`_CONFIDENCE_LEVEL`).
        mean_difference_ci_high: Upper bound of the confidence interval
            for `mean_difference`.
        cohens_d: Standardized effect size (pooled standard deviation).
            NaN when either group has fewer than 2 observations.
        u_statistic: Mann-Whitney U statistic.
        u_p_value: Two-sided p-value for the Mann-Whitney U test.
        rank_biserial_correlation: Non-parametric effect size in
            ``[-1, 1]``.
    """

    t_statistic: float
    t_p_value: float
    t_degrees_of_freedom: float
    mean_difference: float
    mean_difference_ci_low: float
    mean_difference_ci_high: float
    cohens_d: float
    u_statistic: float
    u_p_value: float
    rank_biserial_correlation: float


@dataclass(frozen=True, slots=True)
class MultiGroupComparisonResult:
    """More-than-two-group comparison: one-way ANOVA and Kruskal-Wallis.

    Attributes:
        f_statistic: One-way ANOVA F-statistic. Assumes equal variances
            across groups (unlike the pairwise Welch's t-test).
        f_p_value: p-value for the ANOVA F-test.
        eta_squared: Proportion of total variance explained by group
            membership (``SS_between / SS_total``).
        h_statistic: Kruskal-Wallis H-statistic.
        h_p_value: p-value for the Kruskal-Wallis test.
        epsilon_squared: Non-parametric effect size analogous to
            `eta_squared`; does not assume equal variances.
    """

    f_statistic: float
    f_p_value: float
    eta_squared: float
    h_statistic: float
    h_p_value: float
    epsilon_squared: float


@dataclass(frozen=True, slots=True)
class GroupComparisonResult:
    """Result of comparing a numeric column across the groups of another column.

    Attributes:
        numeric_column: Name of the compared numeric column. Empty when no
            numeric column is available.
        grouping_column: Name of the column used to split rows into
            groups. Empty when no eligible grouping column is available.
        available_numeric_columns: All numeric columns in the dataset, for
            populating the configuration widget.
        available_grouping_columns: All columns with between `MIN_GROUPS`
            and `MAX_GROUPS` distinct non-null values, for populating the
            configuration widget.
        groups: Per-group descriptive summary, in ascending order of the
            group's value. Empty when `error` is set.
        pairwise: Set when `groups` has exactly 2 entries, `None`
            otherwise.
        multi_group: Set when `groups` has more than 2 entries, `None`
            otherwise.
        warnings: Non-blocking caveats about the computed result (e.g. a
            group too small for a reliable statistic). Always empty when
            `error` is set.
        error: A structured reason no result could be computed (e.g. too
            many/too few groups), or `None` when `groups` was successfully
            computed. Set exclusively together with an empty `groups`.
    """

    numeric_column: str
    grouping_column: str
    available_numeric_columns: tuple[str, ...]
    available_grouping_columns: tuple[str, ...]
    groups: tuple[GroupSummary, ...]
    pairwise: PairwiseComparisonResult | None
    multi_group: MultiGroupComparisonResult | None
    warnings: tuple[GroupComparisonWarning, ...]
    error: GroupComparisonError | None


def _numeric_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return every numeric (int or float) column name, in column order."""
    return tuple(str(column) for column in df.columns if classify_series_dtype(df[column]) in _NUMERIC_DTYPES)


def _grouping_candidate_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return columns with a usable number of distinct values for grouping.

    Any dtype is eligible (e.g. a 0/1 flag stored as int is a perfectly
    valid grouping column) - only the distinct-value count is restricted,
    to keep the configuration widget's choices meaningful (excluding
    ID-like columns) without hiding legitimate low-cardinality numeric
    columns behind a dtype filter.
    """
    candidates = []
    for column in df.columns:
        distinct = df[column].nunique(dropna=True)
        if MIN_GROUPS <= distinct <= MAX_GROUPS:
            candidates.append(str(column))
    return tuple(candidates)


def _error_result(
    error: GroupComparisonError,
    *,
    numeric_column: str,
    grouping_column: str,
    numeric_columns: tuple[str, ...],
    grouping_columns: tuple[str, ...],
) -> GroupComparisonResult:
    """Build a `GroupComparisonResult` carrying only a structured error."""
    return GroupComparisonResult(
        numeric_column=numeric_column,
        grouping_column=grouping_column,
        available_numeric_columns=numeric_columns,
        available_grouping_columns=grouping_columns,
        groups=(),
        pairwise=None,
        multi_group=None,
        warnings=(),
        error=error,
    )


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Compute Cohen's d (pooled standard deviation) effect size.

    NaN when either group has fewer than 2 observations (no variance
    estimate possible) or the pooled variance is zero.
    """
    na, nb = len(a), len(b)
    if na < _MIN_OBSERVATIONS_FOR_VARIANCE or nb < _MIN_OBSERVATIONS_FOR_VARIANCE:
        return _NAN

    pooled_variance = ((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1)) / (na + nb - 2)
    if pooled_variance <= 0:
        return _NAN

    return float((np.mean(a) - np.mean(b)) / math.sqrt(pooled_variance))


def _rank_biserial(u_statistic: float, na: int, nb: int) -> float:
    """Compute the rank-biserial correlation effect size from Mann-Whitney U."""
    if na == 0 or nb == 0:
        return _NAN
    return float(1.0 - (2.0 * u_statistic) / (na * nb))


def _eta_squared(groups: list[np.ndarray]) -> float:
    """Compute eta-squared: the proportion of variance explained by group membership."""
    all_values = np.concatenate(groups)
    if len(all_values) == 0:
        return _NAN

    grand_mean = np.mean(all_values)
    ss_total = float(np.sum((all_values - grand_mean) ** 2))
    if ss_total == 0:
        return _NAN

    ss_between = float(sum(len(group) * (np.mean(group) - grand_mean) ** 2 for group in groups))
    return ss_between / ss_total


def _epsilon_squared(h_statistic: float, n_total: int, n_groups: int) -> float:
    """Compute epsilon-squared: a Kruskal-Wallis analogue of eta-squared."""
    denominator = n_total - n_groups
    if denominator <= 0 or math.isnan(h_statistic):
        return _NAN
    return (h_statistic - n_groups + 1) / denominator


def _pairwise_comparison(a: np.ndarray, b: np.ndarray) -> PairwiseComparisonResult:
    """Run Welch's t-test and Mann-Whitney U on exactly two groups' values."""
    with warnings.catch_warnings():
        # scipy warns about reduced precision for near-identical/constant
        # groups; it already returns a valid (if degenerate) result in
        # that case, so the warning would just be noise here.
        warnings.simplefilter("ignore")
        t_result = ttest_ind(a, b, equal_var=False)
        ci = t_result.confidence_interval(confidence_level=_CONFIDENCE_LEVEL)
        u_result = mannwhitneyu(a, b, alternative="two-sided")

    return PairwiseComparisonResult(
        # scipy ships no type stubs (no py.typed marker); pyright cannot
        # infer TtestResult's attributes through its base-class mixin, even
        # though they exist at runtime and mypy (which treats untyped
        # scipy as Any) raises no issue here.
        t_statistic=float(t_result.statistic),  # pyright: ignore[reportAttributeAccessIssue]
        t_p_value=float(t_result.pvalue),  # pyright: ignore[reportAttributeAccessIssue]
        t_degrees_of_freedom=float(t_result.df),  # pyright: ignore[reportAttributeAccessIssue]
        mean_difference=float(np.mean(a) - np.mean(b)),
        mean_difference_ci_low=float(ci.low),
        mean_difference_ci_high=float(ci.high),
        cohens_d=_cohens_d(a, b),
        u_statistic=float(u_result.statistic),
        u_p_value=float(u_result.pvalue),
        rank_biserial_correlation=_rank_biserial(float(u_result.statistic), len(a), len(b)),
    )


def _multi_group_comparison(groups: list[np.ndarray]) -> MultiGroupComparisonResult:
    """Run one-way ANOVA and Kruskal-Wallis on more than two groups' values."""
    with warnings.catch_warnings():
        # scipy warns when every group is constant (F is undefined/infinite)
        # - it already returns NaN in that case, so the warning would just
        # be noise on top of an already-transparent NaN result.
        warnings.simplefilter("ignore")
        f_result = f_oneway(*groups)

    try:
        h_result = kruskal(*groups)
        h_statistic, h_p_value = float(h_result.statistic), float(h_result.pvalue)
    except ValueError:
        # scipy raises (rather than returning NaN) when every value across
        # every group is identical - there is no rank variation at all for
        # the test to use. Degenerate input, not a bug: report it the same
        # way as every other "cannot compute" case in this module.
        h_statistic, h_p_value = _NAN, _NAN

    n_total = sum(len(group) for group in groups)

    return MultiGroupComparisonResult(
        f_statistic=float(f_result.statistic),
        f_p_value=float(f_result.pvalue),
        eta_squared=_eta_squared(groups),
        h_statistic=h_statistic,
        h_p_value=h_p_value,
        epsilon_squared=_epsilon_squared(h_statistic, n_total, len(groups)),
    )


def analyze_group_comparison(
    df: pd.DataFrame,
    numeric_column: str | None = None,
    grouping_column: str | None = None,
) -> GroupComparisonResult:
    """Compare a numeric column's central tendency across another column's groups.

    Args:
        df: The DataFrame to analyze. Never mutated.
        numeric_column: Column to compare. Defaults to the first numeric
            column when `None`; an explicitly given column that is not a
            numeric column of `df` is reported as `NO_NUMERIC_COLUMN`
            rather than silently replaced.
        grouping_column: Column whose distinct values define the groups.
            Defaults to the first eligible column (`MIN_GROUPS`..
            `MAX_GROUPS` distinct values, excluding `numeric_column`) when
            `None`; an explicitly given column that does not exist, or
            equals `numeric_column`, is reported as `NO_GROUPING_COLUMN`
            rather than silently replaced. An explicitly given column with
            too few/many distinct values (after dropping missing data) is
            validated as given and reported as `TOO_FEW_GROUPS` /
            `TOO_MANY_GROUPS` - it is not silently swapped for a different
            column either, so a caller always gets an honest answer about
            the exact column it asked for.

    Returns:
        A populated `GroupComparisonResult`. `error` is set (and `groups`
        empty) when no valid comparison could be made - e.g. no numeric or
        no eligible grouping column is available, or the resolved pair has
        fewer than `MIN_GROUPS` or more than `MAX_GROUPS` groups with valid
        data.
    """
    numeric_columns = _numeric_columns(df)
    grouping_columns = _grouping_candidate_columns(df)

    if numeric_column is None:
        numeric_column = numeric_columns[0] if numeric_columns else ""

    if grouping_column is None:
        eligible_grouping = tuple(column for column in grouping_columns if column != numeric_column)
        grouping_column = eligible_grouping[0] if eligible_grouping else ""

    if not numeric_column or numeric_column not in numeric_columns:
        return _error_result(
            GroupComparisonError.NO_NUMERIC_COLUMN,
            numeric_column=numeric_column,
            grouping_column=grouping_column,
            numeric_columns=numeric_columns,
            grouping_columns=grouping_columns,
        )
    if not grouping_column or grouping_column == numeric_column or grouping_column not in df.columns:
        return _error_result(
            GroupComparisonError.NO_GROUPING_COLUMN,
            numeric_column=numeric_column,
            grouping_column=grouping_column,
            numeric_columns=numeric_columns,
            grouping_columns=grouping_columns,
        )

    working = df[[numeric_column, grouping_column]].copy()
    working[numeric_column] = pd.to_numeric(working[numeric_column], errors="coerce")
    working[numeric_column] = working[numeric_column].replace([np.inf, -np.inf], _NAN)
    working = working.dropna(subset=[numeric_column, grouping_column])

    grouped = working.groupby(grouping_column, sort=True, observed=True)[numeric_column]

    if grouped.ngroups < MIN_GROUPS:
        return _error_result(
            GroupComparisonError.TOO_FEW_GROUPS,
            numeric_column=numeric_column,
            grouping_column=grouping_column,
            numeric_columns=numeric_columns,
            grouping_columns=grouping_columns,
        )
    if grouped.ngroups > MAX_GROUPS:
        return _error_result(
            GroupComparisonError.TOO_MANY_GROUPS,
            numeric_column=numeric_column,
            grouping_column=grouping_column,
            numeric_columns=numeric_columns,
            grouping_columns=grouping_columns,
        )

    summaries: list[GroupSummary] = []
    raw_groups: list[np.ndarray] = []
    group_warnings: list[GroupComparisonWarning] = []

    for label, values in grouped:
        label_text = str(label)
        array = values.to_numpy(dtype=float)
        count = len(array)
        q1, median, q3 = (float(v) for v in np.quantile(array, [0.25, 0.5, 0.75]))
        shapiro_statistic, shapiro_p_value = shapiro_normality(values)

        summaries.append(
            GroupSummary(
                label=label_text,
                count=count,
                mean=float(np.mean(array)),
                std=float(np.std(array, ddof=1)) if count >= _MIN_OBSERVATIONS_FOR_VARIANCE else _NAN,
                minimum=float(np.min(array)),
                q1=q1,
                median=median,
                q3=q3,
                maximum=float(np.max(array)),
                shapiro_statistic=shapiro_statistic,
                shapiro_p_value=shapiro_p_value,
            )
        )
        raw_groups.append(array)

        if count < _MIN_OBSERVATIONS_FOR_VARIANCE:
            group_warnings.append(GroupComparisonWarning(label_text, GroupWarningReason.TOO_FEW_FOR_VARIANCE))
        if count < _MIN_OBSERVATIONS_FOR_NORMALITY:
            group_warnings.append(GroupComparisonWarning(label_text, GroupWarningReason.TOO_FEW_FOR_NORMALITY))

    if len(raw_groups) == MIN_GROUPS:
        pairwise = _pairwise_comparison(raw_groups[0], raw_groups[1])
        multi_group = None
    else:
        pairwise = None
        multi_group = _multi_group_comparison(raw_groups)

    return GroupComparisonResult(
        numeric_column=numeric_column,
        grouping_column=grouping_column,
        available_numeric_columns=numeric_columns,
        available_grouping_columns=grouping_columns,
        groups=tuple(summaries),
        pairwise=pairwise,
        multi_group=multi_group,
        warnings=tuple(group_warnings),
        error=None,
    )
