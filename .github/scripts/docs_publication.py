"""Validate sources and release eligibility for documentation publication."""

from __future__ import annotations

import re


def parse_stable_tag(tag: str) -> tuple[int, int, int]:
    """Parse a stable application release tag for numeric comparison.

    Args:
        tag: Release tag in vMAJOR.MINOR.PATCH format.

    Returns:
        Numeric major, minor, and patch components.

    Raises:
        ValueError: If the tag is not a supported stable release tag.
    """
    match = re.fullmatch(
        r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        tag,
    )
    if match is None:
        message = f"Unsupported stable release tag: {tag!r}"
        raise ValueError(message)

    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def is_stable_release(
    tag: str,
    *,
    draft: bool,
    prerelease: bool,
) -> bool:
    """Return whether a GitHub release is eligible for stable-version selection.

    Args:
        tag: Release tag reported by GitHub.
        draft: Whether GitHub marks the release as a draft.
        prerelease: Whether GitHub marks the release as a prerelease.

    Returns:
        True for a published stable release with a supported tag format.
    """
    if draft or prerelease:
        return False

    try:
        parse_stable_tag(tag)
    except ValueError:
        # Unsupported tags are excluded when filtering GitHub releases.
        return False

    return True
