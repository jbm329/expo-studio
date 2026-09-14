from __future__ import annotations

import pandas as pd

from expo_jbm329.services.data_profile.column_data_profile import (
    ColumnProfile,
    PlotSpec,
    profile_series,
)


def test_profile_series_numeric():
    profile = profile_series(pd.Series([1, 2, 3]), name="num")

    assert isinstance(profile, ColumnProfile)
    assert profile.name == "num"
    assert profile.semantic_dtype in {"int", "float"}
    assert profile.stats["count.n"] == 3
    assert "num.mean" in profile.stats


def test_profile_series_text_and_category_metadata():
    profile = profile_series(pd.Series(["a", "b", "a"]), name="text")

    assert profile.stats["count.n"] == 3
    assert profile.stats["unique.n"] == 2
    assert profile.plot.kind in {"bar_topn", None}

