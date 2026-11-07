from __future__ import annotations

import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.app.metadata import USER_MANUAL_URL

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPOSITORY_ROOT / "docs"


class _HtmlIds(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value is not None:
                self.ids.add(value)


def _explicit_anchors(markdown: str) -> set[str]:
    """Collect explicit heading/HTML IDs, excluding comments and code examples."""
    markdown = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    visible_lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in markdown.splitlines():
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence_character is not None:
            if (
                fence is not None
                and fence[1][0] == fence_character
                and len(fence[1]) >= fence_length
                and not fence[2].strip()
            ):
                fence_character = None
            continue
        if fence is not None:
            fence_character = fence[1][0]
            fence_length = len(fence[1])
            continue
        if line.startswith(("    ", "\t")):
            continue
        visible_lines.append(re.sub(r"(`+).*?\1", "", line))

    visible = "\n".join(visible_lines)
    heading_ids = set(
        re.findall(r"^ {0,3}#{1,6}\s+.*?\{[^{}\n]*#([^\s{}]+)[^{}\n]*\}\s*$", visible, flags=re.MULTILINE)
    )
    parser = _HtmlIds()
    parser.feed(visible)
    parser.close()
    return heading_ids | parser.ids


def _assert_documented_target(relative_target: str, docs_root: Path) -> None:
    """Require the public directory-style path and its explicit anchor to exist."""
    target = urlsplit(relative_target)
    assert not target.scheme and not target.netloc, f"Target must be relative: {relative_target}"
    assert not target.query, f"Unexpected help query: {relative_target}"
    assert not target.path.startswith("/"), f"Target bypasses manual base path: {relative_target}"
    assert "\\" not in target.path, f"Use URL separators: {relative_target}"
    assert not target.path or target.path.endswith("/"), f"Expected directory-style URL: {relative_target}"
    segments = target.path.strip("/").split("/") if target.path else []
    assert all(segment not in {"", ".", ".."} for segment in segments), f"Invalid help path: {relative_target}"
    if not segments:
        source = docs_root / "index.md"
    else:
        page = docs_root.joinpath(*segments)
        source = page / "index.md" if (page / "index.md").is_file() else page.with_suffix(".md")
    assert source.is_file(), f"Missing documentation page for {relative_target}: {source}"
    if target.fragment:
        anchors = _explicit_anchors(source.read_text(encoding="utf-8"))
        assert target.fragment in anchors, f"Missing explicit anchor #{target.fragment} in {source}"


@pytest.mark.parametrize("topic", list(HelpTopic), ids=[topic.name for topic in HelpTopic])
def test_every_help_topic_exists_in_docs(topic: HelpTopic) -> None:
    _assert_documented_target(topic.value, DOCS_ROOT)


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        (HelpTopic.HOME, "https://jbm329.github.io/expo-studio/"),
        (HelpTopic.WORKBENCH_LAYOUT, "https://jbm329.github.io/expo-studio/workbench/#window-layout"),
        (HelpTopic.GENERAL_SETTINGS, "https://jbm329.github.io/expo-studio/settings/general-settings/"),
        (HelpTopic.LOG_SETTINGS, "https://jbm329.github.io/expo-studio/settings/log-settings/"),
        (HelpTopic.DATABASE_CONNECTIONS, "https://jbm329.github.io/expo-studio/settings/database-connections/"),
    ],
)
def test_help_topic_url(topic: HelpTopic, expected: str) -> None:
    assert topic.url == expected


def test_manual_base_url_matches_site_configuration() -> None:
    with (REPOSITORY_ROOT / "zensical.toml").open("rb") as configuration:
        project = tomllib.load(configuration)["project"]
    assert project["site_url"] == USER_MANUAL_URL
    assert USER_MANUAL_URL.endswith("/")


@pytest.mark.parametrize(
    ("relative_target", "source_parts"),
    [
        ("", ("index.md",)),
        ("settings/", ("settings", "index.md")),
        ("settings/general-settings/#basic-settings", ("settings", "general-settings.md")),
    ],
)
def test_documented_target_maps_home_index_and_leaf_pages(
    tmp_path: Path, relative_target: str, source_parts: tuple[str, ...]
) -> None:
    source = tmp_path.joinpath(*source_parts)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("## Settings {#basic-settings}\n", encoding="utf-8")
    _assert_documented_target(relative_target, tmp_path)


def test_missing_documentation_page_fails(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="Missing documentation page"):
        _assert_documented_target("missing/#configure", tmp_path)


def test_anchor_on_another_page_does_not_pass(tmp_path: Path) -> None:
    (tmp_path / "index.md").write_text("## Settings {#configure}\n", encoding="utf-8")
    (tmp_path / "other.md").write_text("## Other settings {#different}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Missing explicit anchor #configure"):
        _assert_documented_target("other/#configure", tmp_path)


def test_missing_anchor_fails(tmp_path: Path) -> None:
    (tmp_path / "index.md").write_text("## Generated heading only\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Missing explicit anchor #generated-heading-only"):
        _assert_documented_target("#generated-heading-only", tmp_path)


def test_explicit_anchors_include_heading_attributes_and_html_ids() -> None:
    assert _explicit_anchors(
        "## Title {#heading}\n"
        "### Title {.class #styled-heading}\n"
        '<a id="legacy"></a>\n'
        "<span id='table-target'>Table</span>\n"
        '<span id="self-closing" />\n'
    ) == {"heading", "styled-heading", "legacy", "table-target", "self-closing"}


def test_example_and_comment_anchors_do_not_pass() -> None:
    markdown = (
        "<!--\n## Hidden {#comment}\n<span id='comment-html'></span>\n-->\n"
        "```markdown\n## Example {#fenced}\n<a id='fenced-html'></a>\n```\n"
        "~~~~markdown\n## Example {#tilde-fenced}\n~~~\n## Still fenced {#still-fenced}\n~~~~\n"
        "    ## Indented {#indented}\n"
        "Inline `<a id='inline-code'></a>` example.\n"
        "Plain text {#not-a-heading}\n"
        "## Real {#real}\n"
    )
    assert _explicit_anchors(markdown) == {"real"}


@pytest.mark.parametrize(
    "relative_target",
    [
        "https://example.com/",
        "//example.com/",
        "/workbench/",
        "../workbench/",
        "workbench/?query=1",
        "workbench.md",
        "workbench\\/",
    ],
)
def test_invalid_target_shapes_fail(tmp_path: Path, relative_target: str) -> None:
    with pytest.raises(AssertionError):
        _assert_documented_target(relative_target, tmp_path)
