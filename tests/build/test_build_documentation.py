"""Documentation entry points preserve commands and failure exit codes."""

import subprocess
from collections.abc import Callable
from unittest.mock import patch

import pytest

from expo_jbm329.build import build_documentation


@pytest.mark.parametrize(
    ("entry_point", "arguments"),
    [
        (build_documentation.main, ["build", "--clean", "--strict"]),
        (build_documentation.preview, ["serve"]),
    ],
)
@pytest.mark.parametrize("returncode", [0, 1])
def test_documentation_command(entry_point: Callable[[], int], arguments: list[str], returncode: int) -> None:
    with patch.object(build_documentation.subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess(args=[], returncode=returncode)

        assert entry_point() == returncode

    run.assert_called_once_with(
        ["uv", "run", "--frozen", "--extra", "docs", "zensical", *arguments],
        cwd=build_documentation.project_root(),
        check=False,
    )


def test_preview_interrupt_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(build_documentation.subprocess, "run", side_effect=KeyboardInterrupt):
        assert build_documentation.preview() == 0

    assert capsys.readouterr().out == "Documentation preview stopped.\n"


def test_preview_startup_error_propagates() -> None:
    with (
        patch.object(build_documentation.subprocess, "run", side_effect=FileNotFoundError("uv not found")),
        pytest.raises(FileNotFoundError, match="uv not found"),
    ):
        build_documentation.preview()
