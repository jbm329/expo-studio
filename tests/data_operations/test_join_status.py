"""Regression coverage for collision-safe join provenance."""

from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.joins import (
    JoinHow,
    JoinRequest,
    UnmatchedFill,
    join_dataframes,
    join_dataframes_with_status,
)


@pytest.mark.parametrize("how", ["inner", "left", "right", "outer"])
@pytest.mark.parametrize("side", ["left", "right", "both"])
@pytest.mark.parametrize("base", ["join_status", "join_status (Film LEFT Actor)"])
def test_status_collisions_preserve_source_data(how: JoinHow, side: str, base: str) -> None:
    """Source status columns remain ordinary data even when excluded for preparation."""
    left = pd.DataFrame({"id": pd.Series([1, 2], dtype="Int64")})
    right = pd.DataFrame({"id": pd.Series([2, 3], dtype="Int64")})
    if side in {"left", "both"}:
        left[base] = pd.Series(["historical-left", pd.NA], dtype="string")
    if side in {"right", "both"}:
        right[base] = pd.Series(["historical-right", pd.NA], dtype="string")
    originals = left.copy(deep=True), right.copy(deep=True)
    expected = left.merge(right, on="id", how=how, suffixes=("_left", "_right"))
    joined = join_dataframes_with_status(
        JoinRequest(
            left, right, ["id"], ["id"], how=how, left_columns=["id"], right_columns=["id"], status_column_base=base
        )
    )

    assert joined.status_column == f"{base} 2"
    pd.testing.assert_frame_equal(joined.frame.drop(columns=joined.status_column), expected)
    expected_status = joined.frame["id"].map({1: "left_only", 2: "both", 3: "right_only"}).tolist()
    assert joined.frame[joined.status_column].tolist() == expected_status
    assert joined.frame[joined.status_column].cat.categories.tolist() == ["left_only", "right_only", "both"]
    assert not joined.frame[joined.status_column].cat.ordered
    pd.testing.assert_frame_equal(left, originals[0])
    pd.testing.assert_frame_equal(right, originals[1])


@pytest.mark.parametrize("base", ["join_status", "join_status (Film INNER Actor)"])
def test_repeated_joins_allocate_available_status_name(base: str) -> None:
    """Repeated operations preserve historical status and skip occupied numbers."""
    right = pd.DataFrame({"id": [1, 2]})
    frame = right.copy(deep=True)
    for number in range(1, 5):
        original = frame.copy(deep=True)
        joined = join_dataframes_with_status(JoinRequest(frame, right, ["id"], ["id"], status_column_base=base))
        assert joined.status_column == (base if number == 1 else f"{base} {number}")
        pd.testing.assert_frame_equal(joined.frame.drop(columns=joined.status_column), original)
        assert joined.frame[joined.status_column].tolist() == ["both", "both"]
        frame = joined.frame


@pytest.mark.parametrize("how", ["inner", "left", "right", "outer"])
@pytest.mark.parametrize("column", ["_left_indicator", "_right_indicator", "__expo_join_left", "__expo_join_right"])
def test_pandas_reserved_and_temporary_names_remain_usable(how: JoinHow, column: str) -> None:
    """Internal bookkeeping never reserves user column names or mutates inputs."""
    left = pd.DataFrame({"id": pd.Series([1, 2], dtype="Int64"), column: ["a", "b"]})
    right = pd.DataFrame({"id": pd.Series([2, 3], dtype="Int64"), column: ["c", "d"]})
    originals = left.copy(deep=True), right.copy(deep=True)
    expected = left.merge(right, on="id", how=how, suffixes=("_left", "_right"))
    joined = join_dataframes_with_status(JoinRequest(left, right, ["id"], ["id"], how=how))
    pd.testing.assert_frame_equal(joined.frame.drop(columns=joined.status_column), expected)
    assert joined.status_column == "join_status"
    pd.testing.assert_frame_equal(left, originals[0])
    pd.testing.assert_frame_equal(right, originals[1])


@pytest.mark.parametrize("base", ["join_status", "__expo_join_left", "__expo_join_right"])
def test_suffix_generated_columns_are_not_overwritten(base: str) -> None:
    """Both status and marker allocation account for suffix-generated labels."""
    stem, suffix = base.rsplit("_", 1)
    left = pd.DataFrame({"id": [1], stem: ["left-data"]})
    right = pd.DataFrame({"id": [1], stem: ["right-data"]})
    expected = left.merge(right, on="id", suffixes=(f"_{suffix}", "_other"))
    joined = join_dataframes_with_status(
        JoinRequest(left, right, ["id"], ["id"], suffixes=(f"_{suffix}", "_other"), status_column_base=base)
    )
    assert joined.status_column == f"{base} 2"
    assert joined.frame[base].tolist() == ["left-data"]
    pd.testing.assert_frame_equal(joined.frame.drop(columns=joined.status_column), expected)


@pytest.mark.parametrize("how", ["left", "right", "outer"])
def test_defaults_use_current_status_not_historical_values(how: JoinHow) -> None:
    """Historical statuses cannot drive filling or replace genuine source NULLs."""
    left = pd.DataFrame({
        "id": [1, 2],
        "join_status": pd.Series(["both", "right_only"], dtype="string"),
        "value": pd.Series([10, pd.NA], dtype="Int64"),
    })
    right = pd.DataFrame({
        "id": [2, 3],
        "join_status": pd.Series(["left_only", "both"], dtype="string"),
        "value": pd.Series([pd.NA, 30], dtype="Int64"),
    })
    joined = join_dataframes_with_status(
        JoinRequest(
            left,
            right,
            ["id"],
            ["id"],
            how=how,
            left_fill={"value": UnmatchedFill(0)} if how in {"right", "outer"} else {},
            right_fill={"value": UnmatchedFill(0)} if how in {"left", "outer"} else {},
        )
    )
    frame = joined.frame.set_index("id")
    assert joined.status_column == "join_status 2"
    assert frame.loc[[2], ["value_left", "value_right"]].isna().all().all()
    if how in {"left", "outer"}:
        assert frame.loc[1, "value_right"] == 0
        assert frame.loc[1, "value_left"] == 10
    if how in {"right", "outer"}:
        assert frame.loc[3, "value_left"] == 0
        assert frame.loc[3, "value_right"] == 30


@pytest.mark.parametrize("how", ["inner", "left", "right", "outer"])
@pytest.mark.parametrize("same_keys", [False, True])
@pytest.mark.parametrize("empty_side", ["neither", "left", "right", "both"])
def test_status_matches_pandas_for_multikey_null_duplicate_and_empty_inputs(
    how: JoinHow, same_keys: bool, empty_side: str
) -> None:
    """Presence markers preserve pandas semantics including matches on NULL keys."""
    left = pd.DataFrame({
        "id": pd.Series([1, 2, 2, pd.NA], dtype="Int64"),
        "part": pd.Series(["a", "b", "b", pd.NA], dtype="string"),
    })
    right = pd.DataFrame({
        "id": pd.Series([2, 2, 3, pd.NA], dtype="Int64"),
        "part": pd.Series(["b", "b", "c", pd.NA], dtype="string"),
    })
    right_keys = ["id", "part"] if same_keys else ["other_id", "other_part"]
    if not same_keys:
        right = right.rename(columns={"id": "other_id", "part": "other_part"})
    if empty_side in {"left", "both"}:
        left = left.iloc[:0]
    if empty_side in {"right", "both"}:
        right = right.iloc[:0]
    expected = left.merge(right, left_on=["id", "part"], right_on=right_keys, how=how, indicator="join_status")
    request = JoinRequest(left, right, ["id", "part"], right_keys, how=how)
    joined = join_dataframes_with_status(request)
    assert joined.status_column == "join_status"
    pd.testing.assert_frame_equal(joined.frame, expected)
    pd.testing.assert_frame_equal(join_dataframes(request), joined.frame)


@pytest.mark.parametrize("how", ["inner", "left", "right", "outer"])
def test_historical_status_can_be_a_join_key(how: JoinHow) -> None:
    """Source identity is preserved even when joining on a former metadata column."""
    left = pd.DataFrame({"join_status": pd.Series(["both", "left_only"], dtype="string")})
    right = pd.DataFrame({"join_status": pd.Series(["both", "right_only"], dtype="string")})
    expected = left.merge(right, on="join_status", how=how)
    joined = join_dataframes_with_status(JoinRequest(left, right, ["join_status"], ["join_status"], how=how))
    assert joined.status_column == "join_status 2"
    pd.testing.assert_frame_equal(joined.frame.drop(columns=joined.status_column), expected)


@pytest.mark.parametrize("label", ["INNER", "LEFT", "RIGHT", "FULL OUTER"])
def test_explicit_descriptive_status_base(label: str) -> None:
    """The Qt-free service accepts the caller's captured descriptive label."""
    base = f"join_status (Film {label} Actor)"
    frame = pd.DataFrame({"id": [1]})
    joined = join_dataframes_with_status(JoinRequest(frame, frame, ["id"], ["id"], status_column_base=base))
    assert joined.status_column == base
    assert joined.frame[base].tolist() == ["both"]


@pytest.mark.parametrize("base", ["", " ", "\t\n"])
def test_empty_status_base_fails_explicitly(base: str) -> None:
    """Invalid generated names are rejected rather than silently replaced."""
    frame = pd.DataFrame({"id": [1]})
    with pytest.raises(ValueError, match="Join status column base must not be empty"):
        join_dataframes_with_status(JoinRequest(frame, frame, ["id"], ["id"], status_column_base=base))
