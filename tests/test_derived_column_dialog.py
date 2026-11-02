"""Existing derived column dialog supports typed formulas without a new editor."""

import pandas as pd
import pytest
from PyQt6.QtWidgets import QDialog

from expo_jbm329.gui.dialogs.workflows.derived_column.derived_column_dialog import DerivedColumnDialog
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    validate_derived_column_spec,
)


@pytest.mark.parametrize(
    "formula",
    [
        "IF([Vehicle] IN('BMW', 'Volvo'); 'Cars'; 'Other')",
        "IF([Column1] IS NULL; 'Empty'; [Column1])",
        "IF([Age] IS NULL; 0; [Age])",
    ],
)
def test_dialog_accepts_conditional_formulas_and_retains_existing_editor(formula, widget_language):
    frame = pd.DataFrame({
        "Vehicle": pd.Series(["BMW", None], dtype="string"),
        "Column1": pd.Series(["text", None], dtype="string"),
        "Age": pd.Series([1, None], dtype="Int64"),
    })

    def validate(name, text):
        result = validate_derived_column_spec(frame, DerivedColumnSpec(name, text))
        return result.ok, "Valid formula." if result.ok else result.error.code

    dialog = DerivedColumnDialog(df=frame, numeric_columns=["Age"], validate_callback=validate)
    dialog._column_name_edit.setText("Group")
    dialog._formula_edit.setPlainText(formula)
    assert dialog._ok_button.isEnabled()
    assert dialog._column_combo.count() == 1
    assert dialog._insert_btn.isEnabled()
    dialog._on_accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_result() == DerivedColumnSpec("Group", formula)


def test_text_only_dialog_retains_but_disables_empty_numeric_insertion_row():
    frame = pd.DataFrame({"Vehicle": ["BMW"]})
    dialog = DerivedColumnDialog(df=frame, numeric_columns=[], validate_callback=lambda name, text: (True, "Valid"))
    assert dialog._column_combo.count() == 0
    assert not dialog._insert_btn.isEnabled()
    dialog._on_insert_column()
    assert dialog._formula_edit.toPlainText() == ""
    dialog.reject()
    assert dialog.get_result() is None


def test_numeric_insertion_escapes_closing_bracket_in_column_name():
    dialog = DerivedColumnDialog(
        df=pd.DataFrame({"a]b": [1]}),
        numeric_columns=["a]b"],
        validate_callback=lambda name, text: (True, "Valid"),
    )
    dialog._on_insert_column()
    assert dialog._formula_edit.toPlainText() == "[a]]b] "


def test_invalid_formula_disables_accept_and_presents_validation_error():
    frame = pd.DataFrame({"Age": [1]})

    def validate(name, text):
        result = validate_derived_column_spec(frame, DerivedColumnSpec(name, text))
        return result.ok, "" if result.ok else result.error.code

    dialog = DerivedColumnDialog(df=frame, numeric_columns=["Age"], validate_callback=validate)
    dialog._column_name_edit.setText("Group")
    dialog._formula_edit.setPlainText("IF([Age] IS NULL; 'Empty'; [Age])")
    assert not dialog._ok_button.isEnabled()
    assert "incompatible_branch_types" in dialog._validation_label.text()
