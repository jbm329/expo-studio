import pandas as pd

from expo_jbm329.services.data_profile.column_data_profile import profile_series


def test_numeric_profile():
    series = pd.Series([1, 2, 3, 4, 5], dtype="Int64", name="n")

    prof = profile_series(series, "n")

    assert prof.name == "n"
    assert prof.semantic_dtype == "int"
    assert prof.stats["count.n"] == 5
    assert prof.stats["missing.n"] == 0
    assert prof.stats["unique.n"] == 5
    assert "num.median" in prof.stats
    assert prof.plot.kind == "hist"


def test_boolean_profile():
    series = pd.Series([True, False, None], dtype="boolean", name="flag")

    prof = profile_series(series, "flag")

    assert prof.semantic_dtype == "bool"
    assert prof.stats["bool.true.n"] == 1
    assert prof.stats["bool.false.n"] == 1
    assert prof.plot.kind == "bar_bool"


def test_datetime_profile():
    series = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-03"]), name="dt")

    prof = profile_series(series, "dt")

    assert prof.semantic_dtype == "datetime"
    assert "dt.min" in prof.stats
    assert "dt.max" in prof.stats
    assert prof.plot.kind == "bar_weekday"


def test_text_profile():
    series = pd.Series(["alpha", "beta", "alpha", None], dtype="string", name="txt")

    prof = profile_series(series, "txt")

    assert prof.semantic_dtype == "string"
    assert prof.stats["count.n"] == 4
    assert prof.stats["missing.n"] == 1
    assert prof.stats["text.topn"][0] == ("alpha", 2)
    assert prof.plot.kind == "bar_topn"


def test_empty_profile():
    series = pd.Series([], dtype="float64", name="empty")

    prof = profile_series(series, "empty")

    assert prof.semantic_dtype == "float"
    assert prof.stats["count.n"] == 0
    assert prof.stats["missing.n"] == 0
    assert prof.plot.kind is None
