"""Classify distributions by the dependency extras that require them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from expo_jbm329.build.notices.distributions import DistributionIndex
    from expo_jbm329.build.notices.models import DistributionInfo

# Marker evaluation uses an empty extra for requirements that are not tied to an extra.
BASE_EXTRA = ""


@dataclass(frozen=True)
class DependencyScope:
    """Canonical distribution names grouped by why they are installed.

    Attributes:
        allowed: Distributions required by the base dependencies or by an allowed extra.
        dev_only: Distributions only required by development extras.
    """

    allowed: frozenset[str]
    dev_only: frozenset[str]


def _parse_requirement(raw: str) -> Requirement | None:
    """Parse a ``Requires-Dist`` entry, ignoring entries that are not valid requirements."""
    try:
        return Requirement(raw)
    except InvalidRequirement:
        return None


def _applies(requirement: Requirement, extras: Iterable[str]) -> bool:
    """Return whether a requirement's marker matches the current environment for any extra."""
    if requirement.marker is None:
        return True
    return any(requirement.marker.evaluate({"extra": extra}) for extra in extras)


def resolve_dependency_closure(
    root: DistributionInfo,
    extras: Iterable[str],
    index: DistributionIndex,
) -> frozenset[str]:
    """Return the canonical names of all installed distributions required by ``root``.

    Requirements that are not installed are skipped because they cannot be bundled.

    Args:
        root: Distribution whose requirements are resolved.
        extras: Extras of ``root`` to include. Base requirements are always included.
        index: Installed distributions.

    Returns:
        Canonical names of the transitive dependencies, excluding ``root`` itself.
    """
    root_extras = {BASE_EXTRA, *extras}
    pending = [
        requirement
        for requirement in (_parse_requirement(raw) for raw in root.requirements)
        if requirement is not None and _applies(requirement, root_extras)
    ]
    resolved: set[str] = set()
    visited: set[tuple[str, str]] = set()
    root_key = canonicalize_name(root.name)

    while pending:
        requirement = pending.pop()
        key = canonicalize_name(requirement.name)
        if key == root_key:
            continue
        distribution = index.get(key)
        if distribution is None:
            continue

        # A distribution can be reached again with additional extras, which may add requirements.
        new_extras = {extra for extra in {BASE_EXTRA, *requirement.extras} if (key, extra) not in visited}
        if not new_extras:
            continue

        visited.update((key, extra) for extra in new_extras)
        resolved.add(key)
        pending.extend(
            child
            for child in (_parse_requirement(raw) for raw in distribution.requirements)
            if child is not None and _applies(child, new_extras)
        )

    return frozenset(resolved)


def classify_dependency_scope(
    root: DistributionInfo,
    index: DistributionIndex,
    allowed_extras: Iterable[str],
    dev_extras: Iterable[str],
) -> DependencyScope:
    """Split installed dependencies of ``root`` into allowed and dev-only sets.

    Args:
        root: Application distribution.
        index: Installed distributions.
        allowed_extras: Extras whose dependencies may be bundled.
        dev_extras: Extras whose dependencies must not be bundled.

    Returns:
        Dependency scope for the application.
    """
    allowed = resolve_dependency_closure(root, allowed_extras, index)
    development = resolve_dependency_closure(root, dev_extras, index)
    return DependencyScope(allowed=allowed, dev_only=development - allowed)
