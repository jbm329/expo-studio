"""Render third-party notice reports as text and JSON."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from expo_jbm329.build.notices.models import LicenseSource

if TYPE_CHECKING:
    from expo_jbm329.build.notices.models import Component, NoticeReport

MANIFEST_SCHEMA_VERSION = 1
SECTION_SEPARATOR = "=" * 79
TEXT_SEPARATOR = "-" * 79
UNKNOWN_VALUE = "UNKNOWN"


def _version_suffix(component: Component) -> str:
    """Return the component version prefixed by a space, or an empty string."""
    return f" {component.version}" if component.version else ""


def _summary_table(components: tuple[Component, ...]) -> list[str]:
    """Return aligned summary table lines for all components."""
    header = ("Component", "Version", "License")
    rows = [(component.name, component.version or "-", component.license or UNKNOWN_VALUE) for component in components]
    name_width = max([len(header[0]), *(len(row[0]) for row in rows)])
    version_width = max([len(header[1]), *(len(row[1]) for row in rows)])
    lines = [f"{header[0]:<{name_width}}  {header[1]:<{version_width}}  {header[2]}"]
    lines.append(f"{'-' * name_width}  {'-' * version_width}  {'-' * len(header[2])}")
    lines.extend(
        f"{name:<{name_width}}  {version:<{version_width}}  {license_name}" for name, version, license_name in rows
    )
    return lines


def _component_section(component: Component) -> list[str]:
    """Return the detailed notice lines for one component."""
    lines = [
        SECTION_SEPARATOR,
        f"{component.name}{_version_suffix(component)}",
        SECTION_SEPARATOR,
        f"License: {component.license or UNKNOWN_VALUE}",
    ]
    if component.license_source is LicenseSource.OVERRIDE:
        lines.append("License note: Not declared in the package metadata; verified against the upstream project.")
    if component.homepage is not None:
        lines.append(f"Homepage: {component.homepage}")
    lines.append("")

    if not component.license_texts:
        lines.extend(["No license text was found in the package metadata.", ""])

    for license_text in component.license_texts:
        lines.extend([TEXT_SEPARATOR, license_text.name, TEXT_SEPARATOR, license_text.text, ""])

    return lines


def render_notices_text(report: NoticeReport, application_name: str, application_version: str) -> str:
    """Render the human-readable ``THIRD-PARTY-NOTICES`` document.

    The output contains no timestamps so that unchanged builds produce identical files.

    Args:
        report: Analysis result.
        application_name: Application display name.
        application_version: Application version.

    Returns:
        Notice document text.
    """
    lines = [
        "THIRD-PARTY SOFTWARE NOTICES AND INFORMATION",
        "",
        f"{application_name} {application_version}",
        "",
        "This application bundles the third-party components listed below. Each",
        "component is licensed under its own terms, reproduced in this document.",
        "These terms apply to the respective components only, not to the",
        "application as a whole.",
        "",
        SECTION_SEPARATOR,
        "SUMMARY",
        SECTION_SEPARATOR,
        "",
        *_summary_table(report.components),
        "",
    ]
    for component in report.components:
        lines.extend(_component_section(component))

    return "\n".join(lines).rstrip() + "\n"


def render_manifest(report: NoticeReport, application_name: str, application_version: str) -> str:
    """Render the machine-readable third-party manifest as JSON.

    Args:
        report: Analysis result.
        application_name: Application display name.
        application_version: Application version.

    Returns:
        JSON document text.
    """
    document = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "application": {"name": application_name, "version": application_version},
        "first_party_file_count": report.first_party_file_count,
        "components": [
            {
                "name": component.name,
                "key": component.component_id.key,
                "kind": str(component.component_id.kind),
                "version": component.version,
                "license": component.license,
                "license_source": str(component.license_source),
                "homepage": component.homepage,
                "file_count": component.file_count,
                "license_texts": [
                    {
                        "files": license_text.name.splitlines(),
                        "sha256": hashlib.sha256(license_text.text.encode("utf-8")).hexdigest(),
                    }
                    for license_text in component.license_texts
                ],
            }
            for component in report.components
        ],
        "issues": [
            {"severity": str(issue.severity), "component": issue.component, "message": issue.message}
            for issue in report.issues
        ],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
