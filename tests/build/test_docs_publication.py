"""Tests for documentation publication policy."""

from pathlib import Path
from runpy import run_path

import pytest

HELPER_PATH = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "docs_publication.py"
HELPER = run_path(str(HELPER_PATH))
parse_stable_tag = HELPER["parse_stable_tag"]
is_stable_release = HELPER["is_stable_release"]


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
