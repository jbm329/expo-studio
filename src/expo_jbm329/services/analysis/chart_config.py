"""Immutable defaults and per-axis policies for analysis chart rendering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class RotationMode(StrEnum):
    """How x-axis tick labels choose their rotation."""

    AUTO = "auto"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    FIXED = "fixed"


class AxisRole(StrEnum):
    """Semantic role used to determine whether x-axis labels are eligible."""

    CATEGORICAL = "categorical"
    CONTINUOUS = "continuous"
    DATE = "date"
    SEMANTIC = "semantic"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class AxisPolicy:
    """Immutable x-axis label policy for a chart axis."""

    role: AxisRole = AxisRole.CATEGORICAL
    rotation_mode: RotationMode = RotationMode.AUTO
    fixed_rotation_degrees: float = 0.0
    overlap_gap_points: float | None = None

    def __post_init__(self) -> None:
        """Validate explicitly configured rotation and measurement tolerance."""
        if not isinstance(self.role, AxisRole):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Axis role must be an AxisRole value."
            raise TypeError(message)
        if not isinstance(self.rotation_mode, RotationMode):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Axis rotation mode must be a RotationMode value."
            raise TypeError(message)
        if not isfinite(self.fixed_rotation_degrees):
            message = "Fixed x-axis label rotation must be finite."
            raise ValueError(message)
        if self.overlap_gap_points is not None and (
            not isfinite(self.overlap_gap_points) or self.overlap_gap_points < 0
        ):
            message = "X-axis overlap gap must be a finite, nonnegative value."
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ChartContentLayoutConfig:
    """Bounded content layout settings captured by each figure.

    Plot minimums are logical pixels at 100 DPI (120 means 1.2 inches), not
    device pixels. Raster limits, padding and tolerance use renderer pixels.

    Used by chart_export to bound renderer-driven image expansion: max_passes
    limits layout retries, max_width_px/max_height_px bound each dimension,
    and max_pixels bounds total raster area. These safeguards bound image
    resource use, not analytical rows or chart sampling. Plot minimums protect
    readable axes; padding and tolerance control clipping/fit measurements.
    The specific budgets are product defaults, not statistical requirements.
    """

    max_passes: int = 12
    max_width_px: int = 8192
    max_height_px: int = 8192
    max_pixels: int = 32_000_000
    minimum_plot_width_px: float = 120.0
    minimum_plot_height_px: float = 120.0
    padding_px: float = 4.0
    tolerance_px: float = 1.0

    def __post_init__(self) -> None:
        """Reject unbounded or invalid export limits."""
        for value in (self.max_passes, self.max_width_px, self.max_height_px, self.max_pixels):
            if (
                not isinstance(value, int)  # pyright: ignore[reportUnnecessaryIsInstance]
                or isinstance(value, bool)
                or value <= 0
            ):
                message = "Chart content layout limits must be positive integers."
                raise ValueError(message)
        for measurement in (
            self.minimum_plot_width_px,
            self.minimum_plot_height_px,
            self.padding_px,
            self.tolerance_px,
        ):
            if not isfinite(measurement) or measurement < 0:
                message = "Chart content layout measurements must be finite and nonnegative."
                raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ChartConfig:
    """Immutable defaults applied by :class:`ChartFigure`."""

    default_axis_policy: AxisPolicy = AxisPolicy()
    overlap_gap_points: float = 2.0
    content_layout: ChartContentLayoutConfig = ChartContentLayoutConfig()

    def __post_init__(self) -> None:
        """Validate the renderer measurement tolerance."""
        if not isinstance(self.default_axis_policy, AxisPolicy):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Default axis policy must be an AxisPolicy value."
            raise TypeError(message)
        if not isinstance(self.content_layout, ChartContentLayoutConfig):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Chart content layout must be a ChartContentLayoutConfig value."
            raise TypeError(message)
        if not isfinite(self.overlap_gap_points) or self.overlap_gap_points < 0:
            message = "Chart overlap gap must be a finite, nonnegative value."
            raise ValueError(message)


DEFAULT_CHART_CONFIG = ChartConfig()
DEFAULT_AXIS_POLICY = AxisPolicy()
