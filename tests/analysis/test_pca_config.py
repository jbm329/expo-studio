from __future__ import annotations

from PyQt6.QtCore import Qt

from expo_jbm329.gui.dialogs.analysis.pca_config import PCAConfigWidget
from expo_jbm329.services.analysis.pca import PCAResult


def _result(
    columns: tuple[str, ...] = ("a", "b", "c"),
    available_columns: tuple[str, ...] = ("a", "b", "c", "d"),
    *,
    standardize: bool = True,
) -> PCAResult:
    return PCAResult(
        columns=columns,
        available_columns=available_columns,
        standardize=standardize,
        total_rows=4,
        rows_used=4,
        rows_dropped=0,
        explained_variance=(),
        explained_variance_ratio=(),
        cumulative_variance_ratio=(),
        loadings=(),
        sample_pc1=(),
        sample_pc2=(),
        sampled=False,
        error=None,
    )


def _set_checked(widget: PCAConfigWidget, column: str, checked: bool) -> None:
    items = widget._column_list.findItems(column, Qt.MatchFlag.MatchExactly)  # noqa: SLF001
    assert len(items) == 1
    items[0].setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


def test_initial_state_reflects_the_displayed_fit():
    widget = PCAConfigWidget(_result(columns=("b", "d"), standardize=False))

    assert widget.checked_columns() == ("b", "d")
    assert widget.analysis_configuration() == (("b", "d"), False)
    assert not widget._standardize_checkbox.isChecked()  # noqa: SLF001


def test_select_all_and_clear_update_pending_features_without_applying():
    widget = PCAConfigWidget(_result(columns=("a", "b")))
    received = _record(widget.analysis_requested)

    assert widget._select_all_button.text() == "Select all"  # noqa: SLF001
    assert widget._clear_button.text() == "Clear"  # noqa: SLF001
    group_layout = widget._select_all_button.parentWidget().layout()  # noqa: SLF001
    assert group_layout.itemAt(0).widget() is widget._column_list  # noqa: SLF001
    button_row = group_layout.itemAt(1).layout()
    assert button_row.indexOf(widget._select_all_button) >= 0  # noqa: SLF001
    assert button_row.indexOf(widget._clear_button) >= 0  # noqa: SLF001
    widget._clear_button.click()  # noqa: SLF001
    assert widget.checked_columns() == ()
    assert widget.analysis_configuration()[0] == ("a", "b")
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    widget._select_all_button.click()  # noqa: SLF001
    assert widget.checked_columns() == ("a", "b", "c", "d")
    assert widget.analysis_configuration()[0] == ("a", "b")
    assert widget._apply_button.isEnabled()  # noqa: SLF001
    assert received == []


def test_initial_population_does_not_request_analysis():
    widget = PCAConfigWidget(_result())
    received = _record(widget.analysis_requested)

    assert received == []


def test_changing_pending_columns_does_not_request_analysis_until_apply():
    widget = PCAConfigWidget(_result(columns=("a", "b")))
    received = _record(widget.analysis_requested)

    _set_checked(widget, "c", True)

    assert widget.checked_columns() == ("a", "b", "c")
    assert widget.analysis_configuration() == (("a", "b"), True)
    assert received == []

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.analysis_configuration() == (("a", "b", "c"), True)


def test_apply_stores_the_standardization_choice():
    widget = PCAConfigWidget(_result())
    received = _record(widget.analysis_requested)

    widget._standardize_checkbox.setChecked(False)  # noqa: SLF001
    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.analysis_configuration() == (("a", "b", "c"), False)


def test_apply_can_rerun_an_unchanged_configuration():
    widget = PCAConfigWidget(_result())
    received = _record(widget.analysis_requested)

    assert widget._apply_button.isEnabled()  # noqa: SLF001
    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]


def test_fewer_than_two_features_disable_apply_and_explain_why():
    widget = PCAConfigWidget(_result(columns=("a", "b")))
    received = _record(widget.analysis_requested)

    _set_checked(widget, "b", False)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert "at least" in widget._selection_label.text()  # noqa: SLF001
    widget._on_apply_clicked()  # noqa: SLF001
    assert received == []
    assert widget.analysis_configuration() == (("a", "b"), True)


def test_selection_label_shows_the_pending_count():
    widget = PCAConfigWidget(_result())

    assert widget._selection_label.text().startswith("3 selected")  # noqa: SLF001
