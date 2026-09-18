"""Preview dialog for join results.

Shows a preview of the joined DataFrame along with metadata
such as match rate, unmatched rows, and join type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.widgets.join_analysis_widget import JoinAnalysisWidget
from expo_jbm329.utils.models import JoinPreviewModel

if TYPE_CHECKING:
    import pandas as pd

    from expo_jbm329.services.data_operations.joins import JoinMetadata


class JoinPreviewDialog(QDialog):
    """Dialog that shows join preview and metadata."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        df: pd.DataFrame,
        metadata: JoinMetadata,
    ):
        """Initialize the JoinPreviewDialog.

        Args:
            parent: The parent widget (default is None).
            df: The DataFrame to preview.
            metadata: The metadata dictionary.
        """
        super().__init__(parent)

        self.setWindowTitle(self.tr("Join preview"))

        # Root layout
        root = QVBoxLayout(self)

        # ======================================================
        # Guard
        # ======================================================

        if "join_status" not in df.columns:
            df = df.copy()
            df["join_status"] = "both"

        # ======================================================
        # Preview table
        # ======================================================
        self.table = QTableView()
        self.model = JoinPreviewModel(df)
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self.table.horizontalHeader()
        if header:
            header.setStretchLastSection(True)
            header.setVisible(True)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        root.addWidget(self.table)

        # ======================================================
        # Metadata panel
        # ======================================================

        self.analysis = JoinAnalysisWidget(self)
        root.addWidget(self.analysis)

        # ======================================================
        # Buttons
        # ======================================================
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_close = QPushButton(self.tr("Close"))
        btn_close.clicked.connect(self.close)

        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        # ======================================================
        # Apply metadata
        # ======================================================
        self.analysis.set_metadata(metadata)

        # Size
        self.resize(800, 700)
