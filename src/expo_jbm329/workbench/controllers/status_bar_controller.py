"""Status bar controller for the Expo application.

This module defines the StatusBarController, which is responsible for
*presenting* status information in the application status bar and
resolving priority between different kinds of status signals.

The status bar is conceptually divided into four independent channels:

1. Main status text (status_label)
   - Represents the current *application state* or a *running process*.
   - Two types of messages exist:
     - Permanent status (timeout=None):
       Represents stable application state (e.g. "Ready", "Connected: X").
       This text persists until explicitly replaced.
     - Transient status (timeout=0 or >0):
       Represents short-lived processes (e.g. "Loading schema…").
       Transient messages never replace permanent state long-term.

2. Qt transient message area (QStatusBar.showMessage)
   - Used internally by Qt for timed messages.
   - Transient messages are mirrored into the main status label to avoid
     split attention between two visual areas.

3. Progress indicators (progress_label, progress bar)
   - Signal that background work is ongoing.
   - Progress indicators do NOT represent application state and must not
     change or override the main status text.

4. Shape indicator (shape_label)
   - Displays dataset information (rows/columns).
   - Orthogonal to status and progress; it must never influence or reset
     the main status text.

Responsibility boundaries:

- StatusBarController owns:
  - Widget creation and layout
  - Rendering logic (permanent vs transient)
  - Timeouts, restoration of permanent state
  - Thread-safe UI updates

- Application-level controllers (e.g. ExpoStudio) own:
  - The meaning of permanent application state
    (e.g. Ready, Connected, Disconnected)

- Feature controllers (e.g. SchemaController) own:
  - Transient process messages
    (e.g. Loading schema, Preloading schema)

Important invariants:

- Permanent status always represents the current application state.
- Transient status may temporarily override the display, but never
  replaces the permanent state.
- Progress indicators and shape indicators must not modify main status.
- UI repainting depends on the Qt event loop; long-running synchronous
  operations must explicitly yield to allow transient status rendering.

This separation is intentional and should be preserved when extending
status, progress, or UI feedback behavior.
"""

from __future__ import annotations

import contextlib
from typing import Any, cast

from PyQt6.QtCore import QT_TR_NOOP, QTimer
from PyQt6.QtWidgets import (
    QLabel,
    QProgressBar,
    QStatusBar,
    QWidget,
)

from expo_jbm329.gui.gui_utils import ui_invoke
from expo_jbm329.utils.i18n_utils import tr, tr_fmt


class StatusBarController:
    """Controller for managing the status bar in the Expo application.

    This class handles all status bar UI and logic, including building widgets,
    managing permanent and transient status messages, displaying data shape
    (rows/columns), and controlling the progress bar.
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_SET_SHAPE_STATUS_DEFAULT = QT_TR_NOOP("Rows: -  |  Columns: -")
    TR_SET_SHAPE_STATUS = QT_TR_NOOP("Rows: {rows}  |  Columns: {columns}")
    TR_SELECT_CONNECTION_STATUS = QT_TR_NOOP("Ready")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("StatusBarController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("StatusBarController", text, **kwargs)

    def __init__(self, parent: QWidget, status_bar: QStatusBar) -> None:
        """Initialize the StatusBarController.

        Args:
            parent: The parent widget.
            status_bar: The QStatusBar instance to manage.
        """
        self._parent = parent
        self._status_bar = status_bar

        # Widgets
        self.status_label = QLabel("", parent)
        self.shape_label = QLabel(self._tr(self.TR_SET_SHAPE_STATUS_DEFAULT), parent)
        self.progress_label = QLabel("", parent)
        self.progress = QProgressBar(parent)

        # Internal permanent status text
        self._permanent_status_text = ""
        self._shape_has_data = False

        self._build_widgets()
        parent_for_legacy = cast("Any", self._parent)
        parent_for_legacy.progress = self.progress
        parent_for_legacy.progress_label = self.progress_label
        parent_for_legacy.shape_label = self.shape_label

        self.init_baseline()

    # ------------------------------------------------------------------
    # UI BUILDING
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        """Build and configure the status bar widgets."""
        sb = self._status_bar

        # Main status label
        sb.addPermanentWidget(self.status_label, 1)

        # Shape label
        self.shape_label.setObjectName("shapeLabel")
        self.shape_label.setStyleSheet("QLabel#shapeLabel { padding-left: 12px; color: #444; }")
        sb.addPermanentWidget(self.shape_label)

        # Optional progress label
        self.progress_label.setVisible(False)
        sb.addPermanentWidget(self.progress_label)

        # Progress bar
        self.progress.setVisible(False)
        self.progress.setFixedWidth(160)
        self.progress.setTextVisible(True)
        sb.addPermanentWidget(self.progress)

    # ------------------------------------------------------------------
    def init_baseline(self) -> None:
        """Initialize the baseline status message.

        Sets the default status message indicating to select a connection.
        """
        self._permanent_status_text = self._tr(self.TR_SELECT_CONNECTION_STATUS)
        self.status_label.setText(self._permanent_status_text)
        self._status_bar.clearMessage()

        # No data loaded initially
        self._shape_has_data = False
        self.shape_label.setText(self._tr(self.TR_SET_SHAPE_STATUS_DEFAULT))

    # ------------------------------------------------------------------
    # STATUS MESSAGE API
    # ------------------------------------------------------------------
    def set_status(self, text: str, timeout_ms: int | None = None) -> None:
        """Thread-safe entry point for updating the status bar."""
        ui_invoke(self._set_status_ui, text, timeout_ms)

    def restore_baseline(self) -> None:
        """Restore the permanent status text in the status bar."""
        ui_invoke(self._restore_baseline_ui)

    # ------------------------------------------------------------------
    # PROGRESS API (thread-safe)
    #
    # Progress indicators represent activity only and must never
    # modify or imply application state.
    #
    # ------------------------------------------------------------------
    def show_progress(self, label: str | None = None, *, indeterminate: bool = True) -> None:
        """Show progress indicators in the status bar."""
        ui_invoke(self._show_progress_ui, label, indeterminate)

    def update_progress(self, value: int, label: str | None = None) -> None:
        """Update progress value and optional label."""
        ui_invoke(self._update_progress_ui, value, label)

    def hide_progress(self) -> None:
        """Hide progress indicators in the status bar."""
        ui_invoke(self._hide_progress_ui)

    # ------------------------------------------------------------------
    # SHAPE DISPLAY
    # ------------------------------------------------------------------

    def set_shape_status(self, rows: int | None, cols: int | None) -> None:
        """Update the rows/columns summary indicator.

        Args:
            rows: Number of rows, or None for default.
            cols: Number of columns, or None for default.
        """
        if rows is None or cols is None:
            # No data
            self._shape_has_data = False
            self.shape_label.setStyleSheet("QLabel#shapeLabel { padding-left: 12px; color: #444; }")
            self.shape_label.setText(self._tr(self.TR_SET_SHAPE_STATUS_DEFAULT))
            return

        # Data present
        self._shape_has_data = True
        self.shape_label.setStyleSheet("QLabel#shapeLabel { padding-left: 12px; }")

        rows_str = f"{rows:,}".replace(",", " ")
        cols_str = f"{cols:,}".replace(",", " ")

        text = self._tr_fmt(self.TR_SET_SHAPE_STATUS, rows=rows_str, columns=cols_str)
        self.shape_label.setText(text)

    # UI language
    def retranslate_ui(self) -> None:
        """Update all translatable status bar texts."""
        # Permanent baseline
        self._permanent_status_text = self._tr(self.TR_SELECT_CONNECTION_STATUS)
        self.status_label.setText(self._permanent_status_text)

        # Shape label
        if not self._shape_has_data:
            self.shape_label.setText(self._tr(self.TR_SET_SHAPE_STATUS_DEFAULT))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _set_status_ui(self, text: str, timeout_ms: int | None) -> None:
        """Update the status bar UI. Must run on the Qt UI thread."""
        # --------------------------------------------------------------
        # Permanent message
        # --------------------------------------------------------------
        if timeout_ms is None:
            self._permanent_status_text = text or ""
            self.status_label.setText(self._permanent_status_text)

            # If we are NOT busy (no progress bar visible),
            # clear any transient message shown via QStatusBar
            busy = False
            with contextlib.suppress(Exception):
                busy = self.progress.isVisible()

            if not busy:
                self._status_bar.clearMessage()

            return

        # --------------------------------------------------------------
        # Transient message
        # --------------------------------------------------------------
        ms = max(0, int(timeout_ms))

        # Show message in the status bar (Qt-managed transient area)
        self._status_bar.showMessage(text or "", ms)

        # Also reflect the transient text in our main status label
        self.status_label.setText(text or "")

        # Auto-restore permanent text after timeout (if requested)
        if ms > 0:
            QTimer.singleShot(
                ms,
                lambda: self.status_label.setText(self._permanent_status_text),
            )

    def _restore_baseline_ui(self) -> None:
        """Restore the permanent status text in the status bar."""
        self._status_bar.clearMessage()
        self.status_label.setText(self._permanent_status_text)

    def _show_progress_ui(self, label: str | None, indeterminate: bool) -> None:
        if label:
            self.progress_label.setText(label)
            self.progress_label.setVisible(True)
        else:
            self.progress_label.clear()
            self.progress_label.setVisible(False)

        self.progress.setRange(0, 0 if indeterminate else 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)

    def _update_progress_ui(self, value: int, label: str | None) -> None:
        if label is not None:
            self.progress_label.setText(label)
            self.progress_label.setVisible(True)

        if self.progress.maximum() == 0:
            # was indeterminate → switch to determinate
            self.progress.setRange(0, 100)

        self.progress.setValue(max(0, min(100, value)))

    def _hide_progress_ui(self) -> None:
        self.progress.setVisible(False)
        self.progress_label.clear()
        self.progress_label.setVisible(False)
