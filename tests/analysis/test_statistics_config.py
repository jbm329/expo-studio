from __future__ import annotations

from expo_jbm329.gui.dialogs.analysis.statistics_config import StatisticsConfigWidget
from expo_jbm329.services.analysis.statistics import (
    ColumnDescriptiveStatistics,
    DescriptiveStatisticsResult,
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
