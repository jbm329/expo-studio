"""Apply manual license overrides and enforce complete license information.

Every bundled distribution must end up with a license identifier and at least
one license text. Gaps in package metadata are closed with version-pinned
entries in ``licenses/overrides.toml``. Entries that are stale, unused or no
longer needed are reported as errors so that the file stays accurate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from packaging.utils import canonicalize_name

from expo_jbm329.build.notices.license_overrides import (
    OVERRIDES_DIRECTORY_NAME,
    OVERRIDES_FILE_NAME,
    find_license_override,
)
from expo_jbm329.build.notices.licenses import read_license_file, resolve_license, resolve_license_texts
from expo_jbm329.build.notices.models import (
    IssueSeverity,
    LicenseSource,
    LicenseText,
    NoticeIssue,
    ResolvedLicense,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from expo_jbm329.build.notices.license_overrides import LicenseOverride
    from expo_jbm329.build.notices.models import DistributionInfo

OVERRIDES_PATH_HINT = f"{OVERRIDES_DIRECTORY_NAME}/{OVERRIDES_FILE_NAME}"
SUPPLIED_TEXT_LABEL_SUFFIX = " (verified upstream; not shipped in the package)"


@dataclass(frozen=True)
class DistributionLicense:
    """Final license information of a bundled distribution.

    Attributes:
        license: License identifier and where it comes from.
        texts: License texts.
        reference: Where manually supplied information was verified, if an override was applied.
        issues: Problems that must be fixed before release.
    """

    license: ResolvedLicense
    texts: tuple[LicenseText, ...]
    reference: str | None
    issues: tuple[NoticeIssue, ...]


def _error(distribution: DistributionInfo, message: str) -> NoticeIssue:
    """Return an error issue for a distribution."""
    return NoticeIssue(severity=IssueSeverity.ERROR, component=distribution.name, message=message)


def override_snippet(
    distribution: DistributionInfo,
    *,
    needs_license: bool,
    needs_license_file: bool,
) -> str:
    """Return a TOML entry template that closes the reported gaps.

    Args:
        distribution: Distribution with incomplete license information.
        needs_license: Whether the license identifier is missing.
        needs_license_file: Whether the license text is missing.

    Returns:
        TOML text to paste into the overrides file after filling in placeholders.
    """
    lines = [
        "[[override]]",
        f'distribution = "{distribution.name}"',
        f'version = "{distribution.version}"',
    ]
    if needs_license:
        lines.append('license = "<SPDX expression>"')
    if needs_license_file:
        lines.append(f'license_file = "{canonicalize_name(distribution.name)}/LICENSE"')
    source = distribution.homepage or "<URL of the upstream LICENSE at this version>"
    lines.append(f'source = "{source}"')
    return "\n".join(lines)


def _missing_information_issue(
    distribution: DistributionInfo,
    *,
    needs_license: bool,
    needs_license_file: bool,
) -> NoticeIssue:
    """Return the error for a distribution with missing license information."""
    missing = [
        label
        for label, is_missing in (("license identifier", needs_license), ("license text", needs_license_file))
        if is_missing
    ]
    snippet = override_snippet(distribution, needs_license=needs_license, needs_license_file=needs_license_file)
    return _error(
        distribution,
        f"No {' or '.join(missing)} found for {distribution.name} {distribution.version}. "
        f"Verify the license upstream and add this entry to {OVERRIDES_PATH_HINT}:\n{snippet}",
    )


def _supplied_text(license_file: Path) -> LicenseText:
    """Return a manually supplied license text.

    Raises:
        OSError: If the license file cannot be read.
    """
    text = read_license_file(license_file, name=license_file.name + SUPPLIED_TEXT_LABEL_SUFFIX)
    return LicenseText(name=text.name, text=text.text, source=LicenseSource.OVERRIDE)


def resolve_distribution_license(
    distribution: DistributionInfo,
    overrides: Iterable[LicenseOverride],
) -> DistributionLicense:
    """Combine declared license information with a matching override.

    Declared metadata always wins. An override must match the bundled version
    exactly, and each of its fields must fill a real gap.

    Args:
        distribution: Bundled distribution.
        overrides: Configured overrides.

    Returns:
        Final license information with any issues that block a release.

    Raises:
        OSError: If a license file cannot be read.
    """
    resolved = resolve_license(distribution)
    texts = resolve_license_texts(distribution)
    override = find_license_override(distribution.name, overrides)

    if override is not None and override.version != distribution.version:
        issue = _error(
            distribution,
            f"License override in {OVERRIDES_PATH_HINT} is for {distribution.name} {override.version}, "
            f"but {distribution.version} is bundled. Re-verify the license at {distribution.version}, "
            "update the license file if needed and bump 'version'.",
        )
        return DistributionLicense(license=resolved, texts=texts, reference=None, issues=(issue,))

    issues: list[NoticeIssue] = []
    reference: str | None = None
    if override is not None:
        reference = override.source
        if override.license is not None:
            if resolved.name is None:
                resolved = ResolvedLicense(name=override.license, source=LicenseSource.OVERRIDE)
            else:
                issues.append(
                    _error(
                        distribution,
                        f"{distribution.name} {distribution.version} now declares license '{resolved.name}'. "
                        f"Remove 'license' from its entry in {OVERRIDES_PATH_HINT}.",
                    )
                )
        if override.license_file is not None:
            if texts:
                issues.append(
                    _error(
                        distribution,
                        f"{distribution.name} {distribution.version} now ships its own license text. "
                        f"Remove 'license_file' from its entry in {OVERRIDES_PATH_HINT}.",
                    )
                )
            else:
                texts = (_supplied_text(override.license_file),)

    needs_license = resolved.name is None
    needs_license_file = not texts
    if needs_license or needs_license_file:
        issues.append(
            _missing_information_issue(
                distribution,
                needs_license=needs_license,
                needs_license_file=needs_license_file,
            )
        )

    return DistributionLicense(license=resolved, texts=texts, reference=reference, issues=tuple(issues))


def unused_override_issues(
    overrides: Iterable[LicenseOverride],
    bundled_distributions: Iterable[DistributionInfo],
) -> list[NoticeIssue]:
    """Return errors for overrides that target no bundled distribution.

    Args:
        overrides: Configured overrides.
        bundled_distributions: Distributions included in the build.

    Returns:
        One error per unused override.
    """
    bundled_keys = {canonicalize_name(distribution.name) for distribution in bundled_distributions}
    return [
        NoticeIssue(
            severity=IssueSeverity.ERROR,
            component=override.distribution,
            message=f"License override for {override.distribution} {override.version} is unused because the "
            f"distribution is not bundled. Remove the entry from {OVERRIDES_PATH_HINT}.",
        )
        for override in overrides
        if override.key not in bundled_keys
    ]
