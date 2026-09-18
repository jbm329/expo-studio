"""REST data source job."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.job_result import JobResult
from expo_jbm329.services.rest.client import RestClientError, fetch_json_pages
from expo_jbm329.services.rest.normalizer import RestNormalizeError, normalize_json_to_df

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.services.rest.models import RestRequestConfig


def fetch_rest_dataset(
    config: RestRequestConfig,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    job_id: str | None = None,
    job_scope: str | None = None,
    corr_id: str | None = None,
) -> JobResult:
    """Fetch data from a REST API and return it as a JobResult.

    This function is intended to be executed by JobManager.run().
    It performs HTTP fetching, JSON normalization, and returns
    a JobResult containing a pandas DataFrame.

    Args:
        config: REST request configuration.
        progress_cb: Optional progress callback (0..100).
        cancel_cb: Optional cancellation callback.
        job_id: Injected job identifier (unused here, for logging/debug).
        job_scope: Injected job scope (unused here).
        corr_id: Correlation identifier for logging.

    Returns:
        JobResult
    """
    t0 = time.perf_counter()

    try:
        if cancel_cb and cancel_cb():
            return JobResult(
                ok=False,
                elapsed=0.0,
                cancelled=True,
                corr_id=corr_id,
            )

        # ---------------- HTTP fetch ----------------
        payloads, _ = fetch_json_pages(
            config,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )

        if cancel_cb and cancel_cb():
            return JobResult(
                ok=False,
                elapsed=time.perf_counter() - t0,
                cancelled=True,
                corr_id=corr_id,
            )

        # ---------------- Normalize ----------------

        df = _normalize_payloads(
            payloads,
            response_path=config.response_path,
        )

        if not isinstance(df, pd.DataFrame):
            msg = "Normalizer did not return a DataFrame"
            raise RuntimeError(msg)

        elapsed = time.perf_counter() - t0

        return JobResult(
            ok=True,
            elapsed=elapsed,
            data=df,
            cancelled=False,
            corr_id=corr_id,
        )

    except (RestClientError, RestNormalizeError) as exc:
        return JobResult(
            ok=False,
            elapsed=time.perf_counter() - t0,
            error=str(exc),
            cancelled=False,
            corr_id=corr_id,
        )

    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
        # Defensive fallback: never let the worker crash
        return JobResult(
            ok=False,
            elapsed=time.perf_counter() - t0,
            error=f"Unexpected error: {exc}",
            cancelled=False,
            corr_id=corr_id,
        )


def _normalize_payloads(
    payloads: list[object],
    *,
    response_path: str | None,
) -> pd.DataFrame:
    """Normalize one or more REST payloads into a single dataframe."""
    if not payloads:
        msg = "REST response did not contain any payloads"
        raise RestNormalizeError(msg)

    frames = [
        normalize_json_to_df(
            payload,
            response_path=response_path,
        )
        for payload in payloads
    ]

    if len(frames) == 1:
        return frames[0]

    return pd.concat(frames, ignore_index=True)
