"""Manage per-tab undo stacks for result tabs."""
from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Callable


class ResultTabUndoManager:
    """Manage per-tab undo stacks for result tabs.

    This service is intentionally UI-agnostic. It owns undo stacks and related
    limits, but it does not show dialogs or know anything about widgets.

    The host controller is responsible for:
        - deciding which tab is active
        - showing user-facing messages
        - applying restored DataFrames to views

    Attributes:
        _stacks: Mapping of tab_id -> list of DataFrame snapshots.
        _undo_limit_per_tab: Maximum number of snapshots to keep per tab.
        _max_size_allow_undo_mb: Maximum DataFrame size (in MB) allowed for undo.
    """

    __slots__ = (
        "_logger",
        "_max_size_allow_undo_mb",
        "_max_size_allow_undo_mb_default",
        "_on_state_changed",
        "_stacks",
        "_undo_limit_per_tab",
        "_undo_limit_per_tab_default",
    )

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        on_state_changed: Callable[[], None] | None = None,
        undo_limit_per_tab: int = 20,
        max_size_allow_undo_mb: int = 100,
    ) -> None:
        """Initialize the undo manager.

        Args:
            logger: Optional logger instance.
            on_state_changed: Optional callback fired when undo availability may
                have changed.
            undo_limit_per_tab: Default maximum snapshots per tab.
            max_size_allow_undo_mb: Default max DataFrame snapshot size in MB.
        """
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._stacks: dict[str, list[pd.DataFrame]] = {}
        self._undo_limit_per_tab_default = max(0, int(undo_limit_per_tab))
        self._undo_limit_per_tab = self._undo_limit_per_tab_default
        self._max_size_allow_undo_mb_default = max(0, int(max_size_allow_undo_mb))
        self._max_size_allow_undo_mb = self._max_size_allow_undo_mb_default
        self._on_state_changed = on_state_changed

    # ==================================================================
    # Public API
    # ==================================================================

    def register_tab(self, tab_id: str) -> None:
        """Ensure an undo stack exists for a tab.

        Args:
            tab_id: Stable tab identifier.
        """
        if not isinstance(tab_id, str) or not tab_id:
            return

        self._stacks.setdefault(tab_id, [])
        self._notify_state_changed()

    def unregister_tab(self, tab_id: str) -> None:
        """Remove all undo state for a tab.

        Args:
            tab_id: Stable tab identifier.
        """
        if not isinstance(tab_id, str) or not tab_id:
            return

        self._stacks.pop(tab_id, None)
        self._notify_state_changed()

    def clear(self) -> None:
        """Remove all undo state for all tabs."""
        self._stacks.clear()
        self._notify_state_changed()

    def reset_tab(self, tab_id: str) -> None:
        """Clear undo history for a specific tab."""
        if not isinstance(tab_id, str) or not tab_id:
            return
        self._stacks[tab_id] = []
        self._notify_state_changed()

    def has_undo(self, tab_id: str | None) -> bool:
        """Return whether the given tab currently has undo snapshots.

        Args:
            tab_id: Stable tab identifier.

        Returns:
            True if at least one snapshot exists, otherwise False.
        """
        if not isinstance(tab_id, str) or not tab_id:
            return False
        return bool(self._stacks.get(tab_id))

    def stack_size(self, tab_id: str | None) -> int:
        """Return snapshot count for a tab.

        Args:
            tab_id: Stable tab identifier.

        Returns:
            Number of snapshots currently stored for the tab.
        """
        if not isinstance(tab_id, str) or not tab_id:
            return 0
        stack = self._stacks.get(tab_id)
        return len(stack) if isinstance(stack, list) else 0

    def push_snapshot(self, tab_id: str, df: pd.DataFrame) -> bool:
        """Push a deep copy snapshot for a tab if allowed by current limits.

        Args:
            tab_id: Stable tab identifier.
            df: DataFrame to snapshot.

        Returns:
            True if a snapshot was stored, otherwise False.
        """
        if not isinstance(tab_id, str) or not tab_id:
            return False

        if not isinstance(df, pd.DataFrame):
            return False

        if not self._allow_snapshot(df):
            self._logger.debug(
                "ResultTabUndoManager: snapshot skipped for tab=%s due to size limit.",
                tab_id,
            )
            return False

        try:
            snapshot = df.copy(deep=True)
        except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
            self._logger.debug(
                "ResultTabUndoManager: failed to copy snapshot for tab=%s.",
                tab_id,
                exc_info=True,
            )
            return False

        stack = self._stacks.setdefault(tab_id, [])
        stack.append(snapshot)
        self._trim_stack(tab_id)
        self._notify_state_changed()

        self._logger.debug(
            "ResultTabUndoManager: snapshot pushed for tab=%s (stack_size=%s).",
            tab_id,
            len(stack),
        )
        return True

    def pop_snapshot(self, tab_id: str) -> pd.DataFrame | None:
        """Pop and return the latest undo snapshot for a tab.

        Args:
            tab_id: Stable tab identifier.

        Returns:
            The previous DataFrame snapshot, or None if no snapshot exists.
        """
        if not isinstance(tab_id, str) or not tab_id:
            return None

        stack = self._stacks.get(tab_id)
        if not stack:
            return None

        snapshot = stack.pop()
        self._notify_state_changed()

        self._logger.debug(
            "ResultTabUndoManager: snapshot popped for tab=%s (stack_size=%s).",
            tab_id,
            len(stack),
        )
        return snapshot

    def reload_settings(self, settings: dict) -> None:
        """Reload undo-related settings from the global settings structure.

        Expected structure:
            {
                "workbench": {
                    "undo_limit_per_tab": int,
                    "max_size_allow_undo_mb": int,
                }
            }

        Args:
            settings: Application settings dictionary.
        """
        try:
            workbench = settings.get("workbench", {}) or {}

            undo_limit_per_tab = int(
                workbench.get(
                    "undo_limit_per_tab",
                    self._undo_limit_per_tab_default,
                )
            )
            max_size_allow_undo_mb = int(
                workbench.get(
                    "max_size_allow_undo_mb",
                    self._max_size_allow_undo_mb_default,
                )
            )

            self.set_limits(
                undo_limit_per_tab=undo_limit_per_tab,
                max_size_allow_undo_mb=max_size_allow_undo_mb,
            )

            self._logger.info(
                "ResultTabUndoManager: settings reloaded "
                "(undo_limit=%s, max_undo_mb=%s).",
                self._undo_limit_per_tab,
                self._max_size_allow_undo_mb,
            )

        except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            self._logger.error(
                "ResultTabUndoManager: failed to reload settings %s",
                exc,
            )

    def set_limits(
        self,
        *,
        undo_limit_per_tab: int,
        max_size_allow_undo_mb: int,
    ) -> None:
        """Set undo retention limits and trim existing stacks if needed.

        Args:
            undo_limit_per_tab: Max number of snapshots per tab.
            max_size_allow_undo_mb: Max snapshot size in MB.
        """
        self._undo_limit_per_tab = max(0, int(undo_limit_per_tab))
        self._max_size_allow_undo_mb = max(0, int(max_size_allow_undo_mb))
        self._trim_all()
        self._notify_state_changed()

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _trim_all(self) -> None:
        """Trim all stacks to satisfy the current per-tab limit."""
        for tab_id in list(self._stacks.keys()):
            self._trim_stack(tab_id)

    def _trim_stack(self, tab_id: str) -> None:
        """Trim one stack to satisfy the current per-tab limit.

        Args:
            tab_id: Stable tab identifier.
        """
        stack = self._stacks.get(tab_id)
        if not isinstance(stack, list):
            return

        while len(stack) > self._undo_limit_per_tab:
            stack.pop(0)

    def _allow_snapshot(self, df: pd.DataFrame) -> bool:
        """Return whether the DataFrame may be stored as an undo snapshot.

        Args:
            df: DataFrame to evaluate.

        Returns:
            True if size is within configured limit, otherwise False.
        """
        size_bytes = self._estimate_df_size_bytes(df)
        limit_bytes = self._max_size_allow_undo_mb * 1024 * 1024
        return size_bytes < limit_bytes

    @staticmethod
    def _estimate_df_size_bytes(df: pd.DataFrame) -> int:
        """Estimate the memory footprint of a DataFrame in bytes.

        Args:
            df: DataFrame to estimate.

        Returns:
            Approximate number of bytes, or 0 on failure.
        """
        try:
            return int(df.memory_usage(deep=True).sum())
        except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
            return 0

    def _notify_state_changed(self) -> None:
        """Notify host that undo state may have changed."""
        cb = self._on_state_changed
        if callable(cb):
            with contextlib.suppress(Exception):
                cb()
