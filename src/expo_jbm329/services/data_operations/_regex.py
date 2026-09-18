"""Constants for regex patterns used in data operations."""
import re

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
