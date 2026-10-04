"""Release version and artifact naming helpers."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, metadata
from typing import TYPE_CHECKING

from expo_jbm329.app.metadata import REPOSITORY_URL
from expo_jbm329.build.build_utils import detect_platform, project_root

if TYPE_CHECKING:
    from pathlib import Path


APP_NAME = "Expo Studio"
APP_SLUG = "ExpoStudio"
EXECUTABLE_BASENAME = "expo"
PACKAGE_NAME = "expo_jbm329"
SOURCE_CODE_URL = REPOSITORY_URL
DOCUMENTATION_FILES = ("LICENSE.txt", "README.md", "CHANGELOG.md")
BUILD_INFO_FILE = "BUILD-INFO.txt"
THIRD_PARTY_NOTICES_FILE = "THIRD-PARTY-NOTICES.txt"
THIRD_PARTY_MANIFEST_FILE = "third-party-manifest.json"


@dataclass(frozen=True)
class ReleaseMetadata:
    """Metadata used for release artifacts."""

    app_name: str
    app_slug: str
    package: str
    version: str
    license: str
    platform: str


def get_app_name() -> str:
    """Return the application display name."""
    return APP_NAME


def get_app_slug() -> str:
    """Return the application slug used in release artifact names."""
    return APP_SLUG


def get_executable_name(platform_name: str | None = None) -> str:
    """Return the platform-specific executable filename.

    Args:
        platform_name: Normalized platform name. If omitted, the current
            platform is detected.

    Returns:
        Executable filename produced by PyInstaller.
    """
    resolved_platform = platform_name or detect_platform()
    if resolved_platform == "windows":
        return f"{EXECUTABLE_BASENAME}.exe"
    return EXECUTABLE_BASENAME


def get_package_name() -> str:
    """Return the Python package distribution name."""
    return PACKAGE_NAME


def get_source_code_url() -> str:
    """Return the source code repository URL."""
    return SOURCE_CODE_URL


def get_documentation_files() -> tuple[str, ...]:
    """Return the documentation files included in release artifacts."""
    return DOCUMENTATION_FILES


def get_build_info_file() -> str:
    """Return the build information filename included in release artifacts."""
    return BUILD_INFO_FILE


def get_third_party_notice_files() -> tuple[str, ...]:
    """Return the generated third-party notice files included in release artifacts."""
    return (THIRD_PARTY_NOTICES_FILE, THIRD_PARTY_MANIFEST_FILE)


def get_version() -> str:
    """Return the installed package version.

    Returns:
        Package version, or ``dev`` when package metadata is unavailable.
    """
    try:
        package_metadata = metadata(get_package_name())
    except PackageNotFoundError:
        return "dev"

    return package_metadata.get("Version", "unknown")


def get_artifact_platform(platform: str) -> str:
    """Return the platform label used in artifact names and build information.

    Args:
        platform: Normalized platform name, such as ``windows`` or ``linux``.

    Returns:
        Artifact platform label.
    """
    return "win64" if platform == "windows" else platform


def get_release_name(platform: str, extension: str, suffix: str = "") -> str:
    """Return a release artifact filename.

    Args:
        platform: Normalized platform name, for example ``windows`` or ``linux``.
        extension: File extension without or with a leading dot. Use an empty
            string for extensionless names.
        suffix: Optional artifact suffix, for example ``setup``.

    Returns:
        Release artifact filename.
    """
    platform_name = get_artifact_platform(platform)
    version = get_version()
    prerelease = re.fullmatch(r"(\d+\.\d+\.\d+)(a|b|rc)(\d+)", version)
    if prerelease is not None:
        version = f"{prerelease[1]}-{prerelease[2]}{prerelease[3]}"

    name_parts = [get_app_slug(), version, platform_name]
    if suffix:
        name_parts.append(suffix)
    base_name = "-".join(name_parts)
    normalized_extension = extension.lstrip(".")
    if not normalized_extension:
        return base_name

    return f"{base_name}.{normalized_extension}"


def build_metadata() -> ReleaseMetadata:
    """Return normalized metadata used for release artifacts."""
    try:
        package_metadata = metadata(get_package_name())
        license_name = (
            package_metadata.get("License-Expression") or package_metadata.get("License") or "GPL-3.0-or-later"
        )
    except PackageNotFoundError:
        license_name = "GPL-3.0-or-later"

    return ReleaseMetadata(
        app_name=get_app_name(),
        app_slug=get_app_slug(),
        package=get_package_name(),
        version=get_version(),
        license=license_name,
        platform=detect_platform(),
    )


def calculate_sha256(path: Path) -> str:
    """Calculate the SHA256 checksum for an artifact.

    Args:
        path: Artifact path to hash.

    Returns:
        Hex-encoded SHA256 digest.

    Raises:
        FileNotFoundError: If the artifact does not exist.
        OSError: If the artifact cannot be read.
    """
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def write_sha256_sum(path: Path, checksum: str) -> Path:
    """Write a standard sha256sum file for an artifact.

    Args:
        path: Artifact path the checksum belongs to.
        checksum: Hex-encoded SHA256 digest.

    Returns:
        Path to the written checksum file.

    Raises:
        OSError: If the checksum file cannot be written.
    """
    checksum_path = path.with_name(f"{path.name}.sha256")
    checksum_path.write_text(f"{checksum}  {path.name}\n", encoding="utf-8")
    return checksum_path


def create_sha256(path: Path) -> Path:
    """Create a SHA256 checksum file for an artifact.

    Args:
        path: Artifact path to hash.

    Returns:
        Path to the created checksum file.

    Raises:
        FileNotFoundError: If the artifact does not exist.
        OSError: If the artifact or checksum file cannot be read or written.
    """
    return write_sha256_sum(path=path, checksum=calculate_sha256(path))


def get_git_tag() -> str | None:
    """Return the exact Git tag for HEAD, if one exists.

    Returns:
        Git tag for HEAD, or None when HEAD is not exactly tagged or git is not
        available.
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],  # noqa: S607 - git is expected on PATH
            check=True,
            capture_output=True,
            cwd=project_root(),
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    tag = result.stdout.strip()
    return tag or None
