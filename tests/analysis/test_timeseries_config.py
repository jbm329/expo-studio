from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.gui.dialogs.analysis.timeseries_config import TimeSeriesConfigWidget
from expo_jbm329.services.analysis.timeseries import DecompositionModel, analyze_time_series


def _result():
    df = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=21, freq="D"),
        "value": range(21),
        "other": range(100, 121),
    })
    result = analyze_time_series(df)
    assert result.error is None
    return result


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


@pytest.mark.parametrize(
    ("control", "setter", "value"),
    [
        ("_datetime_combo", "setCurrentIndex", -1),
        ("_value_combo", "setCurrentIndex", 1),
        ("_frequency_combo", "setCurrentIndex", 1),
        ("_auto_period", "setChecked", True),
        ("_period_spin", "setValue", 4),
        ("_model_combo", "setCurrentIndex", 1),
    ],
)
def test_every_control_edit_invalidates_without_requesting_analysis(control, setter, value):
    widget = TimeSeriesConfigWidget(_result())
    edits = _record(widget.configuration_changed)
    requests = _record(widget.analysis_requested)
    applied = widget.analysis_configuration()
    getattr(getattr(widget, control), setter)(value)
    assert edits == [()]
    assert requests == []
    assert widget.analysis_configuration() == applied
    assert widget.configuration_revision() == 1
    getattr(getattr(widget, control), setter)(value)
    assert edits == [()]


def test_initial_configuration_reflects_the_result():
    widget = TimeSeriesConfigWidget(_result())

    assert widget.analysis_configuration() == ("when", "value", None, 7, DecompositionModel.ADDITIVE)
    assert not widget._auto_period.isChecked()  # noqa: SLF001


def test_auto_period_disables_manual_period():
    widget = TimeSeriesConfigWidget(_result())

    widget._auto_period.setChecked(True)  # noqa: SLF001

    assert not widget._period_spin.isEnabled()  # noqa: SLF001
    assert widget.pending_configuration()[3] is None


def test_apply_captures_controls_and_emits_once():
    widget = TimeSeriesConfigWidget(_result())
    received = _record(widget.analysis_requested)

    widget._value_combo.setCurrentIndex(widget._value_combo.findText("other"))  # noqa: SLF001
    widget._frequency_combo.setCurrentIndex(widget._frequency_combo.findData("W"))  # noqa: SLF001
    widget._period_spin.setValue(4)  # noqa: SLF001
    widget._model_combo.setCurrentIndex(widget._model_combo.findData(DecompositionModel.MULTIPLICATIVE))  # noqa: SLF001
    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.analysis_configuration() == ("when", "other", "W", 4, DecompositionModel.MULTIPLICATIVE)
