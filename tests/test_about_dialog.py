from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator
from PyQt6.QtWidgets import QApplication

from expo_jbm329.gui.dialogs import about_dialog
from expo_jbm329.gui.dialogs.about_dialog import AboutDialog
from expo_jbm329.gui.dialogs.service.dialog_service import DialogService


def test_about_dialog_shows_legal_copy_and_footer_links(monkeypatch) -> None:
    monkeypatch.setattr(
        about_dialog,
        "get_app_metadata",
        lambda: {
            "name": "Expo Studio",
            "version": "1.0.0",
            "description": "Dataset analysis",
            "author": "Jonas Brännström",
            "license": "GPL-3.0-only",
            "repository": "https://github.com/jbm329/expo-studio",
        },
    )

    dialog = AboutDialog()
    label_text = "\n".join(label.text() for label in dialog.findChildren(about_dialog.QLabel))

    assert "Expo Studio 1.0.0" in label_text
    assert "Copyright ©" in label_text
    assert "free software licensed under the GNU General Public License" in label_text
    assert "ABSOLUTELY NO WARRANTY" in label_text
    assert "See <b>Third-party notices</b> for details." in label_text
    assert 'href="license"' in label_text
    assert 'href="repository"' in label_text
    assert 'href="notices"' in label_text


def test_find_document_checks_installed_application_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    application_root = tmp_path / "application"
    executable_directory = application_root / "expo"
    executable_directory.mkdir(parents=True)
    document = application_root / "LICENSE.txt"
    document.write_text("license", encoding="utf-8")
    monkeypatch.setattr(about_dialog.sys, "executable", str(executable_directory / "expo.exe"))

    assert AboutDialog._find_document("LICENSE.txt") == document


def test_find_document_checks_generated_notices_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    notices_directory = tmp_path / "build" / "third-party-notices"
    notices_directory.mkdir(parents=True)
    document = notices_directory / "THIRD-PARTY-NOTICES.txt"
    document.write_text("notices", encoding="utf-8")
    monkeypatch.setattr(about_dialog.sys, "executable", str(tmp_path / "expo.exe"))
    monkeypatch.chdir(tmp_path)

    assert AboutDialog._find_document("THIRD-PARTY-NOTICES.txt") == document


def test_repository_link_opens_application_repository(monkeypatch) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(
        about_dialog.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    dialogs = MagicMock(spec=DialogService)
    dialog = AboutDialog(dialogs=dialogs)

    dialog._open_link("repository")

    assert opened_urls == ["https://github.com/jbm329/expo-studio"]
    dialogs.warn.assert_not_called()


def test_license_link_opens_local_document(monkeypatch, tmp_path: Path) -> None:
    document = tmp_path / "LICENSE.txt"
    document.write_text("license", encoding="utf-8")
    opened_urls: list[str] = []
    monkeypatch.setattr(AboutDialog, "_find_document", staticmethod(lambda _name: document))
    monkeypatch.setattr(
        about_dialog.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toLocalFile()) or True,
    )
    dialogs = MagicMock(spec=DialogService)
    dialog = AboutDialog(dialogs=dialogs)

    dialog._open_link("license")

    assert [Path(url) for url in opened_urls] == [document]
    dialogs.warn.assert_not_called()


def test_about_dialog_uses_swedish_legal_translations() -> None:
    translator = QTranslator()
    locale_path = Path(__file__).parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / "app_sv.qm"
    assert translator.load(str(locale_path))

    app = QApplication.instance()
    assert app is not None
    app.installTranslator(translator)
    try:
        dialog = AboutDialog()
        label_text = "\n".join(label.text() for label in dialog.findChildren(about_dialog.QLabel))
    finally:
        app.removeTranslator(translator)

    assert "Expo Studio är fri programvara licensierad enligt GNU General Public License" in label_text
    assert "Programmet tillhandahålls UTAN NÅGON SOM HELST GARANTI" in label_text


def test_about_dialog_formats_metadata_and_runtime_labels(
    monkeypatch: pytest.MonkeyPatch, widget_language: str
) -> None:
    author = "Author {year} %1 %2"
    monkeypatch.setattr(
        about_dialog,
        "get_app_metadata",
        lambda: {
            "name": "Expo Studio",
            "version": "1.0.0",
            "author": author,
            "repository": "https://github.com/jbm329/expo-studio",
        },
    )
    clock = MagicMock()
    clock.now.return_value.astimezone.return_value.year = 2042
    monkeypatch.setattr(about_dialog, "datetime", clock)
    monkeypatch.setattr(about_dialog.platform, "python_version", lambda: "3.13.test")
    monkeypatch.setattr(about_dialog, "QT_VERSION_STR", "6.qt")
    monkeypatch.setattr(about_dialog, "PYQT_VERSION_STR", "6.pyqt")
    monkeypatch.setattr(about_dialog.platform, "system", lambda: "System %2 {release}")
    monkeypatch.setattr(about_dialog.platform, "release", lambda: "Release %3 {machine}")
    monkeypatch.setattr(about_dialog.platform, "machine", lambda: "Machine %1 {system}")

    dialog = AboutDialog()
    texts = [label.text() for label in dialog.findChildren(about_dialog.QLabel)]

    assert f"Copyright © 2042 {author}" in texts
    platform_label = "Plattform" if widget_language == "sv" else "Platform"
    assert (
        "Python: 3.13.test<br/>Qt: 6.qt | PyQt: 6.pyqt<br/>"
        f"{platform_label}: System %2 {{release}} Release %3 {{machine}} (Machine %1 {{system}})"
    ) in texts
    if widget_language == "sv":
        assert (
            "Applikationen använder programvara från tredje part som distribueras under olika licenser. "
            "Se <b>Information om programvara från tredje part</b> för mer information."
        ) in texts
    else:
        assert (
            "The application uses third-party software distributed under various licenses. "
            "See <b>Third-party notices</b> for details."
        ) in texts


def test_missing_document_formats_warning(monkeypatch: pytest.MonkeyPatch, widget_language: str) -> None:
    document = "LICENSE {document} %1.txt"
    monkeypatch.setitem(about_dialog.LOCAL_DOCUMENTS, "license", document)
    monkeypatch.setattr(AboutDialog, "_find_document", staticmethod(lambda _name: None))
    dialogs = MagicMock(spec=DialogService)
    open_url = MagicMock()
    monkeypatch.setattr(about_dialog.QDesktopServices, "openUrl", open_url)
    dialog = AboutDialog(dialogs=dialogs)

    dialog._open_link("license")

    expected = f"Kunde inte hitta {document}." if widget_language == "sv" else f"Could not find {document}."
    dialogs.warn.assert_called_once_with(dialog, dialog.tr("Document unavailable"), expected)
    open_url.assert_not_called()


@pytest.mark.parametrize("link_id", ["repository", "license"])
def test_failed_link_warns_through_injected_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, widget_language: str, link_id: str
) -> None:
    document = tmp_path / "LICENSE.txt"
    monkeypatch.setattr(AboutDialog, "_find_document", staticmethod(lambda _name: document))
    open_url = MagicMock(return_value=False)
    monkeypatch.setattr(about_dialog.QDesktopServices, "openUrl", open_url)
    dialogs = MagicMock(spec=DialogService)
    dialog = AboutDialog(dialogs=dialogs)

    dialog._open_link(link_id)

    open_url.assert_called_once()
    dialogs.warn.assert_called_once_with(
        dialog, dialog.tr("Unable to open link"), dialog.tr("The requested link could not be opened.")
    )


def test_application_about_dialog_receives_shared_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from expo_jbm329.app import expo_studio

    dialogs = MagicMock(spec=DialogService)
    host = SimpleNamespace(_require_dialogs=lambda: dialogs)
    factory = MagicMock()
    monkeypatch.setattr(expo_studio, "AboutDialog", factory)

    expo_studio.ExpoStudio._show_about_dialog(host)

    factory.assert_called_once_with(parent=host, dialogs=dialogs)
    factory.return_value.exec.assert_called_once_with()


def test_about_dialog_formats_reordered_translated_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    def reordered_tr(self: AboutDialog, source: str) -> str:
        if source == "Qt: {qt_version} | PyQt: {pyqt_version}":
            return "PyQt: {pyqt_version} | Qt: {qt_version}"
        return QCoreApplication.translate("AboutDialog", source)

    monkeypatch.setattr(AboutDialog, "tr", reordered_tr)
    dialog = AboutDialog()
    texts = [label.text() for label in dialog.findChildren(about_dialog.QLabel)]

    assert any(f"PyQt: {about_dialog.PYQT_VERSION_STR} | Qt: {about_dialog.QT_VERSION_STR}" in text for text in texts)
