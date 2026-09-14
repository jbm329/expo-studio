"""Editor tab management for SQL editors.

This module provides EditorTab and EditorTabManager, which together manage
the lifecycle, state, and connection binding of SQL editor tabs.
The manager is intentionally UI-agnostic and does not depend on Qt widgets.
It acts as the single source of truth for which SQL tabs exist, which one is
active, and which database connection (if any) each tab is bound to.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.utils.i18n_utils import tr, tr_fmt


class EditorTabState(Enum):
    """Lifecycle state of an editor tab."""
    UNBOUND = auto()
    DISCONNECTED = auto()
    BOUND = auto()


@dataclass(slots=True)
class EditorTab:
    """Represents a single SQL editor tab.

    This is a pure data model with no UI dependencies.

    Attributes:
        tab_id: Unique identifier for the tab.
        base_title: Human-readable tab title without connection or state suffix.
        sql_text: Current SQL text stored for the tab.
        connection_name: Name of the bound database connection, if any.
        state: Current lifecycle state of the tab.
        last_used_connection: Optional hint for reconnecting or rebinding.
        file_path: Path to the associated file, if any.
        is_dirty: Flag indicating if the tab has unsaved changes.
    """
    tab_id: str
    base_title: str
    sql_text: str = ""
    connection_name: str | None = None
    state: EditorTabState = EditorTabState.UNBOUND
    last_used_connection: str | None = None
    file_path: str | None = None
    is_dirty: bool = False


class EditorTabManager:
    """Manage SQL editor tabs and their connection bindings.

    This class owns all editor tab state and provides a clean API for
    creating, activating, binding, disabling, and querying editor tabs.

    It deliberately does NOT:
      - interact with UI widgets
      - execute SQL
      - manage result tabs
      - show dialogs or status messages
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_QUERY_BASE_NAME = QT_TR_NOOP("Query")
    TR_NO_CONNECTION = QT_TR_NOOP("no connection")
    TR_DISCONNECTED = QT_TR_NOOP("disconnected")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("EditorTabManager", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("EditorTabManager", text, **kwargs)

    __slots__ = (
        "_active_tab_id",
        "_logger",
        "_query_counter",
        "_tabs",
    )

    def __init__(self, logger: logging.Logger | None = None,) -> None:
        """Initialize an empty EditorTabManager."""
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._tabs: dict[str, EditorTab] = {}
        self._active_tab_id: str | None = None
        self._query_counter: int = 0

    # ==================================================================
    # Tab creation & lifecycle
    # ==================================================================

    def create_tab(
        self,
        *,
        connection_name: str | None = None,
        base_title: str | None = None,
    ) -> EditorTab:
        """Create a new editor tab.

        Args:
            connection_name: Optional database connection to bind immediately.
            base_title: Optional base title for the tab. If not provided, a default title will be generated.

        Returns:
            The created EditorTab instance.
        """
        tab_id = uuid.uuid4().hex

        if base_title:
            title = base_title
        else:
            self._query_counter += 1
            title = f"{self._tr(self.TR_QUERY_BASE_NAME)} {self._query_counter}"

        state = (
            EditorTabState.BOUND
            if connection_name
            else EditorTabState.UNBOUND
        )

        tab = EditorTab(
            tab_id=tab_id,
            base_title=title,
            connection_name=connection_name,
            state=state,
            last_used_connection=connection_name,
        )

        self._logger.info(
            "EditorTabManager: tab created (tab_id=%s, connection=%s)",
            tab.tab_id,
            tab.connection_name,
        )

        self._tabs[tab_id] = tab
        self._active_tab_id = tab_id
        return tab

    def close_tab(self, tab_id: str) -> bool:
        """Close an editor tab.

        Args:
            tab_id: Identifier of the tab to close.

        Returns:
            True if the tab was closed, False if it did not exist.
        """
        if tab_id not in self._tabs:
            return False

        del self._tabs[tab_id]

        if self._active_tab_id == tab_id:
            self._active_tab_id = next(iter(self._tabs), None)

        self._logger.info(
            "EditorTabManager: tab closed (tab_id=%s)",
            tab_id,
        )

        return True

    def build_tab_title(self, tab: EditorTab) -> str:
        """Build a user-facing title for an editor tab.

        The title follows the consistent format:

            <base_name>  [<connection_name>] (optional state)

        Examples:
            Query 1  [prod-db]
            customers.sql  [test-db]
            customers.sql  [no connection]
            customers.sql  [prod-db] (disconnected)

        Args:
            tab: The editor tab to build the title for.

        Returns:
            A localized, human-readable tab title string.
        """
        # --------------------------------------------------------------
        # Base name (query or file name)
        # --------------------------------------------------------------
        base_name = tab.base_title.strip() or self._tr(self.TR_QUERY_BASE_NAME)

        if tab.is_dirty:
            base_name = f"{base_name}*"

        # --------------------------------------------------------------
        # Connection context
        # --------------------------------------------------------------
        conn_part = tab.connection_name or self._tr(self.TR_NO_CONNECTION)
        title = f"{base_name}  [{conn_part}]"

        # --------------------------------------------------------------
        # State suffix
        # --------------------------------------------------------------
        if tab.state == EditorTabState.DISCONNECTED:
            state_txt = self._tr(self.TR_DISCONNECTED)
            title = f"{title} ({state_txt})"

        return title

    def rename_tab(self, tab_id: str, new_base_title: str) -> None:
        """Rename an editor tab by updating its base title.

        This updates only the logical tab name (base_title) and does not:
          - change file_path
          - mark the tab dirty
          - affect connection binding

        Args:
            tab_id: Identifier of the tab to rename.
            new_base_title: New base title for the tab.

        Raises:
            KeyError: If the tab does not exist.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            raise KeyError(f"Unknown tab_id: {tab_id}")

        title = new_base_title.strip()
        if not title:
            return

        if title == tab.base_title:
            return

        old_title = tab.base_title
        tab.base_title = title

        self._logger.info(
            "EditorTabManager: tab renamed (tab_id=%s, '%s' → '%s')",
            tab_id,
            old_title,
            title,
        )

    # ==================================================================
    # Active tab handling
    # ==================================================================

    def set_active_tab(self, tab_id: str) -> None:
        """Mark a tab as the active editor tab.

        Args:
            tab_id: Identifier of the tab to activate.

        Raises:
            KeyError: If the tab does not exist.
        """
        if tab_id not in self._tabs:
            raise KeyError(f"Unknown tab_id: {tab_id}")

        self._active_tab_id = tab_id

        self._logger.debug(
            "EditorTabManager: active tab set (tab_id=%s)",
            tab_id,
        )

    def get_active_tab(self) -> EditorTab | None:
        """Return the currently active editor tab."""
        if not self._active_tab_id:
            return None
        return self._tabs.get(self._active_tab_id)

    def get_tab(self, tab_id: str) -> EditorTab | None:
        """Return editor tab by id, or None if it does not exist."""
        return self._tabs.get(tab_id)

    # ==================================================================
    # Connection binding
    # ==================================================================

    def bind_tab_to_connection(self, tab_id: str, connection_name: str) -> None:
        """Bind an existing tab to a database connection.

        Args:
            tab_id: Identifier of the tab.
            connection_name: Name of the database connection.

        Raises:
            KeyError: If the tab does not exist.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            raise KeyError(f"Unknown tab_id: {tab_id}")

        tab.connection_name = connection_name
        tab.last_used_connection = connection_name

    def unbind_tab(self, tab_id: str) -> None:
        """Remove the connection binding from a tab.

        The tab becomes UNBOUND but retains last_used_connection as a hint.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        tab.connection_name = None
        tab.state = EditorTabState.UNBOUND

    # ==================================================================
    # Connection lifecycle integration
    # ==================================================================

    def on_connection_disconnected(self, connection_name: str) -> None:
        """Disable all tabs bound to a disconnected connection.

        Args:
            connection_name: Name of the disconnected connection.
        """
        affected = 0

        for tab in self._tabs.values():
            if tab.connection_name == connection_name and tab.state != EditorTabState.DISCONNECTED:
                tab.state = EditorTabState.DISCONNECTED
                affected += 1

        if affected:
            self._logger.info(
                "EditorTabManager: connection disconnected (connection=%s, affected_tabs=%d)",
                connection_name,
                affected,
            )

    def on_connection_reconnected(self, connection_name: str) -> None:
        """Re-enable all tabs bound to a reconnected connection.

        Args:
            connection_name: Name of the reconnected connection.
        """
        affected = 0

        for tab in self._tabs.values():
            if tab.connection_name == connection_name and tab.state == EditorTabState.DISCONNECTED:
                tab.state = EditorTabState.BOUND
                affected += 1

        if affected:
            self._logger.info(
                "EditorTabManager: connection reconnected (connection=%s, affected_tabs=%d)",
                connection_name,
                affected,
            )

    def on_active_connection_changed(self, *, previous: str | None, current: str | None) -> None:
        """Handle active connection changes."""
        if current:
            # Reconnect existing tabs
            self.on_connection_reconnected(current)

            # If no tab exists for this connection, create policy decision elsewhere
            return

        if previous:
            self.on_connection_disconnected(previous)

    def mark_dirty(self, tab_id: str) -> None:
        """Mark a tab as dirty if it is not already."""
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        if not tab.is_dirty:
            tab.is_dirty = True
            self._logger.debug(
                "EditorTabManager: tab marked dirty (tab_id=%s)",
                tab_id,
            )

    def clear_dirty(self, tab_id: str) -> None:
        """Clear dirty state for a tab."""
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        if tab.is_dirty:
            tab.is_dirty = False
            self._logger.debug(
                "EditorTabManager: tab dirty cleared (tab_id=%s)",
                tab_id,
            )

    def set_file_path(self, tab_id: str, path: str) -> None:
        """Set the file path for a tab."""
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        tab.file_path = path
        tab.base_title = Path(path).name
        self._logger.debug(
            "EditorTabManager: file path set (tab_id=%s, path=%s)",
            tab_id,
            path,
        )

    # ==================================================================
    # Query helpers (used by QueryController / UI)
    # ==================================================================

    def get_connection_for_active_tab(self) -> str | None:
        """Return the connection name for the active tab, if any."""
        tab = self.get_active_tab()
        if not tab:
            return None
        return tab.connection_name

    def can_execute_sql(self) -> bool:
        """Return True if SQL execution is allowed for the active tab."""
        tab = self.get_active_tab()
        if not tab:
            return False
        return tab.state == EditorTabState.BOUND

    # ==================================================================
    # Introspection helpers
    # ==================================================================

    def iter_tabs(self) -> Iterable[EditorTab]:
        """Iterate over all editor tabs."""
        return self._tabs.values()

    def tab_count(self) -> int:
        """Return the number of open editor tabs."""
        return len(self._tabs)
