from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QTableWidget

from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.normality import SHAPIRO_LARGE_SAMPLE_THRESHOLD
from expo_jbm329.services.analysis.statistics import (
    ColumnDescriptiveStatistics,
    DescriptiveStatisticsResult,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value, fmt_pct


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
        "histogram_bins": (20000.0, 40000.0, 60000.0, 80000.0, 90000.0),
        "histogram_counts": (20, 30, 30, 20),
        "shapiro_statistic": 0.98,
        "shapiro_p_value": 0.42,
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


def test_shows_first_columns_distribution_by_default():
    result = DescriptiveStatisticsResult(columns=(_make_column_stats(column="a"), _make_column_stats(column="b")))
    view = StatisticsView(result)

    assert len(view._figure.axes) == 2  # noqa: SLF001


def test_show_distribution_for_switches_to_a_different_column():
    result = DescriptiveStatisticsResult(columns=(_make_column_stats(column="a"), _make_column_stats(column="b")))
    view = StatisticsView(result)

    view.show_distribution_for("b")

    assert len(view._figure.axes) == 2  # noqa: SLF001


def test_show_distribution_for_unknown_column_is_a_no_op():
    result = DescriptiveStatisticsResult(columns=(_make_column_stats(column="a"),))
    view = StatisticsView(result)

    view.show_distribution_for("does-not-exist")  # must not raise


def test_shows_no_data_message_when_histogram_and_boxplot_data_are_missing():
    stats = _make_column_stats(
        median=float("nan"),
        q1=float("nan"),
        q3=float("nan"),
        minimum=float("nan"),
        maximum=float("nan"),
        histogram_bins=(),
        histogram_counts=(),
    )
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    all_texts = [t.get_text() for ax in view._figure.axes for t in ax.texts]  # noqa: SLF001
    assert all_texts.count("No data") == 2


def test_normality_label_shows_the_shapiro_statistic_and_p_value():
    stats = _make_column_stats(shapiro_statistic=0.9876, shapiro_p_value=0.4213)
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    text = view._normality_label.text()  # noqa: SLF001
    assert fmt_num(0.9876) in text
    assert fmt_p_value(0.4213) in text


def test_normality_label_flags_significant_result():
    stats = _make_column_stats(shapiro_p_value=0.001)
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    text = view._normality_label.text()  # noqa: SLF001
    assert "Significant evidence" in text
    assert "No significant evidence" not in text


def test_normality_label_shows_no_significant_result():
    stats = _make_column_stats(shapiro_p_value=0.8)
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    text = view._normality_label.text()  # noqa: SLF001
    assert "No significant evidence" in text


def test_normality_label_shows_large_sample_caveat_above_threshold():
    stats = _make_column_stats(count=SHAPIRO_LARGE_SAMPLE_THRESHOLD + 1)
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    text = view._normality_label.text()  # noqa: SLF001
    assert "may not be accurate" in text


def test_normality_label_omits_large_sample_caveat_at_or_below_threshold():
    stats = _make_column_stats(count=SHAPIRO_LARGE_SAMPLE_THRESHOLD)
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    text = view._normality_label.text()  # noqa: SLF001
    assert "may not be accurate" not in text


def test_normality_label_shows_not_enough_data_when_shapiro_is_nan():
    stats = _make_column_stats(shapiro_statistic=float("nan"), shapiro_p_value=float("nan"))
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    text = view._normality_label.text()  # noqa: SLF001
    assert "Not enough data" in text


def test_normality_label_updates_when_switching_columns():
    result = DescriptiveStatisticsResult(
        columns=(
            _make_column_stats(column="a", shapiro_p_value=0.9),
            _make_column_stats(column="b", shapiro_p_value=0.001),
        )
    )
    view = StatisticsView(result)
    assert "No significant evidence" in view._normality_label.text()  # noqa: SLF001

    view.show_distribution_for("b")

    assert "Significant evidence" in view._normality_label.text()  # noqa: SLF001
