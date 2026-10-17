"""Renderer-aware, bounded x-axis label layout for Matplotlib figures."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Literal

from matplotlib.figure import Figure

from expo_jbm329.services.analysis.chart_config import (
    DEFAULT_CHART_CONFIG,
    AxisPolicy,
    AxisRole,
    ChartConfig,
    RotationMode,
)

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.backend_bases import RendererBase
    from matplotlib.gridspec import SubplotParams
    from matplotlib.layout_engine import LayoutEngine
    from matplotlib.text import Text
    from matplotlib.typing import ColorType

_ROTATION_EPSILON = 1e-6
_MIN_LABELS_FOR_OVERLAP = 2
_MAX_LAYOUT_PASSES = 3
_VERTICAL_ROTATION = 90.0


@dataclass(slots=True)
class _AxisLayoutState:
    policy: AxisPolicy
    preferred_rotation: float
    last_applied_rotation: float | None = None


class ChartFigure(Figure):
    """Matplotlib Figure that adapts crowded x labels using the active renderer.

    Auto mode preserves the axis's original rotation unless rendered labels
    overlap; in that case, it uses vertical labels. It never removes ticks or
    changes locators and formatters. Extremely dense labels can remain
    overlapping after rotation because a fixed-size image has finite space.
    """

    def __init__(
        self,
        figsize: tuple[float, float] | tuple[float, float, Literal["in", "cm", "px"]] | None = None,
        dpi: float | None = None,
        *,
        facecolor: ColorType | None = None,
        edgecolor: ColorType | None = None,
        linewidth: float = 0.0,
        frameon: bool | None = None,
        subplotpars: SubplotParams | None = None,
        tight_layout: bool | dict[str, float] | None = None,
        constrained_layout: bool | dict[str, float] | None = None,
        layout: Literal["constrained", "compressed", "tight", "none"] | LayoutEngine | None = None,
        config: ChartConfig | None = None,
        **kwargs: object,
    ) -> None:
        """Create a Figure with standard Matplotlib geometry options and config.

        Args:
            figsize: Figure dimensions in inches or a Matplotlib unit tuple.
            dpi: Figure resolution.
            facecolor: Figure background color.
            edgecolor: Figure frame color.
            linewidth: Figure frame line width.
            frameon: Whether to draw the figure frame.
            subplotpars: Standard Matplotlib subplot spacing parameters.
            tight_layout: Standard Matplotlib tight-layout option.
            constrained_layout: Standard Matplotlib constrained-layout option.
            layout: Standard Matplotlib layout engine option.
            config: Immutable chart layout defaults; defaults to internal policy.
            **kwargs: Standard Matplotlib Figure artist properties.
        """
        if config is not None and not isinstance(config, ChartConfig):
            message = "Chart figure config must be a ChartConfig value."
            raise TypeError(message)
        self._config = config if config is not None else DEFAULT_CHART_CONFIG
        self._axis_layout: dict[Axes, _AxisLayoutState] = {}
        self._layout_draw_in_progress = False
        super().__init__(
            figsize=figsize,
            dpi=dpi,
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
            frameon=frameon,
            subplotpars=subplotpars,
            tight_layout=tight_layout,
            constrained_layout=constrained_layout,
            layout=layout,  # type: ignore[arg-type]  # Stubs omit runtime-supported layout="none".
            **kwargs,
        )

    @property
    def config(self) -> ChartConfig:
        """Return the immutable configuration captured by this figure."""
        return self._config

    def configure_axis(self, axis: Axes, policy: AxisPolicy | None = None) -> None:
        """Set or reset the immutable policy and preferred angle for an axis.

        Args:
            axis: An axis owned by this figure.
            policy: Axis-specific override, or the figure's default policy.

        Raises:
            ValueError: If the axis does not belong to this figure.
        """
        if axis.figure is not self or axis not in self.axes:
            message = "The configured axis must belong to this figure."
            raise ValueError(message)

        resolved_policy = policy if policy is not None else self.config.default_axis_policy
        self._axis_layout[axis] = _AxisLayoutState(
            policy=resolved_policy,
            preferred_rotation=self._read_preferred_rotation(axis),
        )

    def clear(self, keep_observers: bool = False) -> None:
        """Clear the figure and discard axis-specific layout state."""
        self._axis_layout.clear()
        super().clear(keep_observers=keep_observers)

    def delaxes(self, ax: Axes) -> None:
        """Remove an axis and its retained policy state."""
        self._axis_layout.pop(ax, None)
        super().delaxes(ax)

    def draw(self, renderer: RendererBase) -> None:
        """Measure and promote crowded labels in at most three drawing passes."""
        if self._layout_draw_in_progress:
            return

        self._layout_draw_in_progress = True
        try:
            self._prune_removed_axes()
            self._prepare_measurement_rotations()
            for pass_index in range(_MAX_LAYOUT_PASSES):
                if pass_index:
                    self._clear_renderer_if_supported(renderer)
                super().draw(renderer)
                if pass_index == _MAX_LAYOUT_PASSES - 1 or not self._apply_measured_rotations(
                    renderer, promote_only=pass_index > 0
                ):
                    break
        finally:
            self._layout_draw_in_progress = False

    @staticmethod
    def _clear_renderer_if_supported(renderer: RendererBase) -> None:
        """Clear a reusable renderer before the final full-scene redraw."""
        clear = getattr(renderer, "clear", None)
        if callable(clear):
            clear()

    def _prune_removed_axes(self) -> None:
        """Release state for axes removed without going through ``delaxes``."""
        current_axes = set(self.axes)
        for axis in tuple(self._axis_layout):
            if axis not in current_axes:
                del self._axis_layout[axis]

    def _axis_state(self, axis: Axes) -> _AxisLayoutState:
        """Get or initialize state, capturing chart-authored label rotation."""
        state = self._axis_layout.get(axis)
        if state is None:
            state = _AxisLayoutState(
                policy=self.config.default_axis_policy,
                preferred_rotation=self._read_preferred_rotation(axis),
            )
            self._axis_layout[axis] = state
        return state

    @staticmethod
    def _read_preferred_rotation(axis: Axes) -> float:
        """Read the chart-authored major x-label rotation, defaulting to zero."""
        rotations = [tick.label1.get_rotation() for tick in axis.xaxis.get_major_ticks()]
        if not rotations:
            return 0.0
        return rotations[0] if isfinite(rotations[0]) else 0.0

    def _prepare_measurement_rotations(self) -> None:
        """Restore preferred rotations before checking a new renderer/size."""
        for axis in self.axes:
            state = self._axis_state(axis)
            if not self._is_eligible_axis(axis, state.policy):
                continue
            labels = self._visible_labels(axis)
            if not labels:
                continue
            current_rotations = [label.get_rotation() for label in labels]
            if (
                state.last_applied_rotation is not None
                and any(
                    abs(rotation - state.last_applied_rotation) > _ROTATION_EPSILON
                    for rotation in current_rotations
                )
            ):
                state.preferred_rotation = current_rotations[0]
            forced_rotation = self._rotation_for_policy(state)
            self._set_rotation(
                labels, state.preferred_rotation if forced_rotation is None else forced_rotation
            )

    def _apply_measured_rotations(self, renderer: RendererBase, *, promote_only: bool = False) -> bool:
        """Measure visible major x-labels and apply final rotation decisions."""
        changed = False
        for axis in self.axes:
            state = self._axis_state(axis)
            if not self._is_eligible_axis(axis, state.policy):
                continue
            labels = self._visible_labels(axis)
            if not labels:
                continue

            rotation = self._rotation_for_policy(state)
            if rotation is None:
                rotation = (
                    _VERTICAL_ROTATION
                    if (promote_only and state.last_applied_rotation == _VERTICAL_ROTATION)
                    or self._labels_overlap(axis, renderer, state.policy)
                    else state.preferred_rotation
                )
            if any(abs(label.get_rotation() - rotation) > _ROTATION_EPSILON for label in labels):
                self._set_rotation(labels, rotation)
                changed = True
            state.last_applied_rotation = rotation
        return changed

    @staticmethod
    def _rotation_for_policy(state: _AxisLayoutState) -> float | None:
        """Return a forced angle, or None when auto mode needs measurement."""
        match state.policy.rotation_mode:
            case RotationMode.AUTO:
                return None
            case RotationMode.HORIZONTAL:
                return 0.0
            case RotationMode.VERTICAL:
                return _VERTICAL_ROTATION
            case RotationMode.FIXED:
                return state.policy.fixed_rotation_degrees

    @staticmethod
    def _is_eligible_axis(axis: Axes, policy: AxisPolicy) -> bool:
        """Exclude hidden axes and Matplotlib colorbar axes from rotation."""
        return (
            axis.axison
            and axis.get_visible()
            and axis.xaxis.get_visible()
            and policy.role is not AxisRole.EXCLUDED
            and getattr(axis, "_colorbar", None) is None
            and axis.get_label() != "<colorbar>"
        )

    @staticmethod
    def _visible_labels(axis: Axes) -> list[Text]:
        """Return major x labels actually eligible for drawing in the viewport."""
        lower, upper = sorted(axis.get_xlim())
        return [
            label
            for location, tick in zip(
                axis.xaxis.get_majorticklocs(), axis.xaxis.get_major_ticks(), strict=True
            )
            if lower <= location <= upper
            for label in (tick.label1, tick.label2)
            if label.get_visible() and label.get_text().strip()
        ]

    @staticmethod
    def _set_rotation(labels: list[Text], rotation: float) -> None:
        """Set visible label artists without mutating hidden/shared labels."""
        for label in labels:
            label.set_rotation(rotation)

    def _labels_overlap(self, axis: Axes, renderer: RendererBase, policy: AxisPolicy) -> bool:
        """Detect adjacent visible label collisions in renderer pixel coordinates."""
        labels = self._visible_labels(axis)
        if len(labels) < _MIN_LABELS_FOR_OVERLAP:
            return False

        gap_points = (
            policy.overlap_gap_points
            if policy.overlap_gap_points is not None
            else self.config.overlap_gap_points
        )
        gap_pixels = renderer.points_to_pixels(gap_points)
        extents = sorted((label.get_window_extent(renderer) for label in labels), key=lambda box: box.x0)
        for index, previous in enumerate(extents):
            for current in extents[index + 1 :]:
                if current.x0 >= previous.x1 + gap_pixels:
                    break
                if current.y0 < previous.y1 and previous.y0 < current.y1:
                    return True
        return False
