from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from expo_jbm329.gui.dialogs.analysis.clustering_config import ClusteringConfigWidget
from expo_jbm329.services.analysis.clustering import ClusteringMethod, ClusteringResult


def _result(
    *,
    method: ClusteringMethod = ClusteringMethod.K_MEANS,
    columns: tuple[str, ...] = ("a", "b", "c"),
    standardize: bool = True,
) -> ClusteringResult:
    return ClusteringResult(
        method=method,
        columns=columns,
        available_columns=("a", "b", "c", "d"),
        standardize=standardize,
        cluster_count=4,
        dbscan_epsilon=0.75,
        dbscan_min_samples=6,
        total_rows=10,
        rows_used=10,
        rows_dropped=0,
        clusters=(),
        noise_count=0,
        silhouette_score=None,
        sample_pc1=(),
        sample_pc2=(),
        sample_labels=(),
        sampled=False,
        error=None,
    )


def _set_checked(widget: ClusteringConfigWidget, column: str, checked: bool) -> None:
    items = widget._column_list.findItems(column, Qt.MatchFlag.MatchExactly)  # noqa: SLF001
    assert len(items) == 1
    items[0].setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


@pytest.mark.parametrize("control", ["method", "scaling", "count", "epsilon", "samples", "feature"])
def test_every_configuration_edit_invalidates_without_requesting_fit(control):
    widget = ClusteringConfigWidget(_result())
    edits = _record(widget.configuration_changed)
    requests = _record(widget.analysis_requested)
    applied = widget.analysis_configuration()
    if control == "method":
        widget._method_combo.setCurrentIndex(1)  # noqa: SLF001
    elif control == "scaling":
        widget._standardize_checkbox.toggle()  # noqa: SLF001
    elif control == "count":
        widget._cluster_count_spin.setValue(5)  # noqa: SLF001
    elif control == "epsilon":
        widget._epsilon_spin.setValue(1.0)  # noqa: SLF001
    elif control == "samples":
        widget._min_samples_spin.setValue(7)  # noqa: SLF001
    else:
        _set_checked(widget, "d", True)
    assert edits == [()]
    assert widget.configuration_revision() == 1
    assert requests == []
    assert widget.analysis_configuration() == applied


def test_bulk_edits_emit_once_and_no_op_does_not_invalidate():
    widget = ClusteringConfigWidget(_result())
    edits = _record(widget.configuration_changed)
    widget._select_all_button.click()  # noqa: SLF001
    assert edits == [()]
    widget._select_all_button.click()  # noqa: SLF001
    assert edits == [()]
    widget._clear_button.click()  # noqa: SLF001
    assert edits == [(), ()]
    widget._clear_button.click()  # noqa: SLF001
    assert edits == [(), ()]


def test_initial_state_reflects_the_displayed_fit():
    widget = ClusteringConfigWidget(_result(method=ClusteringMethod.DBSCAN, columns=("b", "d"), standardize=False))

    assert widget.checked_columns() == ("b", "d")
    assert widget.current_method() is ClusteringMethod.DBSCAN
    assert widget.analysis_configuration() == (("b", "d"), ClusteringMethod.DBSCAN, False, 4, 0.75, 6)
    assert not widget._standardize_checkbox.isChecked()  # noqa: SLF001


def test_select_all_and_clear_update_pending_features_without_applying():
    widget = ClusteringConfigWidget(_result(columns=("a", "b")))
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
    widget = ClusteringConfigWidget(_result())
    received = _record(widget.analysis_requested)

    assert received == []


def test_method_switches_visible_parameters_without_requesting_analysis():
    widget = ClusteringConfigWidget(_result())
    received = _record(widget.analysis_requested)
    combo = widget._method_combo  # noqa: SLF001

    assert not widget._cluster_count_spin.isHidden()  # noqa: SLF001
    assert widget._epsilon_spin.isHidden()  # noqa: SLF001

    combo.setCurrentIndex(combo.findData(ClusteringMethod.DBSCAN))

    assert widget._cluster_count_spin.isHidden()  # noqa: SLF001
    assert not widget._epsilon_spin.isHidden()  # noqa: SLF001
    assert not widget._min_samples_spin.isHidden()  # noqa: SLF001
    assert received == []


def test_pending_changes_are_applied_together_on_apply():
    widget = ClusteringConfigWidget(_result())
    received = _record(widget.analysis_requested)
    _set_checked(widget, "c", False)
    widget._standardize_checkbox.setChecked(False)  # noqa: SLF001
    widget._method_combo.setCurrentIndex(widget._method_combo.findData(ClusteringMethod.DBSCAN))  # noqa: SLF001
    widget._epsilon_spin.setValue(1.25)  # noqa: SLF001
    widget._min_samples_spin.setValue(8)  # noqa: SLF001

    assert widget.analysis_configuration() == (("a", "b", "c"), ClusteringMethod.K_MEANS, True, 4, 0.75, 6)
    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.analysis_configuration() == (("a", "b"), ClusteringMethod.DBSCAN, False, 4, 1.25, 8)


def test_apply_can_rerun_an_unchanged_configuration():
    widget = ClusteringConfigWidget(_result())
    received = _record(widget.analysis_requested)

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]


def test_too_few_features_disable_apply_and_explain_why():
    widget = ClusteringConfigWidget(_result(columns=("a", "b")))
    received = _record(widget.analysis_requested)
    _set_checked(widget, "b", False)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert "at least" in widget._selection_label.text()  # noqa: SLF001
    widget._on_apply_clicked()  # noqa: SLF001
    assert received == []


def test_selection_label_shows_the_pending_count():
    widget = ClusteringConfigWidget(_result())

    assert widget._selection_label.text().startswith("3 selected")  # noqa: SLF001
