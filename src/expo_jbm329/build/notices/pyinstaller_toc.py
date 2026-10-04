"""Read PyInstaller TOC files and list the contents of a onedir build."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from expo_jbm329.build.notices.models import BundledEntry, EntryOrigin

COLLECT_TOC_FILE = "COLLECT-00.toc"
PYZ_TOC_FILE = "PYZ-00.toc"
PKG_TOC_FILE = "PKG-00.toc"
DEFAULT_CONTENTS_DIRECTORY = "_internal"
CONTENTS_DIRECTORY_OPTION_PREFIX = "pyi-contents-directory "
# PyInstaller writes these as the source of namespace packages, which carry no files.
NAMESPACE_SOURCE_MARKERS = frozenset({"", "-"})
# COLLECT places executables at the onedir root and everything else in the contents directory.
TOP_LEVEL_TYPECODES = frozenset({"EXECUTABLE"})
# Symlink sources are link targets rather than real source files, so they are not attributed.
SYMLINK_TYPECODE = "SYMLINK"

type TocRow = tuple[str, str, str]


class TocFormatError(ValueError):
    """Raised when a PyInstaller TOC file has an unexpected format."""


@dataclass(frozen=True)
class BundleContents:
    """Entries described by the PyInstaller TOC files of one build.

    Attributes:
        entries: Attributable files and archived modules.
        expected_files: POSIX-style paths of every file COLLECT placed in the onedir
            root, including symlinks.
    """

    entries: tuple[BundledEntry, ...]
    expected_files: frozenset[str]


def _read_toc(path: Path) -> object:
    """Parse a PyInstaller TOC file, which is a Python literal."""
    try:
        return ast.literal_eval(path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError) as exc:
        message = f"Could not parse PyInstaller TOC file: {path}"
        raise TocFormatError(message) from exc


def _as_toc_row(item: object) -> TocRow | None:
    """Return the item as a ``(name, source, typecode)`` TOC row, if it is one."""
    if not isinstance(item, tuple):
        return None
    parts = cast("tuple[object, ...]", item)
    if len(parts) != 3:  # noqa: PLR2004 - TOC rows always have three fields
        return None
    name, source, typecode = parts
    if isinstance(name, str) and isinstance(source, str) and isinstance(typecode, str):
        return (name, source, typecode)
    return None


def _candidate_lists(value: object) -> list[list[object]]:
    """Return the lists contained in a parsed TOC file value."""
    if isinstance(value, list):
        return [cast("list[object]", value)]
    if isinstance(value, tuple):
        return [cast("list[object]", item) for item in cast("tuple[object, ...]", value) if isinstance(item, list)]
    return []


def _find_toc_rows(value: object, path: Path) -> list[TocRow]:
    """Return the first non-empty TOC row list found in a parsed TOC file.

    PyInstaller stores TOC files as tuples whose layout varies between build
    targets and versions, so the first list of TOC rows is used rather than a
    fixed index.
    """
    for candidate in _candidate_lists(value):
        rows = [_as_toc_row(item) for item in candidate]
        valid_rows = [row for row in rows if row is not None]
        if valid_rows and len(valid_rows) == len(rows):
            return valid_rows

    message = f"No TOC entries found in PyInstaller TOC file: {path}"
    raise TocFormatError(message)


def load_toc_rows(path: Path) -> list[TocRow]:
    """Load the TOC rows of a PyInstaller TOC file.

    Args:
        path: TOC file to read.

    Returns:
        ``(name, source, typecode)`` rows.

    Raises:
        OSError: If the file cannot be read.
        TocFormatError: If the file does not contain TOC rows.
    """
    return _find_toc_rows(_read_toc(path), path)


def read_contents_directory(work_dir: Path) -> str:
    """Return the onedir contents directory name used by a build.

    Args:
        work_dir: PyInstaller work directory, for example ``build/expo``.

    Returns:
        Contents directory relative to the onedir root, or ``.`` when files are
        placed directly in the root.

    Raises:
        OSError: If the PKG TOC file exists but cannot be read.
        TocFormatError: If the PKG TOC file has an unexpected format.
    """
    pkg_toc = work_dir / PKG_TOC_FILE
    if not pkg_toc.is_file():
        return DEFAULT_CONTENTS_DIRECTORY

    for name, _source, typecode in load_toc_rows(pkg_toc):
        if typecode == "OPTION" and name.startswith(CONTENTS_DIRECTORY_OPTION_PREFIX):
            return name.removeprefix(CONTENTS_DIRECTORY_OPTION_PREFIX).strip() or "."

    return DEFAULT_CONTENTS_DIRECTORY


def _to_posix(path: str) -> str:
    """Convert a TOC destination path to POSIX separators."""
    return path.replace("\\", "/")


def load_bundle_contents(work_dir: Path) -> BundleContents:
    """Load the files and archived modules a onedir build was assembled from.

    Args:
        work_dir: PyInstaller work directory, for example ``build/expo``.

    Returns:
        Bundle contents described by the COLLECT and PYZ TOC files.

    Raises:
        OSError: If a required TOC file cannot be read.
        TocFormatError: If a TOC file has an unexpected format.
    """
    contents_directory = PurePosixPath(read_contents_directory(work_dir))
    entries: list[BundledEntry] = []
    expected_files: set[str] = set()

    for destination, source, typecode in load_toc_rows(work_dir / COLLECT_TOC_FILE):
        relative = PurePosixPath(_to_posix(destination))
        if typecode not in TOP_LEVEL_TYPECODES:
            relative = contents_directory / relative
        expected_files.add(str(relative))

        if typecode == SYMLINK_TYPECODE or source in NAMESPACE_SOURCE_MARKERS:
            continue
        entries.append(
            BundledEntry(destination=str(relative), source=Path(source), typecode=typecode, origin=EntryOrigin.FILE)
        )

    pyz_toc = work_dir / PYZ_TOC_FILE
    if pyz_toc.is_file():
        entries.extend(
            BundledEntry(
                destination=module_name,
                source=Path(source),
                typecode=typecode,
                origin=EntryOrigin.ARCHIVE_MODULE,
            )
            for module_name, source, typecode in load_toc_rows(pyz_toc)
            if source not in NAMESPACE_SOURCE_MARKERS
        )

    return BundleContents(entries=tuple(entries), expected_files=frozenset(expected_files))


def list_onedir_files(dist_dir: Path) -> frozenset[str]:
    """List every file and symlink in a onedir output without following symlinks.

    Args:
        dist_dir: Onedir output directory, for example ``dist/expo``.

    Returns:
        POSIX-style paths relative to ``dist_dir``.

    Raises:
        FileNotFoundError: If ``dist_dir`` is not a directory.
    """
    if not dist_dir.is_dir():
        message = f"Onedir output directory not found: {dist_dir}"
        raise FileNotFoundError(message)

    files: set[str] = set()
    for current, directory_names, file_names in os.walk(dist_dir, followlinks=False):
        current_path = Path(current)
        names = list(file_names)
        names.extend(name for name in directory_names if (current_path / name).is_symlink())
        files.update((current_path / name).relative_to(dist_dir).as_posix() for name in names)

    return frozenset(files)
