"""Data processing services, primarily for generating profile reports.

This module provides functions to generate single and comparison profile reports
using ydata-profiling.
"""
from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from ydata_profiling import ProfileReport

logger = logging.getLogger("applogger.service")


# ------------------------------------------------------------
# Ydata-Profiling
# ------------------------------------------------------------
def generate_profile_report(df: pd.DataFrame, title: str, corr_id: str) -> ProfileReport:
    """Build a ydata-profiling report for a single DataFrame.

    Args:
        df: The DataFrame to profile.
        title: Title for the report.
        corr_id: Correlation identifier for logging.

    Returns:
        The generated ProfileReport.

    Logging:
      • DEBUG: entry with corr, title, rows/cols
      • INFO:  success with total time
      • ERROR: failure with traceback
    """
    rows = "?"
    cols = "?"
    with contextlib.suppress(Exception):
        rows, cols = str(len(df)), str(len(df.columns))

    logger.debug(
        "Generating profile report (corr=%s, title=%r, rows=%s, cols=%s)",
        corr_id, title, rows, cols
    )
    t0 = time.perf_counter()
    try:
        from ydata_profiling import ProfileReport
        # Disable progress bars: we integrate progress in our own job UI
        profile = ProfileReport(df, title=title, explorative=True, progress_bar=False)
        # Some versions expect config attribute separately; keep defensively:
        with contextlib.suppress(Exception):
            profile.config.progress_bar = False

        dt_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "Profile built (corr=%s, title=%r, ms=%.1f, rows=%s, cols=%s)",
            corr_id, title, dt_ms, rows, cols
        )
        return profile

    except Exception as e:
        logger.error(
            "Generate profile report failed (corr=%s, title=%r): %s",
            corr_id, title, e, exc_info=True
        )
        raise


def generate_comparison_profile_report(
    data: list[tuple[pd.DataFrame, str]],
    corr_id: str | None = None
) -> ProfileReport:
    """Build a comparison report from multiple datasets.

    Args:
        data: List of (DataFrame, title) tuples to compare.
        corr_id: Optional correlation identifier for logging.

    Returns:
        The generated comparison ProfileReport.

    Logging:
      • DEBUG: entry with corr, number of datasets and first few titles
      • INFO:  success with total time
      • ERROR: failure with traceback
    """
    number_of_datasets = 0
    titles_preview = ""
    try:
        number_of_datasets = len(data) if data else 0
        titles_preview = ", ".join([nm for _, nm in (data[:3] if data else [])])
    except Exception:
        pass

    logger.debug(
        "Generate comparison profile report (corr=%s, datasets=%s, preview=%r)",
        corr_id, number_of_datasets, titles_preview
    )

    t0 = time.perf_counter()
    try:
        from ydata_profiling import compare
        reports: list[ProfileReport] = []
        for (df, title) in data or []:
            reports.append(generate_profile_report(df, title, corr_id=corr_id))

        comp = compare(reports)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "Profile comparison built (corr=%s, ms=%.1f, datasets=%s)",
            corr_id, dt_ms, number_of_datasets
        )
        return comp

    except Exception as e:
        logger.error(
            "Generate comparison profile report failed (corr=%s, datasets=%s): %s",
            corr_id, number_of_datasets, e, exc_info=True
        )
        raise

