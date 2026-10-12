from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.gui.dialogs.analysis.chi_square_view import ChiSquareView
from expo_jbm329.gui.dialogs.analysis.group_comparison_view import GroupComparisonView
from expo_jbm329.gui.dialogs.analysis.paired_comparison_view import PairedComparisonView
from expo_jbm329.services.analysis.categories import HypothesisTest
from expo_jbm329.services.analysis.chi_square import analyze_chi_square, initialize_chi_square
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison, initialize_group_comparison
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent as Component,
)
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportRequest,
    HypothesisExportSnapshot,
    hypothesis_export_tables,
)
from expo_jbm329.services.analysis.paired_comparison import analyze_paired_comparison, initialize_paired_comparison
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat as Format


def group_snapshot(groups: int = 2) -> HypothesisExportSnapshot:
    df = pd.DataFrame({
        "Value": np.arange(groups * 6, dtype=float),
        "Group": np.repeat([f"G{i}" for i in range(groups)], 6),
    })
    return HypothesisExportSnapshot(
        HypothesisTest.GROUP_COMPARISON,
        analyze_group_comparison(df, "Value", "Group"),
        ("Value", "Group"),
        ("assumptions", "normality", "caveat", "another note"),
    )


def chi_snapshot(columns: int = 2) -> HypothesisExportSnapshot:
    df = pd.DataFrame(
        [(row, column) for row in ("A", "B") for column in range(columns) for _ in range(3 + column)],
        columns=["Row", "Column"],
    )
    return HypothesisExportSnapshot(
        HypothesisTest.CHI_SQUARE,
        analyze_chi_square(df, "Row", "Column"),
        ("Row", "Column"),
        ("Yates", "Cochran", "residual interpretation"),
    )


def paired_snapshot(occasions: int = 2, subjects: int = 10) -> HypothesisExportSnapshot:
    df = pd.DataFrame({f"Time {i}": np.arange(subjects, dtype=float) + i for i in range(occasions)})
    # Deliberately non-chronological order must be preserved.
    columns = tuple(reversed(df.columns))
    result = analyze_paired_comparison(df, columns)
    return HypothesisExportSnapshot(HypothesisTest.PAIRED_COMPARISON, result, columns, ("ordering", "sampling"))


@pytest.mark.parametrize(
    "groups,tests",
    [(2, ["Welch's t-test", "Student's t-test", "Mann-Whitney U"]), (3, ["One-way ANOVA", "Kruskal-Wallis"])],
)
def test_group_tables_export_all_displayed_tests_and_numeric_summaries(groups, tests):
    snapshot = group_snapshot(groups)
    result = snapshot.result
    tables = hypothesis_export_tables(snapshot, (Component.SUMMARY, Component.TEST_RESULTS))
    summary, results = tables.values()
    assert summary.columns.tolist() == [
        "group",
        "count",
        "mean",
        "median",
        "std",
        "shapiro_statistic",
        "shapiro_p_value",
        "normal",
    ]
    assert summary["group"].tolist() == [group.label for group in result.groups]
    assert summary["count"].tolist() == [6] * groups
    assert results["test"].dropna().tolist() == tests
    assert results["notes"].dropna().tolist() == list(snapshot.notes)
    for column in ("count", "mean", "median", "std", "shapiro_statistic", "shapiro_p_value"):
        assert pd.api.types.is_numeric_dtype(summary[column])
    for column in ("statistic", "p_value", "effect_size", "sample_count"):
        assert pd.api.types.is_numeric_dtype(results[column])
    assert str(results["sample_count"].dtype) == "Int64"
    if groups == 2:
        assert results.loc[0, "ci_low"] == result.pairwise.mean_difference_ci_low
        assert results.loc[1, "ci_high"] == result.pairwise.student_mean_difference_ci_high
        assert results.loc[2, "effect_size"] == result.pairwise.rank_biserial_correlation
    else:
        assert results["effect_size"].dropna().tolist() == [
            result.multi_group.eta_squared,
            result.multi_group.epsilon_squared,
        ]


@pytest.mark.parametrize("columns", [2, 3])
def test_chi_tables_preserve_observed_orientation_totals_fisher_and_caveats(columns):
    snapshot = chi_snapshot(columns)
    result = snapshot.result
    summary, tests = hypothesis_export_tables(snapshot, (Component.SUMMARY, Component.TEST_RESULTS)).values()
    assert summary.iloc[:-1, 1:-1].to_numpy().tolist() == [list(row) for row in result.observed]
    assert summary.iloc[:-1, 0].tolist() == list(result.row_labels)
    assert summary.columns[1:-1].tolist() == list(result.column_labels)
    assert summary.iloc[-1, -1] == result.total
    assert tests.loc[0, "yates_correction"] == (columns == 2)
    assert tests.loc[0, "cochran_violated"] == result.cochran_violated
    assert tests["test"].dropna().tolist() == (
        ["Pearson's chi-square test", "Fisher's exact test"] if columns == 2 else ["Pearson's chi-square test"]
    )
    assert "expected" not in summary.columns
    assert pd.api.types.is_numeric_dtype(summary.iloc[:, 1])
    assert tests["notes"].dropna().tolist() == list(snapshot.notes)


def test_contingency_category_labels_matching_internal_headers_remain_literal():
    result = analyze_chi_square(
        pd.DataFrame({
            "Row": ["a", "a", "b", "b"],
            "Column": ["row_category", "total", "row_category", "total"],
        }),
        "Row",
        "Column",
    )
    snapshot = HypothesisExportSnapshot(HypothesisTest.CHI_SQUARE, result, ("Row", "Column"))
    frame = hypothesis_export_tables(snapshot, (Component.SUMMARY,))[Component.SUMMARY]
    assert frame.columns.tolist() == ["row_category", "row_category", "total", "total"]
    assert frame.iloc[:-1, 1:-1].to_numpy().tolist() == [[1, 1], [1, 1]]


@pytest.mark.parametrize("occasions", [2, 3])
def test_paired_tables_preserve_order_counts_and_kendall_effect(occasions):
    snapshot = paired_snapshot(occasions)
    result = snapshot.result
    summary, tests = hypothesis_export_tables(snapshot, (Component.SUMMARY, Component.TEST_RESULTS)).values()
    assert summary["measurement"].tolist() == list(snapshot.columns)
    assert summary.columns.tolist() == ["measurement", "count", "mean", "median", "std", "q1", "q3"]
    assert summary["count"].tolist() == [result.complete_subjects] * occasions
    assert tests.loc[0, "test"] == ("Wilcoxon signed-rank test" if occasions == 2 else "Friedman test")
    assert tests.loc[0, "excluded_subjects"] == result.excluded_subjects
    assert [tests.loc[0, f"measurement_{i}"] for i in range(1, occasions + 1)] == list(snapshot.columns)
    if occasions == 3:
        assert tests.loc[0, "effect_size"] == result.kendall_w
    else:
        assert "effect_size" not in tests


def test_missing_statistics_are_nan_not_invented_zero():
    df = pd.DataFrame({"Value": [1.0, 2.0], "Group": ["A", "B"]})
    result = analyze_group_comparison(df, "Value", "Group")
    snapshot = HypothesisExportSnapshot(HypothesisTest.GROUP_COMPARISON, result, ("Value", "Group"))
    summary, tests = hypothesis_export_tables(snapshot, (Component.SUMMARY, Component.TEST_RESULTS)).values()
    assert summary["std"].isna().all()
    assert summary["normal"].isna().all()
    assert tests.loc[0, ["statistic", "ci_low", "effect_size"]].isna().all()
    assert tests["notes"].isna().all()


@pytest.mark.parametrize(
    "test,initializer,columns",
    [
        (HypothesisTest.GROUP_COMPARISON, initialize_group_comparison, ("Value", "Group")),
        (HypothesisTest.CHI_SQUARE, initialize_chi_square, ("Group", "Other")),
        (HypothesisTest.PAIRED_COMPARISON, initialize_paired_comparison, ("Value", "Second")),
    ],
)
def test_unfitted_initializers_are_rejected_even_when_error_is_none(test, initializer, columns):
    df = pd.DataFrame({
        "Value": [1, 2, 3, 4],
        "Second": [2, 3, 4, 5],
        "Group": ["a", "b", "a", "b"],
        "Other": ["x", "y", "y", "x"],
    })
    result = initializer(df)
    assert result.error is None
    with pytest.raises(ValueError, match="fitted"):
        HypothesisExportSnapshot(test, result, columns)
    error_result = initializer(pd.DataFrame())
    with pytest.raises(ValueError, match="failed"):
        HypothesisExportSnapshot(test, error_result, columns)


@pytest.mark.parametrize("factory", [group_snapshot, chi_snapshot, paired_snapshot])
def test_snapshot_rejects_mismatched_applied_metadata(factory):
    snapshot = factory()
    with pytest.raises(ValueError):
        replace(snapshot, columns=("pending", "selection"))
    with pytest.raises(ValueError):
        replace(snapshot, test=next(test for test in HypothesisTest if test is not snapshot.test))


def test_snapshot_rejects_malformed_contingency_and_paired_payloads():
    chi = chi_snapshot()
    for changes in ({"observed": ((1,),)}, {"total": 1}, {"adjusted_residuals": ()}):
        with pytest.raises(ValueError):
            replace(chi, result=replace(chi.result, **changes))
    paired = paired_snapshot()
    for changes in (
        {"summaries": ()},
        {"method": None},
        {"complete_subjects": 0},
        {"plot_data": replace(paired.result.plot_data, trajectories=((1,),))},
        {"plot_data": replace(paired.result.plot_data, trajectories=())},
        {"total_subjects": 999},
    ):
        with pytest.raises(ValueError):
            replace(paired, result=replace(paired.result, **changes))
    with pytest.raises(TypeError):
        HypothesisExportSnapshot(HypothesisTest.GROUP_COMPARISON, object(), ())


@pytest.mark.parametrize(
    "components",
    [
        (),
        (Component.CHARTS,),
        (Component.SUMMARY, Component.SUMMARY),
        ("unknown",),
        ("summary",),
    ],
)
def test_table_builder_rejects_invalid_selections(components):
    with pytest.raises(ValueError):
        hypothesis_export_tables(group_snapshot(), components)


@pytest.mark.parametrize(
    "components,format_choice",
    [
        ((), Format.EXCEL),
        ((Component.SUMMARY, Component.SUMMARY), Format.EXCEL),
        (("unknown",), Format.EXCEL),
        ((Component.CHARTS,), Format.CSV),
        ((Component.SUMMARY, Component.TEST_RESULTS), Format.BINARY),
    ],
)
def test_requests_reject_invalid_selections(components, format_choice):
    with pytest.raises(ValueError):
        HypothesisExportRequest(group_snapshot(), components, format_choice)


def test_requests_accept_charts_only_excel_and_one_table_binary():
    snapshot = group_snapshot()
    assert HypothesisExportRequest(snapshot, (Component.CHARTS,), Format.EXCEL).snapshot is snapshot
    assert HypothesisExportRequest(snapshot, (Component.TEST_RESULTS,), Format.BINARY).format is Format.BINARY
    with pytest.raises(TypeError):
        HypothesisExportRequest(snapshot, (Component.SUMMARY,), "unknown")


def test_export_notes_share_displayed_normality_warnings_assumptions_and_sampling():
    result = analyze_group_comparison(pd.DataFrame({"value": [1, 2], "group": ["A", "B"]}), "value", "group")
    view = GroupComparisonView(result)
    notes = view.export_notes(result)
    assert any("does not assume equal variances" in note for note in notes)
    assert any("assumes equal variances" in note for note in notes)
    assert any("normality could not be tested" in note for note in notes)
    assert any("fewer than 2" in note for note in notes)
    assert any("fewer than 3" in note for note in notes)
    snapshot = group_snapshot(3)
    view = GroupComparisonView(snapshot.result)
    assert any("Every group is consistent" in note for note in view.export_notes(snapshot.result))
    chi = chi_snapshot()
    chi_view = ChiSquareView(chi.result)
    assert any("Yates" in note for note in chi_view.export_notes(chi.result))
    assert any("unreliable" in note for note in chi_view.export_notes(chi.result))
    assert any("Fisher" in note for note in chi_view.export_notes(chi.result))
    paired = paired_snapshot(3, 250)
    paired_view = PairedComparisonView(paired.result)
    paired_notes = paired_view.export_notes(paired.result)
    assert any("chronological order is not inferred" in note for note in paired_notes)
    assert any("sample of 200 of 250" in note for note in paired_notes)
    assert any("all complete subjects" in note for note in paired_notes)


def test_export_notes_never_strip_literal_group_label_markup():
    result = analyze_group_comparison(
        pd.DataFrame({"value": [1, 2], "group": ["<b>literal</b>", "B"]}), "value", "group"
    )
    notes = GroupComparisonView(result).export_notes(result)
    assert any("Group '<b>literal</b>'" in note for note in notes)
