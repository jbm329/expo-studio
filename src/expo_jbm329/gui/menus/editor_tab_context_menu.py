"""Context menu for editor tabs.

Note:
This menu currently uses direct callbacks.
If menu complexity grows, this can be refactored to a
context + action-id based dispatcher similar to
ResultTabColumnHeaderContextMenu.

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QPoint
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.editor_tab_manager import EditorTab


class EditorTabContextMenu:
    """Context menu for editor tabs (v1).

    Responsibilities:
      - Build and show the editor-tab context menu
      - Enable/disable actions based on tab state
      - Dispatch actions to injected behaviors
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_RENAME = QT_TR_NOOP("Rename…")
    TR_RENAME_TAB = QT_TR_NOOP("Rename tab")
    TR_NEW_NAME = QT_TR_NOOP("New name:")
    TR_SAVE = QT_TR_NOOP("Save")
    TR_SAVE_AS = QT_TR_NOOP("Save as…")
    TR_CLOSE = QT_TR_NOOP("Close")
    TR_CLOSE_OTHERS = QT_TR_NOOP("Close others")
    TR_CLOSE_RIGHT = QT_TR_NOOP("Close all to the right")
    TR_CLOSE_ALL = QT_TR_NOOP("Close all")
    TR_DUPLICATE_TAB = QT_TR_NOOP("Duplicate tab")
    TR_BIND_TO_CONNECTION = QT_TR_NOOP("Associate with connection")
    TR_UNBIND_TAB = QT_TR_NOOP("Unbind tab")

    @staticmethod
    def _tr(tr_text: str) -> str:
        return tr("EditorTabContextMenu", tr_text)

    @staticmethod
    def _tr_fmt(tr_text: str, **kwargs: str) -> str:
        return tr_fmt("EditorTabContextMenu", tr_text, **kwargs)

    __slots__ = (
        "_bind_tab_to_connection",
        "_close_all_tabs",
        "_close_other_tabs",
        "_close_tab",
        "_close_tabs_to_right",
        "_dialogs",
        "_duplicate_tab",
        "_get_all_tab_ids",
        "_get_connections",
        "_get_tab",
        "_parent",
        "_rename_tab",
        "_save_tab",
        "_save_tab_as",
        "_unbind_tab",
    )

    def __init__(
        self,
        *,
        get_tab: Callable[[str], EditorTab | None],
        get_all_tab_ids: Callable[[], list[str]],
        rename_tab: Callable[[str, str], None],
        close_tab: Callable[[str], None],
        close_other_tabs: Callable[[str], None],
        close_tabs_to_right: Callable[[str], None],
        save_tab: Callable[[], None],
        save_tab_as: Callable[[], None],
        duplicate_tab: Callable[[str], None],
        get_connections: Callable[[], Iterable[str]],
        bind_tab_to_connection: Callable[[str, str]],
        unbind_tab: Callable[[str]],
        close_all_tabs: Callable[[str | None], None],
        dialogs: DialogService | None = None,
        parent,
    ) -> None:
        """Initialize the context menu."""
        self._get_tab = get_tab
        self._get_all_tab_ids = get_all_tab_ids
        self._rename_tab = rename_tab
        self._close_tab = close_tab
        self._close_other_tabs = close_other_tabs
        self._close_tabs_to_right = close_tabs_to_right
        self._save_tab = save_tab
        self._save_tab_as = save_tab_as
        self._duplicate_tab = duplicate_tab
        self._get_connections = get_connections
        self._bind_tab_to_connection = bind_tab_to_connection
        self._unbind_tab = unbind_tab
        self._close_all_tabs = close_all_tabs
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._parent = parent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show(self, *, tab_id: str, global_pos: QPoint) -> None:
        """Show the context menu for a tab."""
        tab = self._get_tab(tab_id)
        if not tab:
            return

        menu = QMenu(self._parent)
        self._populate(menu, tab, tab_id)
        menu.exec(global_pos)

    # ------------------------------------------------------------------
    # Menu building
    # ------------------------------------------------------------------

    def _populate(self, menu: QMenu, tab: EditorTab, tab_id: str) -> None:
        all_tabs = self._get_all_tab_ids()
        has_multiple = len(all_tabs) > 1

        # --------------------------------------------------------------
        # Info row (disabled)
        # --------------------------------------------------------------
        info_text = tab.base_title
        if tab.is_dirty:
            info_text += "*"

        conn = tab.connection_name or self._tr("no connection")
        info_text += f"  [{conn}]"

        if tab.state.name == "DISCONNECTED":
            info_text += f" ({self._tr('disconnected')})"

        info_action = QAction(info_text, menu)
        info_action.setEnabled(False)
        menu.addAction(info_action)

        menu.addSeparator()

        # --------------------------------------------------------------
        # Rename
        # --------------------------------------------------------------
        rename_action = QAction(self._tr(self.TR_RENAME), menu)
        menu.addAction(rename_action)
        rename_action.triggered.connect(
            lambda: self._prompt_rename(tab_id, tab.base_title)
        )

        menu.addSeparator()

        # --------------------------------------------------------------
        # Save
        # --------------------------------------------------------------
        save_action = QAction(self._tr(self.TR_SAVE), menu)
        menu.addAction(save_action)
        save_action.setEnabled(tab.is_dirty)
        save_action.triggered.connect(self._save_tab)

        save_as_action = QAction(self._tr(self.TR_SAVE_AS), menu)
        menu.addAction(save_as_action)
        save_as_action.triggered.connect(self._save_tab_as)

        menu.addSeparator()

        # --------------------------------------------------------------
        # Close actions
        # --------------------------------------------------------------
        close_action = QAction(self._tr(self.TR_CLOSE), menu)
        menu.addAction(close_action)
        close_action.triggered.connect(lambda: self._close_tab(tab_id))

        close_others_action = QAction(self._tr(self.TR_CLOSE_OTHERS), menu)
        menu.addAction(close_others_action)
        close_others_action.setEnabled(has_multiple)
        close_others_action.triggered.connect(
            lambda: self._close_other_tabs(tab_id)
        )

        close_right_action = QAction(self._tr(self.TR_CLOSE_RIGHT), menu)
        menu.addAction(close_right_action)
        close_right_action.setEnabled(has_multiple)
        close_right_action.triggered.connect(
            lambda: self._close_tabs_to_right(tab_id)
        )

        close_all_action = QAction(self._tr(self.TR_CLOSE_ALL), menu)
        menu.addAction(close_all_action)
        close_all_action.setEnabled(has_multiple)
        close_all_action.triggered.connect(lambda: self._close_all_tabs(tab_id))

        menu.addSeparator()

        duplicate_action = QAction(self._tr(self.TR_DUPLICATE_TAB), menu)
        menu.addAction(duplicate_action)
        duplicate_action.triggered.connect(
            lambda: self._duplicate_tab(tab_id)
        )

        menu.addSeparator()

        conn_menu = QMenu(self._tr(self.TR_BIND_TO_CONNECTION), menu)
        menu.addMenu(conn_menu)

        for conn in self._get_connections():
            act = QAction(conn, conn_menu)
            act.setCheckable(True)
            act.setChecked(conn == tab.connection_name)
            conn_menu.addAction(act)

            act.triggered.connect(lambda _, c=conn: self._bind_tab_to_connection(tab_id, c))

        conn_menu.addSeparator()

        unbind_action = QAction(self._tr(self.TR_UNBIND_TAB), conn_menu)
        unbind_action.setEnabled(tab.connection_name is not None)
        conn_menu.addAction(unbind_action)
        unbind_action.triggered.connect(lambda: self._unbind_tab(tab_id))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prompt_rename(self, tab_id: str, current_name: str) -> None:
        new_name, ok = self._dialogs.prompt_text(
            parent=self._parent,
            title=self._tr(self.TR_RENAME_TAB),
            label=self._tr(self.TR_NEW_NAME),
            default=current_name,
        )
        if not ok:
            return

        name = new_name.strip()
        if not name or name == current_name:
            return

        self._rename_tab(tab_id, name)
