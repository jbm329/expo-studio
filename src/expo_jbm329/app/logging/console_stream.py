"""Windows console stream for an opted-in windowed executable."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO

_ATTACH_PARENT_PROCESS = 0xFFFFFFFF
_ERROR_INVALID_HANDLE = 6
_ERROR_INVALID_PARAMETER = 87


def open_parent_console() -> TextIO | None:
    """Open Unicode output to an existing Windows console, never allocating one.

    Returns:
        An owned stream, or None when no parent console is available.

    Raises:
        OSError: Attaching or opening the output device failed unexpectedly.
    """
    if sys.platform == "win32":
        from ctypes import WinDLL, WinError, get_last_error
        from ctypes.wintypes import BOOL, DWORD, UINT

        kernel = WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleOutputCP.argtypes = []
        kernel.GetConsoleOutputCP.restype = UINT
        kernel.AttachConsole.argtypes = [DWORD]
        kernel.AttachConsole.restype = BOOL
        # A previous logging setup may already have attached this process.
        if not kernel.GetConsoleOutputCP() and not kernel.AttachConsole(_ATTACH_PARENT_PROCESS):
            error = get_last_error()
            if error in {_ERROR_INVALID_HANDLE, _ERROR_INVALID_PARAMETER}:
                return None
            raise WinError(error)
        return Path("CONOUT$").open("w", encoding="utf-8", errors="backslashreplace")
    return None
