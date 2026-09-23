"""Create a Windows installer from staged release artifacts."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from string import Template

from expo_jbm329.build.build import executable_name
from expo_jbm329.build.build_utils import installer_dir, project_root, release_dir, staging_dir
from expo_jbm329.build.stage import DOCUMENTATION_FILES, RELEASE_NOTES_FILE, ReleaseMetadata, build_metadata

PUBLISHER = "Jonas Brännström"
TEMPLATE_FILE = "installer.iss.in"
APP_ID_FILE = "installer.appid"
GENERATED_SCRIPT_FILE = "installer.iss"


@dataclass(frozen=True)
class WindowsInstallerPaths:
    """Filesystem paths used for Windows installer packaging."""

    root: Path
    staging_dir: Path
    source_dir: Path
    output_dir: Path
    build_dir: Path
    template_path: Path
    app_id_path: Path
    generated_script_path: Path
    icon_path: Path
    wizard_image_path: Path
    wizard_small_image_path: Path


def _windows_path(path: Path) -> str:
    """Return a Windows-style absolute path for Inno Setup."""
    return str(path.resolve()).replace("/", "\\")


def _inno_literal(value: str) -> str:
    """Escape a literal value for Inno Setup directives."""
    return value.replace("{", "{{").replace("}", "}}")


def _paths() -> WindowsInstallerPaths:
    """Return paths used by Windows installer packaging."""
    root = project_root()
    release_root = release_dir()
    build_dir = release_root / "windows-installer"
    setup_dir = installer_dir()
    return WindowsInstallerPaths(
        root=root,
        staging_dir=staging_dir(),
        source_dir=staging_dir() / "expo",
        output_dir=release_root,
        build_dir=build_dir,
        template_path=setup_dir / TEMPLATE_FILE,
        app_id_path=setup_dir / APP_ID_FILE,
        generated_script_path=build_dir / GENERATED_SCRIPT_FILE,
        icon_path=root / "src" / "expo_jbm329" / "workbench" / "icon" / "app.ico",
        wizard_image_path=root / "src" / "expo_jbm329" / "workbench" / "splash" / "wizard.bmp",
        wizard_small_image_path=root / "src" / "expo_jbm329" / "workbench" / "splash" / "wizard-small.bmp",
    )


def _find_iscc_exe() -> Path | None:
    """Find the Inno Setup compiler executable on Windows."""
    if os.name != "nt":
        return None

    path_hit = shutil.which("ISCC.exe") or shutil.which("iscc.exe")
    if path_hit is not None:
        return Path(path_hit)

    common_candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 7\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    for candidate in common_candidates:
        if candidate.is_file():
            return candidate

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata is not None:
        user_candidates = [
            Path(local_appdata) / "Programs" / "Inno Setup 7" / "ISCC.exe",
            Path(local_appdata) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        ]
        for candidate in user_candidates:
            if candidate.is_file():
                return candidate

    return _find_iscc_exe_from_registry()


def _find_iscc_exe_from_registry() -> Path | None:
    """Find the Inno Setup compiler executable from Windows uninstall registry keys."""
    if os.name != "nt":
        return None

    try:
        import winreg
    except ImportError:
        return None

    uninstall_keys = [
        (winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"),
        (winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
        (winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"),
        (winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
    ]
    for hive, subkey in uninstall_keys:
        with contextlib.suppress(OSError), winreg.OpenKey(hive, subkey) as key:  # type: ignore[attr-defined]
            install_dir, _ = winreg.QueryValueEx(key, "InstallLocation")  # type: ignore[attr-defined]
            candidate = Path(install_dir) / "ISCC.exe"
            if candidate.is_file():
                return candidate

    return None


def _load_or_create_app_id(app_id_path: Path) -> str:
    """Load a stable Inno Setup AppId from file, or create one."""
    if app_id_path.exists():
        value = app_id_path.read_text(encoding="utf-8").strip()
        if value:
            return value

    app_id_path.parent.mkdir(parents=True, exist_ok=True)
    value = "{" + str(uuid.uuid4()).upper() + "}"
    app_id_path.write_text(value + "\n", encoding="utf-8")
    print(f"[package-windows] Created new installer AppId: {app_id_path}")
    return value


def _required_paths(paths: WindowsInstallerPaths) -> list[Path]:
    """Return required input paths for Windows installer packaging."""
    return [
        paths.template_path,
        paths.source_dir,
        paths.icon_path,
        paths.wizard_image_path,
        paths.wizard_small_image_path,
        *(paths.staging_dir / file_name for file_name in DOCUMENTATION_FILES),
        paths.staging_dir / RELEASE_NOTES_FILE,
    ]


def _validate_inputs(paths: WindowsInstallerPaths) -> bool:
    """Validate required input files and directories."""
    missing = [path for path in _required_paths(paths) if not path.exists()]
    if not missing:
        return True

    print("[package-windows] Missing required files or directories:", file=sys.stderr)
    for path in missing:
        print(f" - {path}", file=sys.stderr)
    return False


def render_inno_script(paths: WindowsInstallerPaths, release_metadata: ReleaseMetadata) -> Path:
    """Render the Inno Setup template to a generated script.

    Args:
        paths: Filesystem paths used by packaging.
        release_metadata: Release metadata for output names and installer version.

    Returns:
        Path to the generated Inno Setup script.
    """
    paths.build_dir.mkdir(parents=True, exist_ok=True)
    output_base_filename = f"{release_metadata.app_slug}-{release_metadata.version}-setup"
    template = Template(paths.template_path.read_text(encoding="utf-8"))
    script = template.substitute(
        APP_ID=_inno_literal(_load_or_create_app_id(paths.app_id_path)),
        APP_NAME=release_metadata.app_name,
        APP_SLUG=release_metadata.app_slug,
        VERSION=release_metadata.version,
        PUBLISHER=PUBLISHER,
        EXE_NAME=executable_name("windows"),
        SOURCE_DIR=_windows_path(paths.source_dir),
        OUTPUT_DIR=_windows_path(paths.output_dir),
        OUTPUT_BASE_FILENAME=output_base_filename,
        ICON_PATH=_windows_path(paths.icon_path),
        WIZARD_IMAGE_PATH=_windows_path(paths.wizard_image_path),
        WIZARD_SMALL_IMAGE_PATH=_windows_path(paths.wizard_small_image_path),
        README_PATH=_windows_path(paths.staging_dir / "README.md"),
        CHANGELOG_PATH=_windows_path(paths.staging_dir / "CHANGELOG.md"),
        LICENSE_PATH=_windows_path(paths.staging_dir / "LICENSE.txt"),
        RELEASE_NOTES_PATH=_windows_path(paths.staging_dir / RELEASE_NOTES_FILE),
    )
    paths.generated_script_path.write_text(script, encoding="utf-8")
    return paths.generated_script_path


def package_windows_installer() -> int:
    """Create a Windows installer from the staged onedir release.

    Returns:
        Exit code where 0 indicates success and non-zero indicates failure.
    """
    if os.name != "nt":
        print("[package-windows] Windows installer packaging can only run on Windows.", file=sys.stderr)
        return 1

    paths = _paths()
    release_metadata = build_metadata()

    print(f"[package-windows] staging={paths.staging_dir}")
    print(f"[package-windows] output={paths.output_dir}")

    if not _validate_inputs(paths):
        return 1

    iscc_path = _find_iscc_exe()
    if iscc_path is None:
        print("[package-windows] Inno Setup compiler not found.", file=sys.stderr)
        return 1

    try:
        script_path = render_inno_script(paths=paths, release_metadata=release_metadata)
    except (KeyError, OSError, ValueError) as exc:
        print(f"[package-windows] Failed to render Inno Setup script: {exc}", file=sys.stderr)
        return 1

    cmd = [str(iscc_path), str(script_path)]
    print("[package-windows] Running:", " ".join(cmd))
    result = subprocess.run(cmd, check=False, cwd=paths.root)  # noqa: S603 - trusted build command
    if result.returncode != 0:
        print(f"[package-windows] Inno Setup failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode

    print(f"[package-windows] SUCCESS: {paths.output_dir}")
    return 0
