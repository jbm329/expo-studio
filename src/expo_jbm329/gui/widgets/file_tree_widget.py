"""File tree widget."""

from __future__ import annotations

from PyQt6.QtCore import QDir, Qt
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import QHeaderView, QTreeView, QWidget


class FileTreeWidget(QTreeView):
    """Tree widget for browsing files in the workbench."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the FileTreeWidget."""
        super().__init__(parent)

        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self._model = QFileSystemModel(self)
        self._model.setRootPath("")
        self._model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Files)

        self.setModel(self._model)

        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in (1, 2, 3):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self.setColumnHidden(2, True)
        self.setColumnHidden(3, True)

    @property
    def model(self) -> QFileSystemModel:
        """Returns the model of the tree widget."""
        return self._model
