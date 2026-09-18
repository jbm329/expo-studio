"""Path utility functions for the Expo application.

This module provides helpers for expanding environment variables in paths
and mapping file suffixes to their corresponding default directories.
"""

from __future__ import annotations

import os
from pathlib import Path


def expand(p: str | Path) -> Path:
    """Expand ~ and env-vars in a path and return an absolute Path.

    Args:
        p: The path string or Path object to expand.

    Returns:
        The resolved absolute Path.
    """
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()  # noqa: PTH111
