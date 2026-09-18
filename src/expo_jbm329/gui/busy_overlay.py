"""Busy overlay widget for non-blocking UI feedback.

This module provides an overlay widget that can be placed on top of any other
widget to indicate a busy state with a message, a progress bar, and an optional
cancel button.
"""

from __future__ import annotations

from typing import override

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget


class BusyOverlayWidget(QWidget):
    """Lightweight overlay that sits on top of a target widget.

    The overlay shows a message and a progress bar. Optionally, a centered
    cancel button can be displayed below the progress bar.

    By default, the overlay does not intercept mouse events. When the cancel
    button is shown, mouse transparency is disabled so the button can be used.
    """

    cancel_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget,
        *,
        message: str = "",
        indeterminate: bool = True,
    ) -> None:
        """Initialize the busy overlay.

        Args:
            parent: The widget to overlay.
            message: Message to display.
            indeterminate: Whether the progress bar should be indeterminate.
        """
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow
        )

        self.setStyleSheet(
            """
            QWidget#overlay {
                background-color: rgba(20, 20, 20, 128);
                border-radius: 6px;
            }
            QLabel#label {
                color: white;
                font-size: 12pt;
            }
            QProgressBar {
                border: 1px solid rgba(255,255,255,80);
                border-radius: 3px;
                background: rgba(0,0,0,0);
                color: white;
                min-height: 20px;
            }
            QProgressBar::chunk {
                background-color: rgba(255,255,255,180);
            }
            QPushButton#cancelButton {
                min-width: 110px;
                padding: 6px 14px;
            }
        """
        )

        self._container = QWidget(self)
        self._container.setObjectName("overlay")

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._label = QLabel(message or self.tr("Working…"), self._container)
        self._label.setObjectName("label")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._bar = QProgressBar(self._container)
        self._bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if indeterminate:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, 100)
            self._bar.setValue(0)
        layout.addWidget(self._bar)

        self._cancel_button = QPushButton(self.tr("Cancel"), self._container)
        self._cancel_button.setObjectName("cancelButton")
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(
            self._cancel_button,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        self.hide()

    def show_overlay(
        self,
        *,
        message: str | None = None,
        indeterminate: bool | None = None,
        show_cancel_button: bool = False,
        cancel_text: str | None = None,
    ) -> None:
        """Show the overlay with optional message, progress state, and cancel button.

        Args:
            message: Optional new message.
            indeterminate: Optional new progress mode.
            show_cancel_button: Whether to show the cancel button.
            cancel_text: Optional button text override.
        """
        if message is not None:
            self._label.setText(message)

        if indeterminate is not None:
            if indeterminate:
                self._bar.setRange(0, 0)
            else:
                self._bar.setRange(0, 100)
                self._bar.setValue(0)

        if cancel_text:
            self._cancel_button.setText(cancel_text)

        self._cancel_button.setVisible(show_cancel_button)

        # Overlay should only intercept mouse events when the cancel button
        # is active; otherwise it remains click-through.
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            not show_cancel_button,
        )

        self._relayout()
        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        """Hide the overlay and reset click-through behavior."""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._cancel_button.setVisible(False)
        self.hide()

    def set_progress(self, value: int) -> None:
        """Update the progress bar value.

        Args:
            value: Progress value in the range 0..100.
        """
        if self._bar.maximum() == 0:
            self._bar.setRange(0, 100)
        self._bar.setValue(max(0, min(100, int(value))))

    @override
    def resizeEvent(self, event) -> None:
        """Handle resize events and reposition the overlay.

        Args:
            event: Resize event.
        """
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        """Recalculate overlay and content geometry."""
        parent = self.parentWidget()
        if parent is None:
            return

        self.setGeometry(parent.rect())

        margin_w = max(32, int(self.width() * 0.2))
        width = max(240, self.width() - 2 * margin_w)

        size_hint = self._container.sizeHint()
        container_width = width
        container_height = size_hint.height()

        x = margin_w
        y = max(16, (self.height() - container_height) // 2)

        self._container.setGeometry(
            QRect(QPoint(x, y), self._container.sizeHint())
        )
        self._container.resize(container_width, container_height)
