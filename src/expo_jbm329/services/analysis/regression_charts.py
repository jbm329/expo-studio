"""Qt-free construction of the displayed regression charts and Excel images."""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from itertools import chain
from typing import TYPE_CHECKING

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator
from matplotlib.transforms import Bbox

from expo_jbm329.services.analysis.logistic_charts import LogisticChartLabels, build_logistic_charts
from expo_jbm329.services.analysis.regression import RegressionResult, TermKind
from expo_jbm329.services.analysis.regression_glm import GeneralizedRegressionResult, RegressionModel
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.analysis.survival import SurvivalResult, survival_term_name
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.regression import RegressionPlotData
    from expo_jbm329.services.analysis.regression_export import RegressionExportSnapshot
    from expo_jbm329.services.analysis.regression_glm import CountRegressionPlotData
    from expo_jbm329.services.analysis.survival import SurvivalPlotData, SurvivalTerm

SCATTER_POINT_SIZE = 6
SCATTER_ALPHA = 0.4
COUNT_POINT_SIZE = 12
COUNT_ALPHA = 0.35
_FOREST_TICK_COUNT = 5
_EXPORT_DPI = 120


def _format_number(value: float) -> str:
    """Fallback number formatting for callers without a locale-aware formatter."""
    return f"{value:.3g}"


def _format_count(value: int) -> str:
    """Fallback count formatting for callers without a locale-aware formatter."""
    return str(value)


@dataclass(frozen=True, slots=True)
class LinearChartLabels:
    """Translated linear-regression chart text captured on the GUI thread."""

    residuals_title: str
    fitted_axis: str
    residual_axis: str
    actual_title: str
    predicted_axis: str
    actual_axis: str
    qq_title: str
    theoretical_axis: str
    standardized_axis: str


@dataclass(frozen=True, slots=True)
class CountChartLabels:
    """Translated count-regression chart text captured on the GUI thread."""

    comparison_title: str
    fitted_axis: str
    observed_axis: str
    residuals_title: str
    pearson_axis: str


@dataclass(frozen=True, slots=True)
class CoxChartLabels:
    """Translated Cox chart text and locale-aware formatters captured on the GUI thread."""

    forest_title: str
    forest_unavailable: str
    hazard_axis: str
    survival_title: str
    survival_unavailable: str
    duration_axis: str
    survival_axis: str
    risk_title: str
    tick_format: Callable[[float], str] = _format_number
    time_format: Callable[[float], str] = _format_number
    count_format: Callable[[int], str] = _format_count


ModelChartLabels = LinearChartLabels | CountChartLabels | CoxChartLabels | LogisticChartLabels


@dataclass(frozen=True, slots=True)
class RegressionChartLabels:
    """Everything needed to export the displayed charts of one fitted model.

    Attributes:
        heading: Workbook heading above the chart image.
        model: Model-specific translated chart text.
        captions: Notes shown below the image, such as sampling caveats.
    """

    heading: str
    model: ModelChartLabels
    captions: tuple[str, ...] = ()


# ----------------------------------------------------------------------
# Linear regression
# ----------------------------------------------------------------------


def draw_residuals_vs_fitted(ax: Axes, plot: RegressionPlotData, labels: LinearChartLabels) -> None:
    """Draw residuals against fitted values with a zero reference line."""
    ax.scatter(plot.fitted, plot.residuals, s=SCATTER_POINT_SIZE, alpha=SCATTER_ALPHA)
    ax.axhline(0.0, color="tab:red")
    ax.set_title(labels.residuals_title)
    ax.set_xlabel(labels.fitted_axis)
    ax.set_ylabel(labels.residual_axis)


def draw_actual_vs_predicted(ax: Axes, plot: RegressionPlotData, labels: LinearChartLabels) -> None:
    """Draw observed against predicted values with the identity line."""
    ax.scatter(plot.fitted, plot.actual, s=SCATTER_POINT_SIZE, alpha=SCATTER_ALPHA)
    values = (*plot.fitted, *plot.actual)
    low, high = min(values), max(values)
    ax.plot([low, high], [low, high], color="tab:red")
    ax.set_title(labels.actual_title)
    ax.set_xlabel(labels.predicted_axis)
    ax.set_ylabel(labels.actual_axis)


def draw_normal_qq(ax: Axes, plot: RegressionPlotData, labels: LinearChartLabels) -> None:
    """Draw standardized residual quantiles against normal quantiles with the identity line."""
    ax.scatter(plot.qq_theoretical, plot.qq_sample, s=SCATTER_POINT_SIZE, alpha=SCATTER_ALPHA)
    low = min(plot.qq_theoretical[0], plot.qq_sample[0])
    high = max(plot.qq_theoretical[-1], plot.qq_sample[-1])
    ax.plot([low, high], [low, high], color="tab:red")
    ax.set_title(labels.qq_title)
    ax.set_xlabel(labels.theoretical_axis)
    ax.set_ylabel(labels.standardized_axis)


def draw_linear_charts(figure: Figure, plot: RegressionPlotData, labels: LinearChartLabels) -> None:
    """Draw the three linear diagnostics side by side, in the displayed order."""
    draw_residuals_vs_fitted(figure.add_subplot(131), plot, labels)
    draw_actual_vs_predicted(figure.add_subplot(132), plot, labels)
    draw_normal_qq(figure.add_subplot(133), plot, labels)


# ----------------------------------------------------------------------
# Count regression
# ----------------------------------------------------------------------


def draw_count_charts(figure: Figure, data: CountRegressionPlotData, labels: CountChartLabels) -> None:
    """Draw response-scale fit and variance-aware residual diagnostics side by side."""
    comparison = figure.add_subplot(121)
    residuals = figure.add_subplot(122)
    comparison.scatter(data.fitted, data.observed, alpha=COUNT_ALPHA, s=COUNT_POINT_SIZE)
    upper = max(chain(data.fitted, data.observed))
    comparison.plot([0, upper], [0, upper], linestyle="--", color="tab:red")
    comparison.set_title(labels.comparison_title)
    comparison.set_xlabel(labels.fitted_axis)
    comparison.set_ylabel(labels.observed_axis)
    residuals.scatter(data.fitted, data.pearson_residuals, alpha=COUNT_ALPHA, s=COUNT_POINT_SIZE)
    residuals.axhline(0, linestyle="--", color="tab:red")
    residuals.set_title(labels.residuals_title)
    residuals.set_xlabel(labels.fitted_axis)
    residuals.set_ylabel(labels.pearson_axis)


# ----------------------------------------------------------------------
# Cox regression
# ----------------------------------------------------------------------


def _valid_hazard_interval(term: SurvivalTerm) -> bool:
    """Return whether a term can be drawn on a logarithmic hazard-ratio axis."""
    values = (term.hazard_ratio, term.hazard_ratio_ci_low, term.hazard_ratio_ci_high)
    return (
        all(math.isfinite(value) and value > 0 for value in values)
        and term.hazard_ratio_ci_low <= term.hazard_ratio <= term.hazard_ratio_ci_high
    )


def draw_cox_forest(ax: Axes, terms: Sequence[SurvivalTerm], labels: CoxChartLabels) -> None:
    """Show every term or explicitly explain why a log-scale plot is unavailable."""
    ax.set_title(labels.forest_title)
    if not terms or not all(_valid_hazard_interval(term) for term in terms):
        ax.text(
            0.5,
            0.5,
            labels.forest_unavailable,
            transform=ax.transAxes,
            ha="center",
            va="center",
            wrap=True,
        )
        ax.set_axis_off()
        return
    ratios = [term.hazard_ratio for term in terms]
    positions = list(range(len(terms)))
    ax.set_xscale("log")
    lower = min(1.0, *(term.hazard_ratio_ci_low for term in terms))
    upper = max(1.0, *(term.hazard_ratio_ci_high for term in terms))
    if lower == upper:
        lower, upper = 0.5, 2.0
    # Fixed ticks avoid automatic log locators overflowing on extreme finite intervals.
    log_low, log_high = math.log(lower), math.log(upper)
    last_tick = _FOREST_TICK_COUNT - 1
    ticks = [math.exp(log_low + (log_high - log_low) * index / last_tick) for index in range(_FOREST_TICK_COUNT)]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FixedFormatter([labels.tick_format(value) for value in ticks]))
    ax.xaxis.set_minor_locator(NullLocator())
    lows = [term.hazard_ratio_ci_low for term in terms]
    highs = [term.hazard_ratio_ci_high for term in terms]
    # Draw endpoints directly; reconstructing them from xerr can lose tiny bounds.
    ax.hlines(positions, lows, highs, color="tab:blue")
    ax.plot(ratios, positions, linestyle="none", marker="o", color="tab:blue")
    ax.plot(lows, positions, linestyle="none", marker="|", color="tab:blue")
    ax.plot(highs, positions, linestyle="none", marker="|", color="tab:blue")
    ax.axvline(1.0, linestyle="--", color="tab:red")
    ax.set_xlim(lower, upper)
    ax.set_yticks(positions, [survival_term_name(term) for term in terms])
    ax.set_ylim(len(terms) - 0.5, -0.5)
    ax.set_xlabel(labels.hazard_axis)


def draw_cox_survival(ax: Axes, data: SurvivalPlotData | None, labels: CoxChartLabels) -> None:
    """Draw all unique follow-up times with censor marks."""
    ax.set_title(labels.survival_title)
    if data is None:
        ax.text(0.5, 0.5, labels.survival_unavailable, transform=ax.transAxes, ha="center", va="center")
        ax.set_axis_off()
        return
    ax.step(data.times, data.survival, where="post", color="tab:blue")
    censor_indices = [index for index, count in enumerate(data.censored) if count > 0]
    ax.plot(
        [data.times[index] for index in censor_indices],
        [data.survival[index] for index in censor_indices],
        linestyle="none",
        marker="+",
        color="tab:blue",
    )
    ax.set_ylim(0, 1.05)
    ax.set_xlim(0, data.times[-1])
    ax.set_xlabel(labels.duration_axis)
    ax.set_ylabel(labels.survival_axis)
    ax.set_xticks(data.risk_times)
    ax.tick_params(axis="x", labelrotation=30)


def draw_cox_risk_counts(ax: Axes, data: SurvivalPlotData | None, labels: CoxChartLabels) -> None:
    """Show uniformly spaced follow-up times and their exact risk counts."""
    ax.set_axis_off()
    if data is None:
        return
    ax.set_title(labels.risk_title, fontsize=9)
    table = ax.table(
        cellText=[[labels.count_format(count) for count in data.risk_counts]],
        colLabels=[labels.time_format(time) for time in data.risk_times],
        loc="center",
        bbox=Bbox.from_bounds(0, 0, 1, 1),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)


def draw_cox_charts(figure: Figure, result: SurvivalResult, labels: CoxChartLabels) -> None:
    """Draw the forest plot beside unadjusted survival and its risk table."""
    grid = figure.add_gridspec(2, 2, height_ratios=[5, 1])
    draw_cox_forest(figure.add_subplot(grid[:, 0]), result.terms, labels)
    draw_cox_survival(figure.add_subplot(grid[0, 1]), result.plot_data, labels)
    draw_cox_risk_counts(figure.add_subplot(grid[1, 1]), result.plot_data, labels)


# ----------------------------------------------------------------------
# Export rendering
# ----------------------------------------------------------------------


def _figure_size(result: RegressionResult | GeneralizedRegressionResult | SurvivalResult) -> tuple[float, float]:
    """Return a readable export size in inches for the model's chart layout."""
    match result:
        case RegressionResult():
            return 13.5, 4.5
        case SurvivalResult():
            return 12.0, 6.0
        case GeneralizedRegressionResult() if result.model is RegressionModel.LOGISTIC:
            predictor_count = sum(term.kind is not TermKind.INTERCEPT for term in result.terms)
            return 10.0, max(7.5, 5.0 + predictor_count * 0.24)
        case GeneralizedRegressionResult():
            return 11.0, 4.75


def _draw_model_charts(
    figure: Figure,
    result: RegressionResult | GeneralizedRegressionResult | SurvivalResult,
    labels: ModelChartLabels,
) -> None:
    """Dispatch to the drawing used by the displayed view of this model."""
    match result, labels:
        case RegressionResult(plot=plot), LinearChartLabels() if plot is not None:
            draw_linear_charts(figure, plot, labels)
        case GeneralizedRegressionResult(), LogisticChartLabels() if result.model is RegressionModel.LOGISTIC:
            build_logistic_charts(figure, result, labels)
        case GeneralizedRegressionResult(plot_data=data), CountChartLabels() if data is not None:
            draw_count_charts(figure, data, labels)
        case SurvivalResult(), CoxChartLabels():
            draw_cox_charts(figure, result, labels)
        case _:
            message = "Chart labels do not match the exported regression model."
            raise ValueError(message)


def render_regression_charts(
    snapshot: RegressionExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render all displayed charts of the fitted model as one image.

    Args:
        snapshot: Fitted result with prepared chart data and translated chart
            text captured on the GUI thread; no dataset is consulted.
        progress_cb: Optional image preparation progress.
        cancel_cb: Optional cancellation callback.

    Returns:
        One PNG image owned by the worker, never a live Qt canvas.

    Raises:
        ExcelChartCancelledError: If cancellation is requested before or after drawing.
        ValueError: If the model has no chart data.
    """
    if not snapshot.has_charts:
        message = "The exported regression model has no chart data."
        raise ValueError(message)
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    labels = snapshot.chart_labels
    width, height = _figure_size(snapshot.result)
    with STATISTICS_CHART_LOCK:
        figure = Figure(figsize=(width, height), dpi=_EXPORT_DPI, constrained_layout=True)
        canvas = FigureCanvasAgg(figure)
        _draw_model_charts(figure, snapshot.result, labels.model)
        output = BytesIO()
        canvas.print_png(output)  # type: ignore[no-untyped-call]
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    if progress_cb is not None:
        progress_cb(100)
    return (
        ExcelChartImage(
            labels.heading,
            output.getvalue(),
            round(width * _EXPORT_DPI),
            round(height * _EXPORT_DPI),
            labels.captions,
        ),
    )
