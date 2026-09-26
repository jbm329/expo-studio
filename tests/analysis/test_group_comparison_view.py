from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QTableWidget

from expo_jbm329.gui.dialogs.analysis.group_comparison_view import GroupComparisonView
from expo_jbm329.services.analysis.group_comparison import (
    GroupComparisonError,
    GroupComparisonResult,
    GroupComparisonWarning,
    GroupSummary,
    GroupWarningReason,
    MultiGroupComparisonResult,
    PairwiseComparisonResult,
)


def _make_group(label: str, **overrides: object) -> GroupSummary:
    defaults: dict[str, object] = {
        "label": label,
        "count": 10,
        "mean": 5.0,
        "std": 1.0,
        "minimum": 2.0,
        "q1": 4.0,
        "median": 5.0,
        "q3": 6.0,
        "maximum": 8.0,
        "shapiro_statistic": 0.98,
        "shapiro_p_value": 0.5,
    }
    defaults.update(overrides)
    return GroupSummary(**defaults)  # type: ignore[arg-type]


_PAIRWISE = PairwiseComparisonResult(
    t_statistic=-5.37,
    t_p_value=1.4e-06,
    t_degrees_of_freedom=57.9,
    mean_difference=-2.19,
    mean_difference_ci_low=-3.01,
    mean_difference_ci_high=-1.38,
    cohens_d=-1.39,
    u_statistic=150.0,
    u_p_value=9.5e-06,
    rank_biserial_correlation=0.67,
)

_MULTI_GROUP = MultiGroupComparisonResult(
    f_statistic=9.27,
    f_p_value=0.0003,
    eta_squared=0.25,
    h_statistic=14.8,
    h_p_value=0.0006,
    epsilon_squared=0.22,
)


def _make_result(**overrides: object) -> GroupComparisonResult:
    defaults: dict[str, object] = {
        "numeric_column": "value",
        "grouping_column": "grp",
        "available_numeric_columns": ("value",),
        "available_grouping_columns": ("grp",),
        "groups": (_make_group("A"), _make_group("B")),
        "pairwise": _PAIRWISE,
        "multi_group": None,
        "warnings": (),
        "error": None,
    }
    defaults.update(overrides)
    return GroupComparisonResult(**defaults)  # type: ignore[arg-type]


def _find_table(view: GroupComparisonView) -> QTableWidget:
    tables = view.findChildren(QTableWidget)
    assert len(tables) == 1
    return tables[0]


def _find_labels(view: GroupComparisonView) -> list[QLabel]:
    return view.findChildren(QLabel)


# ----------------------------------------------------------------------
# Error state
# ----------------------------------------------------------------------


def test_error_result_shows_only_a_message_no_table_or_chart():
    result = _make_result(groups=(), pairwise=None, error=GroupComparisonError.NO_NUMERIC_COLUMN)

    view = GroupComparisonView(result)

    assert view.findChildren(QTableWidget) == []
    labels = _find_labels(view)
    assert len(labels) == 1
    assert "numeric column" in labels[0].text()


def test_every_structured_error_has_a_distinct_message():
    texts = set()
    for error in GroupComparisonError:
        result = _make_result(groups=(), pairwise=None, error=error)
        view = GroupComparisonView(result)
        texts.add(_find_labels(view)[0].text())

    assert len(texts) == len(list(GroupComparisonError))


# ----------------------------------------------------------------------
# Per-group table
# ----------------------------------------------------------------------


def test_table_has_one_row_per_group():
    result = _make_result(
        groups=(_make_group("A"), _make_group("B"), _make_group("C")), pairwise=None, multi_group=_MULTI_GROUP
    )

    view = GroupComparisonView(result)

    table = _find_table(view)
    assert table.rowCount() == 3
    assert table.item(0, 0).text() == "A"
    assert table.item(2, 0).text() == "C"


def test_table_marks_a_group_as_not_normal_below_the_significance_level():
    result = _make_result(groups=(_make_group("A", shapiro_p_value=0.9), _make_group("B", shapiro_p_value=0.001)))

    view = GroupComparisonView(result)

    table = _find_table(view)
    normal_column = table.columnCount() - 1
    assert table.item(0, normal_column).text() == "Yes"
    assert table.item(1, normal_column).text() == "No"


def test_table_shows_not_available_when_shapiro_could_not_be_computed():
    result = _make_result(groups=(_make_group("A", shapiro_statistic=float("nan"), shapiro_p_value=float("nan")),))

    view = GroupComparisonView(result)

    table = _find_table(view)
    assert table.item(0, table.columnCount() - 1).text() == "N/A"


# ----------------------------------------------------------------------
# Test results text
# ----------------------------------------------------------------------


def test_pairwise_result_shows_t_test_and_mann_whitney_sections():
    view = GroupComparisonView(_make_result(pairwise=_PAIRWISE, multi_group=None))

    text = " ".join(label.text() for label in _find_labels(view))
    assert "Welch" in text
    assert "Mann-Whitney" in text
    assert "Cohen" in text
    assert "rank-biserial" in text.lower()


def test_multi_group_result_shows_anova_and_kruskal_wallis_sections():
    view = GroupComparisonView(_make_result(pairwise=None, multi_group=_MULTI_GROUP))

    text = " ".join(label.text() for label in _find_labels(view))
    assert "ANOVA" in text
    assert "Kruskal-Wallis" in text
    assert "Eta" in text
    assert "Epsilon" in text


def test_non_normal_group_shows_non_parametric_guidance():
    result = _make_result(
        groups=(_make_group("A", shapiro_p_value=0.001), _make_group("B", shapiro_p_value=0.9)),
        pairwise=_PAIRWISE,
    )

    view = GroupComparisonView(result)

    text = " ".join(label.text() for label in _find_labels(view))
    assert "non-parametric" in text


def test_all_normal_groups_show_parametric_guidance():
    result = _make_result(
        groups=(_make_group("A", shapiro_p_value=0.9), _make_group("B", shapiro_p_value=0.8)),
        pairwise=_PAIRWISE,
    )

    view = GroupComparisonView(result)

    text = " ".join(label.text() for label in _find_labels(view))
    assert "both results" in text


# ----------------------------------------------------------------------
# Warnings
# ----------------------------------------------------------------------


def test_no_warnings_means_no_warnings_label():
    view = GroupComparisonView(_make_result(warnings=()))

    text = " ".join(label.text() for label in _find_labels(view))
    assert "could not be computed" not in text
    assert "could not be tested" not in text


def test_warnings_are_shown_when_present():
    result = _make_result(
        warnings=(
            GroupComparisonWarning("A", GroupWarningReason.TOO_FEW_FOR_VARIANCE),
            GroupComparisonWarning("B", GroupWarningReason.TOO_FEW_FOR_NORMALITY),
        )
    )

    view = GroupComparisonView(result)

    text = " ".join(label.text() for label in _find_labels(view))
    assert "'A'" in text
    assert "'B'" in text
    assert "could not be computed" in text
    assert "could not be tested" in text
