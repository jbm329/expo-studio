import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from expo_jbm329.utils.format_utils import (
    fmt_bytes,
    fmt_category,
    fmt_date,
    fmt_int,
    fmt_num,
    fmt_path,
    fmt_path_size,
    fmt_pct,
    fmt_shape,
    fmt_time,
    fmt_timedelta,
    tuple_to_posix,
)


def test_fmt_pct():
    result = fmt_pct(0.123456, decimals=2)
    assert "12.35%" in result or "12,35%" in result

    result_4 = fmt_pct(0.123456, decimals=4)
    assert "12.3456%" in result_4 or "12,3456%" in result_4


def test_fmt_bytes():
    assert "512 B" in fmt_bytes(512)
    assert "1,00 KB" in fmt_bytes(1024) or "1.00 KB" in fmt_bytes(1024)
    assert "1,00 MB" in fmt_bytes(1024 * 1024) or "1.00 MB" in fmt_bytes(1024 * 1024)


def test_fmt_path_size_for_missing_and_existing_file(tmp_path):
    missing = tmp_path / "missing.txt"
    assert fmt_path_size(missing) == ""

    file_path = tmp_path / "data.txt"
    file_path.write_text("hello", encoding="utf-8")
    assert fmt_path_size(file_path).startswith(" (")
    assert "B" in fmt_path_size(file_path)


def test_fmt_num():
    assert fmt_num(None) == ""
    assert fmt_num(np.nan) == ""
    assert fmt_num(123) == "123"

    result = fmt_num(1.23456, sig=4)
    assert "1,23" in result or "1.23" in result

    result2 = fmt_num(123.456, sig=4)
    assert "123" in result2


def test_fmt_int():
    result = fmt_int(1234)
    assert any(s in result for s in ["1 234", "1\u00A0234", "1,234", "1.234"])


def test_fmt_shape():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    assert fmt_shape(df) == (fmt_int(2), fmt_int(2))
    assert fmt_shape(None) == ("?", "?")


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
    assert fmt_path(Path("folder/subfolder")) == "folder/subfolder"


def test_tuple_to_posix():
    inp = ("C:\\Path", 123, None)
    assert tuple_to_posix(inp) == ("C:/Path", 123, None)
