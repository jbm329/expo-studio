"""Build Qt translation (.qm) files from .ts sources using pyside6-lrelease."""

import pathlib
import subprocess
import sys

from expo_jbm329.build.build_utils import locales_dir

TS_GLOB = "app_*.ts"


def find_ts_files() -> list[pathlib.Path]:
    """Return all .ts files under the locales directory."""
    if not locales_dir().exists():
        print(f"❌ Locales directory not found: {locales_dir()}")
        return []

    return sorted(locales_dir().glob(TS_GLOB))


def compile_ts(ts_path: pathlib.Path) -> pathlib.Path:
    """Compile a .ts file into a .qm file using pyside6-lrelease.

    Args:
        ts_path: Path to the .ts file.

    Returns:
        Path to the generated .qm file.
    """
    qm_path = ts_path.with_suffix(".qm")

    cmd = ["pyside6-lrelease", str(ts_path)]
    print(f"Compiling: {' '.join(cmd)}")

    subprocess.check_call(cmd)  # noqa: S603 - trusted build command
    return qm_path


def main() -> None:
    """Compile all Qt translation (.ts) files into .qm binaries."""
    print("=== Building translation (.qm) files ===")

    ts_files = find_ts_files()
    if not ts_files:
        print("⚠️ No .ts files found.")
        return

    for ts in ts_files:
        try:
            qm = compile_ts(ts)
            print(f"✅ Generated: {qm.name}")
        except subprocess.CalledProcessError as exc:
            print(f"❌ Failed to compile {ts.name}: {exc}")
            sys.exit(1)

    print("✅ Translation build completed.")


if __name__ == "__main__":
    main()
