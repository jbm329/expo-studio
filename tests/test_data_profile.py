import pandas as pd
from expo_jbm329.services.data_profile import profile_series


def test_numeric_profile():
    s = pd.Series([1,2,3,4,5,None])
    prof = profile_series(s, "n")
    assert prof.stats["Antal (n)"] == 6
    assert prof.stats["Saknade (n)"] == 1
    assert "Median" in prof.stats
    assert prof.plot.kind in (None, "hist")