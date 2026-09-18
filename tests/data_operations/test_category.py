import pandas as pd
import pytest

from expo_jbm329.services.data_operations.category import (
    category_remove_unused,
    category_rename_single,
    category_set_order,
)

# =====================================================================
# category_remove_unused
# =====================================================================


def test_category_remove_unused_basic():
    s = pd.Series(
        pd.Categorical(
            ["a", "b", "a"],
            categories=["a", "b", "c"],
        )
    )
    df = pd.DataFrame({"col": s})

    out = category_remove_unused(df, "col")

    assert out is not df
    assert list(out["col"].dtype.categories) == ["a", "b"]


def test_category_remove_unused_non_categorical_noop():
    df = pd.DataFrame({"col": ["a", "b", "a"]})

    out = category_remove_unused(df, "col")

    assert out.equals(df)
    assert out is not df


# =====================================================================
# category_rename_single
# =====================================================================


def test_category_rename_single_simple():
    df = pd.DataFrame({
        "col": pd.Categorical(
            ["a", "b", "a"],
            categories=["a", "b"],
        )
    })

    out = category_rename_single(df, "col", "a", "x")

    assert list(out["col"].dtype.categories) == ["x", "b"]
    assert out["col"].tolist() == ["x", "b", "x"]


def test_category_rename_single_collision():
    df = pd.DataFrame({
        "col": pd.Categorical(
            ["a", "b", "a"],
            categories=["a", "b"],
        )
    })

    # Renaming "a" -> "b" causes a collision
    out = category_rename_single(df, "col", "a", "b")

    assert list(out["col"].dtype.categories) == ["b"]
    assert out["col"].tolist() == ["b", "b", "b"]


def test_category_rename_single_non_categorical():
    df = pd.DataFrame({"col": ["a", "b", "a"]})

    out = category_rename_single(df, "col", "a", "x")

    assert out["col"].dtype.name == "string"
    assert out["col"].tolist() == ["x", "b", "x"]


# =====================================================================
# category_set_order
# =====================================================================


def test_category_set_order_strict():
    df = pd.DataFrame({"col": ["b", "a", "c"]})

    out = category_set_order(
        df,
        "col",
        order_list=["a", "b"],
        strict=True,
    )

    assert list(out["col"].dtype.categories) == ["a", "b"]
    assert pd.isna(out["col"].iloc[2])  # "c" becomes NA


def test_category_set_order_non_strict_append_tail():
    df = pd.DataFrame({"col": ["b", "a", "c"]})

    out = category_set_order(
        df,
        "col",
        order_list=["a", "b"],
        strict=False,
        append_missing_tail=True,
    )

    assert list(out["col"].dtype.categories) == ["a", "b", "c"]
    assert out["col"].tolist() == ["b", "a", "c"]


def test_category_set_order_preserves_order_flag():
    df = pd.DataFrame({"col": ["b", "a"]})

    out = category_set_order(
        df,
        "col",
        order_list=["a", "b"],
        ordered=True,
    )

    assert out["col"].dtype.ordered is True


def test_category_set_order_invalid_column():
    df = pd.DataFrame({"a": ["x"]})

    with pytest.raises(KeyError):
        category_set_order(df, "missing", ["x"])
