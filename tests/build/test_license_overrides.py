from __future__ import annotations

import json
from pathlib import Path

import pytest

from expo_jbm329.build.notices.cli import print_report
from expo_jbm329.build.notices.license_overrides import (
    LicenseOverride,
    LicenseOverrideError,
    load_license_overrides,
)
from expo_jbm329.build.notices.license_policy import (
    override_snippet,
    resolve_distribution_license,
    unused_override_issues,
)
from expo_jbm329.build.notices.models import (
    Component,
    ComponentId,
    ComponentKind,
    DistributionInfo,
    IssueSeverity,
    LicenseSource,
    NoticeIssue,
    NoticeReport,
)
from expo_jbm329.build.notices.renderer import render_manifest, render_notices_text


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _distribution(
    name: str = "minify_html",
    version: str = "0.18.1",
    *,
    license_expression: str | None = None,
    license_files: tuple[Path, ...] = (),
) -> DistributionInfo:
    return DistributionInfo(
        name=name,
        version=version,
        license_expression=license_expression,
        license_field=None,
        classifiers=(),
        requirements=(),
        homepage="https://example.invalid/minify-html",
        files=(),
        license_files=license_files,
    )


def _override(
    tmp_path: Path,
    *,
    version: str = "0.18.1",
    license_name: str | None = "MIT",
    with_file: bool = True,
) -> LicenseOverride:
    license_file = _write(tmp_path / "licenses" / "minify-html" / "LICENSE", "MIT License\nCopyright Wilson Lin\n")
    return LicenseOverride(
        distribution="Minify-HTML",
        version=version,
        license=license_name,
        license_file=license_file if with_file else None,
        source="https://example.invalid/LICENSE",
    )


# ---------------------------------------------------------------- loading


def test_load_license_overrides_parses_entries_and_resolves_files(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "LICENSE", "text")
    path = _write(
        tmp_path / "overrides.toml",
        '[[override]]\ndistribution = "pkg"\nversion = "1.0"\nlicense = "MIT"\n'
        'license_file = "pkg/LICENSE"\nsource = "https://example.invalid"\n',
    )

    (override,) = load_license_overrides(path)

    assert override == LicenseOverride(
        distribution="pkg",
        version="1.0",
        license="MIT",
        license_file=(tmp_path / "pkg" / "LICENSE").resolve(),
        source="https://example.invalid",
    )


def test_load_license_overrides_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert load_license_overrides(tmp_path / "missing.toml") == ()


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        ("[[override]\n", "invalid TOML"),
        ("[other]\n", "unknown top-level keys: other"),
        ('[[override]]\ndistribution = "a"\nversion = "1"\nsource = "s"\n', "at least one of"),
        ('[[override]]\ndistribution = "a"\nversion = "1"\nlicense = "MIT"\n', "missing key: source"),
        ('[[override]]\ndistribution = "a"\nversion = "1"\nlicense = "MIT"\nsource = "s"\nextra = 1\n', "unknown keys"),
        ('[[override]]\ndistribution = "a"\nversion = "1"\nlicense = ""\nsource = "s"\n', "non-empty string"),
        (
            '[[override]]\ndistribution = "a"\nversion = "1"\nlicense_file = "nope/LICENSE"\nsource = "s"\n',
            "license_file does not exist",
        ),
        (
            (
                '[[override]]\ndistribution = "A_b"\nversion = "1"\nlicense = "MIT"\nsource = "s"\n'
                '[[override]]\ndistribution = "a-B"\nversion = "2"\nlicense = "MIT"\nsource = "s"\n'
            ),
            "duplicate entry",
        ),
    ],
)
def test_load_license_overrides_rejects_invalid_files(tmp_path: Path, content: str, expected_message: str) -> None:
    path = _write(tmp_path / "overrides.toml", content)

    with pytest.raises(LicenseOverrideError, match=expected_message):
        load_license_overrides(path)


def test_project_overrides_file_is_valid() -> None:
    project_file = Path(__file__).resolve().parents[2] / "licenses" / "overrides.toml"

    overrides = load_license_overrides(project_file)

    assert all(override.license_file is None or override.license_file.is_file() for override in overrides)


# ---------------------------------------------------------------- policy


def test_override_fills_missing_license_and_text_for_matching_version(tmp_path: Path) -> None:
    result = resolve_distribution_license(_distribution(), (_override(tmp_path),))

    assert result.issues == ()
    assert result.license.name == "MIT"
    assert result.license.source is LicenseSource.OVERRIDE
    assert result.reference == "https://example.invalid/LICENSE"
    (text,) = result.texts
    assert text.source is LicenseSource.OVERRIDE
    assert text.text == "MIT License\nCopyright Wilson Lin"
    assert text.name.startswith("LICENSE (verified upstream")


def test_override_for_other_version_is_an_error_and_not_applied(tmp_path: Path) -> None:
    result = resolve_distribution_license(_distribution(version="0.19.0"), (_override(tmp_path),))

    (issue,) = result.issues
    assert issue.severity is IssueSeverity.ERROR
    assert "is for minify_html 0.18.1, but 0.19.0 is bundled" in issue.message
    assert result.license.name is None
    assert result.texts == ()


def test_override_fields_that_metadata_now_provides_are_errors(tmp_path: Path) -> None:
    shipped = _write(tmp_path / "minify_html-0.18.1.dist-info" / "LICENSE", "Shipped text")
    distribution = _distribution(license_expression="MIT", license_files=(shipped,))

    result = resolve_distribution_license(distribution, (_override(tmp_path),))

    messages = [issue.message for issue in result.issues]
    assert any("Remove 'license'" in message for message in messages)
    assert any("Remove 'license_file'" in message for message in messages)
    assert [text.text for text in result.texts] == ["Shipped text"]
    assert result.license.source is LicenseSource.METADATA


def test_missing_license_information_is_an_error_with_snippet() -> None:
    result = resolve_distribution_license(_distribution(), ())

    (issue,) = result.issues
    assert issue.severity is IssueSeverity.ERROR
    assert issue.component == "minify_html"
    assert "No license identifier or license text found for minify_html 0.18.1" in issue.message
    assert override_snippet(_distribution(), needs_license=True, needs_license_file=True) in issue.message


def test_partial_override_still_reports_remaining_gap(tmp_path: Path) -> None:
    result = resolve_distribution_license(_distribution(), (_override(tmp_path, with_file=False),))

    (issue,) = result.issues
    assert "No license text found" in issue.message
    assert 'license_file = "minify-html/LICENSE"' in issue.message
    assert "license = " not in issue.message


def test_override_snippet_is_valid_toml_shape() -> None:
    snippet = override_snippet(_distribution(), needs_license=False, needs_license_file=True)

    assert snippet.splitlines() == [
        "[[override]]",
        'distribution = "minify_html"',
        'version = "0.18.1"',
        'license_file = "minify-html/LICENSE"',
        'source = "https://example.invalid/minify-html"',
    ]


def test_unused_overrides_are_errors(tmp_path: Path) -> None:
    override = _override(tmp_path)

    assert unused_override_issues((override,), [_distribution(name="minify-html")]) == []
    (issue,) = unused_override_issues((override,), [_distribution(name="other")])
    assert issue.severity is IssueSeverity.ERROR
    assert "is unused" in issue.message


# ---------------------------------------------------------------- output


def _report_with_override(tmp_path: Path) -> NoticeReport:
    resolved = resolve_distribution_license(_distribution(), (_override(tmp_path),))
    component = Component(
        component_id=ComponentId(ComponentKind.PYTHON_DISTRIBUTION, "minify-html"),
        name="minify_html",
        version="0.18.1",
        license=resolved.license.name,
        homepage="https://example.invalid/minify-html",
        license_texts=resolved.texts,
        file_count=1,
        license_source=resolved.license.source,
        license_reference=resolved.reference,
    )
    return NoticeReport(components=(component,), first_party_file_count=0, issues=())


def test_supplied_license_is_rendered_and_recorded_in_manifest(tmp_path: Path) -> None:
    report = _report_with_override(tmp_path)

    notices = render_notices_text(report, "App", "1.0")
    manifest = json.loads(render_manifest(report, "App", "1.0"))

    assert "License verified at: https://example.invalid/LICENSE" in notices
    assert "Copyright Wilson Lin" in notices
    (component,) = manifest["components"]
    assert component["license_source"] == "override"
    assert component["license_reference"] == "https://example.invalid/LICENSE"
    assert component["license_texts"][0]["source"] == "override"


def test_print_report_ends_with_license_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _report_with_override(tmp_path)
    failing = NoticeReport(
        components=report.components,
        first_party_file_count=0,
        issues=(NoticeIssue(severity=IssueSeverity.ERROR, component="minify_html", message="missing"),),
    )

    print_report(report, "[t]")
    ok_output = capsys.readouterr().out
    print_report(failing, "[t]")
    failing_output = capsys.readouterr().err

    assert "[t] License check: OK, all 1 third-party components are resolved" in ok_output
    assert "License check: FAILED, 1 component(s) need action: minify_html" in failing_output
