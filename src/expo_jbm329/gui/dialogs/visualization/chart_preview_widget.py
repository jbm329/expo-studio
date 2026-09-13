"""Chart preview widget for visualization dialog."""
from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ChartPreviewWidget(QWidget):
    """Widget for displaying a matplotlib chart preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the chart preview widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._figure = Figure(constrained_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        self._message_label = QLabel(self.tr("No visualization yet."), self)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._message_label)
        layout.addWidget(self._canvas)

        self._canvas.hide()

    @property
    def figure(self) -> Figure:
        """Return the matplotlib figure."""
        return self._figure

    def show_message(self, text: str) -> None:
        """Display a centered message instead of a chart.

        Args:
            text: Message to show.
        """
        self._message_label.setText(text)
        self._message_label.show()
        self._canvas.hide()

    def show_chart(self) -> None:
        """Display the chart canvas."""
        self._message_label.hide()
        self._canvas.show()
        self._canvas.draw_idle()

    def clear_chart(self) -> None:
        """Clear the current figure and show placeholder message."""
        self._figure.clear()
        self.show_message(self.tr("No visualization yet."))

    def refresh(self) -> None:
        """Redraw the chart canvas."""
        self._canvas.draw_idle()
