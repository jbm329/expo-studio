import ast
import subprocess
from dataclasses import replace
from html import unescape
from pathlib import Path
from shutil import copyfile
from string import Formatter
from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest
from PyQt6.QtCore import QCoreApplication

from expo_jbm329.build import build_i18n, build_locales
from expo_jbm329.i18n import translation_service
from expo_jbm329.i18n.language import Language
from expo_jbm329.services.analysis.outliers_charts import (
    build_outlier_histogram_labels,
    build_outlier_projection_labels,
)
from expo_jbm329.services.analysis.presentation import presentation_label_sources
from expo_jbm329.services.analysis.report import capture_report_labels
from tests.analysis.test_outliers_export import multivariate_result


@pytest.fixture
def check_call(monkeypatch, tmp_path):
    mock = MagicMock()
    monkeypatch.setattr(build_i18n.subprocess, "check_call", mock)
    monkeypatch.setattr(build_i18n, "TS_FILES", [tmp_path / f"app_{language.value}.ts" for language in Language])
    monkeypatch.setattr(build_i18n, "ensure_locales_dir", lambda: None)
    return mock


def test_main_does_not_remove_obsolete(check_call):
    build_i18n.main()

    assert check_call.call_count == len(Language)
    assert [Path(call.args[0][3]).name for call in check_call.call_args_list] == [
        f"app_{language.value}.ts" for language in Language
    ]
    for call in check_call.call_args_list:
        assert "--no-obsolete" not in call.args[0]


def test_main_clean_removes_obsolete(check_call):
    build_i18n.main_clean()

    assert check_call.call_count == len(Language)
    for call in check_call.call_args_list:
        assert "--no-obsolete" in call.args[0]


def test_main_clean_exits_on_failure(check_call):
    check_call.side_effect = subprocess.CalledProcessError(1, "pylupdate6")

    with pytest.raises(SystemExit) as exc_info:
        build_i18n.main_clean()

    assert exc_info.value.code == 1


def _catalog_messages(root: ElementTree.Element) -> dict[tuple[str, str, str], ElementTree.Element]:
    return {
        (context.findtext("name", ""), message.findtext("source", ""), message.findtext("comment", "")): message
        for context in root.findall("context")
        for message in context.findall("message")
    }


@pytest.fixture(scope="module")
def extracted_messages(tmp_path_factory):
    catalog = tmp_path_factory.mktemp("analysis-i18n") / "extracted.ts"
    build_i18n.run_pylupdate(catalog)
    return _catalog_messages(ElementTree.parse(catalog).getroot())


def test_english_catalog_uses_unfinished_source_fallback(
    extracted_messages: dict[tuple[str, str, str], ElementTree.Element],
) -> None:
    english = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / "app_en.ts").getroot())

    assert english.keys() == extracted_messages.keys()
    for key, message in english.items():
        assert message.get("numerus") != "yes", "Review English plural forms before extending this policy."
        translation = message.find("translation")
        assert translation is not None, key
        assert translation.get("type") == "unfinished", key
        assert not translation.text, key
        assert len(translation) == 0, key


@pytest.mark.parametrize(
    ("context", "old_source", "source"),
    [
        ("AboutDialog", "Copyright © %1 %2", "Copyright © {year} {author}"),
        (
            "AboutDialog",
            "The application uses third-party software distributed under various licenses. See <b>%1</b> for details.",
            "The application uses third-party software distributed under various licenses. See <b>{notices}</b> for details.",
        ),
        ("AboutDialog", "Python: %1", "Python: {python_version}"),
        ("AboutDialog", "Qt: %1 | PyQt: %2", "Qt: {qt_version} | PyQt: {pyqt_version}"),
        ("AboutDialog", "Platform: %1 %2 (%3)", "Platform: {system} {release} ({machine})"),
        ("AboutDialog", "Could not find %1.", "Could not find {document}."),
        (
            "ConnectionEditor",
            "Do you want to delete the connection '%1'?",
            "Do you want to delete the connection '{name}'?",
        ),
        ("ConnectionEditor", "Could not connect.\n\n%1", "Could not connect.\n\n{error}"),
        ("SettingsEditor", "Could not save settings:\n%1", "Could not save settings:\n{error}"),
        (
            "QtDialogService",
            "Do you want to permanently delete:\n\n%1%2",
            "Do you want to permanently delete:\n\n{name}{size_hint}",
        ),
        ("QtDialogService", "Column: %1", "Column: {column}"),
        ("QtDialogService", "Current value: %1", "Current value: {current_value}"),
    ],
)
def test_widget_named_fields_survive_extraction_and_compiled_translation(
    extracted_messages: dict[tuple[str, str, str], ElementTree.Element],
    widget_language: str,
    context: str,
    old_source: str,
    source: str,
) -> None:
    key = (context, source, "")
    old_key = (context, old_source, "")
    assert key in extracted_messages
    assert old_key not in extracted_messages
    catalog = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / f"app_{widget_language}.ts").getroot())
    assert old_key not in catalog
    translation = catalog[key].find("translation")
    assert translation is not None
    if widget_language == "en":
        assert translation.get("type") == "unfinished"
        assert not translation.text
        expected = source
    else:
        assert translation.get("type") is None
        assert translation.text
        expected = translation.text

    formatter = Formatter()
    source_fields = sorted(field for _, field, _, _ in formatter.parse(source) if field is not None)
    translated_fields = sorted(field for _, field, _, _ in formatter.parse(expected) if field is not None)
    assert translated_fields == source_fields
    assert all(field.isidentifier() for field in source_fields)
    assert QCoreApplication.translate(context, source) == expected


@pytest.mark.parametrize(
    "relative_path",
    [
        r"analysis\column_combo_box.py",
        r"analysis\report_page.py",
        r"service\categories\conversion.py",
        r"service\categories\order.py",
        r"service\categories\rename.py",
        r"service\common\localization.py",
        r"service\prompts\choice.py",
        r"service\prompts\column_operations.py",
        r"service\prompts\compare_between.py",
        r"service\prompts\datetime_conversion.py",
        r"service\prompts\filter_match.py",
        r"service\prompts\text.py",
    ],
)
def test_explicit_context_wrapper_markers_survive_extraction(
    extracted_messages: dict[tuple[str, str, str], ElementTree.Element], relative_path: str
) -> None:
    dialogs = Path(__file__).parents[1] / "src" / "expo_jbm329" / "gui" / "dialogs"
    module = dialogs.joinpath(*relative_path.split("\\"))
    markers = [
        node
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "QT_TRANSLATE_NOOP"
    ]
    assert markers
    swedish = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / "app_sv.ts").getroot())
    for marker in markers:
        key = (ast.literal_eval(marker.args[0]), ast.literal_eval(marker.args[1]), "")
        assert key in extracted_messages
        assert any(
            location.get("filename", "").replace("\\", "/").endswith(relative_path.replace("\\", "/"))
            for location in extracted_messages[key].findall("location")
        )
        translation = swedish[key].find("translation")
        assert translation is not None and translation.text
        assert translation.get("type") is None


def test_direct_qt_translation_is_confined_to_shared_helpers() -> None:
    package = Path(__file__).parents[1] / "src" / "expo_jbm329"
    unexpected: list[tuple[str, int]] = []
    for module in package.rglob("*.py"):
        if module.name.endswith("_rc.py") or module == package / "utils" / "i18n_utils.py":
            continue
        unexpected.extend(
            (str(module.relative_to(package)), node.lineno)
            for node in ast.walk(ast.parse(module.read_text(encoding="utf-8-sig")))
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "QCoreApplication"
                and node.attr == "translate"
            )
        )
    assert not unexpected


def test_compiled_catalogs_switch_from_english_to_swedish_and_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    locales = tmp_path / "locales"
    locales.mkdir()
    for language in ("en", "sv"):
        catalog = locales / f"app_{language}.ts"
        copyfile(build_i18n.locales_dir() / catalog.name, catalog)
        build_locales.compile_ts(catalog)

    monkeypatch.setattr(translation_service, "get_i18n_root", lambda: tmp_path)
    service = translation_service.TranslationService(logger=None)
    swedish = _catalog_messages(ElementTree.parse(locales / "app_sv.ts").getroot())
    keys = (
        ("AboutDialog", "Close", ""),
        (
            "SurvivalRegressionView",
            "There are too few events relative to the model terms to estimate this model.",
            "",
        ),
    )

    try:
        for language in ("en", "sv", "en"):
            service.switch_language(language)
            assert service._current_language == language
            assert service._translator.isEmpty() == (language == "en")
            for key in keys:
                expected = key[1] if language == "en" else swedish[key].findtext("translation")
                assert expected
                if language == "sv":
                    assert expected != key[1]
                assert QCoreApplication.translate(key[0], key[1]) == expected
            assert QCoreApplication.translate("UncataloguedContext", "Uncatalogued source") == "Uncatalogued source"
    finally:
        QCoreApplication.removeTranslator(service._translator)


def test_shared_analysis_and_report_labels_survive_real_extraction(extracted_messages):
    expected = set(presentation_label_sources()) | {
        (context, source) for context, source, _ in capture_report_labels().translated_labels
    }
    missing = {(context, source) for context, source in expected if (context, source, "") not in extracted_messages}

    assert not missing


def test_analysis_catalog_punctuation_preserves_entities_without_prose_semicolons(
    extracted_messages: dict[tuple[str, str, str], ElementTree.Element],
) -> None:
    swedish = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / "app_sv.ts").getroot())
    for key, message in extracted_messages.items():
        if not any(
            "/analysis/" in location.get("filename", "").replace("\\", "/") for location in message.findall("location")
        ):
            continue
        assert ";" not in unescape(key[1]), key
        translated = swedish[key].findtext("translation")
        assert translated, key
        assert ";" not in unescape(translated), key

    entity_key = ("RegressionView", "* marks coefficients significant at p &lt; {alpha}.", "")
    assert entity_key in extracted_messages
    assert "&lt;" in swedish[entity_key].findtext("translation", "")


def test_outlier_chart_builders_survive_real_extraction_with_finished_swedish(extracted_messages):
    sources: set[tuple[str, str, str]] = set()

    def translate(context: str, source: str) -> str:
        sources.add((context, source, ""))
        return source

    build_outlier_histogram_labels(translate)
    build_outlier_projection_labels(replace(multivariate_result(), sampled=True), translate)
    swedish = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / "app_sv.ts").getroot())
    for key in sources:
        assert key in extracted_messages
        assert any(
            "services/analysis/outliers_charts.py" in location.get("filename", "").replace("\\", "/")
            for location in extracted_messages[key].findall("location")
        )
        translation = swedish[key].find("translation")
        assert translation is not None and translation.text
        assert translation.get("type") not in ("unfinished", "vanished", "obsolete")


def test_explicit_context_analysis_calls_are_not_extracted_as_comments(extracted_messages):
    assert not [key for key in extracted_messages if key[0] == "AnalysisController" and key[2]]
    for key in (
        ("StatisticsView", "Histogram", ""),
        ("StatisticsView", "Boxplot", ""),
        ("StatisticsView", "No data", ""),
        ("ChiSquareView", "Adjusted standardized residuals", ""),
        ("PairedComparisonView", "Subject trajectories", ""),
        ("MultivariateOutliersView", "Anomaly score", ""),
        ("OutliersView", "Distance past fence", ""),
    ):
        assert key in extracted_messages


def test_schema_cache_status_uses_explicit_database_error_context(extracted_messages):
    key = ("DbErrors", "Settings for schema cache updated.", "")
    assert key in extracted_messages
    assert ("SchemaCacheManager", "DbErrors", "Settings for schema cache updated.") not in extracted_messages
    for language in ("en", "sv"):
        catalog = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / f"app_{language}.ts").getroot())
        assert key in catalog
        assert ("SchemaCacheManager", "DbErrors", "Settings for schema cache updated.") not in catalog
    swedish = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / "app_sv.ts").getroot())
    assert swedish[key].findtext("translation") == "Inställningarna för schemacachen har uppdaterats."


def test_rest_duplicate_name_marker_preserves_named_placeholder(extracted_messages):
    key = ("RestController", "A connection named '{name}' already exists.", "")
    assert key in extracted_messages
    for language in ("en", "sv"):
        catalog = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / f"app_{language}.ts").getroot())
        translation = catalog[key].find("translation")
        assert translation is not None
        if language == "en":
            assert translation.get("type") == "unfinished"
            assert not translation.text
        else:
            assert translation.get("type") is None
            assert translation.text == "Det finns redan en anslutning med namnet '{name}'."


def test_active_analysis_swedish_translations_are_finished_and_preserve_placeholders(extracted_messages):
    swedish = _catalog_messages(ElementTree.parse(build_i18n.locales_dir() / "app_sv.ts").getroot())
    formatter = Formatter()
    for key, message in extracted_messages.items():
        if not any(
            "/analysis/" in location.get("filename", "").replace("\\", "/") for location in message.findall("location")
        ):
            continue
        assert key in swedish, key
        translation = swedish[key].find("translation")
        assert translation is not None, key
        assert translation.get("type") not in ("unfinished", "vanished", "obsolete"), key
        translated = translation.text
        assert translated, key
        source_fields = sorted(field for _, field, _, _ in formatter.parse(key[1]) if field is not None)
        translated_fields = sorted(field for _, field, _, _ in formatter.parse(translated) if field is not None)
        assert translated_fields == source_fields, key
