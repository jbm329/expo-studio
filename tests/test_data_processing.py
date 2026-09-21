from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

if "ydata_profiling" not in sys.modules:
    sys.modules["ydata_profiling"] = MagicMock()

import pandas as pd

from expo_jbm329.services import data_processing


@patch("ydata_profiling.ProfileReport")
def test_generate_profile_report(mock_report):
    df = pd.DataFrame({"A": [1, 2, 3]})
    instance = MagicMock()
    mock_report.return_value = instance

    result = data_processing.generate_profile_report(df, "Title", "corr-123")

    assert result is instance
    mock_report.assert_called_once()
    args, kwargs = mock_report.call_args
    assert args[0] is df
    assert kwargs["title"] == "Title"
    assert kwargs["explorative"] is True
    assert kwargs["progress_bar"] is False


@patch("ydata_profiling.compare")
@patch("ydata_profiling.ProfileReport")
def test_generate_comparison_profile_report(mock_report, mock_compare):
    df1 = pd.DataFrame({"A": [1, 2]})
    df2 = pd.DataFrame({"A": [3, 4]})
    data = [(df1, "T1"), (df2, "T2")]

    mock_report.side_effect = [MagicMock(), MagicMock()]
    mock_compare.return_value = MagicMock()

    result = data_processing.generate_comparison_profile_report(data, "corr-456")

    assert result is mock_compare.return_value
    assert mock_report.call_count == 2
    mock_compare.assert_called_once()
