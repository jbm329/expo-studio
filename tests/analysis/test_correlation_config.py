from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QGroupBox

from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.services.analysis.correlation import (
    MAX_SELECTED_COLUMNS,
    CorrelationMatrixResult,
    CorrelationMethod,
)


def _make_result(
    columns: tuple[str, ...] = ("a", "b"),
    available_columns: tuple[str, ...] = ("a", "b", "c", "d"),
    method: CorrelationMethod = CorrelationMethod.PEARSON,
) -> CorrelationMatrixResult:
    return CorrelationMatrixResult(
        method=method,
        columns=columns,
        available_columns=available_columns,
        coefficients=(),
        pairs=(),
        error=None,
    )


def _set_checked(widget: CorrelationConfigWidget, column: str, checked: bool) -> None:
    items = widget._column_list.findItems(column, Qt.MatchFlag.MatchExactly)  # noqa: SLF001
    assert len(items) == 1
    items[0].setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


# ----------------------------------------------------------------------
# Initial state
# ----------------------------------------------------------------------


def test_method_combo_lists_every_method_and_selects_the_results():
    widget = CorrelationConfigWidget(_make_result(method=CorrelationMethod.SPEARMAN))
    combo = widget._method_combo  # noqa: SLF001

    assert [combo.itemData(i) for i in range(combo.count())] == list(CorrelationMethod)
    assert widget.current_method() is CorrelationMethod.SPEARMAN


def test_configuration_has_only_the_method_combo_and_no_scatterplot_group():
    widget = CorrelationConfigWidget(_make_result())

    assert widget.findChildren(QComboBox) == [widget._method_combo]  # noqa: SLF001
    assert all(group.title() != "Scatterplot" for group in widget.findChildren(QGroupBox))


def test_column_list_checks_the_results_columns():
    widget = CorrelationConfigWidget(_make_result(columns=("b", "d")))

    assert widget._column_list.count() == 4  # noqa: SLF001
    assert widget.checked_columns() == ("b", "d")
    assert widget.applied_columns() == ("b", "d")
    assert widget.matrix_configuration() == (CorrelationMethod.PEARSON, ("b", "d"))


def test_select_all_and_clear_update_pending_matrix_columns_without_applying():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b")))
    received = _record(widget.matrix_requested)

    assert widget._select_all_button.text() == "Select all"  # noqa: SLF001
    assert widget._clear_button.text() == "Clear"  # noqa: SLF001
    group_layout = widget._select_all_button.parentWidget().layout()  # noqa: SLF001
    assert group_layout.itemAt(0).widget() is widget._column_list  # noqa: SLF001
    button_row = group_layout.itemAt(1).layout()
    assert button_row.indexOf(widget._select_all_button) >= 0  # noqa: SLF001
    assert button_row.indexOf(widget._clear_button) >= 0  # noqa: SLF001
    widget._clear_button.click()  # noqa: SLF001
    assert widget.checked_columns() == ()
    assert widget.applied_columns() == ("a", "b")
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    widget._select_all_button.click()  # noqa: SLF001
    assert widget.checked_columns() == ("a", "b", "c", "d")
    assert widget.applied_columns() == ("a", "b")
    assert widget._apply_button.isEnabled()  # noqa: SLF001
    assert received == []


# ----------------------------------------------------------------------
# Method
# ----------------------------------------------------------------------


def test_method_change_is_pending_until_applied():
    widget = CorrelationConfigWidget(_make_result())
    received = _record(widget.matrix_requested)
    _set_checked(widget, "c", checked=True)

    widget._method_combo.setCurrentIndex(widget._method_combo.findData(CorrelationMethod.KENDALL))  # noqa: SLF001

    assert received == []
    assert widget.current_method() is CorrelationMethod.KENDALL
    assert widget.applied_method() is CorrelationMethod.PEARSON
    assert widget.matrix_configuration() == (CorrelationMethod.PEARSON, ("a", "b"))

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.matrix_configuration() == (CorrelationMethod.KENDALL, ("a", "b", "c"))


# ----------------------------------------------------------------------
# Columns and Apply
# ----------------------------------------------------------------------


def test_checking_a_column_does_not_request_a_matrix_until_applied():
    widget = CorrelationConfigWidget(_make_result())
    received = _record(widget.matrix_requested)

    _set_checked(widget, "c", checked=True)

    assert received == []
    assert widget.checked_columns() == ("a", "b", "c")
    assert widget.applied_columns() == ("a", "b")

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.applied_columns() == ("a", "b", "c")


def test_apply_reruns_an_unchanged_selection():
    widget = CorrelationConfigWidget(_make_result())
    received = _record(widget.matrix_requested)

    assert widget._apply_button.isEnabled()  # noqa: SLF001
    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]


def test_too_few_checked_columns_disable_apply_with_a_hint():
    widget = CorrelationConfigWidget(_make_result())
    received = _record(widget.matrix_requested)

    _set_checked(widget, "b", checked=False)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert "at least" in widget._selection_label.text()  # noqa: SLF001
    widget._on_apply_clicked()  # noqa: SLF001
    assert received == []
    assert widget.applied_columns() == ("a", "b")


def test_too_many_checked_columns_disable_apply_with_a_hint():
    available = tuple(f"c{i}" for i in range(MAX_SELECTED_COLUMNS + 1))
    widget = CorrelationConfigWidget(_make_result(columns=available[:2], available_columns=available))

    for column in available:
        _set_checked(widget, column, checked=True)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert "at most" in widget._selection_label.text()  # noqa: SLF001

    _set_checked(widget, available[0], checked=False)

    assert widget._apply_button.isEnabled()  # noqa: SLF001


def test_selection_label_shows_the_checked_count():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b", "c")))

    assert widget._selection_label.text().startswith("3 selected")  # noqa: SLF001
