"""Manually verified license identifiers for distributions with incomplete metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LicenseOverride:
    """A manually verified license identifier for a distribution.

    An override only applies when the distribution declares no license identifier
    itself and ships a license file whose text matches ``license_text_sha256``.
    If a future release changes its license file, the override stops applying
    and the missing-license warning returns, prompting a new review.

    Attributes:
        distribution: Distribution name in any normalization.
        license: SPDX license expression.
        license_text_sha256: SHA-256 of the stripped, UTF-8 encoded license text.
        reference: Where the license was verified.
    """

    distribution: str
    license: str
    license_text_sha256: str
    reference: str


DEFAULT_LICENSE_OVERRIDES: tuple[LicenseOverride, ...] = (
    # setuptools 79 ships the MIT license text but no License-Expression,
    # License field or license classifier.
    LicenseOverride(
        distribution="setuptools",
        license="MIT",
        license_text_sha256="dc0589ce4ab317782b1bfe5b24d1a3528eed3c028be8f197c516997c777cdd0c",
        reference="https://github.com/pypa/setuptools/blob/main/LICENSE",
    ),
)
