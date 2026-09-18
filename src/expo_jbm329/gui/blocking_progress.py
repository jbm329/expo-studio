"""Blocking progress dialog for heavy operations.

This module provides a modal dialog that shows a progress bar and a status message,
blocking the UI while a long-running job is in progress.
"""
from __future__ import annotations

import contextlib

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from expo_jbm329.gui.gui_utils import apply_window_hints_strict


class BlockingProgressDialog(QDialog):
    """Modal dialog with deterministic progress and status.

    Used for heavy jobs to block the UI and provide feedback to the user.

    Attributes:
        label: The label displaying the status message.
        progress: The progress bar widget.
        btn_cancel: The cancel button.
    """

    def __init__(self, parent=None, title: str = "Arbetar...", started_msg: str = ""):
        """Initialize the progress dialog.

        Args:
            parent: The parent widget.
            title: The window title.
            started_msg: The initial status message.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        lay = QVBoxLayout(self)
        self.label = QLabel(started_msg or "Arbetar…", self)
        self.label.setWordWrap(True)
        lay.addWidget(self.label)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        lay.addWidget(self.progress)

        btn_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Avbryt", self)
        self.btn_cancel.setEnabled(True)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        lay.addLayout(btn_row)

        apply_window_hints_strict(self, min_width=420, fixed_size=True, show_close_button=False)

    @pyqtSlot()
    def on_started(self):
        """Handle the job start event."""
        # Can update text...

    @pyqtSlot(int)
    def on_progress(self, v: int):
        """Update the progress bar value.

        Args:
            v: The progress value (0-100).
        """
        v = max(0, min(100, int(v)))
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(v)

    @pyqtSlot()
    def on_finished(self):
        """Handle the job completion event."""
        self.accept()

    @pyqtSlot(str)
    def on_error(self, traceback_str: str):
        """Handle the job error event.

        Args:
            traceback_str: The error traceback string.
        """
        self.reject()

    def set_started_msg(self, text: str):
        """Set the initial status message.

        Args:
            text: The message to display.
        """
        self.label.setText(text or "")

    def attach_cancel(self, job_id: str, job_manager):
        """Connect the cancel button to the job manager.

        Args:
            job_id: The ID of the job to cancel.
            job_manager: The manager responsible for the job.
        """
        def do_cancel():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("Avbryter…")

            with contextlib.suppress(Exception):
                job_manager.cancel_job(job_id)

        self.btn_cancel.clicked.connect(do_cancel)



