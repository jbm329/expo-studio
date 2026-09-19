"""Dialog for creating a derived numeric column."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.gui_utils import apply_window_hints_strict
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd


class DerivedColumnDialog(QDialog):
    """Dialog for creating a derived column."""

    def __init__(
        self,
        *,
        df: pd.DataFrame,
        numeric_columns: list[str],
        validate_callback: Callable[[str, str], tuple[bool, str]],
        parent: object=None,
    ) -> None:
        """Initialize dialog.

        Args:
            df: Current DataFrame.
            numeric_columns: List of numeric column names.
            validate_callback: Callback(column_name, formula) -> (ok, message)
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._df = df
        self._numeric_columns = numeric_columns
        self._validate_callback = validate_callback

        self._result: DerivedColumnSpec | None = None

        self.setWindowTitle(self.tr("Derived column"))
        self.setModal(True)

        self._build_ui()
        self._connect_signals()
        self._update_validation()
        apply_window_hints_strict(self, min_width=500, fixed_size=True)

    # ==============================================================
    # Public API
    # ==============================================================

    def get_result(self) -> DerivedColumnSpec | None:
        """Return dialog result."""
        return self._result

    # ==============================================================
    # UI setup
    # ==============================================================

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ------------------------------------------
        # Form inputs
        # ------------------------------------------
        form = QFormLayout()

        self._column_name_edit = QLineEdit()
        self._column_name_edit.setPlaceholderText(self.tr("New column name"))
        form.addRow(self.tr("Column name:"), self._column_name_edit)

        self._formula_edit = QTextEdit()
        self._formula_edit.setPlaceholderText("[A] / [B] * 100")
        self._formula_edit.setFixedHeight(80)
        form.addRow(self.tr("f(x):"), self._formula_edit)

        layout.addLayout(form)

        # ------------------------------------------
        # Insert column row
        # ------------------------------------------
        insert_layout = QHBoxLayout()

        self._column_combo = QComboBox()
        self._column_combo.addItems(self._numeric_columns)

        self._insert_btn = QPushButton(self.tr("Insert"))
        insert_layout.addWidget(QLabel(self.tr("Numeric columns:")))
        insert_layout.addWidget(self._column_combo)
        insert_layout.addWidget(self._insert_btn)

        layout.addLayout(insert_layout)

        # ------------------------------------------
        # Validation label
        # ------------------------------------------
        self._validation_label = QLabel()
        self._validation_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._validation_label.setWordWrap(True)

        layout.addWidget(self._validation_label)

        # ------------------------------------------
        # Buttons
        # ------------------------------------------
        self._buttons = QDialogButtonBox(parent=self)
        self._ok_button = self._buttons.addButton(QDialogButtonBox.StandardButton.Ok)
        self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(self._buttons)
        localize_dialog_buttons(self._buttons)

        # Disable OK initially
        if self._ok_button is not None:
            self._ok_button.setEnabled(False)

    # ==============================================================
    # Signals
    # ==============================================================

    def _connect_signals(self) -> None:
        self._insert_btn.clicked.connect(self._on_insert_column)
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)

        self._column_name_edit.textChanged.connect(self._update_validation)
        self._formula_edit.textChanged.connect(self._update_validation)

    # ==============================================================
    # Event handlers
    # ==============================================================

    def _on_insert_column(self) -> None:
        column = self._column_combo.currentText()

        insert_text = f"[{column}] "

        cursor = self._formula_edit.textCursor()
        cursor.insertText(insert_text)

        self._formula_edit.setFocus()
        self._update_validation()

    def _on_accept(self) -> None:
        column_name = self._column_name_edit.text().strip()
        formula = self._formula_edit.toPlainText().strip()

        self._result = DerivedColumnSpec(
            column_name=column_name,
            formula=formula,
        )

        self.accept()

    # ==============================================================
    # Validation
    # ==============================================================

    def _update_validation(self) -> None:

        column_name = self._column_name_edit.text().strip()
        formula = self._formula_edit.toPlainText().strip()

        if not column_name or not formula:
            self._set_validation_state(False, self.tr("Enter column name and formula."))
            return

        ok, message = self._validate_callback(column_name, formula)

        self._set_validation_state(ok, message)

    def _set_validation_state(self, ok: bool, message: str) -> None:
        """Update validation label and OK button."""
        if ok:
            self._validation_label.setText(self.tr(f"✅ {message or 'Invalid formula.'}"))
            self._validation_label.setStyleSheet("color: #2e7d32;")
        else:
            self._validation_label.setText(f"❌ {message}")
            self._validation_label.setStyleSheet("color: #c62828;")

        if self._ok_button is not None:
            self._ok_button.setEnabled(ok)
