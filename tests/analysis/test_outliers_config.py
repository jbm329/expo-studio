from __future__ import annotations

import pandas as pd
from PyQt6.QtWidgets import QComboBox, QLabel

from expo_jbm329.gui.dialogs.analysis.outliers_config import OutliersConfigWidget
from expo_jbm329.services.analysis.outliers import (
    DEFAULT_THRESHOLDS,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    OutlierMethod,
    OutlierSummaryResult,
    analyze_outlier_summary,
)


def _result(method: OutlierMethod = OutlierMethod.IQR, threshold: float | None = None) -> OutlierSummaryResult:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 50.0], "b": [4.0, 5.0, 6.0, 7.0], "t": list("wxyz")})
    return analyze_outlier_summary(df, method, threshold)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


def _select_method(widget: OutliersConfigWidget, method: OutlierMethod) -> None:
    combo = widget._method_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(method))


# ----------------------------------------------------------------------
# Initial state
# ----------------------------------------------------------------------


def test_initial_state_reflects_the_result():
    widget = OutliersConfigWidget(_result(OutlierMethod.Z_SCORE, 2.5))
    combo = widget._method_combo  # noqa: SLF001

    assert [combo.itemData(i) for i in range(combo.count())] == list(OutlierMethod)
    assert widget.summary_configuration() == (OutlierMethod.Z_SCORE, 2.5)


def test_threshold_range():
    widget = OutliersConfigWidget(_result())
    spin = widget._threshold_spin  # noqa: SLF001

    assert spin.minimum() == MIN_THRESHOLD
    assert spin.maximum() == MAX_THRESHOLD


def test_configuration_has_no_column_selection_controls():
    widget = OutliersConfigWidget(_result())

    assert len(widget.findChildren(QComboBox)) == 2
    assert all(label.text() != widget.tr("Column") for label in widget.findChildren(QLabel))


def test_threshold_label_depends_on_the_method():
    iqr = OutliersConfigWidget(_result(OutlierMethod.IQR))
    z = OutliersConfigWidget(_result(OutlierMethod.Z_SCORE))

    assert iqr._threshold_label.text() == iqr.tr("IQR multiplier")  # noqa: SLF001
    assert z._threshold_label.text() == z.tr("Score threshold")  # noqa: SLF001
    assert iqr._threshold_spin.toolTip() != z._threshold_spin.toolTip()  # noqa: SLF001


def test_construction_does_not_emit():
    widget = OutliersConfigWidget(_result())

    assert _record(widget.summary_requested) == []


# ----------------------------------------------------------------------
# Method and threshold
# ----------------------------------------------------------------------


def test_method_change_resets_the_pending_threshold_without_emitting():
    widget = OutliersConfigWidget(_result(OutlierMethod.IQR, 3.0))
    received = _record(widget.summary_requested)

    _select_method(widget, OutlierMethod.MODIFIED_Z_SCORE)

    assert received == []
    assert widget.current_method() is OutlierMethod.MODIFIED_Z_SCORE
    assert widget.current_threshold() == DEFAULT_THRESHOLDS[OutlierMethod.MODIFIED_Z_SCORE]
    assert widget.summary_configuration() == (OutlierMethod.IQR, 3.0)
    assert widget._threshold_label.text() == widget.tr("Score threshold")  # noqa: SLF001


def test_threshold_change_is_pending_until_applied():
    widget = OutliersConfigWidget(_result())
    received = _record(widget.summary_requested)

    widget._threshold_spin.setValue(2.0)  # noqa: SLF001

    assert received == []
    assert widget.current_threshold() == 2.0
    assert widget.summary_configuration() == (OutlierMethod.IQR, 1.5)


def test_apply_stores_the_pending_configuration_and_emits():
    widget = OutliersConfigWidget(_result())
    received = _record(widget.summary_requested)
    _select_method(widget, OutlierMethod.Z_SCORE)
    widget._threshold_spin.setValue(2.5)  # noqa: SLF001

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.summary_configuration() == (OutlierMethod.Z_SCORE, 2.5)
