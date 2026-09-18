"""Build the Qt translation files from Python source strings."""

from __future__ import annotations

import pathlib
import subprocess
import sys

BASE = pathlib.Path(__file__).parent
SRC_ROOT = BASE
LOCALES_DIR = BASE / "i18n" / "locales"

TS_FILES = [
    LOCALES_DIR / "app_en.ts",
    LOCALES_DIR / "app_sv.ts",
]


def ensure_locales_dir() -> None:
    """Ensure that the locales directory exists."""
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)


def run_pylupdate(ts_file: pathlib.Path) -> None:
    """Run pylupdate6 for a single .ts file.

    Args:
        ts_file: Path to the .ts file to update.
    """
    cmd = [
        "pylupdate6",
        str(SRC_ROOT),
        "--ts",
        str(ts_file),
    ]

    print(f"Extracting strings → {ts_file.name}")
    print("  " + " ".join(cmd))

    subprocess.check_call(cmd)


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
