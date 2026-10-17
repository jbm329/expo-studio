"""Typed, immutable geometry and existing styles for analysis charts.

Edit named font and rotation constants here to configure typography and preferred
angles; drawing functions consume those constants directly. Geometry is configured
only on the named profiles. No Matplotlib defaults or global rcParams are changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class ChartSize:
    """Figure size without overriding renderer DPI or layout policy."""

    figsize: tuple[float, float]

    def __post_init__(self) -> None:
        """Reject nonfinite or nonpositive figure dimensions."""
        if any(not isfinite(value) or value <= 0 for value in self.figsize):
            message = "Chart figure dimensions must be finite and positive."
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ChartGeometry(ChartSize):
    """Export figure size, resolution and constrained-layout policy."""

    dpi: float = 120
    constrained_layout: bool = True

    def __post_init__(self) -> None:
        """Reject nonfinite or nonpositive output dimensions and resolution."""
        ChartSize.__post_init__(self)
        if not isfinite(self.dpi) or self.dpi <= 0:
            message = "Chart DPI must be finite and positive."
            raise ValueError(message)

    @property
    def pixel_size(self) -> tuple[int, int]:
        """Return the declared image dimensions for this geometry."""
        return round(self.figsize[0] * self.dpi), round(self.figsize[1] * self.dpi)


@dataclass(frozen=True, slots=True)
class ChartProfile:
    """Immutable output geometry for a chart family."""

    geometry: ChartGeometry


@dataclass(frozen=True, slots=True)
class ChartGridStyle:
    """Explicit grid visibility and opacity for a chart family."""

    axis: Literal["x", "y", "both"]
    alpha: float


CORRELATION_ANNOTATION_FONT_SIZE = 7
CLUSTERING_LEGEND_FONT_SIZE = 8
OUTLIER_HISTOGRAM_TITLE_FONT_SIZE = 10
OUTLIER_HISTOGRAM_AXIS_FONT_SIZE = 9
OUTLIER_HISTOGRAM_TICK_FONT_SIZE = 8
OUTLIER_HISTOGRAM_LEGEND_FONT_SIZE = 8
OUTLIER_PROJECTION_LEGEND_FONT_SIZE = 8
PCA_LEGEND_FONT_SIZE = 8
LOGISTIC_EFFECT_ANNOTATION_FONT_SIZE = "small"
REGRESSION_COX_TITLE_FONT_SIZE = 9
REGRESSION_COX_TABLE_FONT_SIZE = 8
REGRESSION_GUI_TITLE_FONT_SIZE = 10
REGRESSION_GUI_AXIS_LABEL_FONT_SIZE = 9
REGRESSION_GUI_TICK_FONT_SIZE = 8

PREFERRED_CATEGORICAL_ROTATION = 30
PAIRED_COMPARISON_PREFERRED_ROTATION = PREFERRED_CATEGORICAL_ROTATION
TIME_SERIES_PREFERRED_ROTATION = 30
COX_SURVIVAL_PREFERRED_ROTATION = 30
CORRELATION_MATRIX_PREFERRED_ROTATION = 90

STATISTICS_CHART_PROFILE = ChartProfile(ChartGeometry((9.0, 3.5)))
HYPOTHESIS_CHART_PROFILE = ChartProfile(ChartGeometry((9.0, 3.5)))
CORRELATION_CHART_PROFILE = ChartProfile(ChartGeometry((9.0, 6.0)))
CLUSTERING_PROJECTION_PROFILE = ChartProfile(ChartGeometry((8.0, 6.0)))
OUTLIER_HISTOGRAM_PROFILE = ChartProfile(ChartGeometry((8.0, 3.75)))
OUTLIER_PROJECTION_PROFILE = ChartProfile(ChartGeometry((8.0, 6.0)))
PCA_CHART_PROFILE = ChartProfile(ChartGeometry((8.0, 5.0)))
TIME_SERIES_CHART_PROFILE = ChartProfile(ChartGeometry((8.0, 4.0)))
TIME_SERIES_DECOMPOSITION_PROFILE = ChartProfile(ChartGeometry((8.0, 8.0)))

REGRESSION_LINEAR_PROFILE = ChartProfile(ChartGeometry((13.5, 4.5)))
REGRESSION_SURVIVAL_PROFILE = ChartProfile(ChartGeometry((12.0, 6.0)))
REGRESSION_COUNT_PROFILE = ChartProfile(ChartGeometry((11.0, 4.75)))
REGRESSION_LOGISTIC_MINIMUM_SIZE = (10.0, 7.5)
REGRESSION_LOGISTIC_BASE_SIZE = (10.0, 5.0)
REGRESSION_LOGISTIC_HEIGHT_PER_PREDICTOR = 0.24
COLUMN_PROPERTIES_FIGURE_SIZE = (5.0, 2.6)
COLUMN_PROPERTIES_GRID = ChartGridStyle(axis="y", alpha=0.25)


def regression_logistic_profile(predictor_count: int) -> ChartProfile:
    """Return the existing predictor-dependent logistic export geometry.

    Args:
        predictor_count: Number of non-intercept predictor terms.

    Raises:
        ValueError: If the predictor count is negative.
    """
    if predictor_count < 0:
        message = "A regression chart cannot have a negative predictor count."
        raise ValueError(message)

    base_width, base_height = REGRESSION_LOGISTIC_BASE_SIZE
    minimum_width, minimum_height = REGRESSION_LOGISTIC_MINIMUM_SIZE
    height = max(minimum_height, base_height + predictor_count * REGRESSION_LOGISTIC_HEIGHT_PER_PREDICTOR)
    return ChartProfile(ChartGeometry((max(base_width, minimum_width), height)))
