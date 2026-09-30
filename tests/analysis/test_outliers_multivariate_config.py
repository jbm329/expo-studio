from __future__ import annotations

from PyQt6.QtCore import Qt

from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.services.analysis.multivariate_outliers import (
    MultivariateOutlierMethod,
    MultivariateOutlierResult,
)


def _result(
    method: MultivariateOutlierMethod = MultivariateOutlierMethod.ISOLATION_FOREST,
) -> MultivariateOutlierResult:
    return MultivariateOutlierResult(
        method=method,
        columns=("a", "b", "c"),
        available_columns=("a", "b", "c", "d"),
        standardize=True,
        contamination=0.05,
        lof_neighbors=20,
        total_rows=10,
        rows_used=10,
        rows_dropped=0,
        outlier_count=1,
        inlier_count=9,
        sample_pc1=(),
        sample_pc2=(),
        sample_outliers=(),
        sampled=False,
        row_columns=(),
        extremes=(),
        error=None,
    )


def _set_checked(widget: MultivariateOutliersConfigWidget, column: str, checked: bool) -> None:
    items = widget._column_list.findItems(column, Qt.MatchFlag.MatchExactly)  # noqa: SLF001
    assert len(items) == 1
    items[0].setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


def test_initial_state_reflects_result():
    widget = MultivariateOutliersConfigWidget(_result(MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR))

    assert widget.analysis_configuration() == (
        ("a", "b", "c"),
        MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR,
        True,
        0.05,
        20,
    )
    assert not widget._neighbors_spin.isHidden()  # noqa: SLF001


def test_select_all_and_clear_update_pending_features_without_applying():
    widget = MultivariateOutliersConfigWidget(_result())
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
    assert widget.analysis_configuration()[0] == ("a", "b", "c")
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    widget._select_all_button.click()  # noqa: SLF001
    assert widget.checked_columns() == ("a", "b", "c", "d")
    assert widget.analysis_configuration()[0] == ("a", "b", "c")
    assert widget._apply_button.isEnabled()  # noqa: SLF001
    assert received == []


def test_method_switch_toggles_lof_neighbors_without_requesting_analysis():
    widget = MultivariateOutliersConfigWidget(_result())
    received = _record(widget.analysis_requested)

    assert widget._neighbors_spin.isHidden()  # noqa: SLF001
    combo = widget._method_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR))

    assert not widget._neighbors_spin.isHidden()  # noqa: SLF001
    assert received == []


def test_apply_captures_pending_configuration_and_emits():
    widget = MultivariateOutliersConfigWidget(_result())
    received = _record(widget.analysis_requested)
    _set_checked(widget, "c", False)
    widget._standardize_checkbox.setChecked(False)  # noqa: SLF001
    combo = widget._method_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR))
    widget._contamination_spin.setValue(10.0)  # noqa: SLF001
    widget._neighbors_spin.setValue(10)  # noqa: SLF001

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.analysis_configuration() == (
        ("a", "b"),
        MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR,
        False,
        0.1,
        10,
    )


def test_too_few_features_disable_apply():
    widget = MultivariateOutliersConfigWidget(_result())
    received = _record(widget.analysis_requested)
    _set_checked(widget, "b", False)
    _set_checked(widget, "c", False)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert "at least" in widget._selection_label.text()  # noqa: SLF001
    widget._on_apply_clicked()  # noqa: SLF001
    assert received == []


def test_univariate_mode_emits_a_switch_request():
    widget = MultivariateOutliersConfigWidget(_result())
    received = _record(widget.univariate_requested)

    widget._mode_combo.setCurrentIndex(0)  # noqa: SLF001

    assert received == [()]
