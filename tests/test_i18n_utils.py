import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator

from expo_jbm329.build.build_utils import locales_dir, src_root
from expo_jbm329.utils import i18n_utils
from expo_jbm329.utils.i18n_utils import translate, translate_fmt


def test_translate_forwards_explicit_context_and_source(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = Mock(return_value="Översatt")
    monkeypatch.setattr(i18n_utils, "QCoreApplication", SimpleNamespace(translate=lookup))

    assert translate(context="ExampleContext", text="Source") == "Översatt"
    lookup.assert_called_once_with("ExampleContext", "Source")


def test_translate_fmt_formats_the_translated_template(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = Mock(return_value="Antal: {count}, fil: {file}")
    monkeypatch.setattr(i18n_utils, "QCoreApplication", SimpleNamespace(translate=lookup))

    assert translate_fmt("ExampleContext", "Count: {count}, file: {file}", count=3, file="data.csv") == (
        "Antal: 3, fil: data.csv"
    )
    lookup.assert_called_once_with("ExampleContext", "Count: {count}, file: {file}")


@pytest.mark.parametrize(
    ("template", "values"),
    [
        ("Oförändrad {count}", {}),
        ("Saknat {missing}", {"count": 3}),
        ("Felaktig {", {"count": 3}),
        ("Position {0}", {"count": 3}),
        ("Ogiltigt {count:d}", {"count": "text"}),
    ],
)
def test_translate_fmt_preserves_translated_template_on_formatting_failure(
    monkeypatch: pytest.MonkeyPatch, template: str, values: dict[str, object]
) -> None:
    lookup = Mock(return_value=template)
    monkeypatch.setattr(i18n_utils, "QCoreApplication", SimpleNamespace(translate=lookup))

    assert translate_fmt("ExampleContext", "Different English source", **values) == template


def test_translate_fmt_keeps_context_and_text_positional_only() -> None:
    with pytest.raises(TypeError):
        translate_fmt(context="ExampleContext", text="Source")


@pytest.mark.parametrize(
    ("language", "expected", "formatted"),
    [
        ("en", "Event coding: 1 = event, 0 = censored.", "Events: 3, censored: 5"),
        ("sv", "Händelsekodning: 1 = händelse, 0 = censurerad.", "Händelser: 3, censurerade: 5"),
    ],
)
def test_helpers_use_compiled_translations_and_english_source_fallback(
    language: str, expected: str, formatted: str
) -> None:
    translator = QTranslator()
    assert translator.load(str(locales_dir() / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    try:
        assert translate("SurvivalRegressionView", "Event coding: 1 = event, 0 = censored.") == expected
        assert (
            translate_fmt("SurvivalRegressionView", "Events: {events}, censored: {censored}", events=3, censored=5)
            == formatted
        )
        assert translate("MissingContext", "Uncatalogued text") == "Uncatalogued text"
        expected_status = (
            "Settings for schema cache updated."
            if language == "en"
            else "Inställningarna för schemacachen har uppdaterats."
        )
        assert translate("DbErrors", "Settings for schema cache updated.") == expected_status
    finally:
        QCoreApplication.removeTranslator(translator)


def test_new_helper_names_and_markers_survive_real_extraction(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text(
        "from PyQt6.QtCore import QT_TRANSLATE_NOOP\n"
        "from expo_jbm329.utils.i18n_utils import translate, translate_fmt\n"
        'LABEL = QT_TRANSLATE_NOOP("ExampleContext", "Rows: {count}")\n'
        'translate("ExampleContext", "Direct text")\n'
        'translate_fmt("ExampleContext", LABEL, count=3)\n',
        encoding="utf-8",
    )
    catalog = tmp_path / "example.ts"
    subprocess.run(["pylupdate6", str(source), "--ts", str(catalog)], check=True)
    root = ElementTree.parse(catalog).getroot()
    keys = {
        (context.findtext("name"), message.findtext("source"), message.findtext("comment", ""))
        for context in root.findall("context")
        for message in context.findall("message")
    }

    assert keys == {
        ("ExampleContext", "Direct text", ""),
        ("ExampleContext", "Rows: {count}", ""),
    }


def test_source_no_longer_imports_removed_helper_names() -> None:
    assert not hasattr(i18n_utils, "tr")
    assert not hasattr(i18n_utils, "tr_fmt")
    for path in src_root().rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "expo_jbm329.utils.i18n_utils":
                assert all(alias.name in {"translate", "translate_fmt"} for alias in node.names), path
                assert all(alias.asname is None for alias in node.names), path
