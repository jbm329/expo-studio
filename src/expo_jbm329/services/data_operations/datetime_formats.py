"""Module for handling datetime formats and parsing dates."""

from typing import Literal

DateFormatKey = Literal[
    "auto",
    "iso_date",
    "iso_datetime",
    "dmy_slash",
    "mdy_slash",
    "dmy_dot",
    "ymd_slash",
    "ymd_compact",
]

FORMAT_MAP = {
    "auto": {"fmt": None, "dayfirst": False, "yearfirst": False},
    "iso_date": {"fmt": "%Y-%m-%d", "dayfirst": False, "yearfirst": False},
    "iso_datetime": {"fmt": "%Y-%m-%d %H:%M:%S", "dayfirst": False, "yearfirst": False},
    "dmy_slash": {"fmt": "%d/%m/%Y", "dayfirst": True, "yearfirst": False},
    "mdy_slash": {"fmt": "%m/%d/%Y", "dayfirst": False, "yearfirst": False},
    "dmy_dot": {"fmt": "%d.%m.%Y", "dayfirst": True, "yearfirst": False},
    "ymd_slash": {"fmt": "%Y/%m/%d", "dayfirst": False, "yearfirst": False},
    "ymd_compact": {"fmt": "%Y%m%d", "dayfirst": False, "yearfirst": False},
}
