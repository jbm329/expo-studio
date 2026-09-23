"""Utilities for compiling UI resource files into PyQt-compatible Python modules."""

import pathlib
import re
import subprocess
import sys

from expo_jbm329.build.build_utils import icons_qrc, splash_qrc

QRC_FILES = [
    splash_qrc(),
    icons_qrc(),
]


def compile_qrc(qrc_path: pathlib.Path) -> pathlib.Path:
    """Compile a .qrc file using pyside6-rcc and return output file."""
    out_py = qrc_path.with_name(qrc_path.stem + "_rc.py")

    cmd = ["pyside6-rcc", str(qrc_path), "-o", str(out_py)]
    print(f"Compiling: {' '.join(cmd)}")
    subprocess.check_call(cmd)  # noqa: S603 - trusted build command

    return out_py


def patch_imports(py_file: pathlib.Path) -> None:
    """Replace PySide6 imports with PyQt6 imports."""
    print(f"Patching imports in {py_file}")
    text = py_file.read_text(encoding="utf-8")
    patched = re.sub(r"from PySide6", "from PyQt6", text)
    py_file.write_text(patched, encoding="utf-8")


def main() -> None:
    """Compile the bundled Qt resource files into Python modules."""
    print("=== Building .qrc resources ===")

    for qrc in QRC_FILES:
        if not qrc.exists():
            print(f"⚠️ Missing QRC file: {qrc}")
            continue

        out_file = compile_qrc(qrc)
        patch_imports(out_file)

    print("✅ Resource build completed.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running pyside6-rcc: {e}")
        sys.exit(1)
