"""Validate sources and release eligibility for documentation publication."""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class GitHubRelease(TypedDict):
    """Release metadata required for stable-version selection."""

    tag_name: str
    draft: bool
    prerelease: bool


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


def latest_stable_tag(releases: Sequence[GitHubRelease]) -> str:
    """Select the numerically newest published stable release tag.

    Args:
        releases: Release metadata, in any order, collected from GitHub.

    Returns:
        The highest supported stable release tag.

    Raises:
        ValueError: If no supported published stable release is available.
    """
    eligible_tags = [
        release["tag_name"]
        for release in releases
        if is_stable_release(
            release["tag_name"],
            draft=release["draft"],
            prerelease=release["prerelease"],
        )
    ]
    if not eligible_tags:
        message = "No supported published stable release is available."
        raise ValueError(message)

    return max(eligible_tags, key=parse_stable_tag)


def require_latest_stable_tag(expected_tag: str, releases: Sequence[GitHubRelease]) -> None:
    """Require the requested baseline to match the newest stable release.

    Args:
        expected_tag: Stable release tag the caller intends to document.
        releases: Release metadata collected from GitHub.

    Raises:
        ValueError: If the requested tag is unsupported, no stable release is
            available, or the requested tag is not the newest stable release.
    """
    parse_stable_tag(expected_tag)
    latest_tag = latest_stable_tag(releases)
    if expected_tag != latest_tag:
        message = f"Requested release {expected_tag!r} is not the latest published stable release {latest_tag!r}."
        raise ValueError(message)


def validate_commit_sha(source_sha: str) -> str:
    """Validate a full SHA-1 commit ID and normalize its hexadecimal casing.

    Args:
        source_sha: Explicit source commit ID supplied for publication.

    Returns:
        The lowercase, 40-character hexadecimal commit ID.

    Raises:
        ValueError: If the input is not a full SHA-1 object ID.

    Notes:
        This checks syntax only, not whether the object exists or is a commit.
    """
    if re.fullmatch(r"[0-9a-fA-F]{40}", source_sha) is None:
        message = f"Expected a full 40-character hexadecimal commit SHA: {source_sha!r}"
        raise ValueError(message)

    return source_sha.lower()


def require_commit(repository: Path, source_sha: str) -> str:
    """Require a full object ID to identify a local Git commit.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Explicit source commit ID supplied for publication.

    Returns:
        The validated lowercase commit ID.

    Raises:
        ValueError: If the SHA format is invalid or the object is not a commit.
        subprocess.CalledProcessError: If Git cannot inspect the object.
        OSError: If Git cannot be started or the working directory is invalid.
    """
    commit_sha = validate_commit_sha(source_sha)
    # The command is fixed and its only input argument is a validated object ID.
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "cat-file", "-t", commit_sha],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "commit":
        message = f"Publication source {commit_sha!r} is not a Git commit."
        raise ValueError(message)

    return commit_sha
