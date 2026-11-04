"""Tests for documentation publication policy."""

import subprocess
from pathlib import Path
from runpy import run_path

import pytest

HELPER_PATH = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "docs_publication.py"
HELPER = run_path(str(HELPER_PATH))
parse_stable_tag = HELPER["parse_stable_tag"]
is_stable_release = HELPER["is_stable_release"]
latest_stable_tag = HELPER["latest_stable_tag"]
require_latest_stable_tag = HELPER["require_latest_stable_tag"]
validate_commit_sha = HELPER["validate_commit_sha"]
require_commit = HELPER["require_commit"]
require_ancestor = HELPER["require_ancestor"]
require_remote_branch_contains_commit = HELPER["require_remote_branch_contains_commit"]


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.0.0", (0, 0, 0)),
        ("v1.3.0", (1, 3, 0)),
        ("v1.10.2", (1, 10, 2)),
        ("v12.34.56", (12, 34, 56)),
    ],
)
def test_parse_stable_tag(tag: str, expected: tuple[int, int, int]) -> None:
    assert parse_stable_tag(tag) == expected


@pytest.mark.parametrize(
    "tag",
    [
        "",
        "1.3.0",
        "v1.3",
        "v1.3.0.1",
        "v1.4.0-rc1",
        "v1.4.0-a1",
        "v1.4.0-b1",
        "v1.3.0+build",
        "v01.3.0",
        "v1.03.0",
        "v1.3.00",
        " v1.3.0",
        "v1.3.0\n",
    ],
)
def test_parse_stable_tag_rejects_invalid_tags(tag: str) -> None:
    with pytest.raises(ValueError, match="Unsupported stable release tag"):
        parse_stable_tag(tag)


@pytest.mark.parametrize(
    ("tag", "draft", "prerelease", "expected"),
    [
        ("v1.4.0", False, False, True),
        ("v0.0.0", False, False, True),
        ("v1.4.0", True, False, False),
        ("v1.4.0", False, True, False),
        ("v1.4.0", True, True, False),
        ("v1.4.0-rc1", False, False, False),
        ("v1.4.0-a1", False, False, False),
        ("v1.4.0-b1", False, False, False),
        ("1.4.0", False, False, False),
        ("v01.4.0", False, False, False),
        ("", False, False, False),
    ],
)
def test_is_stable_release(
    tag: str,
    draft: bool,
    prerelease: bool,
    expected: bool,
) -> None:
    assert is_stable_release(tag, draft=draft, prerelease=prerelease) is expected


def test_stable_versions_compare_numerically() -> None:
    assert parse_stable_tag("v1.10.0") > parse_stable_tag("v1.9.0")
    assert parse_stable_tag("v2.0.0") > parse_stable_tag("v1.99.99")


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["v1.3.0"], "v1.3.0"),
        (["v1.9.0", "v1.10.0", "v1.2.0"], "v1.10.0"),
        (["v1.2.0", "v1.10.0", "v1.9.0"], "v1.10.0"),
        (["v1.99.99", "v2.0.0"], "v2.0.0"),
        (["v1.3.0", "v1.3.0"], "v1.3.0"),
    ],
)
def test_latest_stable_tag_uses_numeric_order(tags: list[str], expected: str) -> None:
    releases = [{"tag_name": tag, "draft": False, "prerelease": False} for tag in tags]

    assert latest_stable_tag(releases) == expected


def test_latest_stable_tag_excludes_ineligible_releases() -> None:
    releases = [
        {"tag_name": "v1.3.0", "draft": False, "prerelease": False},
        {"tag_name": "v9.0.0", "draft": True, "prerelease": False},
        {"tag_name": "v8.0.0", "draft": False, "prerelease": True},
        {"tag_name": "v7.0.0-rc1", "draft": False, "prerelease": False},
        {"tag_name": "v06.0.0", "draft": False, "prerelease": False},
        {"tag_name": "unrelated-tag", "draft": False, "prerelease": False},
    ]

    assert latest_stable_tag(releases) == "v1.3.0"


@pytest.mark.parametrize(
    "releases",
    [
        [],
        [{"tag_name": "v1.3.0", "draft": True, "prerelease": False}],
        [{"tag_name": "v1.3.0", "draft": False, "prerelease": True}],
        [{"tag_name": "v1.4.0-rc1", "draft": False, "prerelease": False}],
        [{"tag_name": "unrelated-tag", "draft": False, "prerelease": False}],
    ],
)
def test_latest_stable_tag_requires_an_eligible_release(releases: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError, match="No supported published stable release"):
        latest_stable_tag(releases)


def test_require_latest_stable_tag_accepts_current_baseline() -> None:
    releases = [
        {"tag_name": "v1.9.0", "draft": False, "prerelease": False},
        {"tag_name": "v2.0.0", "draft": True, "prerelease": False},
        {"tag_name": "v1.11.0", "draft": False, "prerelease": True},
        {"tag_name": "v1.10.0", "draft": False, "prerelease": False},
    ]

    assert require_latest_stable_tag("v1.10.0", releases) is None


@pytest.mark.parametrize("expected_tag", ["v1.9.0", "v1.11.0", "v2.0.0"])
def test_require_latest_stable_tag_rejects_other_baselines(expected_tag: str) -> None:
    releases = [
        {"tag_name": "v1.9.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.10.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.11.0", "draft": False, "prerelease": True},
        {"tag_name": "v2.0.0", "draft": True, "prerelease": False},
    ]

    with pytest.raises(ValueError, match="is not the latest published stable release") as error:
        require_latest_stable_tag(expected_tag, releases)

    assert expected_tag in str(error.value)
    assert "v1.10.0" in str(error.value)


@pytest.mark.parametrize("expected_tag", ["v1.10.0-rc1", "main", ""])
def test_require_latest_stable_tag_rejects_unsupported_tags(expected_tag: str) -> None:
    releases = [{"tag_name": "v1.10.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="Unsupported stable release tag"):
        require_latest_stable_tag(expected_tag, releases)


def test_require_latest_stable_tag_rejects_missing_stable_release() -> None:
    with pytest.raises(ValueError, match="No supported published stable release"):
        require_latest_stable_tag("v1.10.0", [])


def test_require_latest_stable_tag_rejects_superseded_baseline() -> None:
    releases = [{"tag_name": "v1.10.0", "draft": False, "prerelease": False}]
    require_latest_stable_tag("v1.10.0", releases)

    releases.append({"tag_name": "v1.11.0", "draft": False, "prerelease": False})

    with pytest.raises(ValueError, match="is not the latest published stable release"):
        require_latest_stable_tag("v1.10.0", releases)


@pytest.mark.parametrize(
    "source_sha",
    [
        "0123456789abcdef0123456789abcdef01234567",
        "0123456789ABCDEF0123456789ABCDEF01234567",
        "0123456789aBcDeF0123456789AbCdEf01234567",
    ],
)
def test_validate_commit_sha_normalizes_full_ids(source_sha: str) -> None:
    assert validate_commit_sha(source_sha) == source_sha.lower()


@pytest.mark.parametrize(
    "source_sha",
    [
        "",
        "main",
        "v1.3.0",
        "abcdef0",
        "a" * 39,
        "a" * 41,
        "a" * 64,
        "g" * 40,
        " " + "a" * 40,
        "a" * 40 + "\n",
        "a" * 40 + "^{commit}",
        "-" + "a" * 39,
    ],
)
def test_validate_commit_sha_rejects_non_full_ids(source_sha: str) -> None:
    with pytest.raises(ValueError, match="Expected a full 40-character hexadecimal commit SHA"):
        validate_commit_sha(source_sha)


def run_git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    run_git(tmp_path, "init", "--quiet")
    run_git(tmp_path, "config", "user.name", "Documentation Tests")
    run_git(tmp_path, "config", "user.email", "docs-tests@example.invalid")
    (tmp_path / "example.txt").write_text("Synthetic test content.\n", encoding="utf-8")
    run_git(tmp_path, "add", "example.txt")
    run_git(tmp_path, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Initial test commit")
    return tmp_path


@pytest.mark.parametrize("uppercase", [False, True])
def test_require_commit_accepts_existing_commit(git_repository: Path, uppercase: bool) -> None:
    commit_sha = run_git(git_repository, "rev-parse", "HEAD")

    assert require_commit(git_repository, commit_sha.upper() if uppercase else commit_sha) == commit_sha


@pytest.mark.parametrize("revision", ["HEAD:example.txt", "HEAD^{tree}", "refs/tags/example"])
def test_require_commit_rejects_other_object_types(git_repository: Path, revision: str) -> None:
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "-a", "example", "-m", "Annotated test tag")
    object_sha = run_git(git_repository, "rev-parse", revision)

    with pytest.raises(ValueError, match="is not a Git commit"):
        require_commit(git_repository, object_sha)


def test_require_commit_rejects_missing_object(git_repository: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        require_commit(git_repository, "0" * 40)


def test_require_commit_rejects_invalid_sha_before_running_git(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Expected a full 40-character hexadecimal commit SHA"):
        require_commit(tmp_path / "nonexistent", "main")


def test_require_commit_surfaces_invalid_repository(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        require_commit(tmp_path, "a" * 40)


def create_test_commit(repository: Path, message: str = "Test descendant") -> str:
    run_git(repository, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "--quiet", "-m", message)
    return run_git(repository, "rev-parse", "HEAD")


def test_require_ancestor_accepts_same_commit(git_repository: Path) -> None:
    commit_sha = run_git(git_repository, "rev-parse", "HEAD")

    assert require_ancestor(git_repository, commit_sha, commit_sha) is None


def test_require_ancestor_accepts_transitive_history(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    create_test_commit(git_repository)
    descendant = create_test_commit(git_repository)

    assert require_ancestor(git_repository, baseline.upper(), descendant.upper()) is None


def test_require_ancestor_rejects_reversed_history(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    descendant = create_test_commit(git_repository)

    with pytest.raises(ValueError, match="is not an ancestor of") as error:
        require_ancestor(git_repository, descendant, baseline)

    assert baseline in str(error.value)
    assert descendant in str(error.value)


def test_require_ancestor_rejects_divergent_history(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    first = create_test_commit(git_repository)
    run_git(git_repository, "checkout", "--quiet", "--detach", baseline)
    second = create_test_commit(git_repository, "Divergent test descendant")

    assert first != second
    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_ancestor(git_repository, first, second)


@pytest.mark.parametrize("missing_ancestor", [False, True])
def test_require_ancestor_surfaces_missing_commit(git_repository: Path, missing_ancestor: bool) -> None:
    existing = run_git(git_repository, "rev-parse", "HEAD")
    ancestor, descendant = ("0" * 40, existing) if missing_ancestor else (existing, "0" * 40)

    with pytest.raises(subprocess.CalledProcessError):
        require_ancestor(git_repository, ancestor, descendant)


@pytest.mark.parametrize("branch", ["main", "docs/1.4.0"])
def test_remote_branch_contains_tip_and_ancestors(git_repository: Path, branch: str) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    tip = create_test_commit(git_repository)
    run_git(git_repository, "update-ref", f"refs/remotes/origin/{branch}", tip)

    assert require_remote_branch_contains_commit(git_repository, branch, tip) == tip
    assert require_remote_branch_contains_commit(git_repository, branch, baseline) == tip


def test_remote_branch_rejects_unmerged_descendant(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "update-ref", "refs/remotes/origin/main", baseline)
    unmerged = create_test_commit(git_repository)

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_remote_branch_contains_commit(git_repository, "main", unmerged)


def test_remote_branch_does_not_fall_back_to_local_branch(git_repository: Path) -> None:
    source = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "branch", "docs/1.4.0", source)

    with pytest.raises(subprocess.CalledProcessError):
        require_remote_branch_contains_commit(git_repository, "docs/1.4.0", source)


@pytest.mark.parametrize("branch", ["main~1", "main^{commit}", "../main", "main\n", "main space"])
def test_remote_branch_rejects_invalid_ref_names(git_repository: Path, branch: str) -> None:
    source = run_git(git_repository, "rev-parse", "HEAD")

    with pytest.raises(subprocess.CalledProcessError):
        require_remote_branch_contains_commit(git_repository, branch, source)
