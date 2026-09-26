from __future__ import annotations

from expo_jbm329.gui.dialogs.analysis.group_comparison_config import GroupComparisonConfigWidget
from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult


def _make_result(
    numeric_column: str = "a",
    grouping_column: str = "grp",
    available_numeric_columns: tuple[str, ...] = ("a", "b"),
    available_grouping_columns: tuple[str, ...] = ("grp", "cat"),
) -> GroupComparisonResult:
    return GroupComparisonResult(
        numeric_column=numeric_column,
        grouping_column=grouping_column,
        available_numeric_columns=available_numeric_columns,
        available_grouping_columns=available_grouping_columns,
        groups=(),
        pairwise=None,
        multi_group=None,
        warnings=(),
        error=None,
    )


def test_populates_numeric_combo_with_every_available_numeric_column():
    widget = GroupComparisonConfigWidget(_make_result())

    assert [widget._numeric_combo.itemText(i) for i in range(widget._numeric_combo.count())] == ["a", "b"]  # noqa: SLF001


def test_populates_grouping_combo_excluding_the_current_numeric_column():
    widget = GroupComparisonConfigWidget(_make_result(numeric_column="a", available_grouping_columns=("a", "grp")))

    assert [widget._grouping_combo.itemText(i) for i in range(widget._grouping_combo.count())] == [  # noqa: SLF001
        "grp"
    ]


def test_defaults_to_the_results_current_selection():
    widget = GroupComparisonConfigWidget(_make_result(numeric_column="b", grouping_column="cat"))

    assert widget.current_selection() == ("b", "cat")


def test_changing_the_numeric_combo_emits_selection_changed():
    widget = GroupComparisonConfigWidget(_make_result())
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda numeric, grouping: received.append((numeric, grouping)))

    widget._numeric_combo.setCurrentIndex(1)  # noqa: SLF001

    assert received == [("b", "grp")]
    assert widget.current_selection() == ("b", "grp")


def test_changing_the_grouping_combo_emits_selection_changed():
    widget = GroupComparisonConfigWidget(_make_result())
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda numeric, grouping: received.append((numeric, grouping)))

    widget._grouping_combo.setCurrentIndex(1)  # noqa: SLF001

    assert received == [("a", "cat")]


def test_changing_numeric_column_to_the_current_grouping_column_rebuilds_grouping_options():
    """When the numeric column changes to whatever was the grouping
    column, that value must no longer be offered as a grouping option -
    comparing a column to itself is meaningless."""
    widget = GroupComparisonConfigWidget(
        _make_result(
            numeric_column="a",
            grouping_column="grp",
            available_numeric_columns=("a", "grp"),
            available_grouping_columns=("grp", "cat"),
        )
    )

    widget._numeric_combo.setCurrentIndex(1)  # noqa: SLF001 - selects "grp"

    assert [widget._grouping_combo.itemText(i) for i in range(widget._grouping_combo.count())] == [  # noqa: SLF001
        "cat"
    ]
    assert widget.current_selection() == ("grp", "cat")


def test_changing_numeric_column_preserves_a_still_valid_grouping_selection():
    widget = GroupComparisonConfigWidget(
        _make_result(
            numeric_column="a",
            grouping_column="cat",
            available_numeric_columns=("a", "b"),
            available_grouping_columns=("grp", "cat"),
        )
    )

    widget._numeric_combo.setCurrentIndex(1)  # noqa: SLF001 - selects "b", unrelated to "cat"

    assert widget.current_selection() == ("b", "cat")


def test_only_the_final_selection_is_emitted_once_when_numeric_column_changes():
    """Rebuilding the grouping combo (clear + re-add + reselect) must not
    itself emit intermediate/duplicate signals - only one, final emission
    per user action."""
    widget = GroupComparisonConfigWidget(
        _make_result(available_numeric_columns=("a", "b"), available_grouping_columns=("grp", "cat"))
    )
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda numeric, grouping: received.append((numeric, grouping)))

    widget._numeric_combo.setCurrentIndex(1)  # noqa: SLF001

    assert len(received) == 1
