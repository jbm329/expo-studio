"""Nested expressions and identity-preserving structural edits."""

from __future__ import annotations

import pytest

from expo_jbm329.services.data_operations.reshape_condition_tree import ConditionDrop, ConditionNode, ConditionTree
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionError,
    ConditionGroup,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    ConditionValue,
    format_condition,
)


def rule(name: str, value: str) -> ConditionRule:
    return ConditionRule(ConditionColumn(0, name, True), ConditionOperator.EQUAL, (ConditionValue("string", value),))


def test_mockup_and_nested_connectors_have_explicit_parentheses():
    group = ConditionGroup(
        (
            ConditionGroup((rule("Year", "2019"), rule("Klinik", "Medicin"))),
            rule("Yrkesroll", "Läkare"),
        ),
        ConditionMatch.ANY,
    )
    assert format_condition(group) == ("(([Year] = '2019' AND [Klinik] = 'Medicin') OR [Yrkesroll] = 'Läkare')")
    nested = ConditionGroup((
        rule("a", "1"),
        ConditionGroup(
            (
                rule("b", "2"),
                ConditionGroup((rule("c]", "'"), rule("d", "4"))),
            ),
            ConditionMatch.ANY,
        ),
    ))
    assert format_condition(nested) == ("([a] = '1' AND ([b] = '2' OR ([c]]] = '''' AND [d] = '4')))")


def test_nested_empty_group_rejected_and_singletons_preserve_flat_syntax():
    with pytest.raises(ConditionError):
        format_condition(ConditionGroup((rule("a", "1"), ConditionGroup(()))))
    assert format_condition(ConditionGroup((ConditionGroup((rule("a", "1"),)),))) == "[a] = '1'"


def test_rule_on_rule_creates_and_group_and_preserves_target_order():
    tree = ConditionTree()
    first, second, third = (tree.add_rule(tree.root) for _ in range(3))
    tree.root.match = ConditionMatch.ANY
    tree.move(second, first, ConditionDrop.INTO)
    group = tree.root.children[0]
    assert group.match == ConditionMatch.ALL
    assert group.children == [first, second]
    assert tree.root.children == [group, third]
    assert tree.parent(first) is group
    tree.move(group, third, ConditionDrop.AFTER)
    assert tree.root.children == [third, group]
    assert group.children == [first, second]


def test_moving_into_group_out_again_and_normalization():
    tree = ConditionTree()
    first, second, third = (tree.add_rule(tree.root) for _ in range(3))
    tree.move(second, first, ConditionDrop.INTO)
    group = tree.parent(first)
    tree.move(third, group, ConditionDrop.INTO)
    assert group.children == [first, second, third]
    tree.move(second, group, ConditionDrop.AFTER)
    assert tree.root.children == [group, second]
    tree.remove_rule(first)
    assert tree.root.children == [third, second]
    assert group not in tree.nodes()
    tree.remove_rule(third)
    tree.remove_rule(second)
    assert tree.nodes() == (tree.root,)
    assert tree.root.match == ConditionMatch.ALL


def test_ungroup_preserves_order_and_uses_parent_connector():
    tree = ConditionTree()
    first, second, third = (tree.add_rule(tree.root) for _ in range(3))
    tree.move(second, first, ConditionDrop.INTO)
    tree.root.match = ConditionMatch.ANY
    tree.ungroup(tree.parent(first))
    assert tree.root.children == [first, second, third]
    assert tree.root.match == ConditionMatch.ANY


@pytest.mark.parametrize("placement", list(ConditionDrop))
def test_invalid_moves_are_atomic(placement):
    tree = ConditionTree()
    first, second = (tree.add_rule(tree.root) for _ in range(2))
    tree.move(second, first, ConditionDrop.INTO)
    group = tree.parent(first)
    before = tuple((node.key, node.match, tuple(node.children)) for node in tree.nodes())
    for source, target in (
        (group, group),
        (group, first),
        (tree.root, first),
        (ConditionNode(), first),
        (first, ConditionNode()),
    ):
        assert not tree.can_move(source, target, placement)
        with pytest.raises(ValueError):
            tree.move(source, target, placement)
        assert tuple((node.key, node.match, tuple(node.children)) for node in tree.nodes()) == before


def test_empty_group_cleanup_and_nested_singleton_cascade():
    tree = ConditionTree()
    first = tree.add_rule(tree.root)
    empty = ConditionNode(ConditionMatch.ALL)
    tree.root.children.append(empty)
    outer = ConditionNode(ConditionMatch.ANY, [ConditionNode(ConditionMatch.ALL, [first])])
    tree.root.children[:] = [empty, outer]
    tree.remove_rule(first)
    assert tree.root.children == []
    with pytest.raises(ValueError):
        tree.ungroup(tree.root)
    with pytest.raises(ValueError):
        tree.remove_rule(tree.root)
    with pytest.raises(ValueError):
        tree.add_rule(first)


def test_root_only_accepts_into_and_reordering_is_stable():
    tree = ConditionTree()
    first, second, third = (tree.add_rule(tree.root) for _ in range(3))
    assert not tree.can_move(first, tree.root, ConditionDrop.BEFORE)
    assert not tree.can_move(first, tree.root, ConditionDrop.AFTER)
    tree.move(first, third, ConditionDrop.AFTER)
    assert tree.root.children == [second, third, first]
    tree.move(first, third, ConditionDrop.BEFORE)
    assert tree.root.children == [second, first, third]
    tree.move(second, tree.root, ConditionDrop.INTO)
    assert tree.root.children == [first, third, second]


def test_group_previous_group_preserves_its_connector():
    tree = ConditionTree()
    first, second, third = (tree.add_rule(tree.root) for _ in range(3))
    tree.move(second, first, ConditionDrop.INTO)
    previous = tree.parent(first)
    previous.match = ConditionMatch.ANY
    tree.group_with_previous(third)
    outer = tree.root.children[0]
    assert outer.match == ConditionMatch.ALL
    assert outer.children == [previous, third]
    assert previous.match == ConditionMatch.ANY
    with pytest.raises(ValueError):
        tree.group_with_previous(previous)
