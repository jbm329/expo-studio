"""Data models used when analysing bundled third-party components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class EntryOrigin(StrEnum):
    """Where a bundled entry lives inside the PyInstaller output."""

    FILE = "file"
    ARCHIVE_MODULE = "archive-module"


class ComponentKind(StrEnum):
    """Kind of component a bundled entry is attributed to."""

    PYTHON_DISTRIBUTION = "python-distribution"
    PYTHON_RUNTIME = "python-runtime"
    SYSTEM_RUNTIME = "system-runtime"
    FIRST_PARTY = "first-party"


class IssueSeverity(StrEnum):
    """Severity of an issue found during analysis."""

    ERROR = "error"
    WARNING = "warning"


class LicenseSource(StrEnum):
    """Where the license identifier of a component comes from."""

    METADATA = "metadata"
    CLASSIFIER = "classifier"
    OVERRIDE = "override"
    BUILTIN = "builtin"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BundledEntry:
    """A single file or archived module included in the onedir output.

    Attributes:
        destination: For files, the POSIX-style path relative to the onedir root.
            For archived modules, the dotted module name.
        source: Absolute source path recorded by PyInstaller.
        typecode: PyInstaller TOC typecode, for example ``BINARY`` or ``PYMODULE``.
        origin: Whether the entry is a file on disk or a module inside the PYZ archive.
    """

    destination: str
    source: Path
    typecode: str
    origin: EntryOrigin


@dataclass(frozen=True)
class DistributionInfo:
    """Installed Python distribution metadata relevant for notices.

    Attributes:
        name: Distribution name as declared in its metadata.
        version: Distribution version.
        license_expression: ``License-Expression`` metadata value, if any.
        license_field: Legacy ``License`` metadata value, if any.
        classifiers: Trove classifiers.
        requirements: Raw ``Requires-Dist`` entries.
        homepage: Best-effort project homepage URL.
        files: Absolute paths of all files listed in the distribution RECORD.
        license_files: Absolute paths of license-related files in the dist-info directory
            and in dist-info directories of vendored packages.
        dist_info_dir: The distribution's own dist-info directory, if known.
    """

    name: str
    version: str
    license_expression: str | None
    license_field: str | None
    classifiers: tuple[str, ...]
    requirements: tuple[str, ...]
    homepage: str | None
    files: tuple[Path, ...]
    license_files: tuple[Path, ...]
    dist_info_dir: Path | None = None


@dataclass(frozen=True)
class ComponentId:
    """Identity of a component that bundled entries are attributed to."""

    kind: ComponentKind
    key: str


@dataclass(frozen=True)
class LicenseText:
    """A license text belonging to a component.

    Attributes:
        name: Heading describing which files or packages the text applies to.
            Merged identical texts list one file per line.
        text: License text.
        source: Whether the text was shipped with the component or supplied manually.
    """

    name: str
    text: str
    source: LicenseSource = LicenseSource.METADATA


@dataclass(frozen=True)
class ResolvedLicense:
    """A license identifier together with where it was found."""

    name: str | None
    source: LicenseSource


@dataclass(frozen=True)
class Component:
    """A third-party component included in the onedir output.

    Attributes:
        component_id: Identity of the component.
        name: Display name.
        version: Version, or an empty string if unknown.
        license: License identifier, or None if it could not be determined.
        homepage: Project homepage URL, if known.
        license_texts: License texts that apply to the component.
        file_count: Number of bundled entries attributed to the component.
        license_source: Where the license identifier comes from.
        license_reference: Where manually supplied license information was verified.
    """

    component_id: ComponentId
    name: str
    version: str
    license: str | None
    homepage: str | None
    license_texts: tuple[LicenseText, ...]
    file_count: int
    license_source: LicenseSource = LicenseSource.METADATA
    license_reference: str | None = None


@dataclass(frozen=True)
class NoticeIssue:
    """A validation problem found during analysis."""

    severity: IssueSeverity
    message: str
    component: str | None = None


@dataclass(frozen=True)
class NoticeReport:
    """Result of analysing a onedir build for third-party notices.

    Attributes:
        components: Third-party components, sorted by name.
        first_party_file_count: Number of entries attributed to the application itself.
        issues: Errors and warnings found during analysis.
    """

    components: tuple[Component, ...]
    first_party_file_count: int
    issues: tuple[NoticeIssue, ...]

    @property
    def errors(self) -> tuple[NoticeIssue, ...]:
        """Return all issues with error severity."""
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.ERROR)

    @property
    def warnings(self) -> tuple[NoticeIssue, ...]:
        """Return all issues with warning severity."""
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.WARNING)

    @property
    def has_errors(self) -> bool:
        """Return whether the analysis found any errors."""
        return bool(self.errors)
