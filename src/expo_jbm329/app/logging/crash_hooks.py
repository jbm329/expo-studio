"""Log unhandled exceptions before the process terminates.

In windowed builds stderr is unavailable, and PyQt6 aborts the process when an
exception escapes a Python override called from Qt (for example ``QThread.run``
or a slot). Without these hooks such crashes leave no trace in the log files.
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from types import TracebackType


def install_crash_hooks(logger: logging.Logger) -> None:
    """Log unhandled exceptions from the main thread and from Python threads.

    The previously installed hooks are still called afterwards, so default
    behavior (such as PyQt6 terminating the process) is preserved.

    Args:
        logger: Logger that receives the unhandled exceptions.
    """
    previous_excepthook = sys.excepthook
    previous_threading_excepthook = threading.excepthook

    def log_unhandled_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if not issubclass(exc_type, KeyboardInterrupt):
            logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        previous_excepthook(exc_type, exc_value, exc_traceback)

    def log_unhandled_thread_exception(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None and not issubclass(args.exc_type, KeyboardInterrupt):
            thread_name = args.thread.name if args.thread is not None else "unknown"
            logger.critical(
                "Unhandled exception in thread %s",
                thread_name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        previous_threading_excepthook(args)

    sys.excepthook = log_unhandled_exception
    threading.excepthook = log_unhandled_thread_exception
