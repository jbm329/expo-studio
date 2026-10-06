from __future__ import annotations

from PyQt6.QtWidgets import QLabel

from expo_jbm329.gui.dialogs.analysis.paired_comparison_view import PairedComparisonView
from expo_jbm329.services.analysis.paired_comparison import (
    PairedComparisonError,
    PairedComparisonMethod,
    PairedComparisonResult,
)
from expo_jbm329.utils.format_utils import fmt_num


def _result(**overrides: object) -> PairedComparisonResult:
    values: dict[str, object] = {
        "columns": ("before", "after"),
        "available_numeric_columns": ("before", "after", "followup"),
        "method": PairedComparisonMethod.WILCOXON,
        "total_subjects": 10,
        "complete_subjects": 8,
        "excluded_subjects": 2,
        "statistic": 2.5,
        "p_value": 0.031,
        "kendall_w": float("nan"),
        "error": None,
    }
    values.update(overrides)
    return PairedComparisonResult(**values)  # type: ignore[arg-type]


def test_displays_wilcoxon_result_and_complete_subject_counts():
    view = PairedComparisonView(_result())
    text = "\n".join(label.text() for label in view.findChildren(QLabel))

    assert "Wilcoxon signed-rank test" in text
    assert "Measurement columns: before, after" in text
    assert "Complete subjects: 8 of 10; excluded for missing values: 2" in text
    assert "paired subjects" in text


def test_displays_friedman_test_and_kendalls_w():
    view = PairedComparisonView(
        _result(
            columns=("before", "after", "followup"),
            method=PairedComparisonMethod.FRIEDMAN,
            kendall_w=0.42,
        )
    )
    text = "\n".join(label.text() for label in view.findChildren(QLabel))

    assert "Friedman test" in text
    assert f"Kendall's W: {fmt_num(0.42)}" in text


def test_displays_structured_analysis_errors():
    view = PairedComparisonView(
        _result(
            method=PairedComparisonMethod.WILCOXON,
            error=PairedComparisonError.NO_DIFFERENCES,
        )
    )
    text = "\n".join(label.text() for label in view.findChildren(QLabel))

    assert "Wilcoxon test is undefined" in text
