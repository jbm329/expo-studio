"""Load manually verified license information for bundled distributions.

Overrides live in ``licenses/overrides.toml`` at the project root. Each entry
is pinned to an exact distribution version so that upgrades force a review.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from packaging.utils import canonicalize_name

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

OVERRIDES_DIRECTORY_NAME = "licenses"
OVERRIDES_FILE_NAME = "overrides.toml"
OVERRIDE_TABLE = "override"
_REQUIRED_KEYS = frozenset({"distribution", "version", "source"})
_OPTIONAL_KEYS = frozenset({"license", "license_file"})


class LicenseOverrideError(ValueError):
    """Raised when the license override file is invalid."""


@dataclass(frozen=True)
class LicenseOverride:
    """Manually verified license information for one distribution version.

    Attributes:
        distribution: Distribution name in any normalization.
        version: Exact distribution version the information was verified for.
        license: SPDX license expression, used when the metadata declares none.
        license_file: Absolute path of a license text, used when the package ships none.
        source: Where the license was verified.
    """

    distribution: str
    version: str
    license: str | None
    license_file: Path | None
    source: str

    @property
    def key(self) -> str:
        """Return the normalized distribution name."""
        return canonicalize_name(self.distribution)


def _string_value(entry: dict[str, object], key: str, location: str) -> str | None:
    """Return a non-empty string value of an entry, or None if the key is absent."""
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        message = f"{location}: '{key}' must be a non-empty string"
        raise LicenseOverrideError(message)
    return value.strip()


def _required_string(entry: dict[str, object], key: str, location: str) -> str:
    """Return a required non-empty string value of an entry."""
    value = _string_value(entry, key, location)
    if value is None:
        message = f"{location}: missing key: {key}"
        raise LicenseOverrideError(message)
    return value


def _parse_entry(entry: object, base_dir: Path, location: str) -> LicenseOverride:
    """Validate one ``[[override]]`` table and convert it to a LicenseOverride."""
    if not isinstance(entry, dict):
        message = f"{location}: expected a table"
        raise LicenseOverrideError(message)

    unknown = set(entry) - _REQUIRED_KEYS - _OPTIONAL_KEYS
    if unknown:
        message = f"{location}: unknown keys: {', '.join(sorted(unknown))}"
        raise LicenseOverrideError(message)

    license_name = _string_value(entry, "license", location)
    license_file_value = _string_value(entry, "license_file", location)
    if license_name is None and license_file_value is None:
        message = f"{location}: at least one of 'license' or 'license_file' is required"
        raise LicenseOverrideError(message)

    license_file = None
    if license_file_value is not None:
        license_file = (base_dir / license_file_value).resolve()
        if not license_file.is_file():
            message = f"{location}: license_file does not exist: {license_file}"
            raise LicenseOverrideError(message)

    return LicenseOverride(
        distribution=_required_string(entry, "distribution", location),
        version=_required_string(entry, "version", location),
        license=license_name,
        license_file=license_file,
        source=_required_string(entry, "source", location),
    )


def _reject_duplicates(overrides: Iterable[LicenseOverride], path: Path) -> None:
    """Raise if more than one entry targets the same distribution."""
    seen: set[str] = set()
    for override in overrides:
        if override.key in seen:
            message = f"{path}: duplicate entry for distribution {override.distribution}"
            raise LicenseOverrideError(message)
        seen.add(override.key)


def load_license_overrides(path: Path) -> tuple[LicenseOverride, ...]:
    """Load and validate license overrides from a TOML file.

    Args:
        path: Overrides file. A missing file means no overrides.

    Returns:
        Overrides in file order.

    Raises:
        LicenseOverrideError: If the file is malformed or an entry is invalid.
        OSError: If the file exists but cannot be read.
    """
    if not path.is_file():
        return ()

    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        message = f"{path}: invalid TOML: {exc}"
        raise LicenseOverrideError(message) from exc

    unknown_tables = set(document) - {OVERRIDE_TABLE}
    if unknown_tables:
        message = f"{path}: unknown top-level keys: {', '.join(sorted(unknown_tables))}"
        raise LicenseOverrideError(message)

    entries = document.get(OVERRIDE_TABLE, [])
    if not isinstance(entries, list):
        message = f"{path}: '{OVERRIDE_TABLE}' must be an array of tables ([[{OVERRIDE_TABLE}]])"
        raise LicenseOverrideError(message)

    overrides = tuple(
        _parse_entry(entry, path.parent, f"{path} entry {index}") for index, entry in enumerate(entries, start=1)
    )
    _reject_duplicates(overrides, path)
    return overrides


def find_license_override(distribution_name: str, overrides: Iterable[LicenseOverride]) -> LicenseOverride | None:
    """Return the override configured for a distribution name, regardless of version.

    Args:
        distribution_name: Distribution name in any normalization.
        overrides: Configured overrides.

    Returns:
        The override for the distribution, or None.
    """
    key = canonicalize_name(distribution_name)
    return next((override for override in overrides if override.key == key), None)
