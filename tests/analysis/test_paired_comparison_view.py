from __future__ import annotations

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.paired_comparison_view import PairedComparisonView
from expo_jbm329.services.analysis.paired_comparison import (
    PairedComparisonError,
    PairedComparisonMethod,
    PairedComparisonResult,
    analyze_paired_comparison,
    initialize_paired_comparison,
)
from expo_jbm329.utils.format_utils import fmt_num


def _result(**overrides: object) -> PairedComparisonResult:
    columns = overrides.get("columns", ("before", "after"))
    assert isinstance(columns, tuple)
    computed = analyze_paired_comparison(
        pd.DataFrame({column: [1.0 + index, 2.0 + index, 3.0 + index] for index, column in enumerate(columns)}),
        columns,
    )
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
        "summaries": computed.summaries,
        "plot_data": computed.plot_data,
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
    assert view.findChild(QTableWidget) is None
    assert view.findChild(FigureCanvasQTAgg) is None


@pytest.mark.parametrize("columns", [("after", "before"), ("followup", "before", "after")])
def test_table_charts_and_comments_follow_hypothesis_test_layout(columns: tuple[str, ...]):
    df = pd.DataFrame({
        "before": [1.0, 2.0, 3.0, 4.0],
        "after": [2.0, 4.0, 5.0, 7.0],
        "followup": [3.0, 5.0, 6.0, 8.0],
    })
    result = analyze_paired_comparison(df, columns)
    view = PairedComparisonView(result)
    view.resize(950, 800)
    view.show()
    QCoreApplication.processEvents()
    try:
        splitter = view.findChild(QSplitter)
        assert splitter is not None
        assert splitter.orientation() is Qt.Orientation.Vertical
        assert splitter.count() == 3
        assert not splitter.childrenCollapsible()
        table = splitter.widget(0).findChild(QTableWidget)
        assert table is not None
        assert table.rowCount() == len(columns)
        assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
        assert table.editTriggers() is QTableWidget.EditTrigger.NoEditTriggers
        assert [table.item(row, 0).text() for row in range(len(columns))] == list(columns)
        assert table.item(0, 2).text() == fmt_num(result.summaries[0].mean)
        assert table.item(0, 5).text() == fmt_num(result.summaries[0].q1)
        assert table.item(0, 6).text() == fmt_num(result.summaries[0].q3)

        canvas = splitter.widget(1).findChild(FigureCanvasQTAgg)
        assert canvas is not None
        canvas.draw()
        distribution, trajectories = canvas.figure.axes
        for line, summary in zip(distribution.lines[5::6], result.summaries, strict=True):
            assert list(line.get_ydata()) == [summary.median, summary.median]
        assert [tick.get_text() for tick in distribution.get_xticklabels()] == list(columns)
        assert [tick.get_text() for tick in trajectories.get_xticklabels()] == list(columns)
        assert result.plot_data is not None
        assert len(trajectories.lines) == result.complete_subjects
        for line, values in zip(trajectories.lines, result.plot_data.trajectories, strict=True):
            assert list(line.get_ydata()) == list(values)
        comments = "\n".join(label.text() for label in splitter.widget(2).findChildren(QLabel))
        assert "chronological order is not inferred" in comments
        assert "whiskers show the minimum and maximum" in comments
        assert "deterministic sample" not in comments
    finally:
        view.close()


def test_sampled_trajectory_notice_preserves_full_cohort_counts():
    df = pd.DataFrame({"a": range(250), "b": range(1, 251)})
    view = PairedComparisonView(analyze_paired_comparison(df, ("a", "b")))
    text = "\n".join(label.text() for label in view.findChildren(QLabel))
    assert "sample of 200 of 250 complete subjects" in text
    assert "Tables, boxplots and tests use all complete subjects" in text
    table = view.findChild(QTableWidget)
    assert table is not None
    assert table.item(0, 1).text() == "250"
    canvas = view.findChild(FigureCanvasQTAgg)
    assert canvas is not None
    assert len(canvas.figure.axes[1].lines) == 200


def test_unfitted_result_shows_apply_prompt_without_charts():
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 3.0]})
    view = PairedComparisonView(initialize_paired_comparison(df))
    assert "click Apply" in view.findChild(QLabel).text()
    assert view.findChild(QTableWidget) is None
    assert view.findChild(FigureCanvasQTAgg) is None


def test_rich_text_comments_escape_measurement_names():
    view = PairedComparisonView(_result(columns=("<b>before</b>", "after & followup")))
    text = "\n".join(label.text() for label in view.findChildren(QLabel))
    assert "&lt;b&gt;before&lt;/b&gt;, after &amp; followup" in text


def test_single_subject_and_constant_occasion_charts_render_without_warnings():
    view = PairedComparisonView(analyze_paired_comparison(pd.DataFrame({"a": [1.0], "b": [2.0]}), ("a", "b")))
    view.resize(950, 800)
    view.show()
    QCoreApplication.processEvents()
    try:
        canvas = view.findChild(FigureCanvasQTAgg)
        assert canvas is not None
        canvas.draw()
        assert len(canvas.figure.axes[1].lines) == 1
    finally:
        view.close()
