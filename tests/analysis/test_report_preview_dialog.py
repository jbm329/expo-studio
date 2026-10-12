from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import QUrl

WORKER_ARGUMENT = "--report-preview-worker"

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QApplication

    from expo_jbm329.gui.dialogs.analysis.report_preview_dialog import ReportPreviewDialog


@pytest.mark.parametrize(
    "scenario",
    (
        "large-html-and-close-cleanup",
        "offline-read-only-policy",
        "load-failure",
        "download-cancel",
        "reject-cleanup",
        "parent-destruction-cleanup",
    ),
)
def test_report_preview_scenario_in_isolated_process(
    scenario: str,
) -> None:
    """Run each Chromium lifetime scenario in its own process."""
    test_file = Path(__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(test_file), WORKER_ARGUMENT, scenario],
        capture_output=True,
        check=False,
        timeout=45,
    )

    assert result.returncode == 0, (
        f"Report preview scenario {scenario!r} failed in its isolated process "
        f"(exit code {result.returncode}).\n"
        f"stdout:\n{result.stdout.decode(errors='replace')}\n"
        f"stderr:\n{result.stderr.decode(errors='replace')}"
    )


def _run_worker(scenario: str) -> None:
    """Run a real Qt WebEngine scenario after the GUI's pre-application setup."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([sys.executable])

    from PyQt6 import sip
    from PyQt6.QtTest import QSignalSpy
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineUrlRequestInfo
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

    from expo_jbm329.gui.dialogs.analysis.report_preview_dialog import ReportPreviewDialog

    if scenario == "startup":
        view = QWebEngineView()
        page = QWebEnginePage()
        view.setPage(page)
        app.processEvents()
    elif scenario == "large-html-and-close-cleanup":
        html = "<html><body>ö</body></html>" + ("x" * (2 * 1024 * 1024))
        dialog = ReportPreviewDialog(html)
        html_path = dialog._html_path
        assert html_path.is_file()
        assert html_path.read_text(encoding="utf-8") == html
        assert html_path.stat().st_size > 2 * 1024 * 1024
        assert dialog.findChild(QWebEngineView) is not None
        assert dialog.findChild(QPushButton).text() == "Close"
        assert dialog.minimumWidth() >= 640
        assert dialog.minimumHeight() >= 480
        assert not dialog.isModal()
        assert dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        load_spy = QSignalSpy(dialog._web_view.loadFinished)
        assert load_spy.wait(10_000), "The large report did not finish loading."
        assert load_spy[0][0], "WebEngine failed to load the large report."
        _finish_and_wait_for_html_cleanup(app, dialog, html_path, dialog.close)
    elif scenario == "offline-read-only-policy":
        dialog = ReportPreviewDialog("<html><body>Report</body></html>")
        page = dialog.findChild(QWebEngineView).page()
        settings = page.settings()
        assert settings is not None
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
            assert not settings.testAttribute(attribute)

        assert not page.acceptNavigationRequest(
            QUrl("https://example.com"),
            QWebEnginePage.NavigationType.NavigationTypeLinkClicked,
            True,
        )
        assert not page.acceptNavigationRequest(
            QUrl.fromLocalFile(str(Path("blocked.html").resolve())),
            QWebEnginePage.NavigationType.NavigationTypeLinkClicked,
            True,
        )
        assert page.acceptNavigationRequest(
            dialog._document_url,
            QWebEnginePage.NavigationType.NavigationTypeTyped,
            True,
        )
        assert not page.acceptNavigationRequest(
            dialog._document_url,
            QWebEnginePage.NavigationType.NavigationTypeTyped,
            False,
        )

        external_request = _RequestProbe(QUrl("https://example.com/report.css"))
        dialog._request_interceptor.interceptRequest(external_request)
        assert external_request.blocked
        local_resource_request = _RequestProbe(
            dialog._document_url,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage,
        )
        dialog._request_interceptor.interceptRequest(local_resource_request)
        assert local_resource_request.blocked
        report_request = _RequestProbe(
            dialog._document_url,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame,
        )
        dialog._request_interceptor.interceptRequest(report_request)
        assert not report_request.blocked
        embedded_request = _RequestProbe(QUrl("data:image/png;base64,AA=="))
        dialog._request_interceptor.interceptRequest(embedded_request)
        assert not embedded_request.blocked

        _finish_and_wait_for_html_cleanup(app, dialog, dialog._html_path, dialog.close)
    elif scenario == "load-failure":
        dialog = ReportPreviewDialog("<html></html>")
        failure_spy = QSignalSpy(dialog.load_failed)
        dialog._html_path.unlink()
        dialog.show()
        assert failure_spy.wait(10_000), "The missing report did not emit a load failure."
        assert len(failure_spy) == 1
        error_label = next(label for label in dialog.findChildren(QLabel) if label.text())
        assert error_label.text() == "The report preview could not be loaded."
        _finish_and_wait_for_html_cleanup(app, dialog, dialog._html_path, dialog.close)
    elif scenario == "download-cancel":
        download = _DownloadProbe()
        ReportPreviewDialog._cancel_download(download)
        assert download.cancelled
    elif scenario == "reject-cleanup":
        dialog = ReportPreviewDialog("<html></html>")
        _finish_and_wait_for_html_cleanup(app, dialog, dialog._html_path, dialog.reject)
    elif scenario == "parent-destruction-cleanup":
        parent = QWidget()
        dialog = ReportPreviewDialog("<html><body>Parent-owned preview</body></html>", parent=parent)
        html_path = dialog._html_path
        dialog.show()
        load_spy = QSignalSpy(dialog._web_view.loadFinished)
        assert load_spy.wait(10_000), "The parent-owned preview did not finish loading."
        assert load_spy[0][0]
        sip.delete(parent)
        assert not html_path.exists()
    else:
        message = f"Unknown report preview test scenario: {scenario}"
        raise ValueError(message)


class _RequestProbe:
    """Small request double for exercising the network interceptor."""

    def __init__(self, url: QUrl, resource_type: object | None = None) -> None:
        """Create a request double with an optional WebEngine resource kind."""
        self._url = url
        self._resource_type = resource_type
        self.blocked = False

    def requestUrl(self) -> QUrl:
        """Return the requested URL."""
        return self._url

    def resourceType(self) -> object:
        """Return the requested resource kind."""
        return self._resource_type

    def block(self, should_block: bool) -> None:
        """Record an interceptor block decision."""
        self.blocked = should_block


class _DownloadProbe:
    """Download double for asserting preview downloads are rejected."""

    def __init__(self) -> None:
        """Initialize an uncancelled download probe."""
        self.cancelled = False

    def cancel(self) -> None:
        """Record the cancellation request."""
        self.cancelled = True


def _finish_and_wait_for_html_cleanup(
    app: QApplication,
    dialog: ReportPreviewDialog,
    html_path: Path,
    finish_dialog: Callable[[], None],
) -> None:
    """Wait until the browser leaves its document and the temporary file is removed."""
    finish_dialog()
    assert not html_path.exists()
    app.processEvents()


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == WORKER_ARGUMENT:
    _run_worker(sys.argv[2])
