"""Local documentation build and preview entry points."""

import subprocess

from expo_jbm329.build.build_utils import project_root


def main() -> int:
    """Create a clean documentation build, treating warnings as errors."""
    return subprocess.run(
        ["uv", "run", "--frozen", "--extra", "docs", "zensical", "build", "--clean", "--strict"],  # noqa: S607
        cwd=project_root(),
        check=False,
    ).returncode


def preview() -> int:
    """Serve the local documentation preview until interrupted."""
    return subprocess.run(
        ["uv", "run", "--frozen", "--extra", "docs", "zensical", "serve"],  # noqa: S607
        cwd=project_root(),
        check=False,
    ).returncode
