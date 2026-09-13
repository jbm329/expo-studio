import datetime
import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import QLocale
from expo_jbm329.utils.format_utils import (
    fmt_pct,
    fmt_bytes,
    fmt_num,
    fmt_int,
    fmt_date,
    fmt_time,
    fmt_datetime_auto,
    fmt_timedelta,
    fmt_category,
    fmt_path,
    tuple_to_posix,
    is_date_only_series
)

def test_fmt_pct():
    val = 0.123456
    result = fmt_pct(val, decimals=2)
    # Handle both . and , as decimal separator
    assert "12.35%" in result or "12,35%" in result
    
    result_4 = fmt_pct(val, decimals=4)
    assert "12.3456%" in result_4 or "12,3456%" in result_4

def test_fmt_bytes():
    assert "512 B" in fmt_bytes(512)
    assert "1,00 KB" in fmt_bytes(1024) or "1.00 KB" in fmt_bytes(1024)
    assert "1,00 MB" in fmt_bytes(1024*1024) or "1.00 MB" in fmt_bytes(1024*1024)

def test_fmt_num():
    assert fmt_num(None) == ""
    assert fmt_num(np.nan) == ""
    assert fmt_num(123) == "123"
    
    # Significant digits (numpy positional might round slightly differently than expected)
    result = fmt_num(1.23456, sig=4)
    assert "1,23" in result or "1.23" in result
    
    result2 = fmt_num(123.456, sig=4)
    assert "123" in result2

def test_fmt_int():
    result = fmt_int(1234)
    # Handle common separators: space, non-breaking space, comma, dot
    assert any(s in result for s in ["1 234", "1\u00A0234", "1,234", "1.234"])

def test_fmt_date():
    dt = datetime.date(2023, 10, 5)
    assert fmt_date(dt) == "2023-10-05"
    
    dttm = datetime.datetime(2023, 10, 5, 12, 30)
    assert fmt_date(dttm) == "2023-10-05"
    assert fmt_date(None) == ""

def test_fmt_time():
    assert fmt_time(3661) == "1:01:01"
    assert fmt_time(61) == "1:01"
    assert fmt_time(5) == "0:05"

def test_fmt_datetime_auto():
    dt_only = datetime.datetime(2023, 10, 5, 0, 0, 0)
    assert fmt_datetime_auto(dt_only) == "2023-10-05"
    
    dt_full = datetime.datetime(2023, 10, 5, 12, 30, 45)
    assert fmt_datetime_auto(dt_full) == "2023-10-05 12:30:45"
    
    assert fmt_datetime_auto(None) == ""
    assert fmt_datetime_auto("not a date") == "not a date"

def test_fmt_timedelta():
    td = datetime.timedelta(days=1, hours=2, minutes=3, seconds=4)
    assert fmt_timedelta(td) == "1 d 02:03:04"
    
    td2 = datetime.timedelta(hours=12, minutes=34, seconds=56)
    assert fmt_timedelta(td2) == "12:34:56"
    
    assert fmt_timedelta(None) == ""

def test_fmt_category():
    assert fmt_category("Test") == "Test"
    assert fmt_category(123) == "123"
    assert fmt_category(None) == ""
    assert fmt_category(np.nan) == ""

def test_fmt_path():
    assert fmt_path("C:\\Users\\Test") == "C:/Users/Test"
    assert fmt_path("folder/subfolder") == "folder/subfolder"

def test_tuple_to_posix():
    inp = ("C:\\Path", 123, None)
    out = tuple_to_posix(inp)
    assert out == ("C:/Path", 123, None)

def test_is_date_only_series():
    s_date = pd.Series(pd.to_datetime(["2023-01-01", "2023-01-02"], format="ISO8601"))
    assert bool(is_date_only_series(s_date)) is True
    
    s_time = pd.Series(pd.to_datetime(["2023-01-01 12:00:00", "2023-01-02 00:00:00"], format="ISO8601"))
    assert bool(is_date_only_series(s_time)) is False
    
    s_empty = pd.Series(pd.to_datetime([], format="ISO8601"))
    assert bool(is_date_only_series(s_empty)) is False
    
    s_not_dt = pd.Series([1, 2, 3])
    assert bool(is_date_only_series(s_not_dt)) is False
