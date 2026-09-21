"""Headless job management and background worker services.

This module provides a UI-agnostic JobManager for coordinating background work
executed either in dedicated QThreads or on a shared ThreadPoolExecutor.

Responsibilities:
    - Create and track jobs.
    - Inject supported runtime context into callables.
    - Expose a consistent Qt-signal based job handle API.
    - Support cooperative cancellation.
    - Perform robust lifecycle cleanup.
    - Emit structured lifecycle logs with correlation support.

Non-responsibilities:
    - No status bar handling.
    - No progress bar handling.
    - No dialogs.
    - No foreground/background UI orchestration.

The returned job handles expose the following Qt signals:
    - started
    - progress(int)
    - result(object)
    - error(str)
    - finished
"""

from __future__ import annotations

import contextlib
import inspect
import logging
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Literal, Protocol, cast

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

RunnerKind = Literal["thread", "pool"]


# =============================================================================
# Protocols and type definitions
# =============================================================================


class _ConnectableSignal(Protocol):
    """Protocol for Qt-like signals exposing connect()."""

    def connect(self, slot: Callable[..., object], connection_type: Qt.ConnectionType = ...) -> object:
        """Connect a slot to the signal."""
        ...


def _connect_queued(signal: object, slot: Callable[..., object]) -> object:
    """Connect a Qt signal using a queued connection."""
    return cast("_ConnectableSignal", signal).connect(slot, Qt.ConnectionType.QueuedConnection)


# =============================================================================
# Data structures
# =============================================================================


@dataclass(slots=True)
class JobMetadata:
    """Structured metadata stored for each running job.

    Attributes:
        job_id: Unique identifier for the job.
        runner: Execution backend used by the job.
        scope: Optional user-defined scope string.
        corr_id: Optional correlation identifier.
        created_monotonic: Monotonic timestamp captured at job creation.
    """

    job_id: str
    runner: RunnerKind
    scope: str | None
    corr_id: str | None
    created_monotonic: float


# =============================================================================
# Signal bridge for pool jobs
# =============================================================================


class _FutureBridge(QObject):
    """QObject signal bridge for thread-pool based jobs.

    This bridge ensures that pool-job lifecycle events are delivered on the
    bridge object's thread via queued connections. This avoids races where a
    very fast future completes before external result/error/finished handlers
    have been connected by the caller.
    """

    started = pyqtSignal()
    progress = pyqtSignal(int)
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    _dispatch_started = pyqtSignal()
    _dispatch_progress = pyqtSignal(int)
    _dispatch_result = pyqtSignal(object)
    _dispatch_error = pyqtSignal(str)
    _dispatch_finished = pyqtSignal()

    def __init__(self, job_id: str) -> None:
        """Initialize the bridge.

        Args:
            job_id: Unique identifier for the job.
        """
        super().__init__()
        self._job_id = job_id

        _connect_queued(self._dispatch_started, self.started.emit)
        _connect_queued(self._dispatch_progress, self.progress.emit)
        _connect_queued(self._dispatch_result, self.result.emit)
        _connect_queued(self._dispatch_error, self.error.emit)
        _connect_queued(self._dispatch_finished, self.finished.emit)

    @property
    def job_id(self) -> str:
        """Return the associated job id."""
        return self._job_id

    def post_started(self) -> None:
        """Queue a started signal on the bridge thread."""
        self._dispatch_started.emit()

    def post_progress(self, value: int) -> None:
        """Queue a progress signal on the bridge thread.

        Args:
            value: Progress value in the range 0..100.
        """
        self._dispatch_progress.emit(int(value))

    def post_result(self, payload: object) -> None:
        """Queue a result signal on the bridge thread.

        Args:
            payload: Result payload.
        """
        self._dispatch_result.emit(payload)

    def post_error(self, payload: str) -> None:
        """Queue an error signal on the bridge thread.

        Args:
            payload: Error traceback or message.
        """
        self._dispatch_error.emit(payload)

    def post_finished(self) -> None:
        """Queue a finished signal on the bridge thread."""
        self._dispatch_finished.emit()


# =============================================================================
# Worker for dedicated QThread jobs
# =============================================================================


class Worker(QObject):
    """Execute a callable inside a dedicated QThread.

    Signals:
        started: Emitted when execution begins.
        progress(int): Emitted on progress updates in the range 0..100.
        result(object): Emitted with the callable result on success.
        error(str): Emitted with a formatted traceback on failure.
        finished: Always emitted once execution completes.

    Supported injected runtime context:
        - progress_cb: Callable[[int], None]
        - cancel_cb: Callable[[], bool]
        - job_id: str
        - job_scope: str | None
        - corr_id: str | None

    Injection only occurs when the callable explicitly supports the parameter
    or accepts arbitrary keyword arguments via **kwargs.
    """

    started = pyqtSignal()
    progress = pyqtSignal(int)
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    # Internal signals for dispatching from the worker thread
    _dispatch_started = pyqtSignal()
    _dispatch_progress = pyqtSignal(int)
    _dispatch_result = pyqtSignal(object)
    _dispatch_error = pyqtSignal(str)
    _dispatch_finished = pyqtSignal()

    def __init__(
        self,
        fn: Callable[..., object],
        *args: object,
        job_id: str,
        job_scope: str | None,
        corr_id: str | None,
        logger: logging.Logger | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize the Worker.

        Args:
            fn: Callable to execute.
            *args: Positional arguments passed to the callable.
            job_id: Unique job identifier.
            job_scope: Optional job scope.
            corr_id: Optional correlation identifier.
            logger: Optional logger instance.
            **kwargs: Keyword arguments passed to the callable.
        """
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = dict(kwargs)

        self._job_id = job_id
        self._job_scope = job_scope
        self._corr_id = corr_id

        self._logger = logger if logger is not None else logging.getLogger("applogger.jobs")
        self._cancel_func: Callable[[], bool] | None = None

        # Reference to self for safe cleanup on finalization
        self._keep_alive: Worker | None = self

        # Connect internal dispatch signals to the public signals with queued connections to ensure thread-safe.
        _connect_queued(self._dispatch_started, self.started.emit)
        _connect_queued(self._dispatch_progress, self.progress.emit)
        _connect_queued(self._dispatch_result, self.result.emit)
        _connect_queued(self._dispatch_error, self.error.emit)

        # When the worker is finished, emit the final finished signal.
        _connect_queued(self._dispatch_finished, self._handle_final_cleanup)

    def _handle_final_cleanup(self) -> None:
        """Safely emit finished and release self-ownership."""
        self.finished.emit()
        self._keep_alive = None  # Nu får objektet raderas av Garbage Collector

    @property
    def job_id(self) -> str:
        """Return the worker job id."""
        return self._job_id

    @property
    def cancel_func(self) -> Callable[[], bool] | None:
        """Return the cooperative cancellation callback."""
        return self._cancel_func

    @cancel_func.setter
    def cancel_func(self, callback: Callable[[], bool] | None) -> None:
        """Set the cooperative cancellation callback."""
        self._cancel_func = callback

    def _emit_progress(self, value: int) -> None:
        """Clamp and emit a progress value.

        Args:
            value: Progress value to emit.
        """
        try:
            clamped = max(0, min(100, int(value)))
            self._dispatch_progress.emit(clamped)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            # Never allow progress reporting to crash job execution.
            self._logger.debug(
                "Worker: failed to emit progress (job_id=%s, corr=%s).",
                self._job_id,
                self._corr_id,
                exc_info=True,
            )

    def run(self) -> None:
        """Execute the configured callable inside the worker thread."""
        self.started.emit()

        try:
            call_kwargs = _build_injected_call_kwargs(
                fn=self._fn,
                base_kwargs=self._kwargs,
                progress_cb=self._emit_progress,
                cancel_cb=self._cancel_func,
                job_id=self._job_id,
                job_scope=self._job_scope,
                corr_id=self._corr_id,
            )

            result = self._fn(*self._args, **call_kwargs)
            self._dispatch_result.emit(result)

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            tb = traceback.format_exc()
            self._logger.exception(
                "Worker: callable raised (job_id=%s, scope=%s, corr=%s): %s",
                self._job_id,
                self._job_scope,
                self._corr_id,
                tb,
            )
            self._dispatch_error.emit(tb)

        finally:
            self._dispatch_finished.emit()


# =============================================================================
# Thread helper
# =============================================================================


def run_in_thread(
    fn: Callable[..., object],
    *args: object,
    job_id: str,
    job_scope: str | None,
    corr_id: str | None,
    logger: logging.Logger | None = None,
    **kwargs: object,
) -> tuple[QThread, Worker]:
    """Create and wire a QThread + Worker pair.

    Args:
        fn: Callable to execute.
        *args: Positional arguments passed to the callable.
        job_id: Unique job identifier.
        job_scope: Optional job scope.
        corr_id: Optional correlation identifier.
        logger: Optional logger instance.
        **kwargs: Keyword arguments passed to the callable.

    Returns:
        A tuple containing the created thread and worker.
    """
    thread = QThread()
    worker = Worker(
        fn,
        *args,
        job_id=job_id,
        job_scope=job_scope,
        corr_id=corr_id,
        logger=logger,
        **kwargs,
    )
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    _connect_queued(worker.finished, worker.deleteLater)
    _connect_queued(thread.finished, thread.deleteLater)

    return thread, worker


# =============================================================================
# Internal helpers
# =============================================================================


def _build_injected_call_kwargs(
    *,
    fn: Callable[..., object],
    base_kwargs: dict[str, object],
    progress_cb: Callable[[int], None] | None,
    cancel_cb: Callable[[], bool] | None,
    job_id: str,
    job_scope: str | None,
    corr_id: str | None,
) -> dict[str, object]:
    """Build callable kwargs with supported runtime context injected.

    Injection is conservative:
        - Existing caller-provided kwargs are never overwritten.
        - Context is only injected if explicitly supported by signature or
          if the callable accepts arbitrary keyword arguments via **kwargs.

    Args:
        fn: Target callable.
        base_kwargs: Caller-provided keyword arguments.
        progress_cb: Progress callback to inject when supported.
        cancel_cb: Cooperative cancel callback to inject when supported.
        job_id: Unique job id.
        job_scope: Optional job scope.
        corr_id: Optional correlation id.

    Returns:
        A new kwargs dictionary to use when invoking the callable.
    """
    call_kwargs = dict(base_kwargs)

    try:
        signature = inspect.signature(fn)
        parameters: Mapping[str, inspect.Parameter] = signature.parameters
        accepts_var_kwargs = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    except (TypeError, ValueError):
        parameters = {}
        accepts_var_kwargs = False

    def supports(name: str) -> bool:
        return name in parameters or accepts_var_kwargs

    if "progress_cb" not in call_kwargs and callable(progress_cb) and supports("progress_cb"):
        call_kwargs["progress_cb"] = progress_cb

    if "cancel_cb" not in call_kwargs and callable(cancel_cb) and supports("cancel_cb"):
        call_kwargs["cancel_cb"] = cancel_cb

    if "job_id" not in call_kwargs and supports("job_id"):
        call_kwargs["job_id"] = job_id

    if "job_scope" not in call_kwargs and supports("job_scope"):
        call_kwargs["job_scope"] = job_scope

    if "corr_id" not in call_kwargs and supports("corr_id"):
        call_kwargs["corr_id"] = corr_id

    return call_kwargs


# =============================================================================
# JobManager
# =============================================================================


class JobManager:
    """UI-agnostic job manager for threaded background tasks.

    This class is intentionally limited to execution infrastructure and job
    lifecycle bookkeeping. It does not manipulate UI state.

    Public API:
        - run(): execute a callable in a dedicated QThread.
        - run_pool(): execute a callable on a shared ThreadPoolExecutor.
        - cancel_job(): request cooperative cancellation for a specific job.
        - cancel_scope(): request cancellation for all jobs in a given scope.
        - cancel_all(): request cancellation for all tracked jobs.
        - abort_all(): best-effort hard stop for all jobs and the thread pool.
        - shutdown(): shut down the internal thread pool.

    Returned job handles:
        - Worker for dedicated thread jobs.
        - _FutureBridge for pool jobs.
    """

    __slots__ = (
        "__weakref__",
        "_cancel_flags",
        "_jobs",
        "_logger",
        "_meta",
        "_pool",
    )

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize the JobManager.

        Args:
            logger: Optional logger instance.
        """
        self._logger = logger if logger is not None else logging.getLogger("applogger.jobs")

        self._pool: ThreadPoolExecutor | None = None
        self._jobs: dict[str, tuple[QThread | None, QObject]] = {}
        self._meta: dict[str, JobMetadata] = {}
        self._cancel_flags: dict[str, bool] = {}

    # -------------------------------------------------------------------------
    # Public properties
    # -------------------------------------------------------------------------

    @property
    def active_jobs(self) -> int:
        """Return the number of tracked active jobs."""
        return len(self._jobs)

    @property
    def active_job_ids(self) -> tuple[str, ...]:
        """Return active job ids as an immutable tuple."""
        return tuple(self._jobs.keys())

    # -------------------------------------------------------------------------
    # Public helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def get_job_id(obj: QObject | None) -> str | None:
        """Return the job id for a Worker or _FutureBridge instance.

        Args:
            obj: Worker, _FutureBridge, or similar QObject.

        Returns:
            The associated job id, or None if unavailable.
        """
        if obj is None:
            return None

        try:
            job_id = getattr(obj, "job_id", None)
            if isinstance(job_id, str) and job_id:
                return job_id
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            pass

        try:
            raw_job_id = getattr(obj, "_job_id", None)
            if isinstance(raw_job_id, str) and raw_job_id:
                return raw_job_id
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            pass

        return None

    def get_metadata(self, job_id: str) -> JobMetadata | None:
        """Return metadata for a tracked job.

        Args:
            job_id: Job identifier.

        Returns:
            JobMetadata if present, otherwise None.
        """
        if not job_id:
            return None
        return self._meta.get(job_id)

    # -------------------------------------------------------------------------
    # Job launch API
    # -------------------------------------------------------------------------

    def run(
        self,
        fn: Callable[..., object],
        *args: object,
        scope: str | None = None,
        corr_id: str | None = None,
        **kwargs: object,
    ) -> Worker:
        """Launch a callable in a dedicated QThread.

        Args:
            fn: Callable to execute.
            *args: Positional arguments passed to the callable.
            scope: Optional job scope string.
            corr_id: Optional correlation identifier.
            **kwargs: Keyword arguments passed to the callable.

        Returns:
            The created Worker instance.

        Raises:
            TypeError: If fn is not callable.
        """
        if not callable(fn):
            msg = "fn must be callable"
            raise TypeError(msg)

        job_id = uuid.uuid4().hex
        self._register_job(
            job_id=job_id,
            runner="thread",
            scope=scope,
            corr_id=corr_id,
        )
        self._cancel_flags[job_id] = False

        thread, worker = run_in_thread(
            fn,
            *args,
            job_id=job_id,
            job_scope=scope,
            corr_id=corr_id,
            logger=self._logger,
            **kwargs,
        )
        worker.cancel_func = partial(self.is_cancelled, job_id)

        with contextlib.suppress(Exception):
            thread.setObjectName(f"job-{job_id}")

        self._jobs[job_id] = (thread, worker)
        self._connect_job_lifecycle_signals(job_id=job_id, job=worker)

        try:
            _connect_queued(
                thread.finished,
                partial(self._finalize_job, job_id),
            )
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.debug(
                "JobManager: failed to connect thread.finished finalizer (job_id=%s).",
                job_id,
                exc_info=True,
            )

        self._logger.info(
            "JobManager: thread job created (job_id=%s, scope=%s, corr=%s)",
            job_id,
            scope,
            corr_id,
        )

        thread.start()
        return worker

    def run_pool(
        self,
        fn: Callable[..., object],
        *args: object,
        scope: str | None = None,
        corr_id: str | None = None,
        **kwargs: object,
    ) -> _FutureBridge:
        """Launch a callable on a shared ThreadPoolExecutor.

        Args:
            fn: Callable to execute.
            *args: Positional arguments passed to the callable.
            scope: Optional job scope string.
            corr_id: Optional correlation identifier.
            **kwargs: Keyword arguments passed to the callable.

        Returns:
            A signal bridge exposing the same Qt signal contract as Worker.

        Raises:
            TypeError: If fn is not callable.
        """
        if not callable(fn):
            msg = "fn must be callable"
            raise TypeError(msg)

        job_id = uuid.uuid4().hex
        self._register_job(
            job_id=job_id,
            runner="pool",
            scope=scope,
            corr_id=corr_id,
        )
        self._cancel_flags[job_id] = False

        bridge = _FutureBridge(job_id)
        self._jobs[job_id] = (None, bridge)
        self._connect_job_lifecycle_signals(job_id=job_id, job=bridge)

        try:
            _connect_queued(
                bridge.finished,
                partial(self._finalize_job, job_id),
            )
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.debug(
                "JobManager: failed to connect pool finished finalizer (job_id=%s).",
                job_id,
                exc_info=True,
            )

        self._logger.info(
            "JobManager: pool job created (job_id=%s, scope=%s, corr=%s)",
            job_id,
            scope,
            corr_id,
        )

        def _post_pool_progress(value: int) -> None:
            bridge.post_progress(int(value))

        def _is_pool_cancelled() -> bool:
            return self.is_cancelled(job_id)

        def wrapped() -> tuple[str, object]:
            try:
                call_kwargs = _build_injected_call_kwargs(
                    fn=fn,
                    base_kwargs=dict(kwargs),
                    progress_cb=_post_pool_progress,
                    cancel_cb=_is_pool_cancelled,
                    job_id=job_id,
                    job_scope=scope,
                    corr_id=corr_id,
                )
                result = fn(*args, **call_kwargs)
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                return "err", traceback.format_exc()
            else:
                return "ok", result

        # Queue started instead of emitting directly. This keeps signal delivery
        # consistent with the rest of the pool bridge and avoids races for any
        # external started listeners.
        bridge.post_started()

        pool = self._ensure_pool()
        future: Future[tuple[str, object]] = pool.submit(wrapped)

        def on_done(done_future: Future[tuple[str, object]]) -> None:
            try:
                tag, payload = done_future.result()
                if tag == "ok":
                    bridge.post_result(payload)
                else:
                    bridge.post_error(str(payload))
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                bridge.post_error(traceback.format_exc())
            finally:
                bridge.post_finished()

        future.add_done_callback(on_done)
        return bridge

    # -------------------------------------------------------------------------
    # Cancellation API
    # -------------------------------------------------------------------------

    def cancel_job(self, job_id: str) -> bool:
        """Request cooperative cancellation for a specific job.

        Args:
            job_id: Job identifier.

        Returns:
            True if the job was tracked and the cancellation flag was set,
            otherwise False.
        """
        if not job_id or job_id not in self._cancel_flags:
            return False

        self._cancel_flags[job_id] = True
        meta = self._meta.get(job_id)

        self._logger.info(
            "JobManager: cancellation requested (job_id=%s, scope=%s, corr=%s)",
            job_id,
            meta.scope if meta is not None else None,
            meta.corr_id if meta is not None else None,
        )
        return True

    def cancel_scope(self, scope: str) -> int:
        """Request cooperative cancellation for all jobs in a scope.

        Args:
            scope: Scope string to match exactly.

        Returns:
            Number of jobs for which cancellation was requested.
        """
        if not scope:
            return 0

        cancelled = 0
        for job_id, meta in list(self._meta.items()):
            if meta.scope == scope and self.cancel_job(job_id):
                cancelled += 1

        self._logger.info(
            "JobManager: scope cancellation requested (scope=%s, count=%s)",
            scope,
            cancelled,
        )
        return cancelled

    def is_cancelled(self, job_id: str) -> bool:
        """Return True if the given job was requested to cancel.

        Args:
            job_id: Job identifier.

        Returns:
            True if cancelled, otherwise False.
        """
        return self._cancel_flags.get(job_id, False) is True

    def cancel_all(self) -> int:
        """Request cooperative cancellation for all tracked jobs.

        Returns:
            Number of jobs flagged for cancellation.
        """
        count = 0
        for job_id in list(self._cancel_flags.keys()):
            self._cancel_flags[job_id] = True
            count += 1

        self._logger.warning("JobManager: cancellation requested for all jobs (count=%s)", count)
        return count

    def abort_all(self, wait_ms: int = 1500) -> list[str]:
        """Request cancellation for all jobs and attempt to stop thread jobs.

        This method is intended for shutdown/teardown scenarios. It does not clear
        tracked thread jobs eagerly; active thread jobs are left to finalize through
        the normal lifecycle path.

        Args:
            wait_ms: Maximum time to wait per tracked QThread job.

        Returns:
            A list of job ids that were still running after the wait timeout.
        """
        if not self._jobs and self._pool is None:
            self._logger.debug("JobManager: abort_all ignored; no active jobs.")
            return []

        self._logger.warning("JobManager: ABORT ALL REQUESTED")
        self.cancel_all()

        still_running: list[str] = []

        for job_id, (thread, _obj) in list(self._jobs.items()):
            if thread is None:
                continue

            meta = self._meta.get(job_id)

            try:
                thread.requestInterruption()
                thread.quit()

                stopped = thread.wait(wait_ms)
                if not stopped:
                    still_running.append(job_id)
                    self._logger.error(
                        "JobManager: thread job still running after abort wait "
                        "(job_id=%s, scope=%s, corr=%s, wait_ms=%s)",
                        job_id,
                        meta.scope if meta is not None else None,
                        meta.corr_id if meta is not None else None,
                        wait_ms,
                    )
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug(
                    "JobManager: failed to stop thread job during abort (job_id=%s).",
                    job_id,
                    exc_info=True,
                )

        if self._pool is not None:
            try:
                self._pool.shutdown(wait=False, cancel_futures=True)
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug(
                    "JobManager: pool shutdown failed during abort.",
                    exc_info=True,
                )
            finally:
                self._pool = None

        # IMPORTANT:
        # Do not clear self._jobs / self._meta / self._cancel_flags here for
        # thread-based jobs. Let _finalize_job() remove them when they actually stop.
        return still_running

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the internal thread pool.

        Args:
            wait: Whether to wait for submitted futures to finish.
        """
        if self._pool is None:
            return

        try:
            self._pool.shutdown(wait=wait, cancel_futures=True)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.debug("JobManager: pool shutdown failed.", exc_info=True)
        finally:
            self._pool = None

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _ensure_pool(self) -> ThreadPoolExecutor:
        """Return the shared thread pool, creating it if needed."""
        pool = self._pool
        if pool is None:
            pool = ThreadPoolExecutor(
                max_workers=4,
                thread_name_prefix="expo-pool",
            )
            self._pool = pool
            self._logger.info(
                "JobManager: created ThreadPoolExecutor (max_workers=%s, prefix=%s)",
                4,
                "expo-pool",
            )
        return pool

    def _register_job(
        self,
        *,
        job_id: str,
        runner: RunnerKind,
        scope: str | None,
        corr_id: str | None,
    ) -> None:
        """Register job metadata before execution begins.

        Args:
            job_id: Unique job identifier.
            runner: Selected execution backend.
            scope: Optional job scope.
            corr_id: Optional correlation identifier.
        """
        self._meta[job_id] = JobMetadata(
            job_id=job_id,
            runner=runner,
            scope=scope,
            corr_id=corr_id,
            created_monotonic=time.perf_counter(),
        )

    def _connect_job_lifecycle_signals(self, *, job_id: str, job: QObject) -> None:
        """Connect lifecycle signals for internal logging and bookkeeping.

        Args:
            job_id: Associated job id.
            job: Worker or _FutureBridge instance.
        """
        started_signal = getattr(job, "started", None)
        error_signal = getattr(job, "error", None)
        finished_signal = getattr(job, "finished", None)

        if started_signal is not None:
            try:
                _connect_queued(
                    started_signal,
                    partial(self._on_job_started, job_id),
                )
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug(
                    "JobManager: failed to connect started logger (job_id=%s).",
                    job_id,
                    exc_info=True,
                )

        if error_signal is not None:
            try:
                _connect_queued(
                    error_signal,
                    partial(self._on_job_error, job_id),
                )
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug(
                    "JobManager: failed to connect error logger (job_id=%s).",
                    job_id,
                    exc_info=True,
                )

        if finished_signal is not None:
            try:
                _connect_queued(
                    finished_signal,
                    partial(self._on_job_finished, job_id),
                )
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug(
                    "JobManager: failed to connect finished logger (job_id=%s).",
                    job_id,
                    exc_info=True,
                )

    def _on_job_started(self, job_id: str) -> None:
        """Log job start once the job becomes active.

        Args:
            job_id: Job identifier.
        """
        meta = self._meta.get(job_id)
        if meta is None:
            return

        self._logger.info(
            "JobManager: job started (job_id=%s, runner=%s, scope=%s, corr=%s)",
            meta.job_id,
            meta.runner,
            meta.scope,
            meta.corr_id,
        )

    def _on_job_error(self, job_id: str, tb: str) -> None:
        """Log job failure at the manager level.

        Args:
            job_id: Job identifier.
            tb: Formatted traceback string.
        """
        meta = self._meta.get(job_id)
        if meta is None:
            return

        self._logger.error(
            "JobManager: job error signaled (job_id=%s, scope=%s, corr=%s)\n%s",
            meta.job_id,
            meta.scope,
            meta.corr_id,
            tb,
        )

    def _on_job_finished(self, job_id: str) -> None:
        """Log when a job signals finished.

        Final cleanup is performed separately through _finalize_job() to ensure
        dedicated-thread jobs are not removed before the QThread has actually
        stopped.

        Args:
            job_id: Job identifier.
        """
        meta = self._meta.get(job_id)
        if meta is None:
            return

        self._logger.debug(
            "JobManager: job finished signal received (job_id=%s, scope=%s, corr=%s)",
            meta.job_id,
            meta.scope,
            meta.corr_id,
        )

    def _finalize_job(self, job_id: str) -> None:
        """Perform idempotent final cleanup for a finished job.

        Args:
            job_id: Job identifier.
        """
        job_tuple = self._jobs.pop(job_id, None)
        meta = self._meta.pop(job_id, None)
        self._cancel_flags.pop(job_id, None)

        # If metadata is already gone, finalization has already occurred.
        if meta is None:
            return

        elapsed_ms = (time.perf_counter() - meta.created_monotonic) * 1000.0

        if job_tuple is None:
            self._logger.debug(
                "JobManager: finalize called for unknown job (job_id=%s, scope=%s, corr=%s)",
                meta.job_id,
                meta.scope,
                meta.corr_id,
            )
            return

        self._logger.info(
            "JobManager: job finalized (job_id=%s, runner=%s, scope=%s, ms=%.1f, corr=%s)",
            meta.job_id,
            meta.runner,
            meta.scope,
            elapsed_ms,
            meta.corr_id,
        )
