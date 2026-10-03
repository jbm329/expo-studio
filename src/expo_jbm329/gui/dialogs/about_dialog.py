"""About dialog for the Expo application.

This module provides an About dialog that displays application
metadata pulled from metadata.py and dynamic system information.
"""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.metadata import get_app_metadata

LOCAL_DOCUMENTS = {
    "license": "LICENSE.txt",
    "notices": "THIRD-PARTY-NOTICES.txt",
}


class AboutDialog(QDialog):
    """About dialog for Expo Studio."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the About dialog."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("About Expo studio"))
        self.setFixedSize(570, 380)
        self._init_ui()

    def _init_ui(self) -> None:
        """Set up the dialog user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        logo_label = QLabel()
        pixmap = QPixmap(":/splash/splash.png")
        if not pixmap.isNull():
            logo_label.setPixmap(
                pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            logo_label.setText("🚀")
            logo_label.setStyleSheet("font-size: 64pt;")
        content_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignTop)

        metadata = get_app_metadata()
        self._repository_url = metadata["repository"]
        name = metadata.get("name") or self.tr("Expo Studio")
        version = metadata.get("version") or self.tr("Unknown")
        author = metadata.get("author") or "Jonas Brännström"

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)

        name_label = QLabel(f"{name} {version}")
        name_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        info_layout.addWidget(name_label)

        copyright_text = self.tr("Copyright © %1 %2")
        copyright_text = copyright_text.replace("%1", str(datetime.now(UTC).astimezone().year))
        copyright_label = QLabel(copyright_text.replace("%2", str(author)))
        info_layout.addWidget(copyright_label)

        content_layout.addWidget(info_widget, 1)
        layout.addLayout(content_layout)

        license_label = QLabel(
            self.tr(
                "Expo Studio is free software licensed under the GNU General Public License, version 3 (GPLv3). "
                "This program comes with ABSOLUTELY NO WARRANTY, to the extent permitted by applicable law."
            )
        )

        license_label.setWordWrap(True)
        layout.addWidget(license_label)

        warranty_label = QLabel(
            self.tr(
                "Expo Studio is distributed in the hope that it will be useful, "
                "but WITHOUT ANY WARRANTY; without even the implied warranty of "
                "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE."
            )
        )
        warranty_label.setWordWrap(True)
        layout.addWidget(warranty_label)

        self._third_party_notices = self.tr("Third-party notices")

        third_party_label = QLabel(
            self.tr(
                "The application uses third-party software distributed under various licenses. "
                "See <b>%1</b> for details."
            ).replace("%1", self._third_party_notices)
        )
        third_party_label.setWordWrap(True)
        layout.addWidget(third_party_label)

        icons_label = QLabel(
            self.tr(
                "Icons provided by <a href='https://icons8.com'>Icons8</a>"
                " and used under the free license which requires attribution."
            )
        )
        icons_label.setTextFormat(Qt.TextFormat.RichText)
        icons_label.setOpenExternalLinks(True)
        icons_label.setStyleSheet("color: #777; font-size: 9pt;")
        layout.addWidget(icons_label)

        python_info = self.tr("Python: %1").replace("%1", platform.python_version())
        qt_info = self.tr("Qt: %1 | PyQt: %2").replace("%1", QT_VERSION_STR).replace("%2", PYQT_VERSION_STR)
        platform_info = self.tr("Platform: %1 %2 (%3)")
        platform_info = platform_info.replace("%1", platform.system())
        platform_info = platform_info.replace("%2", platform.release())
        platform_info = platform_info.replace("%3", platform.machine())
        sys_info = f"{python_info}<br/>{qt_info}<br/>{platform_info}"
        sys_info_label = QLabel(sys_info)
        sys_info_label.setStyleSheet("color: #777; font-size: 9pt;")
        sys_info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(sys_info_label)

        layout.addStretch()
        layout.addLayout(self._create_footer_layout())

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton(self.tr("Close"))
        close_button.setFixedWidth(80)
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def _create_footer_layout(self) -> QHBoxLayout:
        """Create the row of links to project and license documents."""
        layout = QHBoxLayout()
        for link_id, label in (
            ("license", self.tr("License")),
            ("repository", self.tr("Source code")),
            ("notices", self._third_party_notices),
        ):
            link_label = QLabel(f'<a href="{link_id}">{label}</a>')
            link_label.setTextFormat(Qt.TextFormat.RichText)
            link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            link_label.linkActivated.connect(self._open_link)
            layout.addWidget(link_label)

        layout.addStretch()
        return layout

    def _open_link(self, link_id: str) -> None:
        """Open a repository URL or a local license document."""
        if link_id == "repository":
            url = QUrl(self._repository_url)
        else:
            document_name = LOCAL_DOCUMENTS.get(link_id)
            if document_name is None:
                error_message = f"Unsupported About dialog link: {link_id}"
                raise ValueError(error_message)

            document_path = self._find_document(document_name)
            if document_path is None:
                QMessageBox.warning(
                    self,
                    self.tr("Document unavailable"),
                    self.tr("Could not find %1.").replace("%1", document_name),
                )
                return
            url = QUrl.fromLocalFile(str(document_path))

        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                self.tr("Unable to open link"),
                self.tr("The requested link could not be opened."),
            )

    @staticmethod
    def _find_document(document_name: str) -> Path | None:
        """Find a legal document in source, packaged, and generated locations."""
        source_root = Path(__file__).resolve().parents[4]
        executable_directory = Path(sys.executable).resolve().parent
        roots = dict.fromkeys((
            executable_directory.parent,
            executable_directory,
            source_root,
            Path.cwd(),
        ))

        candidates = [root / document_name for root in roots]
        if document_name == LOCAL_DOCUMENTS["notices"]:
            candidates.extend(root / "build" / "third-party-notices" / document_name for root in roots)

        return next((path for path in candidates if path.is_file()), None)
