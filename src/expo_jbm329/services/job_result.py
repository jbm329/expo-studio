"""Data class for job execution results.

This module defines the JobResult class, which encapsulates the outcome of a
background job, including success status, elapsed time, and data payload.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class JobResult:
    """Represents the result of a background job.

    Attributes:
        ok: Whether the job completed successfully.
        elapsed: Time taken for the job in seconds.
        path: Path associated with the job (e.g., input or output file).
        cancelled: Whether the job was cancelled by the user.
        error: Error message if the job failed.
        data: Optional payload returned by the job (e.g., a DataFrame).
        corr_id: Correlation identifier for logging.
    """
    ok: bool
    elapsed: float | None
    path: str | None = None
    cancelled: bool = False
    error: str | None = None
    data: Any | None = None
    corr_id: str | None = None
