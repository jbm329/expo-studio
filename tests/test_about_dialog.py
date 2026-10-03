from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication

from expo_jbm329.gui.dialogs import about_dialog
from expo_jbm329.gui.dialogs.about_dialog import AboutDialog


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
    dialog = AboutDialog()

    dialog._open_link("repository")

    assert opened_urls == ["https://github.com/jbm329/expo-studio"]


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
    dialog = AboutDialog()

    dialog._open_link("license")

    assert [Path(url) for url in opened_urls] == [document]


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
