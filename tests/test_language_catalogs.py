from __future__ import annotations

import re
import subprocess
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter
from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest
from PyQt6.QtCore import QCoreApplication, QLocale, QTranslator

from expo_jbm329.app.settings.settings_editor import LANGUAGES
from expo_jbm329.build import build_i18n, build_locales
from expo_jbm329.i18n import translation_service
from expo_jbm329.i18n.language import Language
from expo_jbm329.utils.i18n_utils import translate_fmt

LOCALES = build_i18n.locales_dir()
TRANSLATION_LOCALES = {
    Language.SWEDISH: "sv_SE",
    Language.GERMAN: "de_DE",
    Language.FRENCH: "fr_FR",
    Language.ITALIAN: "it_IT",
    Language.SPANISH: "es_ES",
    Language.POLISH: "pl_PL",
}
CLOSE_LABELS = {
    Language.ENGLISH: "Close",
    Language.SWEDISH: "Stäng",
    Language.GERMAN: "Schließen",
    Language.FRENCH: "Fermer",
    Language.ITALIAN: "Chiudi",
    Language.SPANISH: "Cerrar",
    Language.POLISH: "Zamknij",
}
COLUMN_LABELS = {
    Language.ENGLISH: "Column: {column}",
    Language.SWEDISH: "Kolumn: {column}",
    Language.GERMAN: "Spalte: {column}",
    Language.FRENCH: "Colonne : {column}",
    Language.ITALIAN: "Colonna: {column}",
    Language.SPANISH: "Columna: {column}",
    Language.POLISH: "Kolumna: {column}",
}


def _messages(root: ElementTree.Element) -> dict[tuple[str, str, str], ElementTree.Element]:
    entries = [
        ((context.findtext("name", ""), message.findtext("source", ""), message.findtext("comment", "")), message)
        for context in root.findall("context")
        for message in context.findall("message")
        if message.find("translation") is None
        or message.find("translation").get("type") not in ("vanished", "obsolete")
    ]
    assert len(entries) == len(dict(entries)), "Duplicate active translation keys"
    return dict(entries)


class _Markup(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.tags: list[tuple[str, str, tuple[tuple[str, str | None], ...]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(("start", tag, tuple(sorted(attrs))))

    def handle_endtag(self, tag: str) -> None:
        self.tags.append(("end", tag, ()))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(("empty", tag, tuple(sorted(attrs))))


def _markup(text: str) -> list[tuple[str, str, tuple[tuple[str, str | None], ...]]]:
    parser = _Markup()
    parser.feed(text)
    parser.close()
    return parser.tags


def _fields(text: str) -> Counter[tuple[str, str, str | None]]:
    return Counter(
        (field, specification, conversion)
        for _, field, specification, conversion in Formatter().parse(text)
        if field is not None
    )


@pytest.fixture(scope="module")
def fresh_catalog(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str, str], ElementTree.Element]:
    path = tmp_path_factory.mktemp("language-extraction") / "extracted.ts"
    build_i18n.run_pylupdate(path)
    return _messages(ElementTree.parse(path).getroot())


def test_language_registry_matches_settings_build_and_shipped_catalogs() -> None:
    codes = {language.value for language in Language}
    assert codes == {"en", "sv", "de", "fr", "it", "es", "pl"}
    assert len({language.display_name for language in Language}) == len(Language)
    assert [(language.display_name, language.value) for language in Language] == LANGUAGES
    assert set(build_i18n.TS_FILES) == {LOCALES / f"app_{code}.ts" for code in codes}
    assert {path.stem.removeprefix("app_") for path in LOCALES.glob("app_*.ts")} == codes
    assert {path.stem.removeprefix("app_") for path in LOCALES.glob("app_*.qm")} == codes


@pytest.mark.parametrize("language", list(Language))
def test_catalogs_have_full_extracted_coverage_and_safe_translations(
    language: Language, fresh_catalog: dict[tuple[str, str, str], ElementTree.Element]
) -> None:
    root = ElementTree.parse(LOCALES / f"app_{language.value}.ts").getroot()
    assert root.get("version") == "2.1"
    if language is not Language.ENGLISH:
        assert root.get("language") == TRANSLATION_LOCALES[language]
        assert root.get("sourcelanguage") == "en_US"
    messages = _messages(root)
    assert messages.keys() == fresh_catalog.keys()
    for key, message in messages.items():
        assert message.get("numerus") != "yes", "Review plural forms before adding numerus messages"
        translation = message.find("translation")
        assert translation is not None, key
        assert not list(translation), key
        if language is Language.ENGLISH:
            assert translation.get("type") == "unfinished", key
            assert not translation.text, key
            continue
        assert translation.get("type") is None, key
        translated = translation.text
        assert translated is not None and translated.strip(), key
        source = key[1]
        assert _fields(translated) == _fields(source), key
        assert _markup(translated) == _markup(source), key
        assert Counter(re.findall(r"https?://[^\s<>\"']+", translated)) == Counter(
            re.findall(r"https?://[^\s<>\"']+", source)
        ), key
        # Existing Swedish wording has intentional layout differences.
        if language is not Language.SWEDISH:
            assert translated.count("\n") == source.count("\n"), key
            assert translated.startswith("\n") == source.startswith("\n"), key
            assert translated.endswith("\n") == source.endswith("\n"), key


@pytest.fixture(scope="module")
def compiled_locales(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("compiled-languages")
    for language in Language:
        name = f"app_{language.value}.ts"
        (directory / name).write_bytes((LOCALES / name).read_bytes())
    original = build_locales.locales_dir
    try:
        build_locales.locales_dir = lambda: directory
        build_locales.main()
    finally:
        build_locales.locales_dir = original
    return directory


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("catalog_source", ["shipped", "rebuilt"])
def test_each_compiled_catalog_translates_representative_messages(
    language: Language, catalog_source: str, compiled_locales: Path
) -> None:
    translator = QTranslator()
    directory = LOCALES if catalog_source == "shipped" else compiled_locales
    assert translator.load(str(directory / f"app_{language.value}.qm"))
    QCoreApplication.installTranslator(translator)
    try:
        assert QCoreApplication.translate("AboutDialog", "Close") == CLOSE_LABELS[language]
        value = "Dataset {column} %1"
        assert translate_fmt("QtDialogService", "Column: {column}", column=value) == COLUMN_LABELS[language].format(
            column=value
        )
        catalog = _messages(ElementTree.parse(LOCALES / f"app_{language.value}.ts").getroot())
        for context, source in (
            (
                "AboutDialog",
                (
                    "The application uses third-party software distributed under various licenses. "
                    "See <b>{notices}</b> for details."
                ),
            ),
            ("ColumnComboBox", "Not available: {count} distinct values (at least {minimum} are needed)."),
            ("ReportPage", "{rows} rows x {columns} columns - {date}"),
            ("SurvivalRegressionView", "There are too few events relative to the model terms to estimate this model."),
        ):
            expected = source if language is Language.ENGLISH else catalog[context, source, ""].findtext("translation")
            assert QCoreApplication.translate(context, source) == expected
    finally:
        QCoreApplication.removeTranslator(translator)


def test_reload_settings_switches_all_languages_and_preserves_system_locale(
    monkeypatch: pytest.MonkeyPatch, compiled_locales: Path, tmp_path: Path
) -> None:
    monkeypatch.setattr(translation_service, "get_i18n_root", lambda: tmp_path)
    service = translation_service.TranslationService(logger=None)
    service._locales_dir = compiled_locales
    system_locale = QLocale.system().name()
    default_locale = QLocale().name()
    try:
        for language in [*Language, Language.ENGLISH]:
            service.reload_settings({"workbench": {"language": f" {language.value.upper()} "}})
            assert service._current_language == language.value
            assert QCoreApplication.translate("AboutDialog", "Close") == CLOSE_LABELS[language]
            assert service._translator.isEmpty() == (language is Language.ENGLISH)
            assert QLocale.system().name() == system_locale
            assert QLocale().name() == default_locale
        service.reload_settings({"workbench": {"language": "xx"}})
        assert service._current_language == "en"
        assert QCoreApplication.translate("UncataloguedContext", "Uncatalogued source") == "Uncatalogued source"
    finally:
        QCoreApplication.removeTranslator(service._translator)


def test_compiler_discovers_extra_catalogs_in_sorted_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("app_zz.ts", "app_de.ts", "not_a_catalog.ts"):
        (tmp_path / name).touch()
    monkeypatch.setattr(build_locales, "locales_dir", lambda: tmp_path)
    assert [path.name for path in build_locales.find_ts_files()] == ["app_de.ts", "app_zz.ts"]


def test_compiler_reports_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(build_locales, "find_ts_files", lambda: [tmp_path / "app_de.ts"])
    compile_catalog = MagicMock(side_effect=subprocess.CalledProcessError(1, "pyside6-lrelease"))
    monkeypatch.setattr(build_locales, "compile_ts", compile_catalog)
    with pytest.raises(SystemExit) as error:
        build_locales.main()
    assert error.value.code == 1


def test_release_spec_includes_all_compiled_languages() -> None:
    specification = (Path(__file__).parents[1] / "expo.spec").read_text(encoding="utf-8")
    assert '"src/expo_jbm329/i18n/locales/*.qm"' in specification
