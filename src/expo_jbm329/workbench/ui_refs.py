"""Shared UI references for the Expo workbench.

This module defines the UI widgets, callbacks, and services that are bundled
together so controllers and services can interact with the workbench without
reaching into the main window directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QFileSystemModel
    from PyQt6.QtWidgets import QTabWidget, QWidget

    from expo_jbm329.gui.widgets.file_tree_widget import FileTreeWidget
    from expo_jbm329.gui.widgets.rest_tree_widget import RestTreeWidget
    from expo_jbm329.gui.widgets.schema_tree_widget import SchemaTreeWidget
    from expo_jbm329.workbench.controllers.editor_panel_controller import EditorPanelController
    from expo_jbm329.workbench.highlighter.sql_highlighter import SqlHighlighter


@dataclass
class WorkbenchUIRefs:
    """Container for workbench UI widgets, callbacks, and services."""

    # GUI widgets
    parent: QWidget
    result_tabs: QTabWidget
    editor_tabs: QTabWidget
    schema_tree: SchemaTreeWidget
    files_tree: FileTreeWidget
    rest_tree: RestTreeWidget
    files_model: QFileSystemModel

    # UI callbacks
    set_status: Callable[[str, int | None], None]
    restore_status: Callable[[], None]
    set_shape: Callable[[int | None, int | None], None]
    update_undo_enabled: Callable[[], None]
    open_rest_connection_dialog: Callable[[str], None]
    editor_panel: EditorPanelController | None = None

    # GUI infrastructure services
    theme_service: object | None = None
    highlighter_theme_service: object | None = None
    icon_service: object | None = None
    file_icon_provider: object | None = None

    # SQL workbench highlighter instance
    editor_highlighter: SqlHighlighter | None = None
