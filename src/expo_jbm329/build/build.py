"""Build the Expo Studio executable in PyInstaller onedir mode."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from expo_jbm329.build.build_utils import detect_platform, project_root
from expo_jbm329.build.version import get_executable_name

if TYPE_CHECKING:
    from collections.abc import Callable


PYINSTALLER_VERSION = "pyinstaller>=6.19"
APP_NAME = "expo"


def _onedir_environment() -> dict[str, str]:
    """Return a subprocess environment that forces the PyInstaller spec to onedir mode."""
    env = os.environ.copy()
    env.pop("EXPO_ONEFILE", None)
    return env


def site_packages() -> str | None:
    """Return the active Python site-packages path, if available."""
    return sysconfig.get_paths().get("purelib")


def _chmod_writable(path: Path) -> None:
    """Ensure a filesystem path is writable."""
    try:
        path.chmod(stat.S_IWRITE)
    except OSError:
        return


def _onerror(func: Callable[[str], object], path: str, _exc_info: object) -> None:
    """Retry a failed filesystem operation after making the path writable."""
    _chmod_writable(Path(path))
    func(path)


def _safe_rmtree(path: Path, retries: int = 6, backoff: float = 0.2) -> bool:
    """Remove a directory tree with retries and backoff.

    Args:
        path: Directory to remove.
        retries: Number of retry attempts.
        backoff: Initial backoff delay multiplier in seconds.

    Returns:
        True if the directory was removed successfully, otherwise False.
    """
    if not path.exists():
        return True

    for attempt in range(retries):
        try:
            shutil.rmtree(path, onexc=_onerror)
        except OSError:
            time.sleep(backoff * (attempt + 1))
        else:
            return True

    return False


def _kill_running_expo() -> None:
    """Terminate running expo.exe processes on Windows."""
    if os.name != "nt":
        return

    subprocess.run(  # noqa: S603 - trusted Windows cleanup command
        ["taskkill", "/IM", get_executable_name("windows"), "/F"],  # noqa: S607 - Windows system utility
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _pre_clean(root: Path) -> None:
    """Remove build artifacts that can interfere with a fresh onedir build."""
    _kill_running_expo()

    for path in [root / "build" / APP_NAME, root / "dist" / APP_NAME]:
        if path.exists():
            print(f"[build-onedir] Removing {path} ...")
            if not _safe_rmtree(path):
                print(
                    f"[build-onedir] WARNING: Could not fully clean {path}; locked files may remain.",
                    file=sys.stderr,
                )


def _ensure_app_ico(root: Path) -> Path:
    """Generate app.ico from the application PNG if missing or outdated.

    Args:
        root: Project root directory.

    Returns:
        Path to the generated or existing ICO file.
    """
    png_path = root / "src" / "expo_jbm329" / "workbench" / "icon" / "themes" / "light" / "app.png"
    ico_path = root / "src" / "expo_jbm329" / "workbench" / "icon" / "app.ico"

    if not png_path.exists():
        print(f"[build-onedir] Source PNG not found: {png_path}; skipping ICO generation.")
        return ico_path

    regenerate = not ico_path.exists() or png_path.stat().st_mtime > ico_path.stat().st_mtime
    if regenerate:
        print(f"[build-onedir] Generating ICO from {png_path} -> {ico_path}")
        ico_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(png_path).convert("RGBA")
        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        image.save(ico_path, format="ICO", sizes=sizes)
    else:
        print(f"[build-onedir] Using existing ICO: {ico_path}")

    return ico_path


def _generate_spec(root: Path, spec_path: Path, entry: Path) -> bool:
    """Generate the base PyInstaller spec file if it does not already exist."""
    if spec_path.exists():
        return True

    print("[build-onedir] expo.spec not found; generating base onedir spec ...")
    cmd = [
        "uv",
        "run",
        "--with",
        PYINSTALLER_VERSION,
        "pyinstaller",
        "--noconsole",
        "--name",
        APP_NAME,
        str(entry),
    ]
    print("[build-onedir] Running:", " ".join(cmd))
    result = subprocess.run(  # noqa: S603 - trusted build command
        cmd,
        check=False,
        cwd=root,
        env=_onedir_environment(),
    )
    if result.returncode != 0:
        print(f"[build-onedir] Spec generation failed with exit code {result.returncode}", file=sys.stderr)
        return False

    if spec_path.exists():
        return True

    print("[build-onedir] Failed to generate expo.spec", file=sys.stderr)
    return False


def build_onedir() -> int:
    """Build the desktop executable in PyInstaller onedir mode.

    Returns:
        Exit code where 0 indicates success and non-zero indicates failure.
    """
    root = project_root()
    spec_path = root / "expo.spec"
    entry = root / "src" / "expo_jbm329" / "gui_main.py"
    dist_root = root / "dist"
    platform_name = detect_platform()
    exe_path = dist_root / APP_NAME / get_executable_name(platform_name)

    print(f"[build-onedir] root={root}")
    print(f"[build-onedir] entry={entry}")
    print(f"[build-onedir] spec={spec_path}")
    print(f"[build-onedir] platform={platform_name}")
    print(f"[build-onedir] SITE_PACKAGES={site_packages()}")

    if not entry.exists():
        print(f"[build-onedir] Entry point not found: {entry}", file=sys.stderr)
        return 1

    if not _generate_spec(root=root, spec_path=spec_path, entry=entry):
        return 1

    _pre_clean(root)
    _ensure_app_ico(root)

    cmd = [
        "uv",
        "run",
        "--with",
        PYINSTALLER_VERSION,
        "pyinstaller",
        "--clean",
        "--noconfirm",
        str(spec_path),
    ]
    print("[build-onedir] Running:", " ".join(cmd))
    result = subprocess.run(  # noqa: S603 - trusted build command
        cmd,
        check=False,
        cwd=root,
        env=_onedir_environment(),
    )
    if result.returncode != 0:
        print(f"[build-onedir] PyInstaller failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode

    if exe_path.exists():
        print(f"[build-onedir] SUCCESS: {exe_path}")
        return 0

    print(f"[build-onedir] Build completed but executable was not found: {exe_path}", file=sys.stderr)
    for candidate in sorted(dist_root.rglob(f"{APP_NAME}*")):
        if candidate.is_file():
            print(" -", candidate.relative_to(root), file=sys.stderr)
    return 1


def main() -> None:
    """Entry point for building the onedir executable."""
    raise SystemExit(build_onedir())


if __name__ == "__main__":
    main()
