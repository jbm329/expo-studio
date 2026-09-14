from expo_jbm329.services.data_profile.column_data_profile import ColumnProfile
from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache


def test_cache_set_get():
    cache = ColumnProfileCache(capacity=2)
    p1 = ColumnProfile(name="A", semantic_dtype="int", storage_dtype="int64", stats={"count": 10})
    p2 = ColumnProfile(name="B", semantic_dtype="float", storage_dtype="float64", stats={"count": 20})

    cache.set(("tab1", "colA"), p1)
    cache.set(("tab1", "colB"), p2)

    assert cache.get(("tab1", "colA")) == p1
    assert cache.get(("tab1", "colB")) == p2


def test_cache_lru_eviction():
    cache = ColumnProfileCache(capacity=2)
    p1 = ColumnProfile(name="A", semantic_dtype="int", storage_dtype="int64", stats={"count": 10})
    p2 = ColumnProfile(name="B", semantic_dtype="float", storage_dtype="float64", stats={"count": 20})
    p3 = ColumnProfile(name="C", semantic_dtype="bool", storage_dtype="bool", stats={"count": 30})

    cache.set(("t", "1"), p1)
    cache.set(("t", "2"), p2)
    cache.get(("t", "1"))
    cache.set(("t", "3"), p3)

    assert cache.get(("t", "1")) == p1
    assert cache.get(("t", "3")) == p3
    assert cache.get(("t", "2")) is None


def test_cache_overwrite_updates_value():
    cache = ColumnProfileCache()
    p1 = ColumnProfile(name="A", semantic_dtype="int", storage_dtype="int64", stats={"count": 10})
    p2 = ColumnProfile(name="A2", semantic_dtype="float", storage_dtype="float64", stats={"count": 20})

    cache.set(("tab", "col"), p1)
    cache.set(("tab", "col"), p2)

    assert cache.get(("tab", "col")) == p2


def test_cache_invalidate_tab():
    cache = ColumnProfileCache()
    p1 = ColumnProfile(name="A", semantic_dtype="int", storage_dtype="int64", stats={"count": 10})
    p2 = ColumnProfile(name="B", semantic_dtype="float", storage_dtype="float64", stats={"count": 20})

    cache.set(("tab1", "colA"), p1)
    cache.set(("tab2", "colB"), p2)

    cache.invalidate_tab("tab1")

    assert cache.get(("tab1", "colA")) is None
    assert cache.get(("tab2", "colB")) == p2


def test_cache_clear():
    cache = ColumnProfileCache()
    cache.set(("t", "1"), ColumnProfile(name="A", semantic_dtype="int", storage_dtype="int64", stats={"count": 1}))

    cache.clear()

    assert cache.get(("t", "1")) is None
