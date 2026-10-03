"""Notice information for bundled components that are not Python distributions."""

from __future__ import annotations

import platform
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from expo_jbm329.build.notices.attribution import (
    LINUX_SYSTEM_RUNTIME_COMPONENT,
    MSVC_RUNTIME_COMPONENT,
    PYTHON_RUNTIME_COMPONENT,
)
from expo_jbm329.build.notices.licenses import read_license_file
from expo_jbm329.build.notices.models import Component, LicenseSource, LicenseText

if TYPE_CHECKING:
    from collections.abc import Sequence

    from expo_jbm329.build.notices.models import BundledEntry

PYTHON_RUNTIME_NAME = "Python"
PYTHON_RUNTIME_LICENSE = "PSF-2.0"
PYTHON_RUNTIME_HOMEPAGE = "https://www.python.org/"
MSVC_RUNTIME_NAME = "Microsoft Visual C++ Runtime"
MSVC_RUNTIME_LICENSE = "LicenseRef-Microsoft-Redistributable"
MSVC_RUNTIME_HOMEPAGE = "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist"
LINUX_SYSTEM_RUNTIME_NAME = "Linux System Runtime Libraries"
LINUX_SYSTEM_RUNTIME_LICENSE = "GPL-3.0-or-later WITH GCC-exception-3.1 OR LGPL-2.1-or-later OR MIT OR BSD-3-Clause"
LINUX_SYSTEM_RUNTIME_HOMEPAGE = "https://gcc.gnu.org/onlinedocs/libstdc++/manual/license.html"


def python_license_candidates(runtime_root: Path, version: str) -> tuple[Path, ...]:
    """Return locations where a Python installation keeps its license file.

    Windows installations keep ``LICENSE.txt`` in the installation root, while
    POSIX installations keep it in the standard library directory.

    Args:
        runtime_root: Base directory of the Python installation.
        version: Python version, for example ``3.13.1``.

    Returns:
        Candidate license file paths in priority order.
    """
    major_minor = ".".join(version.split(".")[:2])
    return (
        runtime_root / "LICENSE.txt",
        runtime_root / "LICENSE",
        runtime_root / "lib" / f"python{major_minor}" / "LICENSE.txt",
        runtime_root / "Lib" / "LICENSE.txt",
    )


def find_python_license(runtime_roots: Sequence[Path], version: str) -> Path | None:
    """Return the license file of the Python installation used for the build.

    Args:
        runtime_roots: Base directories of the Python installation.
        version: Python version.

    Returns:
        License file path, or None if no license file was found.
    """
    for root in runtime_roots:
        for candidate in python_license_candidates(root, version):
            if candidate.is_file():
                return candidate
    return None


def build_python_runtime_component(
    entries: Sequence[BundledEntry],
    runtime_roots: Sequence[Path],
    version: str | None = None,
) -> Component:
    """Return the notice component for the bundled Python runtime.

    The CPython license file also covers third-party libraries shipped with the
    official binaries, such as OpenSSL, SQLite, libffi, zlib and Tcl/Tk.

    Args:
        entries: Entries attributed to the Python runtime.
        runtime_roots: Base directories of the Python installation used for the build.
        version: Python version. Defaults to the running interpreter version.

    Returns:
        Python runtime component.

    Raises:
        OSError: If the license file exists but cannot be read.
    """
    resolved_version = version or platform.python_version()
    license_path = find_python_license(runtime_roots, resolved_version)
    license_texts = () if license_path is None else (read_license_file(license_path, name=license_path.name),)
    return Component(
        component_id=PYTHON_RUNTIME_COMPONENT,
        name=PYTHON_RUNTIME_NAME,
        version=resolved_version,
        license=PYTHON_RUNTIME_LICENSE,
        homepage=PYTHON_RUNTIME_HOMEPAGE,
        license_texts=license_texts,
        file_count=len(entries),
        license_source=LicenseSource.BUILTIN,
    )


def msvc_runtime_notice(file_names: Sequence[str]) -> str:
    """Return the notice text for redistributed Microsoft runtime libraries.

    Args:
        file_names: Bundled Microsoft runtime file names.

    Returns:
        Notice text listing the bundled files.
    """
    listed_files = "\n".join(f"  - {name}" for name in file_names)
    return (
        "This application includes the following Microsoft runtime libraries,\n"
        "redistributed in unmodified form:\n\n"
        f"{listed_files}\n\n"
        "These files are Copyright (c) Microsoft Corporation. They are distributed\n"
        "as redistributable code under the Microsoft Software License Terms for\n"
        "Microsoft Visual Studio and the Windows SDK, and are not covered by the\n"
        "license of this application.\n\n"
        "See https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files\n"
        "and https://visualstudio.microsoft.com/license-terms/ for details."
    )


def build_msvc_runtime_component(entries: Sequence[BundledEntry]) -> Component:
    """Return the notice component for bundled Microsoft C/C++ runtime libraries.

    Args:
        entries: Entries attributed to the Microsoft runtime.

    Returns:
        Microsoft runtime component.
    """
    file_names = sorted({PurePosixPath(entry.destination).name for entry in entries}, key=str.casefold)
    return Component(
        component_id=MSVC_RUNTIME_COMPONENT,
        name=MSVC_RUNTIME_NAME,
        version="",
        license=MSVC_RUNTIME_LICENSE,
        homepage=MSVC_RUNTIME_HOMEPAGE,
        license_texts=(LicenseText(name="Notice", text=msvc_runtime_notice(file_names), source=LicenseSource.BUILTIN),),
        file_count=len(entries),
        license_source=LicenseSource.BUILTIN,
    )


def linux_system_runtime_notice(file_names: Sequence[str]) -> str:
    """Return the notice text for redistributed Linux system and runtime libraries.

    Args:
        file_names: Bundled Linux system runtime file names.

    Returns:
        Notice text listing the bundled files.
    """
    listed_files = "\n".join(f"  - {name}" for name in file_names)
    return (
        "This application includes the following Linux system and runtime libraries,\n"
        "redistributed in unmodified form:\n\n"
        f"{listed_files}\n\n"
        "These libraries originate from the host GNU/Linux operating system environment\n"
        "and are distributed under their respective open source licenses (such as the\n"
        "GNU LGPL, GNU GPL with GCC Runtime Library Exception, MIT, BSD, or zlib licenses),\n"
        "and are not covered by the primary license of this application.\n\n"
        "Source code for standard system libraries can be obtained from the respective\n"
        "upstream project repositories or GNU/Linux distribution package repositories."
    )


def build_linux_system_runtime_component(entries: Sequence[BundledEntry]) -> Component:
    """Return the notice component for bundled Linux system runtime libraries.

    Args:
        entries: Entries attributed to the Linux system runtime.

    Returns:
        Linux system runtime component.
    """
    file_names = sorted({PurePosixPath(entry.destination).name for entry in entries}, key=str.casefold)
    return Component(
        component_id=LINUX_SYSTEM_RUNTIME_COMPONENT,
        name=LINUX_SYSTEM_RUNTIME_NAME,
        version="",
        license=LINUX_SYSTEM_RUNTIME_LICENSE,
        homepage=LINUX_SYSTEM_RUNTIME_HOMEPAGE,
        license_texts=(
            LicenseText(name="Notice", text=linux_system_runtime_notice(file_names), source=LicenseSource.BUILTIN),
        ),
        file_count=len(entries),
        license_source=LicenseSource.BUILTIN,
    )
