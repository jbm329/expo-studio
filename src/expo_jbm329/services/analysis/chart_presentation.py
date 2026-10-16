"""Shared metadata for output-independent chart presentations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChartPresentationMetadata:
    """Worksheet, accessibility, and caption metadata for a chart presentation."""

    worksheet_heading: str
    accessible_name: str
    captions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Require a stable accessible identity while allowing a hidden worksheet heading."""
        if not self.accessible_name:
            message = "A chart presentation requires an accessible name."
            raise ValueError(message)
