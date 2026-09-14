"""Window hints for dialogs."""
from PyQt6.QtWidgets import QWidget

from expo_jbm329.gui.gui_utils import apply_window_hints_strict


def apply_dialog_window_hints(widget: QWidget, *, min_width: int, fixed_size: bool = True) -> None:
    """Apply window hints to a dialog widget."""
    apply_window_hints_strict(widget, min_width=min_width, fixed_size=fixed_size)
