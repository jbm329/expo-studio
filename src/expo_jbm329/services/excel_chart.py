"""Typed image content embedded in named Excel worksheets."""

from __future__ import annotations

from dataclasses import dataclass


class ExcelChartCancelledError(Exception):
    """Raised when asynchronous chart preparation is cooperatively cancelled."""


@dataclass(frozen=True, slots=True)
class ExcelChartImage:
    """A raster image with optional heading, accessible identity and explanatory notes."""

    heading: str
    image_data: bytes
    width_px: int
    height_px: int
    captions: tuple[str, ...] = ()
    accessible_name: str | None = None

    def __post_init__(self) -> None:
        """Reject payloads that cannot be embedded as visible workbook images."""
        if self.accessible_name is not None and not self.accessible_name:
            message = "An explicit accessible chart name must be non-empty."
            raise ValueError(message)
        if not self.image_data:
            message = "Excel chart image data must be non-empty bytes."
            raise ValueError(message)
        if (
            isinstance(self.width_px, bool)
            or self.width_px < 1
            or isinstance(self.height_px, bool)
            or self.height_px < 1
        ):
            message = "Excel chart image dimensions must be positive integers."
            raise ValueError(message)
