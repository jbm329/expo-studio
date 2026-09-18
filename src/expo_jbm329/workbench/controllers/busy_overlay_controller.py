"""Controller for managing BusyOverlayWidget lifecycle.

This controller centralizes:
  • overlay ownership
  • watchdog handling
  • safe teardown
  • progress updates
  • stale-safe cleanup

Intended usage:
    busy = BusyOverlayController(
        parent=self._parent,
        logger=self._logger,
    )

    busy.attach(view)
    busy.show("Processing…")

    job.progress.connect(busy.set_progress)
    job.finished.connect(busy.finish)
    job.error.connect(lambda _: busy.finish())
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QT_TR_NOOP, QTimer
from PyQt6.QtWidgets import QApplication, QTableView, QWidget

from expo_jbm329.gui.busy_overlay import BusyOverlayWidget
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService


class BusyOverlayController:
    """Controller managing BusyOverlayWidget instances."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_TIME_LIMIT_REACHED = QT_TR_NOOP("Time limit reached")

    TR_TOO_LONG_TIME = QT_TR_NOOP("The time limit was reached.\nPlease see logs for more information.")

    # ------------------------------------------------------------------
    @staticmethod
    def _tr(text: str) -> str:
        return tr("BusyOverlayController", text)

    # ------------------------------------------------------------------
    __slots__ = (
        "_dialogs",
        "_logger",
        "_overlays",
        "_parent",
        "_watchdogs",
    )

    def __init__(
        self,
        *,
        parent: QWidget,
        dialogs: DialogService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize BusyOverlayController.

        Args:
            parent: Parent widget for timers/dialogs.
            dialogs: Dialog service instance.
            logger: Logger instance.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        self._overlays: WeakKeyDictionary[QWidget, BusyOverlayWidget] = WeakKeyDictionary()

        self._watchdogs: WeakKeyDictionary[QWidget, QTimer] = WeakKeyDictionary()

    # ==================================================================
    # Public API
    # ==================================================================

    def attach(
        self,
        target: QWidget,
        *,
        message: str = "",
        indeterminate: bool = True,
    ) -> BusyOverlayWidget:
        """Create or reuse overlay for target widget.

        Args:
            target: Target widget.
            message: Initial message.
            indeterminate: Initial progress mode.

        Returns:
            BusyOverlayWidget instance.
        """
        overlay = self._overlays.get(target)

        if overlay is not None:
            return overlay

        overlay = BusyOverlayWidget(
            target,
            message=message,
            indeterminate=indeterminate,
        )

        self._overlays[target] = overlay

        return overlay

    def run(
        self,
        view: QTableView,
        fn: Callable[[], None],
        *,
        message: str | None = None,
        indeterminate: bool = True,
        timeout_ms: int | None = None,
    ) -> None:
        """Run a function while showing a busy overlay.

        Intended for short synchronous UI-blocking operations.
        """
        self.show_for_view(
            view,
            message=message,
            indeterminate=indeterminate,
            timeout_ms=timeout_ms,
        )

        def _execute():
            try:
                fn()
            finally:
                self.hide_for_view(view)

        QTimer.singleShot(0, _execute)

    def show(
        self,
        target: QWidget,
        *,
        message: str | None = None,
        indeterminate: bool | None = None,
        timeout_ms: int | None = None,
        cancelable: bool = False,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Show busy overlay for target widget.

        Args:
            target: Target widget.
            message: Optional message.
            indeterminate: Optional progress mode.
            timeout_ms: Optional watchdog timeout.
            cancelable: Whether the overlay should show a cancel button.
            on_cancel: Optional callback invoked when the cancel button is clicked.
        """
        overlay = self.attach(
            target,
            message=message or "",
            indeterminate=indeterminate if indeterminate is not None else True,
        )

        # Reset any previous cancel wiring before reusing the overlay.
        with contextlib.suppress(TypeError, RuntimeError):
            overlay.cancel_requested.disconnect()

        if cancelable and on_cancel is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                overlay.cancel_requested.connect(on_cancel)

        overlay.show_overlay(
            message=message,
            indeterminate=indeterminate,
            show_cancel_button=cancelable,
        )

        overlay.raise_()

        QApplication.processEvents()

        if timeout_ms is not None and timeout_ms > 0:
            self._start_watchdog(target, timeout_ms)

    def hide(self, target: QWidget) -> None:
        """Hide busy overlay for target widget."""
        overlay = self._overlays.get(target)

        if overlay is not None:
            with contextlib.suppress(Exception):
                overlay.hide_overlay()

        self._stop_watchdog(target)

    def finish(self, target: QWidget) -> None:
        """Fully teardown overlay lifecycle for target widget."""
        self.hide(target)

    def set_progress(self, target: QWidget, value: int) -> None:
        """Update progress for target widget overlay.

        Args:
            target: Target widget.
            value: Progress value (0-100).
        """
        overlay = self._overlays.get(target)

        if overlay is not None:
            with contextlib.suppress(Exception):
                overlay.set_progress(value)

    def is_visible(self, target: QWidget) -> bool:
        """Return True if overlay is visible."""
        overlay = self._overlays.get(target)

        if overlay is None:
            return False

        try:
            return overlay.isVisible()
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return False

    # ==================================================================
    # Convenience helpers
    # ==================================================================

    def show_for_view(
        self,
        view: QTableView,
        *,
        message: str | None = None,
        indeterminate: bool | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        """Show overlay using QTableView viewport when available.

        Args:
            view: QTableView viewport.
            message: Optional message.
            indeterminate: Optional progress mode.
            timeout_ms: Optional watchdog timeout.
        """
        viewport = view.viewport()
        target = viewport if viewport is not None else view

        self.show(
            target,
            message=message,
            indeterminate=indeterminate,
            timeout_ms=timeout_ms,
        )

    def hide_for_view(self, view: QTableView) -> None:
        """Hide overlay for QTableView."""
        viewport = view.viewport()
        target = viewport if viewport is not None else view

        self.hide(target)

    def set_progress_for_view(
        self,
        view: QTableView,
        value: int,
    ) -> None:
        """Update progress for QTableView overlay.

        Args:
            view: QTableView viewport.
            value: Progress value (0-100).
        """
        viewport = view.viewport()
        target = viewport if viewport is not None else view

        self.set_progress(target, value)

    # ==================================================================
    # Watchdog
    # ==================================================================

    def _start_watchdog(
        self,
        target: QWidget,
        timeout_ms: int,
    ) -> None:
        """Start watchdog timer."""
        self._stop_watchdog(target)

        timer = QTimer(self._parent)
        timer.setSingleShot(True)
        timer.setInterval(timeout_ms)

        def _watchdog_fire():
            self._logger.warning("BusyOverlayController: watchdog timeout reached.")

            self.hide(target)

            self._dialogs.warn(
                self._parent,
                title=self._tr(self.TR_TIME_LIMIT_REACHED),
                text=self._tr(self.TR_TOO_LONG_TIME),
            )

        timer.timeout.connect(_watchdog_fire)

        self._watchdogs[target] = timer

        timer.start()

    def _stop_watchdog(self, target: QWidget) -> None:
        """Stop watchdog timer."""
        timer = self._watchdogs.get(target)

        if timer is not None:
            with contextlib.suppress(Exception):
                timer.stop()

            with contextlib.suppress(Exception):
                timer.deleteLater()

            with contextlib.suppress(Exception):
                del self._watchdogs[target]
