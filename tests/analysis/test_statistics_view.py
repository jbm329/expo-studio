from __future__ import annotations

from contextlib import contextmanager
from threading import Event, Thread

import pandas as pd
import pytest
from matplotlib.backends.backend_qt import FigureCanvasQT
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6 import sip
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPaintEvent, QResizeEvent
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget, QTabWidget

from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.normality import SHAPIRO_LARGE_SAMPLE_THRESHOLD
from expo_jbm329.services.analysis.statistics import (
    CategoricalColumnStatistics,
    CategoryFrequency,
    ColumnDescriptiveStatistics,
    DescriptiveStatisticsResult,
    analyze_descriptive_statistics,
)
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
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


def test_layout_has_titled_table_chart_and_text_sections_with_adjustable_dividers():
    view = StatisticsView(DescriptiveStatisticsResult(columns=(_make_column_stats(),)))

    splitters = view.findChildren(QSplitter)
    assert len(splitters) == 1
    splitter = splitters[0]
    assert splitter.orientation() is Qt.Orientation.Vertical
    assert splitter.childrenCollapsible() is False
    assert splitter.count() == 3

    table = view.findChild(QTableWidget)
    assert table is not None
    assert splitter.widget(0).isAncestorOf(table)
    assert any(label.text() == "Descriptive statistics" for label in splitter.widget(0).findChildren(QLabel))

    canvases = splitter.widget(1).findChildren(FigureCanvasQTAgg)
    assert len(canvases) == 1
    assert any(label.text() == "Distribution" for label in splitter.widget(1).findChildren(QLabel))

    assert splitter.widget(2).isAncestorOf(view._normality_label)  # noqa: SLF001


def test_statistics_tabs_have_extra_horizontal_padding_for_selected_text():
    view = StatisticsView(
        DescriptiveStatisticsResult(
            columns=(_make_column_stats(),),
            categorical_columns=(
                CategoricalColumnStatistics(
                    column="group",
                    count=1,
                    missing_count=0,
                    missing_fraction=0.0,
                    frequencies=(CategoryFrequency(value="A", count=1, fraction=1.0),),
                ),
            ),
        )
    )
    tabs = view.findChild(QTabWidget)

    assert tabs is not None
    style = tabs.styleSheet()
    assert "border-bottom-color: palette(highlight)" in style
    assert "border: none" in style
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        text_width = tabs.tabBar().fontMetrics().horizontalAdvance(tabs.tabText(index))
        assert tabs.tabBar().tabRect(index).width() >= text_width + 12


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
        f"{fmt_num(stats.mean)} ± {fmt_num(stats.std)} *",
        f"{fmt_num(stats.median)} ({fmt_num(stats.q1)} to {fmt_num(stats.q3)})",
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


@pytest.mark.parametrize("signal_name", ["cellClicked", "cellActivated"])
def test_selecting_a_statistics_row_displays_that_column(signal_name):
    result = DescriptiveStatisticsResult(columns=(_make_column_stats(column="a"), _make_column_stats(column="b")))
    view = StatisticsView(result)
    table = view.findChild(QTableWidget)

    assert table is not None
    getattr(table, signal_name).emit(1, 3)

    assert table.currentRow() == 1
    assert view._figure._suptitle is not None  # noqa: SLF001
    assert view._figure._suptitle.get_text() == "b"  # noqa: SLF001


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


def test_categorical_table_shows_counts_percentages_and_missing_separately():
    result = DescriptiveStatisticsResult(
        columns=(),
        categorical_columns=(
            CategoricalColumnStatistics(
                column="sex",
                count=3,
                missing_count=1,
                missing_fraction=0.25,
                frequencies=(
                    CategoryFrequency(value="F", count=2, fraction=2 / 3),
                    CategoryFrequency(value="M", count=1, fraction=1 / 3),
                ),
            ),
        ),
    )
    view = StatisticsView(result)
    table = view.findChild(QTableWidget)

    assert table is not None
    assert table.horizontalHeaderItem(3).text() == "Percent (non-missing)"
    assert table.item(0, 0).text() == "sex"
    assert table.item(0, 1).text() == "F"
    assert table.item(0, 2).text() == fmt_int(2)
    assert table.item(0, 3).text() == fmt_pct(2 / 3)
    assert table.item(0, 4).text() == fmt_int(1)
    assert table.item(1, 4).text() == ""


@pytest.mark.parametrize(("p_value", "star_column"), [(0.8, 15), (0.05, 15), (0.049, 16), (float("nan"), None)])
def test_both_summaries_are_present_and_only_the_suggested_summary_is_starred(p_value, star_column):
    stats = _make_column_stats(shapiro_p_value=p_value)
    view = StatisticsView(DescriptiveStatisticsResult(columns=(stats,)))
    table = view.findChild(QTableWidget)
    assert table is not None

    assert table.columnCount() == 17
    assert table.horizontalHeaderItem(15).text() == "Mean ± SD"
    assert table.horizontalHeaderItem(16).text() == "Median (Q1 to Q3)"
    for column in (15, 16):
        assert table.item(0, column).text().endswith(" *") == (column == star_column)


def test_legend_and_selected_column_guidance_are_below_the_continuous_table():
    result = DescriptiveStatisticsResult(
        columns=(
            _make_column_stats(column="<a>", shapiro_p_value=0.8),
            _make_column_stats(column="b", shapiro_p_value=0.001),
        )
    )
    view = StatisticsView(result)
    tabs = view.findChild(QTabWidget)
    page = tabs.widget(0)
    layout = page.layout()
    assert isinstance(layout.itemAt(0).widget(), QTableWidget)
    assert "* marks" in layout.itemAt(1).widget().text()
    recommendation = layout.itemAt(2).widget()
    assert recommendation.textFormat() is Qt.TextFormat.PlainText
    assert "<a>: Shapiro-Wilk suggests Mean ± SD" in recommendation.text()
    view.show_distribution_for("b")
    assert "b: Shapiro-Wilk suggests Median (Q1 to Q3)" in recommendation.text()
    assert "guide, not proof" in recommendation.text()
    table = view.findChild(QTableWidget)
    assert table.item(0, 15).text().endswith("*")
    assert table.item(1, 16).text().endswith("*")


@pytest.mark.parametrize("values", [[1.0, 2.0], [1.0, 1.0, 1.0], [float("nan")] * 3])
def test_unavailable_normality_never_stars_the_fallback_summary(values):
    result = analyze_descriptive_statistics(pd.DataFrame({"a": values}))
    view = StatisticsView(result)
    table = next(table for table in view.findChildren(QTableWidget) if table.columnCount() == 17)
    assert table is not None
    assert "*" not in table.item(0, 15).text()
    assert "*" not in table.item(0, 16).text()
    assert "could not provide a recommendation" in view._recommendation_label.text()  # noqa: SLF001


def test_undefined_mean_sd_summary_remains_blank_without_a_star():
    view = StatisticsView(DescriptiveStatisticsResult(columns=(_make_column_stats(std=float("nan")),)))
    table = view.findChild(QTableWidget)
    assert table.item(0, 15).text() == ""


def test_recommendation_repeats_large_sample_caveat():
    view = StatisticsView(
        DescriptiveStatisticsResult(columns=(_make_column_stats(count=SHAPIRO_LARGE_SAMPLE_THRESHOLD + 1),))
    )
    assert "may not be accurate" in view._recommendation_label.text()  # noqa: SLF001


def test_normality_label_shows_the_shapiro_statistic_and_p_value():
    stats = _make_column_stats(shapiro_statistic=0.9876, shapiro_p_value=0.4213)
    result = DescriptiveStatisticsResult(columns=(stats,))
    view = StatisticsView(result)

    text = view._normality_label.text()  # noqa: SLF001
    assert fmt_num(0.9876) in text
    assert fmt_p_value(0.4213) in text
    assert "<br>" in text
    assert "\n" not in text


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


@contextmanager
def _worker_holds_chart_lock():
    """Use events, not timing, to simulate a worker inside Matplotlib."""
    acquired = Event()
    release = Event()
    timed_out = Event()

    def worker():
        with STATISTICS_CHART_LOCK:
            acquired.set()
            if not release.wait(10):
                timed_out.set()

    thread = Thread(target=worker)
    thread.start()
    assert acquired.wait(10)
    try:
        yield
    finally:
        release.set()
        thread.join(10)
        assert not thread.is_alive()
        assert not timed_out.is_set(), "GUI waited for the worker's chart lock"


def test_shared_canvas_chart_builder_defers_without_blocking_and_keeps_latest_builder():
    from matplotlib.figure import Figure

    from expo_jbm329.gui.dialogs.analysis.statistics_view import SerializedAnalysisCanvas

    figure = Figure()
    canvas = SerializedAnalysisCanvas(figure)
    calls = []
    with _worker_holds_chart_lock():
        canvas.build_chart(lambda: calls.append("old"))
        canvas.build_chart(lambda: calls.append(STATISTICS_CHART_LOCK._is_owned()))
        assert not calls
    canvas._retry_render()
    assert calls == [True]
    canvas._retry_render()
    assert calls == [True]


def test_distribution_creation_defers_without_blocking_and_keeps_latest_selection(qt_app):
    result = DescriptiveStatisticsResult(columns=(_make_column_stats(column="a"), _make_column_stats(column="b")))
    with _worker_holds_chart_lock():
        view = StatisticsView(result)
        view.show_distribution_for("b")
        qt_app.processEvents()
        assert view._figure is None
        assert view._canvas is None
        assert view._distribution_timer.isActive()
        assert "b:" in view._recommendation_label.text()
        view._distribution_timer.timeout.emit()
        assert view._figure is None

    view._distribution_timer.timeout.emit()
    assert view._figure._suptitle.get_text() == "b"
    assert not view._distribution_timer.isActive()
    sip.delete(view)


def test_distribution_mutation_defers_and_coalesces_until_worker_finishes(qt_app):
    view = StatisticsView(
        DescriptiveStatisticsResult(
            columns=(_make_column_stats(column="a"), _make_column_stats(column="b"), _make_column_stats(column="c"))
        )
    )
    figure = view._figure
    axes = tuple(figure.axes)
    with _worker_holds_chart_lock():
        view.show_distribution_for("b")
        view.show_distribution_for("c")
        qt_app.processEvents()
        assert tuple(figure.axes) == axes
        assert figure._suptitle.get_text() == "a"
        assert view._canvas._draw_pending

    view._distribution_timer.timeout.emit()
    assert view._figure is figure
    assert figure._suptitle.get_text() == "c"
    sip.delete(view)


def test_actual_deferred_qt_draw_holds_lock_and_retries_nonblocking(qt_app, monkeypatch):
    view = StatisticsView(DescriptiveStatisticsResult(columns=(_make_column_stats(),)))
    canvas = view._canvas
    draws: list[bool] = []
    monkeypatch.setattr(FigureCanvasQTAgg, "draw", lambda self: draws.append(STATISTICS_CHART_LOCK._is_owned()))
    with _worker_holds_chart_lock():
        canvas.draw_idle()
        qt_app.processEvents()
        canvas.draw()
        canvas._retry_timer.timeout.emit()
        assert draws == []
        assert canvas._draw_pending
        assert canvas._retry_timer.isActive()

    canvas._retry_timer.timeout.emit()
    assert draws == [True]
    assert not canvas._draw_pending
    sip.delete(view)


def test_qt_resize_paint_and_dpi_changes_defer_and_hold_lock(monkeypatch):
    view = StatisticsView(DescriptiveStatisticsResult(columns=(_make_column_stats(),)))
    canvas = view._canvas
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        FigureCanvasQTAgg,
        "resizeEvent",
        lambda self, event: calls.append(("resize", STATISTICS_CHART_LOCK._is_owned())),
    )
    monkeypatch.setattr(
        FigureCanvasQTAgg,
        "paintEvent",
        lambda self, event: calls.append(("paint", STATISTICS_CHART_LOCK._is_owned())),
    )
    monkeypatch.setattr(
        FigureCanvasQT,
        "_update_pixel_ratio",
        lambda self: calls.append(("dpi", STATISTICS_CHART_LOCK._is_owned())),
    )
    with _worker_holds_chart_lock():
        canvas.resizeEvent(QResizeEvent(QSize(800, 400), canvas.size()))
        canvas.paintEvent(QPaintEvent(canvas.rect()))
        canvas._update_pixel_ratio()
        assert calls == []
        assert canvas._resize_pending
        assert canvas._pixel_ratio_pending

    canvas._retry_timer.timeout.emit()
    canvas.paintEvent(QPaintEvent(canvas.rect()))
    assert calls == [("dpi", True), ("resize", True), ("paint", True)]
    sip.delete(view)


@pytest.mark.parametrize("canvas_created", [False, True])
def test_chart_retries_are_destroyed_with_their_qt_owner(qt_app, canvas_created):
    result = DescriptiveStatisticsResult(columns=(_make_column_stats(),))
    view = StatisticsView(result) if canvas_created else None
    with _worker_holds_chart_lock():
        if view is None:
            view = StatisticsView(result)
        view.show_distribution_for("salary")
        timers = [view._distribution_timer]
        if view._canvas is not None:
            view._canvas.draw()
            timers.append(view._canvas._retry_timer)
        assert all(timer.isActive() for timer in timers)
        sip.delete(view)
        assert all(sip.isdeleted(timer) for timer in timers)
    qt_app.processEvents()
