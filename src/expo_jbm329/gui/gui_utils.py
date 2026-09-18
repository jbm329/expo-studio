"""GUI utility functions.

This module provides common utility functions for GUI-related tasks,
such as scheduling functions to run on the UI thread and applying
standard window hints to dialogs.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, Qt, QTimer

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QDialog

_APP_CLOSING = False


def set_app_closing(value: bool = True) -> None:
    """Mark the GUI application as closing.

    This prevents queued UI callbacks from running during Qt teardown.
    """
    global _APP_CLOSING
    _APP_CLOSING = value


def ui_invoke(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Schedule a function to be executed on the UI thread as soon as possible.

    This acts as a trampoline to ensure UI updates are always performed on
    the main thread, which is required by Qt.

    Args:
        fn: The function to execute.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.
    """
    app = QCoreApplication.instance()
    if app is None or _APP_CLOSING:
        return

    def _invoke() -> None:
        if _APP_CLOSING or QCoreApplication.instance() is None:
            return
        fn(*args, **kwargs)

    QTimer.singleShot(0, _invoke)


def apply_window_hints_strict(
    dlg: QDialog,
    *,
    min_width: int | None = 520,
    fixed_size: bool = False,
    show_close_button: bool = True,
) -> None:
    """Apply a unified strict window policy to a dialog.

    Features:
      - No minimize/maximize buttons.
      - Optional close button (default: shown).
      - Optional fixed size.
      - Enforced clean window flag mask.

    Args:
        dlg: The dialog to apply hints to.
        min_width: Minimum width for the dialog.
        fixed_size: Whether to fix the dialog size.
        show_close_button: Whether to show the close button.
    """
    # Base flags: dialog + custom + title
    flags = Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint

    # Add close button if allowed
    if show_close_button:
        flags |= Qt.WindowType.WindowCloseButtonHint

    dlg.setWindowFlags(flags)
    dlg.setSizeGripEnabled(False)

    # Apply layout polish
    with contextlib.suppress(Exception):
        dlg.ensurePolished()
        dlg.adjustSize()

    # Enforce minimum width if needed
    if isinstance(min_width, int) and min_width > 0 and dlg.width() < min_width:
        dlg.resize(min_width, dlg.height())

    # Fix size if requested
    if fixed_size:
        dlg.setFixedSize(dlg.size())
