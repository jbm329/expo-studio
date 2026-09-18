from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations import category_orders, datetime_formats
from expo_jbm329.services.data_operations._internal import drop_column
from expo_jbm329.services.data_operations._regex import _DATE_RE, _DATETIME_RE, _TIME_RE


def test_category_order_keys():
    assert category_orders.CategoryOrderKey.__args__ == ("alpha", "freq", "preserve")


def test_datetime_format_map():
    assert datetime_formats.FORMAT_MAP["iso_date"]["fmt"] == "%Y-%m-%d"
    assert datetime_formats.FORMAT_MAP["dmy_slash"]["dayfirst"] is True
    assert datetime_formats.FORMAT_MAP["auto"]["fmt"] is None


def test_regex_patterns_match_expected_strings():
    assert _DATE_RE.match("2026-09-14")
    assert _DATETIME_RE.match("2026-09-14 14:44:00")
    assert _DATETIME_RE.match("2026-09-14T14:44")
    assert _TIME_RE.match("14:44")
    assert not _DATE_RE.match("14/09/2026")


def test_drop_column_removes_column_and_raises_for_missing():
    df = pd.DataFrame({"a": [1], "b": [2]})
    result = drop_column(df, "a")

    assert list(result.columns) == ["b"]

    with pytest.raises(KeyError, match="not found"):
        drop_column(df, "missing")
