"""Build, stage, and package Expo Studio releases."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from expo_jbm329.build.build import build_onedir
from expo_jbm329.build.build_utils import detect_platform
from expo_jbm329.build.package_portable import package_portable_zip
from expo_jbm329.build.package_windows import package_windows_installer
from expo_jbm329.build.stage import stage_onedir

if TYPE_CHECKING:
    from collections.abc import Callable


def _run_step(name: str, step: Callable[[], int]) -> int:
    """Run one release step and return its exit code."""
    print(f"[release] Starting {name} ...")
    exit_code = step()
    if exit_code != 0:
        print(f"[release] FAILED: {name} exited with {exit_code}", file=sys.stderr)
        return exit_code

    print(f"[release] Completed {name}.")
    return 0


def _run_windows_packaging() -> int:
    """Run all Windows packaging steps."""
    for name, step in [
        ("windows installer packaging", package_windows_installer),
        ("portable ZIP packaging", package_portable_zip),
    ]:
        exit_code = _run_step(name, step)
        if exit_code != 0:
            return exit_code

    return 0


def release() -> int:
    """Build, stage, and package a release for the current platform.

    Returns:
        Exit code where 0 indicates success and non-zero indicates failure.
    """
    for name, step in [
        ("onedir executable build", build_onedir),
        ("release staging", stage_onedir),
    ]:
        exit_code = _run_step(name, step)
        if exit_code != 0:
            return exit_code

    platform_name = detect_platform()
    print(f"[release] platform={platform_name}")

    if platform_name == "windows":
        return _run_windows_packaging()

    print(f"[release] Packaging is not implemented for platform: {platform_name}", file=sys.stderr)
    return 1


def main() -> None:
    """Entry point for building and packaging a release."""
    raise SystemExit(release())


if __name__ == "__main__":
    main()
