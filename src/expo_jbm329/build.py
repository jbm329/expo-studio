"""Build and release utilities for Expo Studio.

This module provides helper functions and entry points for building
Windows executables using PyInstaller, including:

- Pre-cleaning of build and dist artifacts
- Optional onefile or onedir builds
- Automatic icon generation
- Creation of versioned release archive

The module is designed to be executed via `uv run` to ensure a clean,
ephemeral build environment.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import sys
import sysconfig
import tarfile
import time
import uuid
import winreg
import zipfile
from datetime import datetime
from importlib.metadata import PackageNotFoundError, metadata
from pathlib import Path

from PIL import Image


def _detect_platform() -> str:
    """Return a normalized platform identifier for release artifacts."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("darwin"):
        return "macos"
    return sys.platform.replace(" ", "_")


def _build_metadata() -> dict:
    """Return normalized metadata used for release artifacts."""
    try:
        meta = metadata("expo_jbm329")

        version = meta.get("Version", "unknown")
        license_ = (
            meta.get("License-Expression")
            or meta.get("License")
            or "GPL-3.0-or-later"
        )
    except PackageNotFoundError:
        version = "dev"
        license_ = "GPL-3.0-or-later"

    return {
        "app_name": "Expo Studio",
        "app_slug": "ExpoStudio",
        "package": "expo_jbm329",
        "version": version,
        "license": license_,
        "platform": _detect_platform(),
    }


def _build_release_notes(meta: dict[str, str], build_type: str) -> str:
    """Return release notes text for packaged release artifacts."""
    now = datetime.now()
    return (
        f"{meta['app_name']}\n"
        f"Version: {meta['version']}\n\n"
        f"Build date: {now.isoformat(timespec='seconds')}\n"
        f"Platform: {meta['platform']}\n"
        f"Build type: {build_type}\n\n"
        f"License: {meta['license']}\n"
        "Source code: https://github.com/jbm329/expo-studio\n\n"
        "This is a standalone desktop build created from the open source project.\n"
        "The application is provided as-is and developed as a personal side project.\n"
    )


def _project_root() -> Path:
    """Return the project root directory.

    The project root is resolved relative to this module's location.
    """
    return Path(__file__).resolve().parents[2]


def _site_packages() -> str | None:
    """Return the active Python site-packages path, if available."""
    return sysconfig.get_paths().get("purelib")


def _stamp() -> str:
    """Return a timestamp suitable for naming release artifacts."""
    return datetime.now().strftime("%Y%m%d-%H%M")


# -----------------------------
# Pre-clean helpers
# -----------------------------
def _chmod_writable(path: Path):
    """Ensure a filesystem path is writable.

    This is primarily used to handle read-only files on Windows.
    """
    with contextlib.suppress(Exception):
        path.chmod(stat.S_IWRITE)


def _onerror(func, path, _exc_info):
    """Error handler for shutil.rmtree.

    Attempts to make the path writable and retry the original operation.
    """
    _chmod_writable(Path(path))
    try:
        func(path)
    except Exception:
        raise


def _safe_rmtree(path: Path, retries: int = 6, backoff: float = 0.2) -> bool:
    """Remove a directory tree with retries and backoff.

    This helper is designed to handle transient file locks and read-only
    files (common on Windows).

    Args:
        path: Directory to remove.
        retries: Number of retry attempts.
        backoff: Initial backoff delay multiplier in seconds.

    Returns:
        True if the directory was removed successfully, otherwise False.
    """
    if not path.exists():
        return True

    for i in range(retries):
        try:
            shutil.rmtree(path, onerror=_onerror)
            return True
        except Exception:
            time.sleep(backoff * (i + 1))

    return False


def _kill_running_expo():
    """Terminate running expo.exe processes on Windows.

    This is a silent no-op on non-Windows platforms.
    """
    if os.name != "nt":
        return

    with contextlib.suppress(Exception):
        subprocess.run(
            ["taskkill", "/IM", "expo.exe", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _pre_clean(root: Path):
    """Perform pre-build cleanup steps.

    This function:
    - Terminates running expo.exe processes (Windows only)
    - Removes existing build/expo and dist/expo directories
    """
    _kill_running_expo()

    for p in [root / "build" / "expo", root / "dist" / "expo"]:
        if p.exists():
            print(f"[pre-clean] Removing {p} ...")
            ok = _safe_rmtree(p)
            if not ok:
                print(
                    "[pre-clean] WARNING: Could not fully clean directory "
                    "(locked files?) - continuing anyway."
                )


def _ensure_app_ico(root: Path) -> Path:
    """Generate app.ico from PNG if missing or outdated.

    The ICO is generated from the light theme application PNG and written
    to the canonical icon location used by PyInstaller.

    Args:
        root: Project root directory.

    Returns:
        Path to the generated or existing ICO file.
    """
    png_path = (
        root
        / "src"
        / "expo_jbm329"
        / "workbench"
        / "icon"
        / "themes"
        / "light"
        / "app.png"
    )
    ico_path = root / "src" / "expo_jbm329" / "workbench" / "icon" / "app.ico"

    if not png_path.exists():
        print(
            f"[icon] Source PNG not found: {png_path} "
            "- skipping ICO generation."
        )
        return ico_path

    regenerate = (
        not ico_path.exists()
        or png_path.stat().st_mtime > ico_path.stat().st_mtime
    )

    if regenerate:
        print(f"[icon] Generating ICO from {png_path} -> {ico_path}")
        ico_path.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(png_path).convert("RGBA")
        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        im.save(ico_path, format="ICO", sizes=sizes)
    else:
        print(f"[icon] Using existing ICO: {ico_path}")

    return ico_path


def _archive_onedir_with_docs(
    src_dir: Path,
    archive_path: Path,
    platform: str,
    docs: dict[str, Path],
    release_notes: str,
):
    """Archive an onedir build and include documentation files.

    The archive will contain:
      expo/
        <application files>
        README.md
        CHANGELOG.md
        LICENSE.txt
        RELEASE-NOTES.txt
    """
    root_name = src_dir.name  # "expo"

    if platform == "windows":
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            # Application files
            for p in src_dir.rglob("*"):
                if p.is_file():
                    zf.write(p, Path(root_name) / p.relative_to(src_dir))

            # Documentation files
            for name, path in docs.items():
                if path.exists():
                    zf.write(path, Path(root_name) / name)

            zf.writestr(str(Path(root_name) / "RELEASE-NOTES.txt"), release_notes)

    else:
        with tarfile.open(archive_path, "w:gz") as tf:
            # Application files
            tf.add(src_dir, arcname=root_name)

            # Documentation files
            for name, path in docs.items():
                if path.exists():
                    tf.add(path, arcname=f"{root_name}/{name}")

            # RELEASE-NOTES
            import io
            data = release_notes.encode("utf-8")
            info = tarfile.TarInfo(name=f"{root_name}/RELEASE-NOTES.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def _find_iscc_exe() -> str | None:
    """Find Inno Setup compiler executable (ISCC.exe) on Windows."""
    if os.name != "nt":
        return None

    # 1) PATH
    path_hit = shutil.which("ISCC.exe") or shutil.which("iscc.exe")
    if path_hit:
        return path_hit

    # 2) Common machine installs (6 and 7)
    common_candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 7\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    for candidate in common_candidates:
        if candidate.exists():
            return str(candidate)

    # 3) Per-user installs (6 and 7)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        user_candidates = [
            Path(local_appdata) / "Programs" / "Inno Setup 7" / "ISCC.exe",
            Path(local_appdata) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        ]
        for candidate in user_candidates:
            if candidate.exists():
                return str(candidate)

    # 4) Registry uninstall keys (HKLM + HKCU, 7 then 6)
    uninstall_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
    ]
    for hive, subkey in uninstall_keys:
        with contextlib.suppress(Exception), winreg.OpenKey(hive, subkey) as key:
            install_dir, _ = winreg.QueryValueEx(key, "InstallLocation")
            exe = Path(install_dir) / "ISCC.exe"
            if exe.exists():
                return str(exe)

    return None


def _load_or_create_app_id(root: Path) -> str:
    """Load a stable Inno Setup AppId from file, or create one.

    A stable AppId is required for upgrade/uninstall continuity.
    """
    appid_file = root / "installer.appid"
    if appid_file.exists():
        value = appid_file.read_text(encoding="utf-8").strip()
        if value:
            return value

    value = "{" + str(uuid.uuid4()).upper() + "}"
    appid_file.write_text(value + "\n", encoding="utf-8")
    return value


def _write_release_notes_file(root: Path, meta: dict[str, str], build_type: str) -> Path:
    """Write release notes file and return its path."""
    release_notes_path = root / "RELEASE-NOTES.txt"
    release_notes_path.write_text(
        _build_release_notes(meta=meta, build_type=build_type),
        encoding="utf-8",
    )
    return release_notes_path


def _write_inno_script(
    root: Path,
    app_name: str,
    app_slug: str,
    version: str,
    publisher: str,
    exe_name: str,
    source_dir: Path,
    output_dir: Path,
    app_id: str,
) -> Path:
    """Generate an Inno Setup script for installer/uninstaller/upgrade support."""
    script_path = root / "build" / "installer.iss"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_app_id = app_id.replace("{", "{{").replace("}", "}}")

    icon_path = (root / "src" / "expo_jbm329" / "workbench" / "icon" / "app.ico").resolve()
    icon_path_str = str(icon_path).replace("/", "\\")

    wizard_image_path = (root / "src" / "expo_jbm329" / "workbench" / "splash" / "wizard.bmp").resolve()
    wizard_image_path_str = str(wizard_image_path).replace("/", "\\")

    wizard_small_image_path = (root / "src" / "expo_jbm329" / "workbench" / "splash" / "wizard-small.bmp").resolve()
    wizard_small_image_path_str = str(wizard_small_image_path).replace("/", "\\")

    license_path = (root / "LICENSE.txt").resolve()
    license_path_str = str(license_path).replace("/", "\\")

    release_notes_path = (root / "RELEASE-NOTES.txt").resolve()
    release_notes_path_str = str(release_notes_path).replace("/", "\\")

    readme_path = (root / "README.md").resolve()
    readme_path_str = str(readme_path).replace("/", "\\")

    changelog_path = (root / "CHANGELOG.md").resolve()
    changelog_path_str = str(changelog_path).replace("/", "\\")

    # Note:
    # - ArchitecturesInstallIn64BitMode=x64 + ArchitecturesAllowed=x64 = x64 installer
    # - PrivilegesRequiredOverridesAllowed lets user choose all users/current user
    # - Same AppId enables upgrade + uninstall registration continuity
    script = f"""[Setup]
AppId={escaped_app_id}
AppName={app_name}
SetupIconFile={icon_path_str}
WizardSmallImageFile={wizard_small_image_path_str}
WizardImageFile={wizard_image_path_str}
LicenseFile={license_path_str}
InfoAfterFile={release_notes_path_str}
AppVersion={version}
AppPublisher={publisher}
DefaultDirName={{autopf}}\\{app_name}
DisableProgramGroupPage=yes
DefaultGroupName={app_name}
UninstallDisplayIcon={{app}}\\{exe_name}
OutputDir={output_dir}
OutputBaseFilename={app_slug}-{version}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "swedish"; MessagesFile: "compiler:Languages\\Swedish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
swedish.desktopicon=Skapa genväg på skrivbordet
swedish.launch=Starta {app_name}
english.desktopicon=Create desktop shortcut
english.launch=Launch {app_name}

[Tasks]
Name: "desktopicon"; Description: "{{cm:desktopicon}}"; Flags: unchecked

[Files]
Source: "{source_dir}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{readme_path_str}"; DestDir: "{{app}}"
Source: "{changelog_path_str}"; DestDir: "{{app}}"
Source: "{license_path_str}"; DestDir: "{{app}}"
Source: "{release_notes_path_str}"; DestDir: "{{app}}"


[Icons]
Name: "{{group}}\\{app_name}"; Filename: "{{app}}\\{exe_name}"
Name: "{{autodesktop}}\\{app_name}"; Filename: "{{app}}\\{exe_name}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{exe_name}"; Description: "{{cm:launch}}"; Flags: nowait postinstall skipifsilent
"""
    script_path.write_text(script, encoding="utf-8")
    return script_path


def _build_windows_installer(root: Path, onedir_dir: Path) -> Path | None:
    """Build a Windows installer using Inno Setup."""
    iscc = _find_iscc_exe()
    if iscc is None:
        print("[installer] Inno Setup compiler not found. Falling back to ZIP archive.")
        return None

    meta = _build_metadata()
    app_id = _load_or_create_app_id(root)
    out_dir = root / "release"
    out_dir.mkdir(exist_ok=True)

    script_path = _write_inno_script(
        root=root,
        app_name=meta["app_name"],
        app_slug=meta["app_slug"],
        version=meta["version"],
        publisher="Jonas Brännström",
        exe_name="expo.exe",
        source_dir=onedir_dir,
        output_dir=out_dir,
        app_id=app_id,
    )

    cmd = [iscc, str(script_path)]
    print("[installer] Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=root)

    return out_dir


def build_exe(onefile: bool = False, make_release: bool = False) -> int:
    """Build the Windows executable using PyInstaller.

    The build is performed via `uv run` to ensure a clean environment with
    an ephemeral PyInstaller installation.

    Behavior:
    - Generates a base spec file (onedir) if expo.spec does not exist
    - Performs pre-clean steps before building
    - Supports optional onefile builds via environment variable
    - Optionally packages release artifacts into versioned ZIP files

    Args:
        onefile: If True, build a onefile executable.
        make_release: If True, create a versioned release artifact.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    root = _project_root()
    spec_path = root / "expo.spec"
    entry = root / "src" / "expo_jbm329" / "gui_main.py"
    default_dist_root = root / "dist"

    print(f"[build-exe] root={root}")
    print(f"[build-exe] entry={entry}")
    print(f"[build-exe] spec={spec_path}")
    print(f"[build-exe] SITE_PACKAGES={_site_packages()}")

    if not entry.exists():
        print(
            f"[build-exe] Entry point not found: {entry}",
            file=sys.stderr,
        )
        return 1

    # Generate a basic onedir spec file on first run
    if not spec_path.exists():
        print(
            "[build-exe] expo.spec not found - generating base spec (onedir) ..."
        )
        cmd_gen = [
            "uv",
            "run",
            "--with",
            "pyinstaller>=6.19",
            "pyinstaller",
            "--noconsole",
            "--name",
            "expo",
            str(entry),
        ]
        print("[build-exe] Running:", " ".join(cmd_gen))
        subprocess.run(cmd_gen, check=True, cwd=root)

        if not spec_path.exists():
            print(
                "[build-exe] Failed to generate expo.spec",
                file=sys.stderr,
            )
            return 1

        # NOTE: Re-apply any manual modifications to expo.spec after generation.

    # Pre-build cleanup
    _pre_clean(root)

    # Ensure application icon is available
    _ensure_app_ico(root)

    # Build using spec file; onefile is controlled via environment variable
    env = os.environ.copy()
    if onefile:
        env["EXPO_ONEFILE"] = "1"

    cmd_build = [
        "uv",
        "run",
        "--with",
        "pyinstaller>=6.19",
        "pyinstaller",
        "--clean",
        "--noconfirm",
        str(spec_path),
    ]
    print("[build-exe] Running:", " ".join(cmd_build))
    subprocess.run(cmd_build, check=True, cwd=root, env=env)

    # Locate resulting executable
    exe_onedir = default_dist_root / "expo" / "expo.exe"
    exe_onefile = default_dist_root / "expo.exe"
    exe_path = exe_onefile if onefile else exe_onedir

    if not exe_path.exists():
        candidates = sorted(default_dist_root.rglob("*.exe"))
        if candidates:
            exe_path = candidates[0]

    if exe_path.exists():
        print(f"[build-exe] SUCCESS: {exe_path}")
    else:
        print(
            "[build-exe] Build completed but executable was not found "
            "at the expected location."
        )
        for p in sorted(default_dist_root.rglob("*.exe")):
            print(" -", p.relative_to(root))

    # Release packaging
    if make_release:
        rel_root = root / "release"
        rel_root.mkdir(exist_ok=True)
        stamp = _stamp()

        if onefile:
            out_exe = rel_root / f"expo_{stamp}.exe"
            if exe_onefile.exists():
                shutil.copy2(exe_onefile, out_exe)
                print(f"[release] Copied onefile executable to: {out_exe}")
            else:
                print(
                    "[release] WARNING: Onefile artifact was not found."
                )
        else:
            # ONEDIR -> create platform-specific archive (zip or tar.gz)
            onedir_dir = default_dist_root / "expo"
            if onedir_dir.exists():
                meta = _build_metadata()
                date_str = datetime.now().strftime("%Y-%m-%d")
                _write_release_notes_file(root=root, meta=meta, build_type="onedir")

                docs = {
                    "README.md": root / "README.md",
                    "CHANGELOG.md": root / "CHANGELOG.md",
                    "LICENSE.txt": root / "LICENSE.txt",
                    "RELEASE-NOTES.txt": root / "RELEASE-NOTES.txt",
                }

                if meta["platform"] == "windows":
                    installer_out_dir = _build_windows_installer(root=root, onedir_dir=onedir_dir)
                    if installer_out_dir is not None:
                        print(f"[release] Created Windows installer in: {installer_out_dir}")
                    else:
                        archive_name = (
                            f"{meta['app_slug']}-{meta['version']}-windows-onedir-{date_str}.zip"
                        )
                        archive_path = rel_root / archive_name
                        _archive_onedir_with_docs(
                            src_dir=onedir_dir,
                            archive_path=archive_path,
                            platform=meta["platform"],
                            docs=docs,
                            release_notes=(root / "RELEASE-NOTES.txt").read_text(encoding="utf-8"),
                        )
                        print(f"[release] Created archive: {archive_path}")
                else:
                    archive_name = f"{meta['app_slug']}-{meta['version']}-{meta['platform']}-onedir-{date_str}.tar.gz"
                    archive_path = rel_root / archive_name
                    _archive_onedir_with_docs(
                        src_dir=onedir_dir,
                        archive_path=archive_path,
                        platform=meta["platform"],
                        docs=docs,
                        release_notes=(root / "RELEASE-NOTES.txt").read_text(encoding="utf-8"),
                    )
                    print(f"[release] Created archive: {archive_path}")
            else:
                print(
                    "[release] WARNING: onedir artifact was not found."
                )

    return 0


def build_release():
    """Entry point for `uv run build-release`.

    Performs an onedir build and packages the result as a versioned ZIP.
    """
    raise SystemExit(build_exe(onefile=False, make_release=True))


if __name__ == "__main__":
    # Support: uv run python -m expo_jbm329.build --onefile --release
    onefile = "--onefile" in sys.argv
    make_release = "--release" in sys.argv
    raise SystemExit(build_exe(onefile=onefile, make_release=make_release))
