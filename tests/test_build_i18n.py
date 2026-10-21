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
    monkeypatch.setattr(build_i18n, "TS_FILES", [tmp_path / "app_en.ts", tmp_path / "app_sv.ts"])
    monkeypatch.setattr(build_i18n, "ensure_locales_dir", lambda: None)
    return mock


def test_main_does_not_remove_obsolete(check_call):
    build_i18n.main()

    assert check_call.call_count == 2
    for call in check_call.call_args_list:
        assert "--no-obsolete" not in call.args[0]


def test_main_clean_removes_obsolete(check_call):
    build_i18n.main_clean()

    assert check_call.call_count == 2
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
