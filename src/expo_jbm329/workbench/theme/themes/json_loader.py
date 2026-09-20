"""Load Qt theme definitions from JSON files into the app's Theme dataclass."""

from __future__ import annotations

import json
from dataclasses import fields
from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor

from expo_jbm329.workbench.highlighter.sql_highlighter import Theme

if TYPE_CHECKING:
    from pathlib import Path


def _parse_color(value: str | dict[str, object] | None) -> QColor:
    """Parse a color from supported JSON representations.

    Supported values include a hex string like "#RRGGBB" and a dict of RGBA values.
    """
    if value is None:
        return QColor(0, 0, 0, 0)

    if isinstance(value, str):
        return QColor(value)

    if isinstance(value, dict):
        r = value.get("r", 0)
        g = value.get("g", 0)
        b = value.get("b", 0)
        a = value.get("a", 255)
        if not isinstance(r, int | str) or not isinstance(g, int | str):
            msg = f"Unsupported color format: {value}"
            raise TypeError(msg)
        if not isinstance(b, int | str) or not isinstance(a, int | str):
            msg = f"Unsupported color format: {value}"
            raise TypeError(msg)
        return QColor(
            int(r),
            int(g),
            int(b),
            int(a),
        )

    msg = f"Unsupported color format: {value}"
    raise TypeError(msg)


def load_theme_from_json(path: Path) -> Theme:
    """Load a Theme from a JSON file.

    Friendly name and values must match Theme dataclass fields. Unknown keys are ignored.
    """
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))

    kwargs: dict[str, object] = {}

    # Handle friendly_name first (string, no color parsing)
    friendly = data.get("friendly_name")
    if not isinstance(friendly, str):
        msg = f"Theme JSON '{path.name}' is missing required friendly_name:string"
        raise TypeError(msg)
    kwargs["friendly_name"] = friendly

    # Handle remaining Theme fields
    for f in fields(Theme):
        field_name = f.name

        # friendly_name handled above
        if field_name == "friendly_name":
            continue

        if field_name not in data:
            continue

        val = data[field_name]

        # QColor fields
        if isinstance(val, (str, dict)) or val is None:
            kwargs[field_name] = _parse_color(val)
        else:
            # Booleans, numbers etc.
            kwargs[field_name] = val

    return Theme(**kwargs)  # type: ignore[arg-type]
