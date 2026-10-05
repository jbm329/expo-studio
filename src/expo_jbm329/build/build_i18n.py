"""Build the Qt translation files from Python source strings."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from expo_jbm329.build.build_utils import locales_dir, src_root

if TYPE_CHECKING:
    import pathlib

TS_FILES = [
    locales_dir() / "app_en.ts",
    locales_dir() / "app_sv.ts",
]


def ensure_locales_dir() -> None:
    """Ensure that the locales directory exists."""
    locales_dir().mkdir(parents=True, exist_ok=True)


def run_pylupdate(ts_file: pathlib.Path, *, remove_obsolete: bool = False) -> None:
    """Run pylupdate6 for a single .ts file.

    Args:
        ts_file: Path to the .ts file to update.
        remove_obsolete: If True, messages no longer present in the sources
            are removed from the .ts file instead of being marked as vanished.
    """
    cmd = [
        "pylupdate6",
        str(src_root()),
        "--ts",
        str(ts_file),
    ]
    if remove_obsolete:
        cmd.append("--no-obsolete")

    print(f"Extracting strings → {ts_file.name}")
    print("  " + " ".join(cmd))

    subprocess.check_call(cmd)  # noqa: S603 - trusted build command


def run_extraction(*, remove_obsolete: bool) -> None:
    """Extract translatable strings to all .ts files.

    Args:
        remove_obsolete: If True, obsolete/unused messages are removed.
    """
    if remove_obsolete:
        print("=== Extracting i18n strings and removing obsolete entries (.py → .ts) ===")
    else:
        print("=== Extracting i18n strings (.py → .ts) ===")
    ensure_locales_dir()

    try:
        for ts in TS_FILES:
            run_pylupdate(ts, remove_obsolete=remove_obsolete)
    except subprocess.CalledProcessError as exc:
        print(f"❌ pylupdate6 failed: {exc}")
        sys.exit(1)

    print("✅ i18n extraction completed.")
    for ts in TS_FILES:
        print(f"  - {ts}")


def main() -> None:
    """Extract translatable strings from the Python sources to .ts files."""
    run_extraction(remove_obsolete=False)


def main_clean() -> None:
    """Extract translatable strings and remove obsolete entries from .ts files."""
    run_extraction(remove_obsolete=True)


if __name__ == "__main__":
    main()
