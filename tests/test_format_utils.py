import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import QLocale
from pytest import MonkeyPatch

from expo_jbm329.utils.format_utils import (
    fmt_bytes,
    fmt_category,
    fmt_cell,
    fmt_date,
    fmt_float_fixed,
    fmt_int,
    fmt_num,
    fmt_p_value,
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


def test_fmt_path_size_for_missing_and_existing_file(tmp_path: Path) -> None:
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


@pytest.mark.parametrize(
    ("locale_name", "expected"),
    [
        ("en_US", "1,234.50"),
        ("sv_SE", "1\u00a0234,50"),
        ("de_DE", "1.234,50"),
    ],
)
def test_fmt_float_fixed_localizes_grouping_and_decimals(
    monkeypatch: MonkeyPatch, locale_name: str, expected: str
) -> None:
    monkeypatch.setattr(QLocale, "system", lambda: QLocale(locale_name))

    assert fmt_float_fixed(1234.5) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1234.0, "1,234.00"),
        (-1234.5, "-1,234.50"),
        (0.0, "0.00"),
        (-0.0, "0.00"),
        (0.00001, "0.00"),
        (1.236, "1.24"),
        (1e20, "100,000,000,000,000,000,000.00"),
        (np.float32(1234.5), "1,234.50"),
        (np.float64(1234.5), "1,234.50"),
        (float("inf"), "inf"),
        (float("-inf"), "-inf"),
        (float("nan"), ""),
        (None, ""),
    ],
)
def test_fmt_float_fixed_values(monkeypatch: MonkeyPatch, value: float | None, expected: str) -> None:
    monkeypatch.setattr(QLocale, "system", lambda: QLocale("en_US"))

    assert fmt_float_fixed(value) == expected


def test_fmt_float_fixed_enables_grouping_without_mutating_locale(monkeypatch: MonkeyPatch) -> None:
    locale = QLocale("en_US")
    locale.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    # QLocale.system() returns a value copy, not a shared mutable locale.
    monkeypatch.setattr(QLocale, "system", lambda: QLocale(locale))

    assert fmt_float_fixed(1234.0) == "1,234.00"
    assert locale.numberOptions() == QLocale.NumberOption.OmitGroupSeparator


def test_fmt_float_fixed_groups_in_c_locale(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(QLocale, "system", QLocale.c)

    assert fmt_float_fixed(1234.0) == "1,234.00"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (9007199254740993, "9,007,199,254,740,993"),
        (-(2**63), "-9,223,372,036,854,775,808"),
        (2**63 - 1, "9,223,372,036,854,775,807"),
        (2**63, "9,223,372,036,854,775,808"),
        (2**64 - 1, "18,446,744,073,709,551,615"),
    ],
)
def test_fmt_int_preserves_full_integer_precision(monkeypatch: MonkeyPatch, value: int, expected: str) -> None:
    monkeypatch.setattr(QLocale, "system", lambda: QLocale("en_US"))

    assert fmt_int(value) == expected


def test_fmt_p_value():
    assert fmt_p_value(None) == ""
    assert fmt_p_value(np.nan) == ""

    result = fmt_p_value(0.4213)
    assert "0,4213" in result or "0.4213" in result

    # Below the default threshold: reported as "< threshold", not the
    # (potentially misleadingly rounded-to-zero) exact value.
    below = fmt_p_value(0.00001)
    assert below.startswith("< ")
    assert "0,001" in below or "0.001" in below

    # Exactly at the threshold is not "below" it.
    at_threshold = fmt_p_value(0.001)
    assert not at_threshold.startswith("< ")

    custom = fmt_p_value(0.02, threshold=0.05)
    assert custom.startswith("< ")


def test_fmt_int():
    result = fmt_int(1234)
    assert any(s in result for s in ["1 234", "1\u00a0234", "1,234", "1.234"])


def test_fmt_int_groups_when_qt_locale_omits_grouping(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(QLocale, "system", QLocale.c)

    assert fmt_int(1234) == "1,234"


def test_fmt_shape():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    assert fmt_shape(df) == (fmt_int(2), fmt_int(2))
    assert fmt_shape(None) == ("?", "?")


def test_fmt_date():
    dt = datetime.date(2023, 10, 5)
    assert fmt_date(dt) == "2023-10-05"

    dttm = datetime.datetime(2023, 10, 5, 12, 30)  # noqa: DTZ001 - deterministic naive formatting fixture
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


def test_fmt_cell_renders_missing_values_as_empty_text():
    assert fmt_cell(None) == ""
    assert fmt_cell(np.nan) == ""
    assert fmt_cell(float("nan")) == ""
    assert fmt_cell(pd.NaT) == ""
    assert fmt_cell(pd.NA) == ""


def test_fmt_cell_formats_floats_through_fmt_num():
    assert fmt_cell(1234.56789) == fmt_num(1234.56789)
    assert fmt_cell(2.0) == fmt_num(2.0)


def test_fmt_cell_falls_back_to_str_for_other_values():
    assert fmt_cell("text") == "text"
    assert fmt_cell(7) == "7"
    assert fmt_cell(True) == "True"
    assert fmt_cell(pd.Timestamp("2024-01-02 03:04:05")) == "2024-01-02 03:04:05"


def test_fmt_path():
    assert fmt_path("C:\\Users\\Test") == "C:/Users/Test"
    assert fmt_path(Path("folder/subfolder")) == "folder/subfolder"


def test_tuple_to_posix():
    inp = ("C:\\Path", 123, None)
    assert tuple_to_posix(inp) == ("C:/Path", 123, None)
