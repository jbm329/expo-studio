"""Tests for the Qt backend selected by the test environment."""

import os
import sys

import pytest

from tests.conftest import _configure_qt_platform


@pytest.mark.parametrize(
    ("platform", "wayland_display", "configured_platform", "expected"),
    [
        ("linux", "wayland-0", None, "offscreen"),
        ("linux", "wayland-0", "wayland", "wayland"),
        ("linux", "wayland-0", "xcb", "xcb"),
        ("linux", None, None, None),
        ("win32", "wayland-0", None, None),
        ("darwin", "wayland-0", None, None),
    ],
)
def test_qt_platform_defaults_only_for_wayland(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    wayland_display: str | None,
    configured_platform: str | None,
    expected: str | None,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    if wayland_display is None:
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    else:
        monkeypatch.setenv("WAYLAND_DISPLAY", wayland_display)
    if configured_platform is None:
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    else:
        monkeypatch.setenv("QT_QPA_PLATFORM", configured_platform)

    _configure_qt_platform()

    assert os.environ.get("QT_QPA_PLATFORM") == expected
