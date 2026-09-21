from __future__ import annotations

from expo_jbm329.services.file_types import (
    classify_file,
    is_data_file,
    is_html_file,
    is_sql_file,
)


def test_classify_file_routes_by_suffix():
    assert classify_file("query.sql") == "sql"
    assert classify_file("data.csv") == "data"
    assert classify_file("report.html") == "html"
    assert classify_file("unknown.txt") == "unknown"


def test_helpers_match_classification():
    assert is_sql_file("query.sql")
    assert is_data_file("data.xlsx")
    assert is_html_file("index.htm")
