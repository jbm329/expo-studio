"""Typed image content embedded in named Excel worksheets."""

from __future__ import annotations

from dataclasses import dataclass


class ExcelChartCancelledError(Exception):
    """Raised when asynchronous chart preparation is cooperatively cancelled."""


@dataclass(frozen=True, slots=True)
class ExcelChartImage:
    """A raster chart image with its worksheet heading and display dimensions."""

    heading: str
    image_data: bytes
    width_px: int
    height_px: int

    def __post_init__(self) -> None:
        """Reject payloads that cannot be embedded as visible workbook images."""
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
