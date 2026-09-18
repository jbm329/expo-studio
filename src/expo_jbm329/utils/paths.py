"""Path utility functions for the Expo application.

This module provides helpers for expanding environment variables in paths
and mapping file suffixes to their corresponding default directories.
"""

from __future__ import annotations

import os
from pathlib import Path


def expand(p: str | Path) -> Path:
    """Expand ~ and env-vars in a path and return an absolute Path.

    Args:
        p: The path string or Path object to expand.

    Returns:
        The resolved absolute Path.
    """
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()


# def suffix_to_dir(suffix: str, settings: dict) -> Path:
#     """Return the base directory Path for a given file suffix.
#
#     Mapping rules:
#       - .sql                -> get_sql_dir
#       - .csv                -> get_csv_dir
#       - .xls/.xlsx          -> get_excel_dir
#       - .df/.pkl/.pickle    -> get_data_dir
#       - .json/.parquet/.feather -> get_data_dir
#       - .html/.htm          -> get_report_dir
#       - fallback            -> get_documents_dir
#
#     Args:
#         suffix: The file suffix (e.g., ".csv").
#         settings: Application settings dictionary.
#
#     Returns:
#         The mapped directory Path.
#     """
#     s = (suffix or "").strip().lower()
#
#     if s == ".sql":
#         return get_sql_dir(settings)
#
#     if s == ".csv":
#         return get_csv_dir(settings)
#
#     if s in {".xlsx", ".xls"}:
#         return get_excel_dir(settings)
#
#     if s in {".df", ".pkl", ".pickle", ".parquet", ".feather", ".ft"}:
#         return get_data_dir(settings)
#
#     if s == ".json":
#         return get_data_dir(settings)
#
#     if s in {".html", ".htm"}:
#         return get_report_dir(settings)
#
#     # fallback: använd Documents/Expo
#     return get_documents_dir(settings)
