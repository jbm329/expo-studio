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
    "auto": dict(fmt=None, dayfirst=False, yearfirst=False),
    "iso_date": dict(fmt="%Y-%m-%d", dayfirst=False, yearfirst=False),
    "iso_datetime": dict(fmt="%Y-%m-%d %H:%M:%S", dayfirst=False, yearfirst=False),
    "dmy_slash": dict(fmt="%d/%m/%Y", dayfirst=True, yearfirst=False),
    "mdy_slash": dict(fmt="%m/%d/%Y", dayfirst=False, yearfirst=False),
    "dmy_dot": dict(fmt="%d.%m.%Y", dayfirst=True, yearfirst=False),
    "ymd_slash": dict(fmt="%Y/%m/%d", dayfirst=False, yearfirst=False),
    "ymd_compact": dict(fmt="%Y%m%d", dayfirst=False, yearfirst=False),
}
