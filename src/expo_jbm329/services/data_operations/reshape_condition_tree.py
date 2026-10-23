"""Identity-preserving structural edits for the nested condition builder."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from expo_jbm329.services.data_operations.reshape_conditions import ConditionMatch


class ConditionDrop(StrEnum):
    """Explicit destinations independent of a drag event's coordinates."""

    BEFORE = "before"
    AFTER = "after"
    INTO = "into"


@dataclass(eq=False, slots=True)
class ConditionNode:
    """Editable tree identity; a None connector denotes a rule leaf."""

    match: ConditionMatch | None = None
    children: list[ConditionNode] = field(default_factory=list)
    key: str = field(default_factory=lambda: uuid.uuid4().hex)


class ConditionTree:
    """Own structural rules without depending on Qt or rule editor state."""

    def __init__(self) -> None:
        """Start with an empty permanent outer AND group."""
        self.root = ConditionNode(ConditionMatch.ALL)

    def nodes(self) -> tuple[ConditionNode, ...]:
        """Return nodes in visual preorder."""
        result: list[ConditionNode] = []

        def visit(node: ConditionNode) -> None:
            result.append(node)
            for child in node.children:
                visit(child)

        visit(self.root)
        return tuple(result)

    def parent(self, node: ConditionNode) -> ConditionNode | None:
        """Find a node's current parent using identity, not row positions."""
        return next((candidate for candidate in self.nodes() if node in candidate.children), None)

    def add_rule(self, parent: ConditionNode) -> ConditionNode:
        """Append a new incomplete rule to an existing group."""
        if parent not in self.nodes() or parent.match is None:
            message = "A condition rule requires an existing parent group."
            raise ValueError(message)
        node = ConditionNode()
        parent.children.append(node)
        return node

    def can_move(self, source: ConditionNode, target: ConditionNode, placement: ConditionDrop) -> bool:
        """Reject self, outer-root and descendant drops before changing anything."""
        nodes = self.nodes()
        if source is self.root or source is target or source not in nodes or target not in nodes:
            return False
        if target is self.root and placement != ConditionDrop.INTO:
            return False
        ancestor: ConditionNode | None = target
        while ancestor is not None:
            if ancestor is source:
                return False
            ancestor = self.parent(ancestor)
        return True

    def move(self, source: ConditionNode, target: ConditionNode, placement: ConditionDrop) -> None:
        """Move a node or wrap it with a rule target in a new AND group."""
        if not self.can_move(source, target, placement):
            message = "Invalid condition tree move."
            raise ValueError(message)
        old_parent = self.parent(source)
        if old_parent is None:
            message = "Condition source has no parent."
            raise ValueError(message)
        old_parent.children.remove(source)
        if placement == ConditionDrop.INTO and target.match is not None:
            target.children.append(source)
        else:
            parent = self.parent(target)
            if parent is None:
                message = "Condition target has no parent."
                raise ValueError(message)
            index = parent.children.index(target)
            if placement == ConditionDrop.INTO:
                parent.children[index] = ConditionNode(ConditionMatch.ALL, [target, source])
            else:
                parent.children.insert(index + (placement == ConditionDrop.AFTER), source)
        self._normalize(self.root)

    def remove_rule(self, node: ConditionNode) -> None:
        """Remove one leaf and simplify the enclosing groups."""
        parent = self.parent(node)
        if parent is None or node.match is not None:
            message = "Only an existing condition rule can be removed."
            raise ValueError(message)
        parent.children.remove(node)
        self._normalize(self.root)

    def group_with_previous(self, node: ConditionNode) -> None:
        """Wrap adjacent siblings in a new AND group, even if either is a group."""
        parent = self.parent(node)
        if parent is None or parent.children.index(node) == 0:
            message = "Grouping requires a previous sibling."
            raise ValueError(message)
        index = parent.children.index(node)
        previous = parent.children[index - 1]
        parent.children[index - 1 : index + 1] = [ConditionNode(ConditionMatch.ALL, [previous, node])]
        self._normalize(self.root)

    def ungroup(self, node: ConditionNode) -> None:
        """Replace a nested group with its children under the parent's connector."""
        parent = self.parent(node)
        if parent is None or node.match is None:
            message = "Only a nested condition group can be ungrouped."
            raise ValueError(message)
        index = parent.children.index(node)
        parent.children[index : index + 1] = node.children
        self._normalize(self.root)

    def _normalize(self, node: ConditionNode) -> None:
        children: list[ConditionNode] = []
        for child in node.children:
            if child.match is not None:
                self._normalize(child)
                if not child.children:
                    continue
                if len(child.children) == 1:
                    children.append(child.children[0])
                    continue
            children.append(child)
        node.children[:] = children
