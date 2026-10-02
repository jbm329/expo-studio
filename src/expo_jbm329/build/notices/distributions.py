"""Index installed Python distributions by name and by installed file."""

from __future__ import annotations

import os
import re
from importlib.metadata import Distribution, distributions
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.utils import canonicalize_name

from expo_jbm329.build.notices.models import DistributionInfo

if TYPE_CHECKING:
    from collections.abc import Iterable

DIST_INFO_SUFFIX = ".dist-info"
# PEP 639 places license files under "<dist-info>/licenses"; older tools use the dist-info root.
PEP639_LICENSE_DIRECTORY = "licenses"
LICENSE_FILE_PATTERN = re.compile(r"^(licen[cs]e|copying|notice|authors|copyright)", re.IGNORECASE)
HOMEPAGE_LABELS = ("homepage", "home", "source", "source code", "repository", "code")


def normalize_path(path: Path | str) -> str:
    """Return an absolute, normalized and case-normalized path string for lookups.

    Args:
        path: Path to normalize.

    Returns:
        Normalized path string suitable for dictionary keys.
    """
    return os.path.normcase(os.path.normpath(Path(path).absolute()))


def is_path_under(path: Path | str, root: Path | str) -> bool:
    """Return whether ``path`` is ``root`` or located below it.

    Args:
        path: Path to check.
        root: Candidate parent directory.

    Returns:
        True if ``path`` is inside ``root``.
    """
    normalized_path = normalize_path(path)
    normalized_root = normalize_path(root)
    return normalized_path == normalized_root or normalized_path.startswith(normalized_root.rstrip(os.sep) + os.sep)


def enclosing_dist_info_dir(path: Path) -> Path | None:
    """Return the nearest dist-info directory that contains a file.

    Args:
        path: File path.

    Returns:
        The enclosing dist-info directory, or None if the file is not inside one.
    """
    return next((parent for parent in path.parents if parent.name.endswith(DIST_INFO_SUFFIX)), None)


def dist_info_relative_name(path: Path) -> str | None:
    """Return the path of a file relative to its enclosing dist-info directory.

    Args:
        path: File path.

    Returns:
        POSIX-style relative path, or None if the file is not inside a dist-info directory.
    """
    dist_info_dir = enclosing_dist_info_dir(path)
    if dist_info_dir is None:
        return None
    return path.relative_to(dist_info_dir).as_posix()


def is_license_file(path: Path) -> bool:
    """Return whether a dist-info file contains license or notice information.

    Args:
        path: File path.

    Returns:
        True for files in the PEP 639 ``licenses`` directory or with license-like names.
    """
    relative_name = dist_info_relative_name(path)
    if relative_name is None:
        return False
    if relative_name.startswith(f"{PEP639_LICENSE_DIRECTORY}/"):
        return True
    return LICENSE_FILE_PATTERN.match(path.name) is not None


def _homepage(distribution: Distribution) -> str | None:
    """Return the best available project homepage URL from distribution metadata."""
    metadata = distribution.metadata
    home_page = metadata.get("Home-page")
    if home_page is not None and home_page.strip() and home_page.strip().upper() != "UNKNOWN":
        return home_page.strip()

    project_urls: dict[str, str] = {}
    for entry in metadata.get_all("Project-URL") or []:
        label, separator, url = entry.partition(",")
        if separator:
            project_urls.setdefault(label.strip().casefold(), url.strip())

    for label in HOMEPAGE_LABELS:
        if label in project_urls:
            return project_urls[label]

    return next(iter(project_urls.values()), None)


def _optional_text(value: str | None) -> str | None:
    """Return stripped metadata text, or None for empty and ``UNKNOWN`` values."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.upper() == "UNKNOWN":
        return None
    return stripped


def own_dist_info_dir(files: Iterable[Path]) -> Path | None:
    """Return the distribution's own dist-info directory from its RECORD file list.

    Vendored packages keep their dist-info directories deeper in the package tree,
    so the shallowest dist-info directory that contains ``METADATA`` is the
    distribution's own.

    Args:
        files: Absolute paths of the files listed in the distribution RECORD.

    Returns:
        The dist-info directory, or None if the RECORD does not list one.
    """
    candidates = [
        file.parent for file in files if file.name == "METADATA" and file.parent.name.endswith(DIST_INFO_SUFFIX)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda path: (len(path.parts), path.as_posix()))


def distribution_info_from_metadata(distribution: Distribution) -> DistributionInfo:
    """Convert an ``importlib.metadata`` distribution into a :class:`DistributionInfo`.

    Args:
        distribution: Installed distribution.

    Returns:
        Metadata relevant for notices.
    """
    metadata = distribution.metadata
    files = tuple(Path(str(distribution.locate_file(file))) for file in distribution.files or [])
    license_files = sorted((file for file in files if is_license_file(file)), key=lambda path: path.as_posix())
    return DistributionInfo(
        name=metadata.get("Name") or "",
        version=distribution.version,
        license_expression=_optional_text(metadata.get("License-Expression")),
        license_field=_optional_text(metadata.get("License")),
        classifiers=tuple(metadata.get_all("Classifier") or []),
        requirements=tuple(distribution.requires or []),
        homepage=_homepage(distribution),
        files=files,
        license_files=tuple(license_files),
        dist_info_dir=own_dist_info_dir(files),
    )


def load_installed_distributions() -> list[DistributionInfo]:
    """Load metadata for every distribution installed in the current environment.

    Returns:
        Distribution metadata in ``sys.path`` order.
    """
    return [distribution_info_from_metadata(distribution) for distribution in distributions()]


class DistributionIndex:
    """Look up installed distributions by canonical name or by installed file."""

    def __init__(self, installed: Iterable[DistributionInfo]) -> None:
        """Build lookup tables.

        When the same distribution is installed more than once, the first one
        wins, matching how ``sys.path`` resolves imports.

        Args:
            installed: Installed distributions.
        """
        self._by_name: dict[str, DistributionInfo] = {}
        self._by_file: dict[str, DistributionInfo] = {}
        for distribution in installed:
            if not distribution.name:
                continue
            key = canonicalize_name(distribution.name)
            if key in self._by_name:
                continue
            self._by_name[key] = distribution
            for file in distribution.files:
                self._by_file.setdefault(normalize_path(file), distribution)

    def get(self, name: str) -> DistributionInfo | None:
        """Return the distribution with the given name, if installed.

        Args:
            name: Distribution name in any normalization.

        Returns:
            The distribution, or None if it is not installed.
        """
        return self._by_name.get(canonicalize_name(name))

    def find_by_file(self, path: Path) -> DistributionInfo | None:
        """Return the distribution whose RECORD lists the given file.

        Args:
            path: Absolute path of an installed file.

        Returns:
            The owning distribution, or None if no RECORD lists the file.
        """
        return self._by_file.get(normalize_path(path))
