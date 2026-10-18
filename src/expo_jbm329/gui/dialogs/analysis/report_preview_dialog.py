"""Read-only dialog for previewing rendered analysis reports."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, override

from PyQt6 import sip
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from PyQt6.QtCore import QObject
    from PyQt6.QtGui import QCloseEvent


class _OfflineRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Allow only the local report document and embedded data resources."""

    def __init__(self, document_url: QUrl, parent: QObject) -> None:
        """Initialize the interceptor for one report document."""
        super().__init__(parent)
        self._document_url = document_url

    @override
    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        """Block requests not satisfied by the local document or embedded data."""
        request_url = info.requestUrl()
        if request_url.scheme() == "data":
            return
        is_preview_document = (
            request_url == self._document_url
            and info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame
        )
        if not is_preview_document:
            info.block(True)


class _OfflineReportPage(QWebEnginePage):
    """Prevent the preview from navigating away from its local report file."""

    def __init__(self, profile: QWebEngineProfile, document_url: QUrl, parent: QObject) -> None:
        """Initialize a page restricted to its report document."""
        super().__init__(profile, parent)
        self._document_url = document_url

    @override
    def acceptNavigationRequest(
        self,
        url: QUrl,
        type: QWebEnginePage.NavigationType,
        isMainFrame: bool,
    ) -> bool:
        """Allow the initial local report only; reject every link and redirect."""
        del type
        return isMainFrame and url == self._document_url


class ReportPreviewDialog(QDialog):
    """Display rendered report HTML in a bounded, offline WebEngine view."""

    load_failed = pyqtSignal(str)

    def __init__(self, html: str, parent: QWidget | None = None) -> None:
        """Initialize the preview dialog.

        Args:
            html: Complete, rendered HTML document to preview.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Report preview"))
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(1100, 800)
        self.setMinimumSize(640, 480)

        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = tempfile.TemporaryDirectory(
            prefix="expo-report-preview-"
        )
        self._html_path = Path(self._temporary_directory.name) / "report.html"
        try:
            self._html_path.write_text(html, encoding="utf-8", newline="")
        except (OSError, UnicodeError):
            self._temporary_directory.cleanup()
            self._temporary_directory = None
            raise

        self._document_url = QUrl.fromLocalFile(str(self._html_path))
        self._closing = False
        self._cleanup_pending = False
        self.finished.connect(self._begin_cleanup)
        self._create_ui()
        self._configure_web_view()
        self._web_view.loadFinished.connect(self._on_load_finished)
        self._web_view.setUrl(self._document_url)

    def _create_ui(self) -> None:
        """Create the embedded browser, failure message, and close control."""
        layout = QVBoxLayout(self)
        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #b00020;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._web_view = QWebEngineView(self)
        self._web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._web_view.setAcceptDrops(False)
        layout.addWidget(self._web_view, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton(self.tr("Close"), self)
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def _configure_web_view(self) -> None:
        """Set up an ephemeral WebEngine profile with offline, read-only policies."""
        profile = QWebEngineProfile(self)
        self._profile = profile
        self._request_interceptor = _OfflineRequestInterceptor(self._document_url, profile)
        profile.setUrlRequestInterceptor(self._request_interceptor)
        profile.downloadRequested.connect(self._cancel_download)

        page = _OfflineReportPage(profile, self._document_url, self._web_view)
        self._page = page
        if self._temporary_directory is not None:
            page.destroyed.connect(self._temporary_directory.cleanup)
        self._web_view.setPage(page)
        settings = page.settings()
        if settings is None:
            message = "The report preview page has no WebEngine settings."
            raise RuntimeError(message)
        for attribute in (
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.JavascriptCanPaste,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.PluginsEnabled,
            QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
        ):
            settings.setAttribute(attribute, False)

    @staticmethod
    def _cancel_download(download: QWebEngineDownloadRequest) -> None:
        """Reject every attempted report download."""
        download.cancel()

    def _on_load_finished(self, succeeded: bool) -> None:
        """Show and signal the error when the report document cannot be loaded."""
        if not succeeded and not self._closing:
            message = self.tr("The report preview could not be loaded.")
            self._error_label.setText(message)
            self._error_label.show()
            self.load_failed.emit(message)

    def _cleanup_temporary_html(self) -> None:
        """Remove the private temporary report file after WebEngine releases it."""
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None

    def _begin_cleanup(self) -> None:
        """Release the page before deleting its private HTML and WebEngine profile."""
        if self._cleanup_pending:
            return
        self._closing = True
        self._cleanup_pending = True
        self._web_view.stop()
        sip.delete(self._page)
        sip.delete(self._web_view)
        sip.delete(self._profile)
        self._cleanup_temporary_html()

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Release the browser before closing and deleting the temporary HTML."""
        self._begin_cleanup()
        super().closeEvent(a0)
