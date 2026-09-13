"""Application metadata access for Expo Studio.

This module provides a small, centralized API for accessing application
metadata (name, version, description, author, license) at runtime.

The metadata is retrieved from the installed package distribution using
``importlib.metadata``. This makes the information available consistently
across development environments and bundled distributions (e.g. PyInstaller
executables), without relying on direct access to ``pyproject.toml``.

The module intentionally avoids file system access and build-time assumptions
to ensure robustness in frozen and deployed environments.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, metadata
from typing import TypedDict


class AppMetadata(TypedDict):
    """Typed representation of application metadata.

    Attributes:
        name: Human-readable application name.
        version: Application version string.
        description: Short summary or description of the application.
        author: Primary author or maintainer.
        license: License identifier or expression.
    """

    name: str
    version: str
    description: str
    author: str
    license: str


def get_app_metadata() -> AppMetadata:
    """Retrieve application metadata from the installed package.

    This function reads distribution metadata using ``importlib.metadata`` and
    maps it to a normalized dictionary suitable for UI presentation (e.g. an
    About dialog).

    The function is resilient to differences in packaging backends and metadata
    standards (PEP 621, PEP 639), and includes sensible fallbacks for fields that
    may be absent or represented differently across environments.

    Returns:
        AppMetadata: A dictionary containing normalized application metadata.

    Raises:
        None. If the package metadata cannot be found, a safe fallback metadata
        dictionary is returned instead.
    """
    try:
        meta = metadata("expo_jbm329")

        # --- Author handling (PEP 621 realities) ---
        author = (
            meta.get("Author")
            or meta.get("Author-email")
            or ", ".join(meta.get_all("Author") or [])
            or "Jonas Brännström"
        )

        # --- License handling (PEP 639 realities) ---
        license_ = meta.get("License-Expression") or meta.get("License") or "GPL-3.0-or-later"

        return {
            "name": "Expo studio",
            "version": meta.get("Version", "unknown"),
            "description": meta.get("Summary", ""),
            "author": author,
            "license": license_,
        }

    except PackageNotFoundError:
        # Extremely early dev / edge-case fallback
        return {
            "name": "Expo Studio",
            "version": "dev",
            "description": "Workbench for datapreparation and dataset analysis",
            "author": "Jonas Brännström",
            "license": "GPL-3.0-or-later",
        }
