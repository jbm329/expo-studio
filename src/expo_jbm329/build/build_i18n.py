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


def run_pylupdate(ts_file: pathlib.Path) -> None:
    """Run pylupdate6 for a single .ts file.

    Args:
        ts_file: Path to the .ts file to update.
    """
    cmd = [
        "pylupdate6",
        str(src_root()),
        "--ts",
        str(ts_file),
    ]

    print(f"Extracting strings → {ts_file.name}")
    print("  " + " ".join(cmd))

    subprocess.check_call(cmd)  # noqa: S603 - trusted build command


def main() -> None:
    """Extract translatable strings from the Python sources to .ts files."""
    print("=== Extracting i18n strings (.py → .ts) ===")
    ensure_locales_dir()

    try:
        for ts in TS_FILES:
            run_pylupdate(ts)
    except subprocess.CalledProcessError as exc:
        print(f"❌ pylupdate6 failed: {exc}")
        sys.exit(1)

    print("✅ i18n extraction completed.")
    for ts in TS_FILES:
        print(f"  - {ts}")


if __name__ == "__main__":
    main()
