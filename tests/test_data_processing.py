import sys
from unittest.mock import MagicMock, patch

# Mock ydata_profiling before importing data_processing if it's not present
if "ydata_profiling" not in sys.modules:
    sys.modules["ydata_profiling"] = MagicMock()

import pandas as pd
import pytest
from expo_jbm329.services import data_processing

@patch("ydata_profiling.ProfileReport")
def test_generate_profile_report(mock_report):
    df = pd.DataFrame({"A": [1, 2, 3]})
    mock_instance = MagicMock()
    mock_report.return_value = mock_instance
    
    res = data_processing.generate_profile_report(df, "Title", "corr-123")
    
    assert res == mock_instance
    mock_report.assert_called_once()
    # Check that it was called with df and title
    args, kwargs = mock_report.call_args
    assert args[0] is df
    assert kwargs["title"] == "Title"

@patch("ydata_profiling.compare")
@patch("ydata_profiling.ProfileReport")
def test_generate_comparison_profile_report(mock_report, mock_compare):
    df1 = pd.DataFrame({"A": [1, 2]})
    df2 = pd.DataFrame({"A": [3, 4]})
    data = [(df1, "T1"), (df2, "T2")]
    
    mock_report.side_effect = [MagicMock(), MagicMock()]
    mock_compare.return_value = MagicMock()
    
    res = data_processing.generate_comparison_profile_report(data, "corr-456")
    
    assert res == mock_compare.return_value
    assert mock_report.call_count == 2
    mock_compare.assert_called_once()
