"""Widget that visualizes join quality and metadata.

Provides:
  - Summary label (qualitative assessment)
  - Progress bars for match distribution
  - Metadata display

Designed to be embedded in dialogs (preview or result analysis).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.utils.format_utils import fmt_num


class JoinAnalysisWidget(QWidget):
    """Widget for displaying join success rate and metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the widget."""
        super().__init__(parent)

        root = QVBoxLayout(self)

        # ======================================================
        # Summary label (top)
        # ======================================================
        self.lbl_summary = QLabel()
        self.lbl_summary.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.lbl_summary)

        # ======================================================
        # Progress section
        # ======================================================
        self.pb_match = QProgressBar()
        self.pb_left = QProgressBar()
        self.pb_right = QProgressBar()

        for pb in (self.pb_match, self.pb_left, self.pb_right):
            pb.setRange(0, 100)
            pb.setTextVisible(True)

        root.addWidget(QLabel(self.tr("Match success")))
        root.addWidget(self.pb_match)

        root.addWidget(QLabel(self.tr("Left only")))
        root.addWidget(self.pb_left)

        root.addWidget(QLabel(self.tr("Right only")))
        root.addWidget(self.pb_right)

        # ======================================================
        # Metadata panel
        # ======================================================
        meta_box = QGroupBox(self.tr("Join metadata"))
        meta_layout = QFormLayout(meta_box)

        self.lbl_cardinality = QLabel()
        self.lbl_estimated_rows = QLabel()

        meta_layout.addRow(self.tr("Cardinality:"), self.lbl_cardinality)
        meta_layout.addRow(self.tr("Estimated number of rows:"), self.lbl_estimated_rows)

        root.addWidget(meta_box)

        # ======================================================
        # Styling colors
        # ======================================================
        self._apply_styles()

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def set_metadata(self, metadata: object) -> None:
        """Populate widget with join metadata.

        Args:
            metadata: JoinMetadata-like object with attributes:
                - match_rate: float
                - left_only: float
                - right_only: float
                - cardinality: str
                - estimated_rows: int (optional)
        """

        def to_pct(val: float) -> int:
            return int(max(0.0, min(1.0, val)) * 100)

        # --- progress bars ---
        self.pb_match.setValue(to_pct(getattr(metadata, "match_rate", 0.0)))
        self.pb_left.setValue(to_pct(getattr(metadata, "left_only", 0.0)))
        self.pb_right.setValue(to_pct(getattr(metadata, "right_only", 0.0)))

        # --- summary ---
        rate = getattr(metadata, "match_rate", 0.0)

        if rate > 0.9:
            text = self.tr("✅ Excellent match")
        elif rate > 0.7:
            text = self.tr("🟢 Good match")
        elif rate > 0.4:
            text = self.tr("⚠ Partial match")
        else:
            text = self.tr("❌ Poor match")

        self.lbl_summary.setText(text)

        # --- metadata ---
        self.lbl_cardinality.setText(str(getattr(metadata, "cardinality", "-")))
        est = getattr(metadata, "estimated_rows", None)

        if est is not None:
            self.lbl_estimated_rows.setText(fmt_num(est))
        else:
            self.lbl_estimated_rows.setText("-")

    # ---------------------------------------------------------
    # Styling
    # ---------------------------------------------------------

    def _apply_styles(self) -> None:
        """Apply clean, consistent styling."""
        base_style = """
        QProgressBar {
            border: none;
            background-color: #e0e0e0;
            text-align: center;
            height: 18px;
        }
        QProgressBar::chunk {
            border: none;
        }
        """

        self.pb_match.setStyleSheet(base_style + "QProgressBar::chunk { background-color: #4CAF50; }")

        self.pb_left.setStyleSheet(base_style + "QProgressBar::chunk { background-color: #FFC107; }")

        self.pb_right.setStyleSheet(base_style + "QProgressBar::chunk { background-color: #F44336; }")
