"""Validate sources and release eligibility for documentation publication."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class GitHubRelease(TypedDict):
    """Release metadata required for stable-version selection."""

    tag_name: str
    draft: bool
    prerelease: bool


class PublicationManifest(TypedDict):
    """Versioned provenance stored alongside the published website."""

    schema_version: int
    mode: Literal["bootstrap", "release", "correction"]
    baseline_tag: str
    source_sha: str
    run_id: str


def parse_publication_manifest(value: object) -> PublicationManifest:
    """Validate publication provenance decoded from JSON.

    Args:
        value: Decoded JSON content of the publication manifest.

    Returns:
        Validated metadata with a normalized source commit ID.

    Raises:
        ValueError: If the manifest schema or any metadata field is invalid.

    Notes:
        A bootstrap baseline identifies the existing app release, not a claim
        that the placeholder documents that release. Metadata alone does not
        establish a successful deployment or commit eligibility.
    """
    required = {"schema_version", "mode", "baseline_tag", "source_sha", "run_id"}
    if not isinstance(value, dict) or set(value) != required:
        message = "Publication manifest must contain exactly the supported provenance fields."
        raise ValueError(message)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        message = "Unsupported publication manifest schema version."
        raise ValueError(message)
    mode = value["mode"]
    if mode not in ("bootstrap", "release", "correction"):
        message = "Unsupported publication manifest mode."
        raise ValueError(message)
    baseline = value["baseline_tag"]
    source = value["source_sha"]
    run_id = value["run_id"]
    if not isinstance(baseline, str) or not isinstance(source, str):
        message = "Publication manifest baseline and source must be strings."
        raise ValueError(message)  # noqa: TRY004 - Invalid decoded manifest data uses one validation error type.
    parse_stable_tag(baseline)
    source = validate_commit_sha(source)
    if not isinstance(run_id, str) or re.fullmatch(r"[1-9][0-9]*", run_id) is None:
        message = "Publication manifest run ID must be a positive decimal string."
        raise ValueError(message)
    return {
        "schema_version": 1,
        "mode": mode,
        "baseline_tag": baseline,
        "source_sha": source,
        "run_id": run_id,
    }


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


def require_documentation_setup(repository: Path, source_sha: str) -> None:
    """Require the documentation entry files to exist in a commit.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Full commit ID to inspect without checking it out.

    Raises:
        ValueError: If the commit ID is invalid or required regular files are missing.
        subprocess.CalledProcessError: If Git cannot inspect the commit.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        File presence does not establish valid configuration or buildability.
    """
    source = require_commit(repository, source_sha)
    required_paths = ("zensical.toml", "pyproject.toml", "uv.lock", "docs/index.md")
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "ls-tree", "-r", "-z", source, "--", *required_paths],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    regular_paths = set()
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, object_type, _ = metadata.split()
        if mode == b"100644" and object_type == b"blob":
            regular_paths.add(path.decode("utf-8"))
    missing = sorted(set(required_paths) - regular_paths)
    if missing:
        message = f"Commit {source!r} lacks required regular documentation files: {', '.join(missing)}."
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
        ValueError: If release eligibility, source format, required documentation
            files, ancestry, or correction scope fails.
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
    require_documentation_setup(repository, baseline)
    require_remote_branch_contains_commit(repository, f"docs/{expected_tag.removeprefix('v')}", source)
    require_correction_changes(repository, baseline, source)
    require_documentation_setup(repository, source)
    return baseline


def require_release_source(
    repository: Path,
    expected_tag: str,
    source_sha: str,
    releases: Sequence[GitHubRelease],
) -> str:
    """Require automatic publication to use the newest stable release's commit.

    Args:
        repository: Repository with freshly fetched release tags.
        expected_tag: Published stable release to document.
        source_sha: Full commit ID supplied by the release workflow.
        releases: Current release metadata collected from GitHub.

    Returns:
        The validated release commit ID.

    Raises:
        ValueError: If the release is ineligible, the source does not match the
            tag, or required documentation files are missing.
        subprocess.CalledProcessError: If required Git objects or tags are
            missing, or Git cannot inspect them.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        The caller must enforce successful application release publication.
        This does not yet check website buildability or deployed provenance.
    """
    source = validate_commit_sha(source_sha)
    require_latest_stable_tag(expected_tag, releases)
    release_commit = resolve_stable_tag_commit(repository, expected_tag)
    if source != release_commit:
        message = f"Publication source {source!r} does not match release {expected_tag!r} commit {release_commit!r}."
        raise ValueError(message)
    require_documentation_setup(repository, release_commit)
    return release_commit


def require_bootstrap_content(repository: Path, source_sha: str) -> None:
    """Restrict the committed bootstrap manual to the approved placeholder.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Full commit ID containing the proposed bootstrap content.

    Raises:
        ValueError: If the documentation tree or landing-page text is unexpected.
        subprocess.CalledProcessError: If Git cannot inspect the source.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If the landing page is not valid UTF-8.

    Notes:
        Configuration routing and release eligibility are checked separately.
    """
    source = require_commit(repository, source_sha)
    tree = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "ls-tree", "-r", "-z", source, "--", "docs"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    entries = [entry for entry in tree.stdout.split(b"\0") if entry]
    if len(entries) != 1:
        message = "Bootstrap documentation must contain only the regular docs/index.md placeholder."
        raise ValueError(message)
    metadata, path = entries[0].split(b"\t", 1)
    mode, object_type, _ = metadata.split()
    if path != b"docs/index.md" or mode != b"100644" or object_type != b"blob":
        message = "Bootstrap documentation must contain only the regular docs/index.md placeholder."
        raise ValueError(message)
    page = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "show", f"{source}:docs/index.md"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    content = page.stdout.decode("utf-8").replace("\r\n", "\n").strip()
    expected = "# Expo Studio User Manual\n\nThe user manual is under construction."
    if content != expected:
        message = "Bootstrap landing page must contain only the approved under-construction heading and message."
        raise ValueError(message)


def require_bootstrap_configuration(repository: Path, source_sha: str) -> None:
    """Require the committed bootstrap configuration to match the approved setup.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Full commit ID containing the proposed configuration.

    Raises:
        ValueError: If required files are missing, TOML is invalid, or the
            configuration differs from the approved bootstrap settings.
        subprocess.CalledProcessError: If Git cannot inspect the source.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If the configuration is not valid UTF-8.

    Notes:
        Parsed values are compared, so comments and formatting may differ.
        Normal released manuals are not restricted to this bootstrap setup.
    """
    source = validate_commit_sha(source_sha)
    require_documentation_setup(repository, source)
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "show", f"{source}:zensical.toml"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    configuration = tomllib.loads(result.stdout.decode("utf-8"))
    expected = {
        "project": {
            "site_name": "Expo Studio User Manual",
            "site_url": "https://jbm329.github.io/expo-studio/",
            "docs_dir": "docs",
            "site_dir": "site",
        }
    }
    if configuration != expected:
        message = "Bootstrap configuration must match the approved site identity, URL, and source/output directories."
        raise ValueError(message)


def require_publication_progress(
    repository: Path,
    published_tag: str,
    published_sha: str,
    expected_tag: str,
    source_sha: str,
) -> None:
    """Prevent publication from reverting an existing released manual.

    Args:
        repository: Repository containing the published and proposed commits.
        published_tag: Application baseline recorded by the published manual.
        published_sha: Source commit recorded by the published manual.
        expected_tag: Application baseline of the proposed publication.
        source_sha: Source commit of the proposed publication.

    Raises:
        ValueError: If IDs are invalid, the proposed version is older, or its
            same-version source does not descend from the published source.
        subprocess.CalledProcessError: If Git cannot inspect required commits.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        Call only for released manuals, after validating publication eligibility.
        Bootstrap transitions and missing deployment state are handled separately.
    """
    published_version = parse_stable_tag(published_tag)
    proposed_version = parse_stable_tag(expected_tag)
    published_source = require_commit(repository, published_sha)
    source = require_commit(repository, source_sha)
    if proposed_version < published_version:
        message = f"Publication for {expected_tag!r} would replace the newer published manual for {published_tag!r}."
        raise ValueError(message)
    if proposed_version == published_version:
        require_ancestor(repository, published_source, source)


def require_manifest_progress(
    repository: Path,
    published: PublicationManifest,
    proposed: PublicationManifest,
) -> None:
    """Require a publication to advance or repeat the deployed provenance.

    Args:
        repository: Repository containing both publication source commits.
        published: Validated provenance of the existing deployment.
        proposed: Validated provenance of the proposed deployment.

    Raises:
        ValueError: If bootstrap would replace a released manual, the application
            baseline moves backward, or same-version source history regresses.
        subprocess.CalledProcessError: If required Git commits cannot be inspected.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        Validate both manifests before calling. Source eligibility must also be
        checked independently; run IDs are provenance, not publication ordering.
    """
    if published["mode"] != "bootstrap" and proposed["mode"] == "bootstrap":
        message = "Bootstrap cannot replace an already published released manual."
        raise ValueError(message)
    require_publication_progress(
        repository,
        published["baseline_tag"],
        published["source_sha"],
        proposed["baseline_tag"],
        proposed["source_sha"],
    )


def require_bootstrap_source(
    repository: Path,
    expected_tag: str,
    source_sha: str,
    releases: Sequence[GitHubRelease],
) -> str:
    """Validate the initial landing-page publication against a pre-docs release.

    Args:
        repository: Repository with freshly fetched release tags and origin refs.
        expected_tag: Latest stable release, which must predate site configuration.
        source_sha: Full commit ID of the approved bootstrap source on main.
        releases: Current release metadata collected from GitHub.

    Returns:
        The resolved stable-release baseline commit ID.

    Raises:
        ValueError: If the baseline already contains site configuration or any
            release, source, branch, content, or configuration check fails.
        subprocess.CalledProcessError: If Git cannot inspect required objects.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If source text is not valid UTF-8.

    Notes:
        Any committed zensical.toml entry closes bootstrap, even if incomplete.
        Deployment provenance and website buildability are checked separately.
    """
    source = validate_commit_sha(source_sha)
    require_latest_stable_tag(expected_tag, releases)
    baseline = resolve_stable_tag_commit(repository, expected_tag)
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "ls-tree", "-z", baseline, "--", "zensical.toml"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    if result.stdout:
        message = f"Bootstrap is unavailable: stable release {expected_tag!r} already contains site configuration."
        raise ValueError(message)
    require_remote_branch_contains_commit(repository, "main", source)
    require_ancestor(repository, baseline, source)
    require_bootstrap_configuration(repository, source)
    require_bootstrap_content(repository, source)
    return baseline
