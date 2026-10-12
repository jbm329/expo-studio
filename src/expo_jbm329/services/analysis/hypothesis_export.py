"""Typed exports of a successfully displayed hypothesis-test selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.analysis.categories import HypothesisTest
from expo_jbm329.services.analysis.chi_square import ChiSquareResult
from expo_jbm329.services.analysis.group_comparison import MIN_GROUPS, GroupComparisonResult, group_normality_verdict
from expo_jbm329.services.analysis.paired_comparison import PairedComparisonMethod, PairedComparisonResult
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

if TYPE_CHECKING:
    from collections.abc import Sequence

HypothesisResult = GroupComparisonResult | ChiSquareResult | PairedComparisonResult
HypothesisExportFormat = StatisticsExportFormat


class HypothesisExportComponent(StrEnum):
    """Selectable displayed components; charts are Excel-only."""

    SUMMARY = "summary"
    TEST_RESULTS = "Test results"
    CHARTS = "Charts"


@dataclass(frozen=True, slots=True)
class HypothesisExportSnapshot:
    """Own the applied result and translated notes, never pending controls."""

    test: HypothesisTest
    result: HypothesisResult
    columns: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject metadata initializers, failed results and mismatched selections."""
        result = self.result
        if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            result,
            (GroupComparisonResult, ChiSquareResult, PairedComparisonResult),
        ):
            message = "A typed hypothesis result is required."
            raise TypeError(message)
        if result.error is not None:
            message = "A failed hypothesis result cannot be exported."
            raise ValueError(message)
        match result:
            case GroupComparisonResult():
                valid = (
                    self.test is HypothesisTest.GROUP_COMPARISON
                    and self.columns == (result.numeric_column, result.grouping_column)
                    and len(result.groups) >= MIN_GROUPS
                    and all(group.count > 0 for group in result.groups)
                    and (
                        (
                            len(result.groups) == MIN_GROUPS
                            and result.pairwise is not None
                            and result.multi_group is None
                        )
                        or (
                            len(result.groups) > MIN_GROUPS
                            and result.multi_group is not None
                            and result.pairwise is None
                        )
                    )
                )
            case ChiSquareResult():
                shape = (len(result.row_labels), len(result.column_labels))
                valid = (
                    self.test is HypothesisTest.CHI_SQUARE
                    and self.columns == (result.row_column, result.column_column)
                    and min(shape) >= MIN_GROUPS
                    and result.total > 0
                    and all(
                        len(matrix) == shape[0] and all(len(row) == shape[1] for row in matrix)
                        for matrix in (result.observed, result.expected, result.adjusted_residuals)
                    )
                    and sum(map(sum, result.observed)) == result.total
                )
            case PairedComparisonResult():
                valid = (
                    self.test is HypothesisTest.PAIRED_COMPARISON
                    and self.columns == result.columns
                    and len(result.columns) >= MIN_GROUPS
                    and result.complete_subjects > 0
                    and result.method
                    is (
                        PairedComparisonMethod.WILCOXON
                        if len(result.columns) == MIN_GROUPS
                        else PairedComparisonMethod.FRIEDMAN
                    )
                    and tuple(summary.column for summary in result.summaries) == result.columns
                    and all(summary.count == result.complete_subjects for summary in result.summaries)
                    and result.complete_subjects + result.excluded_subjects == result.total_subjects
                    and result.plot_data is not None
                    and bool(result.plot_data.trajectories)
                    and all(len(row) == len(result.columns) for row in result.plot_data.trajectories)
                )
        if not valid:
            message = "Only a fitted result matching the applied hypothesis selection can be exported."
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class HypothesisExportRequest:
    """Selected components from one immutable displayed snapshot."""

    snapshot: HypothesisExportSnapshot
    components: tuple[HypothesisExportComponent, ...]
    format: StatisticsExportFormat

    def __post_init__(self) -> None:
        """Validate selection without altering retained dialog choices."""
        if not self.components or len(set(self.components)) != len(self.components):
            message = "Select distinct available hypothesis components."
            raise ValueError(message)
        if any(
            not isinstance(item, HypothesisExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.components
        ):
            message = "Unknown hypothesis export component."
            raise ValueError(message)
        if not isinstance(self.format, StatisticsExportFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Unknown hypothesis export format."
            raise TypeError(message)
        if self.format is not StatisticsExportFormat.EXCEL and (
            HypothesisExportComponent.CHARTS in self.components or len(self.components) != 1
        ):
            message = "CSV and binary exports require exactly one table and no charts."
            raise ValueError(message)


def hypothesis_export_tables(
    snapshot: HypothesisExportSnapshot, components: Sequence[HypothesisExportComponent]
) -> dict[HypothesisExportComponent, pd.DataFrame]:
    """Build typed displayed tables without formatting or Qt widget scraping.

    Args:
        snapshot: Successful applied selection, including captured presentation notes.
        components: Requested table components; charts are rendered separately.

    Returns:
        Ordered numeric DataFrames with stable internal column names.

    Raises:
        ValueError: If the selection is empty, duplicated or includes charts.
    """
    if (
        not components
        or len(set(components)) != len(components)
        or any(
            not isinstance(item, HypothesisExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            or item not in (HypothesisExportComponent.SUMMARY, HypothesisExportComponent.TEST_RESULTS)
            for item in components
        )
    ):
        message = "Select distinct hypothesis tables."
        raise ValueError(message)
    return {
        item: _summary(snapshot.result) if item is HypothesisExportComponent.SUMMARY else _test_results(snapshot)
        for item in components
    }


def _summary(result: HypothesisResult) -> pd.DataFrame:
    """Build exactly the summary columns displayed by each test view."""
    match result:
        case GroupComparisonResult():
            return pd.DataFrame([
                {
                    "group": group.label,
                    "count": group.count,
                    "mean": group.mean,
                    "median": group.median,
                    "std": group.std,
                    "shapiro_statistic": group.shapiro_statistic,
                    "shapiro_p_value": group.shapiro_p_value,
                    "normal": group_normality_verdict(group),
                }
                for group in result.groups
            ]).astype({"normal": "boolean"})
        case ChiSquareResult():
            # Keep category labels literal, including labels equal to translated headers.
            counts = [[*row, sum(row)] for row in result.observed]
            counts.append(
                [sum(row[index] for row in result.observed) for index in range(len(result.column_labels))]
                + [result.total]
            )
            return pd.DataFrame(
                [[label, *row] for label, row in zip((*result.row_labels, "total"), counts, strict=True)],
                columns=["row_category", *result.column_labels, "total"],
            )
        case PairedComparisonResult():
            return pd.DataFrame([
                {
                    "measurement": summary.column,
                    "count": summary.count,
                    "mean": summary.mean,
                    "median": summary.median,
                    "std": summary.std,
                    "q1": summary.q1,
                    "q3": summary.q3,
                }
                for summary in result.summaries
            ])


def _test_results(snapshot: HypothesisExportSnapshot) -> pd.DataFrame:
    """Keep all displayed statistics numeric, with notes in the same component."""
    result = snapshot.result
    rows: list[dict[str, object]] = []
    match result:
        case GroupComparisonResult():
            pair = result.pairwise
            multi = result.multi_group
            if pair is not None:
                rows = [
                    {
                        "test": "Welch's t-test",
                        "statistic": pair.t_statistic,
                        "p_value": pair.t_p_value,
                        "degrees_of_freedom": pair.t_degrees_of_freedom,
                        "mean_difference": pair.mean_difference,
                        "ci_low": pair.mean_difference_ci_low,
                        "ci_high": pair.mean_difference_ci_high,
                        "effect_name": "Cohen's d",
                        "effect_size": pair.cohens_d,
                    },
                    {
                        "test": "Student's t-test",
                        "statistic": pair.student_t_statistic,
                        "p_value": pair.student_t_p_value,
                        "degrees_of_freedom": pair.student_t_degrees_of_freedom,
                        "mean_difference": pair.mean_difference,
                        "ci_low": pair.student_mean_difference_ci_low,
                        "ci_high": pair.student_mean_difference_ci_high,
                    },
                    {
                        "test": "Mann-Whitney U",
                        "statistic": pair.u_statistic,
                        "p_value": pair.u_p_value,
                        "effect_name": "Rank-biserial correlation",
                        "effect_size": pair.rank_biserial_correlation,
                    },
                ]
            elif multi is not None:
                rows = [
                    {
                        "test": "One-way ANOVA",
                        "statistic": multi.f_statistic,
                        "p_value": multi.f_p_value,
                        "effect_name": "Eta²",
                        "effect_size": multi.eta_squared,
                    },
                    {
                        "test": "Kruskal-Wallis",
                        "statistic": multi.h_statistic,
                        "p_value": multi.h_p_value,
                        "effect_name": "Epsilon²",
                        "effect_size": multi.epsilon_squared,
                    },
                ]
            for row in rows:
                row.update(
                    numeric_column=result.numeric_column,
                    grouping_column=result.grouping_column,
                    sample_count=sum(group.count for group in result.groups),
                )
        case ChiSquareResult():
            rows = [
                {
                    "test": "Pearson's chi-square test",
                    "statistic": result.chi2_statistic,
                    "p_value": result.p_value,
                    "degrees_of_freedom": result.degrees_of_freedom,
                    "effect_name": "Cramér's V",
                    "effect_size": result.cramers_v,
                    "yates_correction": result.yates_correction_applied,
                    "cochran_violated": result.cochran_violated,
                    "low_expected_fraction": result.low_expected_fraction,
                    "min_expected": result.min_expected,
                }
            ]
            if result.fisher_p_value is not None and result.fisher_odds_ratio is not None:
                rows.append({
                    "test": "Fisher's exact test",
                    "p_value": result.fisher_p_value,
                    "odds_ratio": result.fisher_odds_ratio,
                })
            for row in rows:
                row.update(row_column=result.row_column, column_column=result.column_column, sample_count=result.total)
        case PairedComparisonResult():
            rows = [
                {
                    "test": "Wilcoxon signed-rank test"
                    if result.method is PairedComparisonMethod.WILCOXON
                    else "Friedman test",
                    "statistic": result.statistic,
                    "p_value": result.p_value,
                    "sample_count": result.complete_subjects,
                    "total_subjects": result.total_subjects,
                    "excluded_subjects": result.excluded_subjects,
                }
            ]
            for index, column in enumerate(result.columns, 1):
                rows[0][f"measurement_{index}"] = column
            if result.method is PairedComparisonMethod.FRIEDMAN:
                rows[0].update(effect_name="Kendall's W", effect_size=result.kendall_w)
    frame = pd.DataFrame(rows)
    # Notes share result rows where possible, adding rows only when necessary.
    frame = frame.reindex(range(max(len(rows), len(snapshot.notes))))
    for column in ("sample_count", "total_subjects", "excluded_subjects"):
        if column in frame:
            frame[column] = frame[column].astype(pd.Int64Dtype())
    for column in ("yates_correction", "cochran_violated"):
        if column in frame:
            frame[column] = frame[column].astype(pd.BooleanDtype())
    frame["notes"] = pd.Series(snapshot.notes, dtype=pd.StringDtype())
    return frame
