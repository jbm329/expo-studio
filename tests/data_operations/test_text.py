import pandas as pd
import pytest

from expo_jbm329.services.data_operations.text import (
    capitalize_first,
    clean_text,
    extract_digits,
    extract_letters,
    insert_text,
    normalize_whitespace,
    remove_regex,
    replace_text,
    replace_values,
    set_cell_value_text,
    strip_chars,
    to_title_case,
)

# =====================================================================
# set_cell_value_text
# =====================================================================

def test_set_cell_value_text_basic():
    df = pd.DataFrame({"a": ["x", "y"]})

    out = set_cell_value_text(df, "a", 1, 123)

    assert out is not df
    assert out["a"].iloc[1] == "123"
    assert out["a"].dtype.name == "string"


def test_set_cell_value_text_invalid_column():
    df = pd.DataFrame({"a": ["x"]})

    with pytest.raises(KeyError):
        set_cell_value_text(df, "b", 0, "x")


# =====================================================================
# replace_values
# =====================================================================

def test_replace_values_literal():
    df = pd.DataFrame({"a": ["foo", "bar", "foo"]})

    out = replace_values(df, "a", "foo", "baz")

    assert out["a"].tolist() == ["baz", "bar", "baz"]


def test_replace_values_regex():
    df = pd.DataFrame({"a": ["a1", "b2", "c3"]})

    out = replace_values(df, "a", r"\d", "", regex=True)

    assert out["a"].tolist() == ["a", "b", "c"]


# =====================================================================
# remove_regex
# =====================================================================

def test_remove_regex_basic():
    df = pd.DataFrame({"a": ["ab12", "cd34"]})

    out = remove_regex(df, "a", r"\d+")

    assert out["a"].tolist() == ["ab", "cd"]


# =====================================================================
# clean_text
# =====================================================================

def test_clean_text_strip_lower():
    df = pd.DataFrame({"a": ["  Foo  ", " BAR"]})

    out = clean_text(df, "a", strip=True, lower=True)

    assert out["a"].tolist() == ["foo", "bar"]


def test_clean_text_remove_literal():
    df = pd.DataFrame({"a": ["abcXYZ", "XYZabc"]})

    out = clean_text(df, "a", remove="XYZ")

    assert out["a"].tolist() == ["abc", "abc"]


# =====================================================================
# normalize_whitespace
# =====================================================================

def test_normalize_whitespace():
    df = pd.DataFrame({"a": ["  a   b  c ", "x    y"]})

    out = normalize_whitespace(df, "a")

    assert out["a"].tolist() == ["a b c", "x y"]


# =====================================================================
# strip_chars
# =====================================================================

def test_strip_chars():
    df = pd.DataFrame({"a": ["--abc--", "##x##"]})

    out = strip_chars(df, "a", "-#")

    assert out["a"].tolist() == ["abc", "x"]


# =====================================================================
# extract_digits
# =====================================================================

def test_extract_digits():
    df = pd.DataFrame({"a": ["tel: 070-123", "id42"]})

    out = extract_digits(df, "a")

    assert out["a"].tolist() == ["070123", "42"]


# =====================================================================
# extract_letters
# =====================================================================

def test_extract_letters_keep_swedish():
    df = pd.DataFrame({"a": ["Åsa123", "Bo!"]})

    out = extract_letters(df, "a", keep_swedish=True)

    assert out["a"].tolist() == ["Åsa", "Bo"]


def test_extract_letters_ascii_only():
    df = pd.DataFrame({"a": ["Åsa123", "Bo!"]})

    out = extract_letters(df, "a", keep_swedish=False)

    assert out["a"].tolist() == ["sa", "Bo"]


# =====================================================================
# to_title_case
# =====================================================================

def test_to_title_case():
    df = pd.DataFrame({"a": ["hello world", "FOO bar"]})

    out = to_title_case(df, "a")

    assert out["a"].tolist() == ["Hello World", "Foo Bar"]


# =====================================================================
# capitalize_first
# =====================================================================

def test_capitalize_first_basic():
    df = pd.DataFrame({"a": ["aNNa", "BO", None]})

    out = capitalize_first(df, "a")

    assert out["a"].tolist() == ["Anna", "Bo", pd.NA]


# =====================================================================
# replace_text
# =====================================================================

def test_replace_text_case_sensitive():
    df = pd.DataFrame({"a": ["Hello", "hello"]})

    out = replace_text(df, "a", "Hello", "Hi", case=True)

    assert out["a"].tolist() == ["Hi", "hello"]


def test_replace_text_case_insensitive():
    df = pd.DataFrame({"a": ["Hello", "hello"]})

    out = replace_text(df, "a", "hello", "hi", case=False)

    assert out["a"].tolist() == ["hi", "hi"]


# =====================================================================
# insert_text
# =====================================================================

def test_insert_text_positive_position():
    df = pd.DataFrame({"a": ["abcd"]})

    out = insert_text(df, "a", "-", 2)

    assert out["a"].iloc[0] == "ab-cd"


def test_insert_text_negative_position():
    df = pd.DataFrame({"a": ["abcd"]})

    out = insert_text(df, "a", "-", -1)

    assert out["a"].iloc[0] == "abc-d"
