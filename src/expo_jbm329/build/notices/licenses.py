"""Resolve license identifiers and license texts for bundled components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from expo_jbm329.build.notices.distributions import enclosing_dist_info_dir, normalize_path
from expo_jbm329.build.notices.models import LicenseSource, LicenseText, ResolvedLicense

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from expo_jbm329.build.notices.models import DistributionInfo

LICENSE_CLASSIFIER_PREFIX = "License :: "
# Generic classifier segments that do not name a license on their own.
GENERIC_LICENSE_CLASSIFIER_SEGMENTS = frozenset({"OSI Approved", "Other/Proprietary License"})
# Legacy License fields longer than this, or spanning several lines, contain a license text
# rather than a license name.
MAX_LICENSE_NAME_LENGTH = 120
LEGACY_LICENSE_TEXT_NAME = "License (from package metadata)"
VENDORED_LABEL_SUFFIX = " (vendored)"


@dataclass(frozen=True)
class _LabelledLicenseFile:
    """A license file with its display label and whether it belongs to the distribution itself."""

    path: Path
    label: str
    is_own: bool


def _is_license_name(value: str) -> bool:
    """Return whether a legacy ``License`` metadata value is a short license name."""
    return "\n" not in value and len(value) <= MAX_LICENSE_NAME_LENGTH


def _license_from_classifiers(classifiers: tuple[str, ...]) -> str | None:
    """Return license names declared through trove classifiers."""
    names: list[str] = []
    for classifier in classifiers:
        if not classifier.startswith(LICENSE_CLASSIFIER_PREFIX):
            continue
        segments = [segment.strip() for segment in classifier.split("::")[1:]]
        specific = [segment for segment in segments if segment not in GENERIC_LICENSE_CLASSIFIER_SEGMENTS]
        name = specific[-1] if specific else segments[-1]
        if name not in names:
            names.append(name)

    return "; ".join(names) if names else None


def resolve_license_name(distribution: DistributionInfo) -> str | None:
    """Return the most precise license identifier declared by a distribution.

    Args:
        distribution: Distribution metadata.

    Returns:
        License identifier or name, or None if the distribution declares none.
    """
    return resolve_license(distribution).name


def resolve_license(distribution: DistributionInfo) -> ResolvedLicense:
    """Return the license identifier declared by a distribution and where it was found.

    The SPDX ``License-Expression`` is preferred, then a short legacy ``License``
    value, then trove classifiers.

    Args:
        distribution: Distribution metadata.

    Returns:
        Resolved license. ``name`` is None when the metadata declares nothing.
    """
    if distribution.license_expression is not None:
        return ResolvedLicense(name=distribution.license_expression, source=LicenseSource.METADATA)

    if distribution.license_field is not None and _is_license_name(distribution.license_field):
        return ResolvedLicense(name=distribution.license_field, source=LicenseSource.METADATA)

    from_classifiers = _license_from_classifiers(distribution.classifiers)
    if from_classifiers is not None:
        return ResolvedLicense(name=from_classifiers, source=LicenseSource.CLASSIFIER)

    return ResolvedLicense(name=None, source=LicenseSource.UNKNOWN)


def _read_text(path: Path) -> str:
    """Read a license file, replacing undecodable bytes, and strip surrounding whitespace."""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def read_license_file(path: Path, name: str) -> LicenseText:
    """Read a license file as text.

    Args:
        path: License file to read.
        name: Heading for the license text.

    Returns:
        License text. Undecodable bytes are replaced so that one malformed file
        does not prevent notice generation.

    Raises:
        OSError: If the file cannot be read.
    """
    return LicenseText(name=name, text=_read_text(path))


def _license_file_label(path: Path, own_dist_info_dir: Path | None) -> tuple[str, bool]:
    """Return the display label of a license file and whether it belongs to the distribution itself.

    Files in the distribution's own dist-info directory are labelled relative to
    it. Files in other dist-info directories belong to vendored packages and are
    labelled with that directory name, which contains the vendored package name
    and version.
    """
    dist_info_dir = enclosing_dist_info_dir(path)
    if dist_info_dir is None:
        return path.name, True

    relative = path.relative_to(dist_info_dir).as_posix()
    if own_dist_info_dir is None or normalize_path(dist_info_dir) == normalize_path(own_dist_info_dir):
        return relative, True

    return f"{dist_info_dir.name}/{relative}{VENDORED_LABEL_SUFFIX}", False


def _labelled_license_files(distribution: DistributionInfo) -> list[_LabelledLicenseFile]:
    """Return the distribution's license files with labels, own files first."""
    entries: list[_LabelledLicenseFile] = []
    for path in distribution.license_files:
        label, is_own = _license_file_label(path, distribution.dist_info_dir)
        entries.append(_LabelledLicenseFile(path=path, label=label, is_own=is_own))
    entries.sort(key=lambda entry: (not entry.is_own, entry.label.casefold()))
    return entries


def merge_identical_license_texts(texts: Sequence[LicenseText]) -> tuple[LicenseText, ...]:
    """Merge license texts with identical content into one entry.

    Packages that vendor other packages often ship many copies of the same
    license text. Each distinct text is kept once, with a heading listing every
    file it applies to, in first-occurrence order.

    Args:
        texts: License texts.

    Returns:
        Distinct license texts.
    """
    names_by_text: dict[str, list[str]] = {}
    for license_text in texts:
        names = names_by_text.setdefault(license_text.text, [])
        if license_text.name not in names:
            names.append(license_text.name)

    return tuple(LicenseText(name="\n".join(names), text=text) for text, names in names_by_text.items())


def resolve_license_texts(distribution: DistributionInfo) -> tuple[LicenseText, ...]:
    """Return all distinct license texts shipped with a distribution.

    The distribution's own license files come first, followed by license files of
    vendored packages. Identical texts are merged. Falls back to a long legacy
    ``License`` metadata value when the distribution ships no license files.

    Args:
        distribution: Distribution metadata.

    Returns:
        License texts in a deterministic order.

    Raises:
        OSError: If a license file listed in the RECORD cannot be read.
    """
    texts = [
        read_license_file(entry.path, entry.label)
        for entry in _labelled_license_files(distribution)
        if entry.path.is_file()
    ]
    if texts:
        return merge_identical_license_texts(texts)

    if distribution.license_field is not None and not _is_license_name(distribution.license_field):
        return (LicenseText(name=LEGACY_LICENSE_TEXT_NAME, text=distribution.license_field),)

    return ()
