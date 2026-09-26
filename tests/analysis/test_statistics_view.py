from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QTableWidget

from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.statistics import (
    ColumnDescriptiveStatistics,
    DescriptiveStatisticsResult,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_pct


def _make_column_stats(**overrides: object) -> ColumnDescriptiveStatistics:
    defaults: dict[str, object] = {
        "column": "salary",
        "count": 100,
        "missing_count": 5,
        "missing_fraction": 0.05,
        "mean": 50000.0,
        "median": 48000.0,
        "std": 12000.0,
        "variance": 144000000.0,
        "minimum": 20000.0,
        "maximum": 90000.0,
        "range": 70000.0,
        "q1": 40000.0,
        "q3": 60000.0,
        "iqr": 20000.0,
        "skewness": 0.3,
        "kurtosis": -0.5,
    }
    defaults.update(overrides)
    return ColumnDescriptiveStatistics(**defaults)  # type: ignore[arg-type]


def test_shows_empty_message_when_no_numeric_columns():
    result = DescriptiveStatisticsResult(columns=())
    view = StatisticsView(result)

    label = view.findChild(QLabel)
    assert label is not None
    assert "No numeric columns" in label.text()
    assert view.findChild(QTableWidget) is None


def test_builds_one_table_row_per_numeric_column():
    result = DescriptiveStatisticsResult(columns=(_make_column_stats(column="a"), _make_column_stats(column="b")))
    view = StatisticsView(result)

    table = view.findChild(QTableWidget)
    assert table is not None
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "a"
    assert table.item(1, 0).text() == "b"


def test_table_cells_use_format_utils_for_every_statistic():
    stats = _make_column_stats()
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    table = view.findChild(QTableWidget)
    assert table is not None
    row_texts = [table.item(0, col).text() for col in range(table.columnCount())]

    assert row_texts == [
        stats.column,
        fmt_int(stats.count),
        fmt_pct(stats.missing_fraction),
        fmt_num(stats.mean),
        fmt_num(stats.median),
        fmt_num(stats.std),
        fmt_num(stats.variance),
        fmt_num(stats.minimum),
        fmt_num(stats.maximum),
        fmt_num(stats.range),
        fmt_num(stats.q1),
        fmt_num(stats.q3),
        fmt_num(stats.iqr),
        fmt_num(stats.skewness),
        fmt_num(stats.kurtosis),
    ]


def test_nan_statistics_render_as_empty_string():
    stats = _make_column_stats(mean=float("nan"), std=float("nan"))
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    table = view.findChild(QTableWidget)
    assert table is not None
    assert table.item(0, 3).text() == ""  # Mean column
    assert table.item(0, 5).text() == ""  # Std Dev column
