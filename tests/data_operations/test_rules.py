import pandas as pd
import pytest

from expo_jbm329.services.data_operations.rules import (
    RemoveValueRule,
    ReplaceRule,
    Rule,
    StripRule,
    apply_rules,
)

# =====================================================================
# ReplaceRule
# =====================================================================


def test_replace_rule_literal():
    df = pd.DataFrame({"a": ["foo", "bar", "foo"]})

    rule = ReplaceRule(column="a", pattern="foo", replacement="baz")

    out = rule.apply(df)

    assert out is not df
    assert out["a"].tolist() == ["baz", "bar", "baz"]


def test_replace_rule_regex():
    df = pd.DataFrame({"a": ["a1", "b2", "c3"]})

    rule = ReplaceRule(column="a", pattern=r"\d", replacement="", regex=True)

    out = rule.apply(df)

    assert out["a"].tolist() == ["a", "b", "c"]


def test_replace_rule_missing_column():
    df = pd.DataFrame({"a": ["x"]})

    rule = ReplaceRule(column="missing", pattern="x", replacement="y")

    with pytest.raises(KeyError):
        rule.apply(df)


# =====================================================================
# RemoveValueRule
# =====================================================================


def test_remove_value_rule_basic():
    df = pd.DataFrame({"a": [1, 2, 1]})

    rule = RemoveValueRule(column="a", value=1)

    out = rule.apply(df)

    assert out is not df
    assert out["a"].tolist() == [2]


def test_remove_value_rule_missing_column():
    df = pd.DataFrame({"a": [1]})

    rule = RemoveValueRule(column="missing", value=1)

    with pytest.raises(KeyError):
        rule.apply(df)


# =====================================================================
# StripRule
# =====================================================================


def test_strip_rule_basic():
    df = pd.DataFrame({"a": ["  foo ", " bar"]})

    rule = StripRule(column="a")

    out = rule.apply(df)

    assert out["a"].tolist() == ["foo", "bar"]


# =====================================================================
# apply_rules (pipeline behavior)
# =====================================================================


def test_apply_rules_sequential():
    df = pd.DataFrame({"a": [" foo ", "bar", " foo "]})

    rules = [
        StripRule(column="a"),
        ReplaceRule(column="a", pattern="foo", replacement="baz"),
    ]

    out = apply_rules(df, rules)

    assert out["a"].tolist() == ["baz", "bar", "baz"]


def test_apply_rules_empty_rules():
    df = pd.DataFrame({"a": [1, 2]})

    out = apply_rules(df, [])

    assert out is df or out.equals(df)


def test_apply_rules_does_not_mutate_input():
    df = pd.DataFrame({"a": [" foo "]})

    rules = [StripRule(column="a")]

    _ = apply_rules(df, rules)

    # Original DataFrame must remain unchanged
    assert df["a"].iloc[0] == " foo "


# =====================================================================
# Rule base class
# =====================================================================


def test_rule_base_class_not_implemented():
    df = pd.DataFrame({"a": [1]})

    rule = Rule(column="a")

    with pytest.raises(NotImplementedError):
        rule.apply(df)
