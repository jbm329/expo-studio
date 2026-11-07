from __future__ import annotations

import re
from xml.etree import ElementTree

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator

from expo_jbm329.build import build_i18n
from expo_jbm329.i18n.language import Language

LOCALES = build_i18n.locales_dir()


@pytest.mark.parametrize("language", list(Language))
def test_catalogs_do_not_have_question_marks_inside_words(language: Language) -> None:
    root = ElementTree.parse(LOCALES / f"app_{language.value}.ts").getroot()
    for context in root.findall("context"):
        for message in context.findall("message"):
            translation = message.find("translation")
            if translation is None:
                continue
            text = "".join(translation.itertext())
            key = (language.value, context.findtext("name"), message.findtext("source"))
            assert re.search(r"[^\W\d_]\?+[^\W\d_]", text) is None, key
            assert "\ufffd" not in text, key


@pytest.mark.parametrize("language", list(Language))
def test_compiled_manual_and_condition_messages_preserve_accents(language: Language) -> None:
    translator = QTranslator()
    assert translator.load(str(LOCALES / f"app_{language.value}.qm"))
    root = ElementTree.parse(LOCALES / f"app_{language.value}.ts").getroot()
    QCoreApplication.installTranslator(translator)
    try:
        for context in root.findall("context"):
            name = context.findtext("name", "")
            if name not in {"MenuController", "ExpoStudio", "ConditionEditor"}:
                continue
            for message in context.findall("message"):
                translation = message.find("translation")
                if translation is None or translation.get("type") in {"vanished", "obsolete"}:
                    continue
                source = message.findtext("source", "")
                if "?" in source:
                    continue
                text = translation.text or ""
                assert "?" not in text, (language.value, name, source)
                expected = source if language is Language.ENGLISH else text
                assert QCoreApplication.translate(name, source) == expected, (language.value, name, source)
        if language is Language.SWEDISH:
            assert QCoreApplication.translate("MenuController", "User manual") == "Användarhandbok"
            assert QCoreApplication.translate("ExpoStudio", "The user manual could not be opened.\n\n{url}") == (
                "Användarhandboken kunde inte öppnas.\n\n{url}"
            )
    finally:
        QCoreApplication.removeTranslator(translator)
