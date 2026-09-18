"""About dialog for the Expo application.

This module provides an About dialog that displays application
metadata pulled from metadata.py and dynamic system information.
"""

from __future__ import annotations

import platform
from pathlib import Path

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.metadata import get_app_metadata


class AboutDialog(QDialog):
    """About dialog for Expo Studio."""

    def __init__(self, parent: QWidget | None = None):
        """Initialize the About dialog."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("About Expo studio"))
        self.setFixedSize(565, 370)
        self._init_ui()

    def _init_ui(self):
        """Set up the dialog user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Content area with horizontal layout for logo and text
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # Logo/Icon
        logo_label = QLabel()
        pixmap = QPixmap(":/splash/splash.png")
        if not pixmap.isNull():
            logo_label.setPixmap(
                pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            # Placeholder if pixmap fails
            logo_label.setText("🚀")
            logo_label.setStyleSheet("font-size: 64pt;")

        content_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignTop)

        # Text information
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)

        metadata = get_app_metadata()

        name_label = QLabel(f"<b>{metadata.get('name', 'Expo studio')}</b>")
        name_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        info_layout.addWidget(name_label)

        version_label = QLabel(self.tr("Version: %1").replace("%1", metadata.get("version", self.tr("Unknown"))))
        version_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(version_label)

        desc_label = QLabel(metadata.get("description", ""))
        desc_label.setWordWrap(True)
        info_layout.addWidget(desc_label)

        info_layout.addSpacing(10)

        author_label = QLabel(self.tr("Author: %1").replace("%1", metadata.get("author", "Jonas Brännström")))
        info_layout.addWidget(author_label)

        license_label = QLabel(self.tr("License: %1").replace("%1", metadata.get("license", "GPL-3.0-or-later")))
        info_layout.addWidget(license_label)
        source_code_label = QLabel(
            self.tr("Source code: <a href='%1'>%1</a>").replace(
                "%1", metadata.get("repository", "https://github.com/jbm329/expo-studio")
            )
        )
        source_code_label.setTextFormat(Qt.TextFormat.RichText)
        source_code_label.setOpenExternalLinks(True)
        info_layout.addWidget(source_code_label)

        # --- Icons / Attribution ---
        icons_label = QLabel(
            "Icons provided by <a href='https://icons8.com'>Icons8</a>.<br/>"
            "Used under the free license which requires attribution."
        )
        icons_label.setTextFormat(Qt.TextFormat.RichText)
        icons_label.setOpenExternalLinks(True)
        icons_label.setStyleSheet("color: #777; font-size: 9pt;")

        info_layout.addSpacing(5)
        info_layout.addWidget(icons_label)

        info_layout.addStretch()
        content_layout.addWidget(info_widget, 1)
        layout.addLayout(content_layout)

        # Dynamic System Info Section
        sys_info_group = QWidget()
        sys_info_layout = QVBoxLayout(sys_info_group)
        sys_info_layout.setContentsMargins(0, 10, 0, 0)
        sys_info_layout.setSpacing(2)

        sys_info = (
            f"Python: {platform.python_version()}<br/>"
            f"Qt: {QT_VERSION_STR} | PyQt: {PYQT_VERSION_STR}<br/>"
            f"Plattform: {platform.system()} {platform.release()} ({platform.machine()})"
        )
        sys_info_label = QLabel(sys_info)
        sys_info_label.setStyleSheet("color: #777; font-size: 9pt;")
        sys_info_label.setTextFormat(Qt.TextFormat.RichText)
        sys_info_layout.addWidget(sys_info_label)

        layout.addWidget(sys_info_group)

        # OK Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_button = QPushButton(self.tr("Close"))
        ok_button.setFixedWidth(80)
        ok_button.clicked.connect(self.accept)
        btn_layout.addWidget(ok_button)
        layout.addLayout(btn_layout)

    def _open_file_link(self, link: str):
        """Open a local file link using the system default application."""
        file_path = Path(link)
        if not file_path.is_absolute():
            # Try to resolve relative to project root
            potential_roots = [Path(), Path(__file__).resolve().parents[4]]
            for root in potential_roots:
                full_path = root / file_path
                if full_path.exists():
                    file_path = full_path
                    break

        if file_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path.absolute())))
