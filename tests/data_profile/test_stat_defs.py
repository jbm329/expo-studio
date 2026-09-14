from __future__ import annotations

from expo_jbm329.services.data_profile.stat_defs import STAT_DEFS, StatDef, StatFormat


def test_stat_defs_registry_contains_expected_entries():
    assert STAT_DEFS["count.n"] == StatDef("count.n", StatFormat.INT)
    assert STAT_DEFS["missing.pct"].fmt == StatFormat.PERCENT
    assert STAT_DEFS["sample.values"].fmt == StatFormat.HEADER_ONLY

