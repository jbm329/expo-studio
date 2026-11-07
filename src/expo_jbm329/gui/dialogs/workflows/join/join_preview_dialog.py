"""Preview dialog for join results.

Shows a preview of the joined DataFrame along with metadata
such as match rate, unmatched rows, and join type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.widgets.join_analysis_widget import JoinAnalysisWidget
from expo_jbm329.utils.models import JoinPreviewModel

if TYPE_CHECKING:
    import pandas as pd

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.services.data_operations.joins import JoinMetadata


class JoinPreviewDialog(QDialog):
    """Dialog that shows join preview and metadata."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        df: pd.DataFrame,
        metadata: JoinMetadata,
        dialogs: DialogService | None = None,
    ) -> None:
        """Initialize the JoinPreviewDialog.

        Args:
            parent: The parent widget (default is None).
            df: The DataFrame to preview.
            metadata: The metadata dictionary.
            dialogs: Service for displaying warnings, defaulting to QtDialogService.
        """
        super().__init__(parent)
        self._dialogs = dialogs if dialogs is not None else QtDialogService()

        self.setWindowTitle(self.tr("Join preview"))

        # Root layout
        root = QVBoxLayout(self)

        # ======================================================
        # Guard
        # ======================================================

        if "join_status" not in df.columns:
            df = df.copy()
            df["join_status"] = "both"

        # ======================================================
        # Preview table
        # ======================================================
        self.table = QTableView()
        self.model = JoinPreviewModel(df)
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self.table.horizontalHeader()
        if header:
            header.setStretchLastSection(True)
            header.setVisible(True)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        root.addWidget(self.table)

        # ======================================================
        # Metadata panel
        # ======================================================

        self.analysis = JoinAnalysisWidget(self)
        root.addWidget(self.analysis)

        # ======================================================
        # Buttons
        # ======================================================
        btn_row = QHBoxLayout()
        help_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Help, self)
        localize_dialog_buttons(help_buttons)
        help_button = help_buttons.button(QDialogButtonBox.StandardButton.Help)
        if help_button is None:
            message = "Join preview help button has not been created."
            raise RuntimeError(message)
        help_button.setAutoDefault(False)
        help_buttons.helpRequested.connect(self._open_help)
        btn_row.addWidget(help_buttons)
        btn_row.addStretch(1)

        btn_close = QPushButton(self.tr("Close"))
        btn_close.clicked.connect(self.close)

        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        self._help_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents), self)
        self._help_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._help_shortcut.activated.connect(self._open_help)

        # ======================================================
        # Apply metadata
        # ======================================================
        self.analysis.set_metadata(metadata)

        # Size
        self.resize(800, 700)

    def _open_help(self) -> None:
        """Open preview guidance without changing the displayed join result."""
        url = HelpTopic.JOIN_PREVIEW.url
        if not QDesktopServices.openUrl(QUrl(url)):
            self._dialogs.warn(
                self,
                self.tr("Unable to open link"),
                self.tr("The user manual could not be opened.\n\n{url}").format(url=url),
            )
