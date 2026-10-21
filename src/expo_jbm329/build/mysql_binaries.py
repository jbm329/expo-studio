"""Collect MySQL Connector/Python's required Windows OpenSSL libraries."""

from __future__ import annotations

from importlib.metadata import distribution
from pathlib import Path

CONNECTOR_DISTRIBUTION = "mysql-connector-python"
OPENSSL_DLLS = ("libcrypto-3-x64.dll", "libssl-3-x64.dll")


def collect_mysql_connector_openssl_binaries() -> list[tuple[str, str]]:
    """Return PyInstaller binary entries for Connector/Python's OpenSSL DLLs.

    The files are selected from the connector distribution's own installation
    record so a runner-installed MySQL Server cannot become their source.

    Returns:
        Source and destination pairs for the required DLLs.

    Raises:
        FileNotFoundError: If the connector distribution does not provide a
            required DLL at the site-packages root.
        RuntimeError: If the connector distribution has no installed file list.
    """
    connector = distribution(CONNECTOR_DISTRIBUTION)
    recorded_files = connector.files
    if recorded_files is None:
        message = f"{CONNECTOR_DISTRIBUTION} does not provide an installed file list"
        raise RuntimeError(message)

    site_packages = Path(str(connector.locate_file(""))).resolve()
    expected_names = {name.casefold() for name in OPENSSL_DLLS}
    source_by_name: dict[str, Path] = {}

    for recorded_file in recorded_files:
        if recorded_file.name.casefold() not in expected_names:
            continue

        source = Path(str(connector.locate_file(recorded_file))).resolve()
        if source.parent == site_packages and source.is_file():
            source_by_name[source.name.casefold()] = source

    missing_names = [name for name in OPENSSL_DLLS if name.casefold() not in source_by_name]
    if missing_names:
        missing = ", ".join(missing_names)
        message = (
            f"{CONNECTOR_DISTRIBUTION} is missing required Windows OpenSSL DLLs at its site-packages root: {missing}"
        )
        raise FileNotFoundError(message)

    return [(str(source_by_name[name.casefold()]), ".") for name in OPENSSL_DLLS]
