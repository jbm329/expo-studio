"""Shared nonblocking Qt canvas for application charts."""

from __future__ import annotations

import logging
from math import ceil
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QSize, QTimer
from PyQt6.QtGui import QPaintEvent, QResizeEvent

from expo_jbm329.services.analysis.chart_export import measure_chart_growth
from expo_jbm329.services.analysis.chart_layout import ChartFigure
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.figure import Figure

CHART_RETRY_INTERVAL_MS = 25


class SerializedAnalysisCanvas(FigureCanvasQTAgg):
    """Serialize chart layout and Qt rendering without waiting for a worker."""

    def __init__(self, figure: Figure) -> None:
        """Initialize an object-owned retry timer for rendering and resizing."""
        super().__init__(figure)  # type: ignore[no-untyped-call]
        self._resize_pending = False
        self._draw_pending = False
        self._pixel_ratio_pending = False
        self._chart_builder: Callable[[], None] | None = None
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.setInterval(CHART_RETRY_INTERVAL_MS)
        self._retry_timer.timeout.connect(self._retry_render)
        self._content_size_timer = QTimer(self)
        self._content_size_timer.setSingleShot(True)
        self._content_size_timer.timeout.connect(self._apply_content_minimum)
        self._content_minimum: QSize | None = None
        self._content_limit_reported = False
        self._content_resize_passes = 0
        self._content_axes: tuple[object, ...] = ()
        self._original_minimum: QSize | None = None

    def build_chart(self, builder: Callable[[], None]) -> None:
        """Build a chart when rendering is available, without blocking Qt."""
        self._chart_builder = builder
        self._build_pending_chart()

    def _build_pending_chart(self) -> None:
        """Serialize figure mutations with worker and live canvas drawing."""
        if self._chart_builder is None:
            return
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._defer_render()
            return
        try:
            builder = self._chart_builder
            self._chart_builder = None
            builder()
            self.draw_idle()  # type: ignore[no-untyped-call]
        finally:
            STATISTICS_CHART_LOCK.release()

    def _defer_render(self) -> None:
        """Coalesce retries; QObject ownership cancels them on destruction."""
        if not self._retry_timer.isActive():
            self._retry_timer.start()

    def draw(self) -> None:
        """Protect renderer-aware layout and actual Agg drawing."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._draw_pending = True
            self._defer_render()
            return
        try:
            self._draw_pending = False
            super().draw()  # type: ignore[no-untyped-call]
            self._measure_content_minimum()
        finally:
            STATISTICS_CHART_LOCK.release()

    def _measure_content_minimum(self) -> None:
        """Request extra space after rendering, without resizing inside a draw."""
        figure = self.figure
        if not isinstance(figure, ChartFigure) or figure.stale:
            return
        axes = tuple(figure.axes)
        if axes != self._content_axes:
            self._content_axes = axes
            self._content_limit_reported = False
            self._content_resize_passes = 0
            if self._original_minimum is None:
                self._original_minimum = self.minimumSize()
            elif self.minimumSize() != self._original_minimum:
                self._content_minimum = QSize(self._original_minimum)
                self._content_size_timer.start(0)
                return
        renderer = self.get_renderer()  # type: ignore[no-untyped-call]
        extra_width, extra_height = measure_chart_growth(figure, renderer)
        config = figure.config.content_layout
        if extra_width <= config.tolerance_px and extra_height <= config.tolerance_px:
            self._content_resize_passes = 0
            if self._content_minimum is not None and self._content_minimum != self._original_minimum:
                self._content_size_timer.stop()
                self._content_minimum = None
            return
        if self._content_resize_passes >= config.max_passes:
            if not self._content_limit_reported:
                logging.getLogger("applogger.ui").warning(
                    "Chart content did not fit within the live canvas layout iteration limit."
                )
                self._content_limit_reported = True
            return
        ratio = self.device_pixel_ratio
        width = (
            ceil((figure.bbox.width + extra_width + config.padding_px) / ratio)
            if extra_width > config.tolerance_px
            else self.minimumWidth()
        )
        height = (
            ceil((figure.bbox.height + extra_height + config.padding_px) / ratio)
            if extra_height > config.tolerance_px
            else self.minimumHeight()
        )
        max_width = int(config.max_width_px / ratio)
        max_height = int(config.max_height_px / ratio)
        raster_width = max(width, self.width())
        raster_height = max(height, self.height())
        if (
            raster_width > max_width
            or raster_height > max_height
            or raster_width * raster_height * ratio**2 > config.max_pixels
        ):
            if not self._content_limit_reported:
                logging.getLogger("applogger.ui").warning(
                    "Chart content exceeds configured live canvas layout limits (%s x %s pixels).",
                    width,
                    height,
                )
                self._content_limit_reported = True
            return
        self._content_minimum = QSize(max(self.minimumWidth(), width), max(self.minimumHeight(), height))
        if not self._content_size_timer.isActive():
            self._content_resize_passes += 1
        self._content_size_timer.start(0)

    def _apply_content_minimum(self) -> None:
        """Let the owning scroll area accommodate a content-sized canvas."""
        if self._content_minimum is None:
            return
        self.setMinimumSize(self._content_minimum)
        self._content_minimum = None
        self.updateGeometry()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """Defer Qt's figure-size mutation while a worker owns Matplotlib."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._resize_pending = True
            self._defer_render()
            return
        try:
            self._resize_pending = False
            super().resizeEvent(event)  # type: ignore[no-untyped-call]
        finally:
            STATISTICS_CHART_LOCK.release()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Protect deferred drawing and renderer-buffer access during painting."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._defer_render()
            return
        try:
            super().paintEvent(event)  # type: ignore[no-untyped-call]
        finally:
            STATISTICS_CHART_LOCK.release()

    def _update_pixel_ratio(self) -> None:
        """Protect figure DPI changes on show and screen-change events."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._pixel_ratio_pending = True
            self._defer_render()
            return
        try:
            self._pixel_ratio_pending = False
            super()._update_pixel_ratio()
        finally:
            STATISTICS_CHART_LOCK.release()

    def _retry_render(self) -> None:
        """Replay the latest resize and draw, then request another Qt paint."""
        self._build_pending_chart()
        if self._pixel_ratio_pending:
            self._update_pixel_ratio()
        if self._resize_pending:
            self.resizeEvent(QResizeEvent(self.size(), self.size()))
        if self._draw_pending:
            self.draw()
        self.update()
