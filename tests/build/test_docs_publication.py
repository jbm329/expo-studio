"""Tests for documentation publication policy."""

from pathlib import Path
from runpy import run_path

import pytest

HELPER_PATH = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "docs_publication.py"
HELPER = run_path(str(HELPER_PATH))
parse_stable_tag = HELPER["parse_stable_tag"]
is_stable_release = HELPER["is_stable_release"]
latest_stable_tag = HELPER["latest_stable_tag"]
validate_commit_sha = HELPER["validate_commit_sha"]


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
