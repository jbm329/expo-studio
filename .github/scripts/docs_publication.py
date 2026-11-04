"""Validate sources and release eligibility for documentation publication."""

from __future__ import annotations

import re
import subprocess
from pathlib import PurePosixPath
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


def require_correction_changes(repository: Path, baseline_sha: str, source_sha: str) -> None:
    """Require the net changes from a release baseline to contain only manual files.

    Args:
        repository: Working directory of the checked-out repository.
        baseline_sha: Full commit ID of the stable release baseline.
        source_sha: Full commit ID of the proposed corrected documentation.

    Raises:
        ValueError: If ancestry fails or a changed file is outside correction scope.
        subprocess.CalledProcessError: If Git cannot inspect the commits or diff.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If a changed path is not valid UTF-8.

    Notes:
        Checks the complete tree difference, not only the most recent commit.
        Renames are inspected as a deletion and an addition.
    """
    baseline = validate_commit_sha(baseline_sha)
    source = validate_commit_sha(source_sha)
    require_ancestor(repository, baseline, source)
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "--no-replace-objects",
            "diff",
            "--raw",
            "--no-abbrev",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "-z",
            baseline,
            source,
            "--",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    fields = result.stdout.split(b"\0")
    for index in range(0, len(fields) - 1, 2):
        metadata = fields[index].decode("ascii").split()
        path = fields[index + 1].decode("utf-8")
        for mode in (metadata[0].removeprefix(":"), metadata[1]):
            if mode != "000000":
                require_correction_file(path, mode)


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


def resolve_stable_tag_commit(repository: Path, tag: str) -> str:
    """Resolve an exact stable release tag to its underlying commit.

    Args:
        repository: Working directory of the checked-out repository.
        tag: Stable release tag in vMAJOR.MINOR.PATCH format.

    Returns:
        The lowercase commit ID, peeling annotated tags when necessary.

    Raises:
        ValueError: If the tag format is unsupported.
        subprocess.CalledProcessError: If the exact tag is missing, does not
            resolve to a commit, or Git cannot inspect it.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        The caller must fetch the release tags before resolving them.
        A local tag does not establish that a GitHub Release was published.
    """
    parse_stable_tag(tag)
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return require_commit(repository, result.stdout.strip())


def require_ancestor(repository: Path, ancestor_sha: str, descendant_sha: str) -> None:
    """Require one commit to be an ancestor of another, allowing equality.

    Args:
        repository: Working directory of the checked-out repository.
        ancestor_sha: Full commit ID of the required baseline.
        descendant_sha: Full commit ID whose history must include the baseline.

    Raises:
        ValueError: If either ID is invalid or the ancestry requirement fails.
        subprocess.CalledProcessError: If Git cannot inspect the commits or history.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        The repository must contain the history needed to establish ancestry.
    """
    ancestor = require_commit(repository, ancestor_sha)
    descendant = require_commit(repository, descendant_sha)
    # Git uses status 1 for a valid query with no ancestor relationship.
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "merge-base", "--is-ancestor", ancestor, descendant],  # noqa: S607
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        message = f"Commit {ancestor!r} is not an ancestor of {descendant!r}."
        raise ValueError(message)
    result.check_returncode()


def require_remote_branch_contains_commit(repository: Path, branch: str, source_sha: str) -> str:
    """Require the source commit to be reachable from an origin branch.

    Args:
        repository: Working directory of the checked-out repository.
        branch: Branch name, such as main or docs/1.4.0, without a ref prefix.
        source_sha: Full commit ID to check for branch membership.

    Returns:
        The resolved branch-tip commit ID.

    Raises:
        ValueError: If the source ID is invalid or is not in the branch history.
        subprocess.CalledProcessError: If the branch name is invalid, the remote
            branch is missing, or Git cannot inspect the history.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        This inspects local remote-tracking refs. The caller must fetch fresh
        origin branch refs and sufficient history before calling it. Reachability
        does not establish that a pull request was reviewed or approved.
    """
    source = require_commit(repository, source_sha)
    remote_ref = f"refs/remotes/origin/{branch}"
    subprocess.run(  # noqa: S603
        ["git", "check-ref-format", remote_ref],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "show-ref", "--verify", "--hash", remote_ref],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    branch_tip = require_commit(repository, result.stdout.strip())
    require_ancestor(repository, source, branch_tip)
    return branch_tip


def require_correction_file(path: str, mode: str) -> None:
    """Require a correction file to be non-executable manual content.

    Args:
        path: Repository-relative Git path, using forward slashes.
        mode: Git file mode, which must be 100644 for a regular content file.

    Raises:
        ValueError: If the path or file mode is outside the correction scope.

    Notes:
        SVG and HTML are excluded because they can contain active content.
        This validates metadata, not file contents or image decoding.
    """
    file_path = PurePosixPath(path)
    canonical = (
        file_path.as_posix() == path
        and not file_path.is_absolute()
        and ".." not in file_path.parts
        and "\\" not in path
        and PurePosixPath("docs") in file_path.parents
    )
    markdown = file_path.suffix == ".md"
    image = PurePosixPath("docs/assets") in file_path.parents and file_path.suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
    }
    if mode != "100644" or not canonical or not (markdown or image):
        message = f"Correction file is outside the permitted manual content scope: {path!r} (mode {mode!r})."
        raise ValueError(message)


def require_correction_source(
    repository: Path,
    expected_tag: str,
    source_sha: str,
    releases: Sequence[GitHubRelease],
) -> str:
    """Validate a correction's release baseline, branch history, and changed files.

    Args:
        repository: Repository with freshly fetched release tags and origin refs.
        expected_tag: Published stable release the correction must document.
        source_sha: Full commit ID of the proposed corrected documentation.
        releases: Current release metadata collected from GitHub.

    Returns:
        The resolved release-baseline commit ID.

    Raises:
        ValueError: If release eligibility, source format, ancestry, or scope fails.
        subprocess.CalledProcessError: If required Git objects or refs are missing,
            or Git cannot inspect the history.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If a changed path is not valid UTF-8.

    Notes:
        This does not yet check website buildability or deployed provenance.
        Maintenance-branch reachability does not prove pull-request approval.
    """
    source = validate_commit_sha(source_sha)
    require_latest_stable_tag(expected_tag, releases)
    baseline = resolve_stable_tag_commit(repository, expected_tag)
    require_remote_branch_contains_commit(repository, f"docs/{expected_tag.removeprefix('v')}", source)
    require_correction_changes(repository, baseline, source)
    return baseline
