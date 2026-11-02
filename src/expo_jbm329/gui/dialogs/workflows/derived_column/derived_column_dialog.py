"""Dialog for creating a derived numeric or text column."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.workflows.derived_column.formula_editor import FormulaEditor
from expo_jbm329.gui.dialogs.workflows.derived_column.month_labels import capture_month_labels
from expo_jbm329.gui.gui_utils import apply_window_hints_strict
from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    ExpressionType,
    expression_columns,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

    from expo_jbm329.services.data_operations.derived_column.derived_column_parser import FormulaValidationResult


class DerivedColumnDialog(QDialog):
    """Dialog for creating a derived column."""

    def __init__(
        self,
        *,
        df: pd.DataFrame,
        validate_callback: Callable[[str, str], tuple[FormulaValidationResult, str]],
        parent: QWidget | None = None,
    ) -> None:
        """Initialize dialog.

        Args:
            df: Current DataFrame.
            validate_callback: Callback returning structured validation and a localized message.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._columns = expression_columns(list(df.columns), list(df.dtypes))
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

        self._formula_edit = FormulaEditor(
            [
                column.name
                for column in self._columns
                if column.available and column.value_type != ExpressionType.UNSUPPORTED
            ],
            self,
        )
        self._formula_edit.setPlaceholderText("[A] / [B] * 100")
        self._formula_edit.setAccessibleName(self.tr("f(x):"))
        self._formula_edit.setFixedHeight(80)
        form.addRow(self.tr("f(x):"), self._formula_edit)

        layout.addLayout(form)

        # ------------------------------------------
        # Validation label
        # ------------------------------------------
        self._validation_label = QLabel()
        self._validation_label.setTextFormat(Qt.TextFormat.PlainText)
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
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)

        self._column_name_edit.textChanged.connect(self._update_validation)
        self._formula_edit.textChanged.connect(self._update_validation)

    # ==============================================================
    # Event handlers
    # ==============================================================

    def _on_accept(self) -> None:
        self._update_validation()
        if self._ok_button is None or not self._ok_button.isEnabled():
            return
        column_name = self._column_name_edit.text().strip()
        formula = self._formula_edit.toPlainText().strip()

        self._result = DerivedColumnSpec(
            column_name=column_name,
            formula=formula,
            month_labels=capture_month_labels(),
        )

        self.accept()

    # ==============================================================
    # Validation
    # ==============================================================

    def _update_validation(self) -> None:

        column_name = self._column_name_edit.text().strip()
        formula = self._formula_edit.toPlainText()

        if not column_name or not formula.strip():
            self._formula_edit.set_diagnostic(None)
            self._set_validation_state(False, self.tr("Enter column name and formula."))
            return

        result, message = self._validate_callback(column_name, formula)
        self._formula_edit.set_diagnostic(result.error, message)

        self._set_validation_state(result.ok, message)

    def _set_validation_state(self, ok: bool, message: str) -> None:
        """Update validation label and OK button."""
        if ok:
            self._validation_label.setText(f"✅ {message}")
            self._validation_label.setStyleSheet("color: #2e7d32;")
        else:
            self._validation_label.setText(f"❌ {message}")
            self._validation_label.setStyleSheet("color: #c62828;")

        if self._ok_button is not None:
            self._ok_button.setEnabled(ok)
