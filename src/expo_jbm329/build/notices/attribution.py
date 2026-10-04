"""Attribute bundled entries to the components they originate from."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from packaging.utils import canonicalize_name

from expo_jbm329.build.notices.distributions import is_path_under
from expo_jbm329.build.notices.models import BundledEntry, ComponentId, ComponentKind, EntryOrigin

if TYPE_CHECKING:
    from collections.abc import Iterable

    from expo_jbm329.build.notices.distributions import DistributionIndex

FIRST_PARTY_COMPONENT = ComponentId(kind=ComponentKind.FIRST_PARTY, key="first-party")
PYTHON_RUNTIME_COMPONENT = ComponentId(kind=ComponentKind.PYTHON_RUNTIME, key="python")
MSVC_RUNTIME_COMPONENT = ComponentId(kind=ComponentKind.SYSTEM_RUNTIME, key="microsoft-visual-cpp-runtime")
LINUX_SYSTEM_RUNTIME_COMPONENT = ComponentId(kind=ComponentKind.SYSTEM_RUNTIME, key="linux-system-runtime")

LINUX_SYSTEM_LIBRARY_ROOTS = (
    Path("/lib"),
    Path("/lib64"),
    Path("/usr/lib"),
    Path("/usr/lib64"),
    Path("/usr/local/lib"),
    Path("/usr/local/lib64"),
)

# Microsoft C/C++ runtime DLLs are attributed by name because several distributions
# vendor their own copies, and PyInstaller may also collect them from the system.
MSVC_RUNTIME_FILE_PATTERN = re.compile(
    r"^(vcruntime\d+(_\d+)?|msvcp\d+(_\w+)?|vcomp\d+|concrt\d+|vccorlib\d+|ucrtbase|api-ms-win-[\w-]+)\.dll$",
    re.IGNORECASE,
)
# PyInstaller assembles the frozen standard library into this archive in its work directory.
BASE_LIBRARY_ARCHIVE = "base_library.zip"
BOOTLOADER_DISTRIBUTION = "pyinstaller"
SITE_PACKAGES_DIRECTORY_NAMES = frozenset({"site-packages", "dist-packages"})


@dataclass(frozen=True)
class AttributionContext:
    """Build-specific information needed to attribute bundled entries.

    Attributes:
        executable_name: File name of the application executable at the onedir root.
        first_party_distribution: Name of the application distribution.
        first_party_roots: Directories containing application sources and build hooks.
        python_runtime_roots: Base directories of the Python installation used for the build.
        bootloader_distribution: Distribution that provides the executable bootloader.
    """

    executable_name: str
    first_party_distribution: str
    first_party_roots: tuple[Path, ...]
    python_runtime_roots: tuple[Path, ...]
    bootloader_distribution: str = BOOTLOADER_DISTRIBUTION


@dataclass
class AttributionResult:
    """Bundled entries grouped by component."""

    components: dict[ComponentId, list[BundledEntry]] = field(default_factory=dict[ComponentId, list[BundledEntry]])
    unattributed: list[BundledEntry] = field(default_factory=list[BundledEntry])


def _distribution_component(name: str, context: AttributionContext) -> ComponentId:
    """Return the component for a distribution, treating the application itself as first-party."""
    key = canonicalize_name(name)
    if key == canonicalize_name(context.first_party_distribution):
        return FIRST_PARTY_COMPONENT
    return ComponentId(kind=ComponentKind.PYTHON_DISTRIBUTION, key=key)


def _is_python_runtime_file(source: Path, context: AttributionContext) -> bool:
    """Return whether a source file belongs to the Python installation itself."""
    if any(part.casefold() in SITE_PACKAGES_DIRECTORY_NAMES for part in source.parts):
        return False
    return any(is_path_under(source, root) for root in context.python_runtime_roots)


def _is_linux_system_file(source: Path) -> bool:
    """Return whether a source file is a system runtime library on Linux."""
    return any(is_path_under(source, root) for root in LINUX_SYSTEM_LIBRARY_ROOTS)


def _attribute_by_destination(entry: BundledEntry, context: AttributionContext) -> ComponentId | None:
    """Attribute files that PyInstaller generates or that are identified by their name."""
    if entry.origin is not EntryOrigin.FILE:
        return None

    destination = PurePosixPath(entry.destination)
    if MSVC_RUNTIME_FILE_PATTERN.fullmatch(destination.name):
        return MSVC_RUNTIME_COMPONENT

    if destination.name == BASE_LIBRARY_ARCHIVE:
        return PYTHON_RUNTIME_COMPONENT

    if entry.destination == context.executable_name:
        return _distribution_component(context.bootloader_distribution, context)

    return None


def attribute_entry(
    entry: BundledEntry,
    index: DistributionIndex,
    context: AttributionContext,
) -> ComponentId | None:
    """Return the component a bundled entry originates from.

    Rules are applied in order: name-based rules for runtime DLLs and PyInstaller
    output, the RECORD of installed distributions, application sources, and
    finally the Python installation.

    Args:
        entry: Bundled entry.
        index: Installed distributions.
        context: Build-specific attribution information.

    Returns:
        The owning component, or None if the entry cannot be attributed.
    """
    by_destination = _attribute_by_destination(entry, context)
    if by_destination is not None:
        if by_destination.kind is ComponentKind.PYTHON_DISTRIBUTION and index.get(by_destination.key) is None:
            return None
        return by_destination

    distribution = index.find_by_file(entry.source)
    if distribution is not None:
        return _distribution_component(distribution.name, context)

    if any(is_path_under(entry.source, root) for root in context.first_party_roots):
        return FIRST_PARTY_COMPONENT

    if _is_python_runtime_file(entry.source, context):
        return PYTHON_RUNTIME_COMPONENT

    if _is_linux_system_file(entry.source):
        return LINUX_SYSTEM_RUNTIME_COMPONENT

    return None


def attribute_entries(
    entries: Iterable[BundledEntry],
    index: DistributionIndex,
    context: AttributionContext,
) -> AttributionResult:
    """Group bundled entries by the component they originate from.

    Args:
        entries: Bundled entries.
        index: Installed distributions.
        context: Build-specific attribution information.

    Returns:
        Entries grouped by component, plus entries that could not be attributed.
    """
    result = AttributionResult()
    for entry in entries:
        component = attribute_entry(entry, index, context)
        if component is None:
            result.unattributed.append(entry)
        else:
            result.components.setdefault(component, []).append(entry)
    return result
