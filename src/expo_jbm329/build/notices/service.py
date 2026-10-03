"""Analyse a PyInstaller onedir build and generate third-party notices."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.utils import canonicalize_name

from expo_jbm329.build.build_utils import project_root
from expo_jbm329.build.notices.attribution import (
    FIRST_PARTY_COMPONENT,
    LINUX_SYSTEM_RUNTIME_COMPONENT,
    AttributionContext,
    AttributionResult,
    attribute_entries,
)
from expo_jbm329.build.notices.dependency_scope import classify_dependency_scope
from expo_jbm329.build.notices.distributions import DistributionIndex, load_installed_distributions
from expo_jbm329.build.notices.license_overrides import (
    OVERRIDES_DIRECTORY_NAME,
    OVERRIDES_FILE_NAME,
    LicenseOverride,
    load_license_overrides,
)
from expo_jbm329.build.notices.license_policy import resolve_distribution_license, unused_override_issues
from expo_jbm329.build.notices.models import (
    BundledEntry,
    Component,
    ComponentId,
    ComponentKind,
    IssueSeverity,
    NoticeIssue,
    NoticeReport,
)
from expo_jbm329.build.notices.pyinstaller_toc import list_onedir_files, load_bundle_contents
from expo_jbm329.build.notices.renderer import render_manifest, render_notices_text
from expo_jbm329.build.notices.runtime_components import (
    build_linux_system_runtime_component,
    build_msvc_runtime_component,
    build_python_runtime_component,
)
from expo_jbm329.build.version import (
    THIRD_PARTY_MANIFEST_FILE,
    THIRD_PARTY_NOTICES_FILE,
    get_app_name,
    get_executable_name,
    get_package_name,
    get_version,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from expo_jbm329.build.notices.models import DistributionInfo

DEFAULT_ALLOWED_EXTRAS = ("profiling", "build")
DEFAULT_DEV_EXTRAS = ("dev",)


@dataclass(frozen=True)
class NoticeConfig:
    """Configuration for analysing one onedir build.

    Attributes:
        dist_dir: Onedir output directory, for example ``dist/expo``.
        work_dir: PyInstaller work directory containing the TOC files, for example ``build/expo``.
        application_name: Application display name used in the generated documents.
        application_version: Application version used in the generated documents.
        root_distribution: Name of the application distribution whose dependencies are checked.
        attribution: Build-specific attribution information.
        allowed_extras: Extras of the application whose dependencies may be bundled.
        dev_extras: Extras of the application whose dependencies must not be bundled.
        case_sensitive_paths: Whether onedir paths are compared case-sensitively.
        license_overrides: Version-pinned license information for distributions
            whose metadata is incomplete.
    """

    dist_dir: Path
    work_dir: Path
    application_name: str
    application_version: str
    root_distribution: str
    attribution: AttributionContext
    allowed_extras: tuple[str, ...] = DEFAULT_ALLOWED_EXTRAS
    dev_extras: tuple[str, ...] = DEFAULT_DEV_EXTRAS
    case_sensitive_paths: bool = os.name != "nt"
    license_overrides: tuple[LicenseOverride, ...] = ()


@dataclass(frozen=True)
class NoticeOutputFiles:
    """Paths of the generated notice documents."""

    notices: Path
    manifest: Path


def python_runtime_roots() -> tuple[Path, ...]:
    """Return the base directories of the running Python installation."""
    roots = [Path(sys.base_prefix)]
    if Path(sys.base_exec_prefix) != roots[0]:
        roots.append(Path(sys.base_exec_prefix))
    return tuple(roots)


def create_default_config(dist_dir: Path, work_dir: Path) -> NoticeConfig:
    """Return the notice configuration for Expo Studio builds.

    Args:
        dist_dir: Onedir output directory to analyse.
        work_dir: PyInstaller work directory of the same build.

    Returns:
        Notice configuration.

    Raises:
        LicenseOverrideError: If ``licenses/overrides.toml`` is invalid.
        OSError: If ``licenses/overrides.toml`` cannot be read.
    """
    root = project_root()
    return NoticeConfig(
        dist_dir=dist_dir,
        work_dir=work_dir,
        application_name=get_app_name(),
        application_version=get_version(),
        root_distribution=get_package_name(),
        attribution=AttributionContext(
            executable_name=get_executable_name(),
            first_party_distribution=get_package_name(),
            first_party_roots=(root / "src", root / "hooks"),
            python_runtime_roots=python_runtime_roots(),
        ),
        license_overrides=load_license_overrides(root / OVERRIDES_DIRECTORY_NAME / OVERRIDES_FILE_NAME),
    )


def _compare_onedir_contents(
    expected_files: frozenset[str],
    onedir_files: frozenset[str],
    case_sensitive: bool,
) -> list[NoticeIssue]:
    """Return errors for differences between the PyInstaller TOC and the onedir output."""

    def key(path: str) -> str:
        return path if case_sensitive else path.casefold()

    expected_by_key = {key(path): path for path in expected_files}
    onedir_by_key = {key(path): path for path in onedir_files}
    issues = [
        NoticeIssue(
            severity=IssueSeverity.ERROR,
            message=f"File in onedir output is not described by the PyInstaller build: {onedir_by_key[path_key]}",
        )
        for path_key in sorted(onedir_by_key.keys() - expected_by_key.keys())
    ]
    issues.extend(
        NoticeIssue(
            severity=IssueSeverity.ERROR,
            message=(
                "File listed by the PyInstaller build is missing from the onedir output "
                f"(stale work directory?): {expected_by_key[path_key]}"
            ),
        )
        for path_key in sorted(expected_by_key.keys() - onedir_by_key.keys())
    )
    return issues


def _unattributed_issues(entries: Sequence[BundledEntry]) -> list[NoticeIssue]:
    """Return errors for bundled entries that could not be attributed to a component."""
    return [
        NoticeIssue(
            severity=IssueSeverity.ERROR,
            message=f"Bundled {entry.origin} could not be attributed to a component: {entry.destination} "
            f"(source: {entry.source})",
        )
        for entry in sorted(entries, key=lambda entry: (entry.origin, entry.destination))
    ]


def _dependency_scope_issues(
    config: NoticeConfig,
    index: DistributionIndex,
    bundled_distributions: Iterable[DistributionInfo],
) -> list[NoticeIssue]:
    """Return issues for bundled distributions that are not runtime dependencies."""
    root = index.get(config.root_distribution)
    if root is None:
        return [
            NoticeIssue(
                severity=IssueSeverity.ERROR,
                message=f"Application distribution is not installed; cannot check dependency scope: "
                f"{config.root_distribution}",
            )
        ]

    scope = classify_dependency_scope(root, index, config.allowed_extras, config.dev_extras)
    issues: list[NoticeIssue] = []
    for distribution in bundled_distributions:
        key = canonicalize_name(distribution.name)
        if key in scope.dev_only:
            issues.append(
                NoticeIssue(
                    severity=IssueSeverity.ERROR,
                    component=distribution.name,
                    message=f"Development-only distribution is bundled: {distribution.name}. "
                    "Exclude it in expo.spec or build from an environment without dev extras.",
                )
            )
        elif key not in scope.allowed:
            issues.append(
                NoticeIssue(
                    severity=IssueSeverity.WARNING,
                    component=distribution.name,
                    message=f"Bundled distribution is not a declared dependency of {root.name}: {distribution.name}",
                )
            )
    return issues


def _distribution_component(
    component_id: ComponentId,
    distribution: DistributionInfo,
    file_count: int,
    overrides: Iterable[LicenseOverride],
) -> tuple[Component, tuple[NoticeIssue, ...]]:
    """Return the notice component for a bundled Python distribution and its license issues."""
    resolved = resolve_distribution_license(distribution, overrides)
    component = Component(
        component_id=component_id,
        name=distribution.name,
        version=distribution.version,
        license=resolved.license.name,
        homepage=distribution.homepage,
        license_texts=resolved.texts,
        file_count=file_count,
        license_source=resolved.license.source,
        license_reference=resolved.reference,
    )
    return component, resolved.issues


def _runtime_license_issues(component: Component) -> list[NoticeIssue]:
    """Return errors for a runtime component with incomplete license information."""
    missing = [
        label
        for label, is_missing in (
            ("license identifier", component.license is None),
            ("license text", not component.license_texts),
        )
        if is_missing
    ]
    if not missing:
        return []
    return [
        NoticeIssue(
            severity=IssueSeverity.ERROR,
            component=component.name,
            message=f"No {' or '.join(missing)} found for runtime component {component.name}",
        )
    ]


@dataclass(frozen=True)
class _ComponentsResult:
    """Third-party components of a build with the distributions and license issues behind them."""

    components: list[Component]
    bundled_distributions: list[DistributionInfo]
    license_issues: list[NoticeIssue]


def _build_components(
    attribution: AttributionResult,
    index: DistributionIndex,
    config: NoticeConfig,
) -> _ComponentsResult:
    """Return third-party components, the distributions they are based on and license issues."""
    components: list[Component] = []
    bundled_distributions: list[DistributionInfo] = []
    license_issues: list[NoticeIssue] = []

    for component_id, entries in attribution.components.items():
        match component_id.kind:
            case ComponentKind.FIRST_PARTY:
                continue
            case ComponentKind.PYTHON_RUNTIME:
                runtime = build_python_runtime_component(entries, config.attribution.python_runtime_roots)
                components.append(runtime)
                license_issues.extend(_runtime_license_issues(runtime))
            case ComponentKind.SYSTEM_RUNTIME:
                if component_id == LINUX_SYSTEM_RUNTIME_COMPONENT:
                    runtime = build_linux_system_runtime_component(entries)
                else:
                    runtime = build_msvc_runtime_component(entries)
                components.append(runtime)
                license_issues.extend(_runtime_license_issues(runtime))
            case ComponentKind.PYTHON_DISTRIBUTION:
                distribution = index.get(component_id.key)
                if distribution is None:
                    message = f"Attributed distribution is not installed: {component_id.key}"
                    raise LookupError(message)
                bundled_distributions.append(distribution)
                component, issues = _distribution_component(
                    component_id, distribution, len(entries), config.license_overrides
                )
                components.append(component)
                license_issues.extend(issues)

    components.sort(key=lambda component: (component.name.casefold(), component.component_id.key))
    bundled_distributions.sort(key=lambda distribution: distribution.name.casefold())
    license_issues.extend(unused_override_issues(config.license_overrides, bundled_distributions))
    return _ComponentsResult(
        components=components,
        bundled_distributions=bundled_distributions,
        license_issues=license_issues,
    )


def analyze_onedir(config: NoticeConfig, installed: Iterable[DistributionInfo]) -> NoticeReport:
    """Determine which third-party components a onedir build contains.

    Args:
        config: Build configuration.
        installed: Distributions installed in the environment that produced the build.

    Returns:
        Report with third-party components and validation issues.

    Raises:
        OSError: If the build output or a license file cannot be read.
        TocFormatError: If a PyInstaller TOC file has an unexpected format.
    """
    contents = load_bundle_contents(config.work_dir)
    onedir_files = list_onedir_files(config.dist_dir)
    index = DistributionIndex(installed)
    attribution = attribute_entries(contents.entries, index, config.attribution)
    built = _build_components(attribution, index, config)

    issues = _compare_onedir_contents(contents.expected_files, onedir_files, config.case_sensitive_paths)
    issues.extend(_unattributed_issues(attribution.unattributed))
    issues.extend(_dependency_scope_issues(config, index, built.bundled_distributions))
    issues.extend(built.license_issues)

    first_party_entries = attribution.components.get(FIRST_PARTY_COMPONENT, [])
    return NoticeReport(
        components=tuple(built.components),
        first_party_file_count=len(first_party_entries),
        issues=tuple(issues),
    )


def write_notice_files(report: NoticeReport, config: NoticeConfig, output_dir: Path) -> NoticeOutputFiles:
    """Write the notice document and manifest for a report.

    Args:
        report: Analysis result.
        config: Build configuration.
        output_dir: Directory to write the documents to.

    Returns:
        Paths of the written documents.

    Raises:
        OSError: If a document cannot be written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = NoticeOutputFiles(
        notices=output_dir / THIRD_PARTY_NOTICES_FILE,
        manifest=output_dir / THIRD_PARTY_MANIFEST_FILE,
    )
    outputs.notices.write_text(
        render_notices_text(report, config.application_name, config.application_version),
        encoding="utf-8",
        newline="\n",
    )
    outputs.manifest.write_text(
        render_manifest(report, config.application_name, config.application_version),
        encoding="utf-8",
        newline="\n",
    )
    return outputs


def generate_third_party_notices(
    config: NoticeConfig,
    output_dir: Path,
    installed: Iterable[DistributionInfo] | None = None,
) -> NoticeReport:
    """Analyse a onedir build and write its third-party notice documents.

    The documents are written even when the report contains errors so that the
    problems can be inspected.

    Args:
        config: Build configuration.
        output_dir: Directory to write the documents to.
        installed: Installed distributions. Defaults to the current environment.

    Returns:
        Analysis report.

    Raises:
        OSError: If the build output cannot be read or a document cannot be written.
        TocFormatError: If a PyInstaller TOC file has an unexpected format.
    """
    resolved_installed = load_installed_distributions() if installed is None else installed
    report = analyze_onedir(config, resolved_installed)
    write_notice_files(report, config, output_dir)
    return report
