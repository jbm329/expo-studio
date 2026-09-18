"""Cache for column profiles to speed up repeated accesses.

This module provides the ColumnProfileCache class, which uses an LRU-based approach
to store and manage column profile results.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from expo_jbm329.services.data_profile.column_data_profile import ColumnProfile


class ColumnProfileCache:
    """LRU-based cache for storing column profiles.

    Attributes:
        _capacity: The maximum number of profiles to cache.
        _store: An OrderedDict mapping (tab_id, column_name) tuples to ColumnProfile.
    """

    def __init__(self, capacity: int = 128) -> None:
        """Initialize the ColumnProfileCache.

        Args:
            capacity: The maximum number of entries to store.
        """
        self._capacity = capacity
        self._store: OrderedDict[tuple[str, str], ColumnProfile] = OrderedDict()

    def get(self, key: tuple[str, str]) -> ColumnProfile | None:
        """Retrieve a cached column profile.

        Args:
            key: A tuple of (tab_id, column_name).

        Returns:
            The cached ColumnProfile, or None if not found.
        """
        v = self._store.get(key)
        if v is not None:
            self._store.move_to_end(key)
        return v

    def set(self, key: tuple[str, str], value: ColumnProfile):
        """Store a column profile in the cache.

        Args:
            key: A tuple of (tab_id, column_name).
            value: The ColumnProfile to cache.
        """
        self._store[key] = value
        self._store.move_to_end(key)
        if len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def invalidate_tab(self, tab_id: str):
        """Remove all cached profiles associated with a given tab.

        Args:
            tab_id: The identifier of the tab to invalidate.
        """
        for k in [k for k in self._store if k[0] == tab_id]:
            self._store.pop(k, None)

    def clear(self):
        """Remove all entries from the cache."""
        self._store.clear()
