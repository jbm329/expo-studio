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
require_correction_file = HELPER["require_correction_file"]
require_correction_changes = HELPER["require_correction_changes"]
resolve_stable_tag_commit = HELPER["resolve_stable_tag_commit"]
require_correction_source = HELPER["require_correction_source"]
require_documentation_setup = HELPER["require_documentation_setup"]
require_release_source = HELPER["require_release_source"]
require_bootstrap_content = HELPER["require_bootstrap_content"]


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


@pytest.mark.parametrize(
    "path",
    [
        "docs/index.md",
        "docs/data-preparation/derived-columns.md",
        "docs/assets/images/editor.png",
        "docs/assets/example.jpg",
        "docs/assets/example.jpeg",
        "docs/assets/example.gif",
        "docs/assets/example.webp",
        "docs/assets/example.avif",
    ],
)
def test_require_correction_file_accepts_manual_content(path: str) -> None:
    assert require_correction_file(path, "100644") is None


@pytest.mark.parametrize(
    "path",
    [
        "",
        "README.md",
        "zensical.toml",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/docs.yml",
        "src/example.py",
        "docs/example.py",
        "docs/example.html",
        "docs/assets/example.svg",
        "docs/assets/example.js",
        "docs/images/example.png",
        "/docs/index.md",
        "docs/../README.md",
        "./docs/index.md",
        "docs//index.md",
        "docs/index.md/",
        "docs\\index.md",
        "documentation/index.md",
    ],
)
def test_require_correction_file_rejects_out_of_scope_paths(path: str) -> None:
    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_file(path, "100644")


@pytest.mark.parametrize("mode", ["100755", "120000", "160000", "040000", "000000", ""])
def test_require_correction_file_rejects_non_content_modes(mode: str) -> None:
    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_file("docs/index.md", mode)


def commit_all(repository: Path) -> str:
    run_git(repository, "add", "--all")
    return create_test_commit(repository)


def test_correction_changes_accepts_unchanged_baseline(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")

    assert require_correction_changes(git_repository, baseline, baseline) is None


def test_correction_changes_accepts_manual_edits_additions_and_deletions(git_repository: Path) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("Original.\n", encoding="utf-8")
    (docs / "old.md").write_text("Old page.\n", encoding="utf-8")
    baseline = commit_all(git_repository)
    (docs / "index.md").write_text("Corrected.\n", encoding="utf-8")
    (docs / "old.md").unlink()
    (docs / "new page.md").write_text("New page.\n", encoding="utf-8")
    assets = docs / "assets"
    assets.mkdir()
    (assets / "example.png").write_bytes(b"Synthetic image fixture")
    source = commit_all(git_repository)

    assert require_correction_changes(git_repository, baseline, source) is None


@pytest.mark.parametrize("operation", ["modify", "delete", "rename"])
def test_correction_changes_rejects_out_of_scope_changes(git_repository: Path, operation: str) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    original = git_repository / "example.txt"
    if operation == "modify":
        original.write_text("Changed application content.\n", encoding="utf-8")
    elif operation == "delete":
        original.unlink()
    else:
        docs = git_repository / "docs"
        docs.mkdir()
        original.rename(docs / "renamed.md")
    source = commit_all(git_repository)

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_changes(git_repository, baseline, source)


def test_correction_changes_checks_all_commits_since_baseline(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    (git_repository / "example.txt").write_text("Out-of-scope change.\n", encoding="utf-8")
    commit_all(git_repository)
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("A later documentation change.\n", encoding="utf-8")
    source = commit_all(git_repository)

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_changes(git_repository, baseline, source)


def test_correction_changes_rejects_executable_markdown(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("Executable fixture.\n", encoding="utf-8")
    run_git(git_repository, "add", "docs/index.md")
    run_git(git_repository, "update-index", "--chmod=+x", "docs/index.md")
    source = create_test_commit(git_repository)

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_changes(git_repository, baseline, source)


@pytest.mark.parametrize("annotated", [False, True])
def test_resolve_stable_tag_commit_accepts_tag_types(git_repository: Path, annotated: bool) -> None:
    expected = run_git(git_repository, "rev-parse", "HEAD")
    if annotated:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "-a", "v1.4.0", "-m", "Test release")
    else:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.4.0")
    create_test_commit(git_repository)

    assert resolve_stable_tag_commit(git_repository, "v1.4.0") == expected


def test_resolve_stable_tag_commit_does_not_use_matching_branch(git_repository: Path) -> None:
    run_git(git_repository, "branch", "v1.4.0")

    with pytest.raises(subprocess.CalledProcessError):
        resolve_stable_tag_commit(git_repository, "v1.4.0")


@pytest.mark.parametrize("annotated", [False, True])
def test_resolve_stable_tag_commit_rejects_non_commit_tags(git_repository: Path, annotated: bool) -> None:
    blob = run_git(git_repository, "rev-parse", "HEAD:example.txt")
    if annotated:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "-a", "v1.4.0", blob, "-m", "Blob tag")
    else:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.4.0", blob)

    with pytest.raises(subprocess.CalledProcessError):
        resolve_stable_tag_commit(git_repository, "v1.4.0")


@pytest.mark.parametrize("tag", ["v1.4.0-rc1", "HEAD", "v1.4.0^{commit}", ""])
def test_resolve_stable_tag_commit_rejects_invalid_tag_before_git(tmp_path: Path, tag: str) -> None:
    with pytest.raises(ValueError, match="Unsupported stable release tag"):
        resolve_stable_tag_commit(tmp_path / "nonexistent", tag)


@pytest.fixture
def correction_history(git_repository: Path) -> tuple[Path, str, str]:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("Released instructions.\n", encoding="utf-8")
    (git_repository / "zensical.toml").write_text('[project]\nsite_name = "Test manual"\n', encoding="utf-8")
    (git_repository / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (git_repository / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    baseline = commit_all(git_repository)
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.4.0", baseline)
    (docs / "index.md").write_text("Corrected instructions.\n", encoding="utf-8")
    source = commit_all(git_repository)
    run_git(git_repository, "update-ref", "refs/remotes/origin/docs/1.4.0", source)
    return git_repository, baseline, source


def test_correction_source_accepts_matching_release_branch_and_scope(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, source = correction_history
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    assert require_correction_source(repository, "v1.4.0", source.upper(), releases) == baseline


def test_correction_source_rejects_newer_release(correction_history: tuple[Path, str, str]) -> None:
    repository, _, source = correction_history
    releases = [
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.5.0", "draft": False, "prerelease": False},
    ]

    with pytest.raises(ValueError, match="is not the latest published stable release"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_correction_source_rejects_unmerged_changes(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    source = create_test_commit(repository)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_correction_source_rejects_merged_code_changes(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    (repository / "example.txt").write_text("Application change.\n", encoding="utf-8")
    source = commit_all(repository)
    run_git(repository, "update-ref", "refs/remotes/origin/docs/1.4.0", source)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_correction_source_rejects_branch_outside_release_history(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    older = run_git(repository, "rev-parse", f"{baseline}^")
    run_git(repository, "update-ref", "refs/remotes/origin/docs/1.4.0", older)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_correction_source(repository, "v1.4.0", older, releases)


def test_documentation_setup_uses_committed_files(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    (repository / "zensical.toml").unlink()

    assert require_documentation_setup(repository, baseline) is None


@pytest.mark.parametrize("path", ["zensical.toml", "pyproject.toml", "uv.lock", "docs/index.md"])
def test_documentation_setup_rejects_missing_entry_file(correction_history: tuple[Path, str, str], path: str) -> None:
    repository, _, _ = correction_history
    repository.joinpath(*path.split("/")).unlink()
    source = commit_all(repository)

    with pytest.raises(ValueError, match="lacks required regular documentation files") as error:
        require_documentation_setup(repository, source)

    assert path in str(error.value)


def test_documentation_setup_rejects_executable_entry_file(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    run_git(repository, "update-index", "--chmod=+x", "zensical.toml")
    source = create_test_commit(repository)

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_documentation_setup(repository, source)


def test_correction_source_rejects_baseline_without_documentation(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.3.0", baseline)
    releases = [{"tag_name": "v1.3.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_correction_source(git_repository, "v1.3.0", baseline, releases)


def test_correction_source_rejects_deleted_landing_page(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    (repository / "docs" / "index.md").unlink()
    source = commit_all(repository)
    run_git(repository, "update-ref", "refs/remotes/origin/docs/1.4.0", source)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_release_source_accepts_exact_tagged_commit(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    assert require_release_source(repository, "v1.4.0", baseline.upper(), releases) == baseline


@pytest.mark.parametrize("use_older_commit", [False, True])
def test_release_source_rejects_other_commits(
    correction_history: tuple[Path, str, str], use_older_commit: bool
) -> None:
    repository, baseline, correction = correction_history
    source = run_git(repository, "rev-parse", f"{baseline}^") if use_older_commit else correction
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="does not match release") as error:
        require_release_source(repository, "v1.4.0", source, releases)

    assert source in str(error.value)
    assert baseline in str(error.value)


def test_release_source_rejects_superseded_release(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    releases = [
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.5.0", "draft": False, "prerelease": False},
    ]

    with pytest.raises(ValueError, match="is not the latest published stable release"):
        require_release_source(repository, "v1.4.0", baseline, releases)


def test_release_source_rejects_baseline_without_documentation(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.3.0", baseline)
    releases = [{"tag_name": "v1.3.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_release_source(git_repository, "v1.3.0", baseline, releases)


@pytest.fixture
def bootstrap_history(git_repository: Path) -> tuple[Path, str]:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text(
        "# Expo Studio User Manual\n\nThe user manual is under construction.\n", encoding="utf-8"
    )
    return git_repository, commit_all(git_repository)


def test_bootstrap_content_accepts_committed_placeholder(bootstrap_history: tuple[Path, str]) -> None:
    repository, source = bootstrap_history
    (repository / "docs" / "index.md").write_text("Uncommitted content.\n", encoding="utf-8")

    assert require_bootstrap_content(repository, source) is None


@pytest.mark.parametrize("extra_path", ["guide.md", "assets/image.png", ".hidden.md"])
def test_bootstrap_content_rejects_additional_files(bootstrap_history: tuple[Path, str], extra_path: str) -> None:
    repository, _ = bootstrap_history
    extra = repository.joinpath("docs", *extra_path.split("/"))
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("Extra content.\n", encoding="utf-8")
    source = commit_all(repository)

    with pytest.raises(ValueError, match="must contain only the regular docs/index.md"):
        require_bootstrap_content(repository, source)


@pytest.mark.parametrize(
    "content",
    [
        "# Expo Studio User Manual\n\nActual feature instructions.\n",
        "# Expo Studio User Manual\n\nThe user manual is under construction.\n\n<script>alert(1)</script>",
        "# Expo Studio User Manual\n\nThe user manual is under construction.\n\n[Guide](guide.md)",
        "",
    ],
)
def test_bootstrap_content_rejects_unapproved_landing_text(bootstrap_history: tuple[Path, str], content: str) -> None:
    repository, _ = bootstrap_history
    (repository / "docs" / "index.md").write_text(content, encoding="utf-8")
    source = commit_all(repository)

    with pytest.raises(ValueError, match="approved under-construction heading and message"):
        require_bootstrap_content(repository, source)


def test_bootstrap_content_rejects_missing_docs(git_repository: Path) -> None:
    source = run_git(git_repository, "rev-parse", "HEAD")

    with pytest.raises(ValueError, match="must contain only the regular docs/index.md"):
        require_bootstrap_content(git_repository, source)


def test_bootstrap_content_rejects_executable_placeholder(bootstrap_history: tuple[Path, str]) -> None:
    repository, _ = bootstrap_history
    run_git(repository, "update-index", "--chmod=+x", "docs/index.md")
    source = create_test_commit(repository)

    with pytest.raises(ValueError, match="must contain only the regular docs/index.md"):
        require_bootstrap_content(repository, source)
