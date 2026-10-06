from __future__ import annotations

from dataclasses import replace

from expo_jbm329.gui.dialogs.analysis.statistics_config import StatisticsConfigWidget
from expo_jbm329.services.analysis.statistics import (
    ColumnDescriptiveStatistics,
    DescriptiveStatisticsResult,
    DescriptiveSummaryMethod,
)


def _make_stats(column: str) -> ColumnDescriptiveStatistics:
    return ColumnDescriptiveStatistics(
        column=column,
        count=10,
        missing_count=0,
        missing_fraction=0.0,
        mean=1.0,
        median=1.0,
        std=1.0,
        variance=1.0,
        minimum=0.0,
        maximum=2.0,
        range=2.0,
        q1=0.5,
        q3=1.5,
        iqr=1.0,
        skewness=0.0,
        kurtosis=0.0,
        histogram_bins=(0.0, 1.0, 2.0),
        histogram_counts=(5, 5),
        shapiro_statistic=0.98,
        shapiro_p_value=0.42,
    )


def test_populates_combo_with_every_column_in_order():
    result = DescriptiveStatisticsResult(columns=(_make_stats("a"), _make_stats("b"), _make_stats("c")))
    widget = StatisticsConfigWidget(result)

    assert [widget._column_combo.itemText(i) for i in range(widget._column_combo.count())] == [  # noqa: SLF001
        "a",
        "b",
        "c",
    ]


def test_defaults_to_the_first_column():
    result = DescriptiveStatisticsResult(columns=(_make_stats("a"), _make_stats("b")))
    widget = StatisticsConfigWidget(result)

    assert widget.selected_column() == "a"
    assert widget.selected_summary_method() is DescriptiveSummaryMethod.MEAN_SD


def test_summary_method_can_be_overridden_and_is_preserved_per_column():
    result = DescriptiveStatisticsResult(columns=(_make_stats("a"), _make_stats("b")))
    widget = StatisticsConfigWidget(result)
    received: list[tuple[str, str]] = []
    widget.summary_method_changed.connect(lambda column, method: received.append((column, method)))

    widget._summary_method_combo.setCurrentIndex(1)  # noqa: SLF001
    widget._column_combo.setCurrentIndex(1)  # noqa: SLF001
    assert widget.selected_summary_method() is DescriptiveSummaryMethod.MEAN_SD
    widget._summary_method_combo.setCurrentIndex(1)  # noqa: SLF001
    widget._column_combo.setCurrentIndex(0)  # noqa: SLF001

    assert received == [
        ("a", DescriptiveSummaryMethod.MEDIAN_IQR.value),
        ("b", DescriptiveSummaryMethod.MEDIAN_IQR.value),
    ]
    assert widget.selected_summary_method() is DescriptiveSummaryMethod.MEDIAN_IQR
    assert widget.summary_method("b") is DescriptiveSummaryMethod.MEDIAN_IQR


def test_unavailable_shapiro_recommends_median_iqr():
    stats = replace(_make_stats("a"), shapiro_p_value=float("nan"))
    widget = StatisticsConfigWidget(DescriptiveStatisticsResult(columns=(stats,)))

    assert widget.selected_summary_method() is DescriptiveSummaryMethod.MEDIAN_IQR
    assert "could not provide a recommendation" in widget._recommendation_label.text()  # noqa: SLF001


def test_changing_the_combo_emits_column_changed():
    result = DescriptiveStatisticsResult(columns=(_make_stats("a"), _make_stats("b")))
    widget = StatisticsConfigWidget(result)
    received: list[str] = []
    widget.column_changed.connect(received.append)

    widget._column_combo.setCurrentIndex(1)  # noqa: SLF001

    assert received == ["b"]
    assert widget.selected_column() == "b"


def test_empty_result_leaves_no_selection():
    result = DescriptiveStatisticsResult(columns=())
    widget = StatisticsConfigWidget(result)

    assert widget.selected_column() is None


def test_set_selected_column_updates_selection_without_emitting_change():
    result = DescriptiveStatisticsResult(columns=(_make_stats("a"), _make_stats("b")))
    widget = StatisticsConfigWidget(result)
    changed_columns: list[str] = []
    widget.column_changed.connect(changed_columns.append)

    widget.set_selected_column("b")

    assert widget.selected_column() == "b"
    assert changed_columns == []


def test_set_selected_column_ignores_unknown_column():
    result = DescriptiveStatisticsResult(columns=(_make_stats("a"),))
    widget = StatisticsConfigWidget(result)

    widget.set_selected_column("unknown")

    assert widget.selected_column() == "a"
