"""Controller for the REST panel in the workbench UI.

This controller is responsible for wiring the REST tree widget to
UI-facing services such as icons and themes. It does not perform
any REST execution logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt

from expo_jbm329.app.settings.config_store import read_rest_connections
from expo_jbm329.gui.widgets.rest_tree_widget import RestTreeWidget
from expo_jbm329.services.rest.registry import rest_registry

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.workbench.controllers.rest_controller import RestController
    from expo_jbm329.workbench.icon.icon_service import IconService


class RestPanelController:
    """Coordinate REST panel UI behavior."""

    __slots__ = (
        "__weakref__",
        "_icon_service",
        "_logger",
        "_open_rest_connection_dialog",
        "_parent",
        "_rest_controller",
        "_rest_tree",
    )

    def __init__(
        self,
        *,
        parent_widget: QWidget,
        rest_tree: RestTreeWidget,
        rest_controller: RestController,
        open_rest_connection_dialog: Callable[[str], None],
        icon_service: IconService,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the REST panel controller.

        Args:
            parent_widget: Parent widget (for future dialogs).
            rest_tree: The REST tree widget.
            rest_controller: The REST controller for managing REST operations.
            open_rest_connection_dialog: Callback to open the REST connection dialog.
            icon_service: Icon service used for themed icons.
            logger: Optional logger.
        """
        self._parent = parent_widget
        self._rest_tree = rest_tree
        self._rest_controller = rest_controller
        self._open_rest_connection_dialog = open_rest_connection_dialog
        self._icon_service = icon_service
        self._logger = logger or logging.getLogger("applogger.ui")

    # --------------------------------------------------------------
    # Initialization / binding
    # --------------------------------------------------------------
    def initialize(self) -> None:
        """Bind services and initialize the REST panel."""
        self._logger.debug("RestPanelController: initializing REST panel")

        # Bind icon updates
        self._icon_service.icons_updated.connect(self._update_icons)

        # Bind widget signals
        self._rest_tree.load_requested.connect(self._rest_controller.load_preset)
        self._rest_tree.edit_requested.connect(self._on_edit_requested)
        self._rest_tree.copy_requested.connect(self._on_copy_requested)

        # Initial setup
        self.reload()

    def reload(self) -> None:
        """Reload REST tree and apply icons."""
        rest_registry.reload_user_connections(read_rest_connections())
        self._rest_tree.reload()
        self._update_icons()

    # --------------------------------------------------------------
    # Icon handling
    # --------------------------------------------------------------
    def _update_icons(self) -> None:
        """Update folder and REST icons in the tree."""
        root = self._rest_tree.invisibleRootItem()
        if root is None:
            return

        for i in range(root.childCount()):
            child = root.child(i)
            if child is not None:
                self._update_item_icons_recursive(child)

    def _update_item_icons_recursive(self, item) -> None:
        role = item.data(0, Qt.ItemDataRole.UserRole)

        if role == RestTreeWidget.FOLDER_ROLE:
            item.setIcon(0, self._icon_service.get("folder"))
        else:
            item.setIcon(0, self._icon_service.get("rest"))

        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._update_item_icons_recursive(child)

    # --------------------------------------------------------------
    # Edit REST request handling
    # --------------------------------------------------------------
    def _on_edit_requested(self, name: str) -> None:
        """Handle REST edit request."""
        self._logger.debug("RestPanelController: REST edit requested: %s", name)
        self._open_rest_connection_dialog(name)

    def _on_copy_requested(self, name: str) -> None:
        """Handle REST copy request."""
        self._logger.debug("RestPanelController: REST copy requested: %s", name)
        new_name = self._rest_controller.copy_preset(name)
        if new_name:
            self._rest_tree.reload()
            self._update_icons()
            self._open_rest_connection_dialog(new_name)
