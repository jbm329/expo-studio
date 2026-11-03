"""Compiled month translations and stable GUI-thread capture for worker output."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import get_ident
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pandas.testing import assert_series_equal
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QDialog, QTableView, QWidget

from expo_jbm329.gui.dialogs.workflows.derived_column import month_labels as month_capture
from expo_jbm329.gui.dialogs.workflows.derived_column.derived_column_dialog import DerivedColumnDialog
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    create_derived_column,
    preview_derived_column,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_time import DEFAULT_MONTH_LABELS
from expo_jbm329.workbench.controllers.derived_column_controller import DerivedColumnController

EXPECTED = {
    "en": (
        "January February March April May June July August September October November December",
        "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
    ),
    "sv": (
        "januari februari mars april maj juni juli augusti september oktober november december",
        "jan feb mars apr maj juni juli aug sep okt nov dec",
    ),
    "de": (
        "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
        "Jan. Feb. März Apr. Mai Juni Juli Aug. Sept. Okt. Nov. Dez.",
    ),
    "fr": (
        "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
        "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.",
    ),
    "it": (
        "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
        "gen feb mar apr mag giu lug ago set ott nov dic",
    ),
    "es": (
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
        "ene feb mar abr may jun jul ago sep oct nov dic",
    ),
    "pl": (
        "styczeń luty marzec kwiecień maj czerwiec lipiec sierpień wrzesień październik listopad grudzień",
        "sty lut mar kwi maj cze lip sie wrz paź lis gru",
    ),
}


def load_catalog(language):
    translator = QTranslator()
    catalog = Path(__file__).parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    return translator


@pytest.mark.parametrize("language", EXPECTED)
def test_all_compiled_month_labels_and_creation_preview_parity(qt_app, language):
    translator = load_catalog(language)
    qt_app.installTranslator(translator)
    try:
        labels = month_capture.capture_month_labels()
        assert labels.full == tuple(EXPECTED[language][0].split())
        assert labels.short == tuple(EXPECTED[language][1].split())
        source = pd.DataFrame({"When": pd.to_datetime([f"2026-{month:02d}-01" for month in range(1, 13)] + [None])})
        source.index = pd.Index([7] * len(source), name="row")
        for function, names, context, english in (
            ("MONTH", labels.full, "DerivedColumnMonths", DEFAULT_MONTH_LABELS.full),
            ("MONTHSHORT", labels.short, "DerivedColumnShortMonths", DEFAULT_MONTH_LABELS.short),
        ):
            for name in english:
                translated = translator.translate(context, name)
                if language != "en":
                    assert translated
                    assert "{" not in translated and "}" not in translated
            spec = DerivedColumnSpec("Result", f"{function}([When])", month_labels=labels)
            expected = pd.Series([*names, pd.NA], index=source.index, dtype="string", name="Result")
            assert_series_equal(create_derived_column(source, spec)["Result"], expected)
            assert_series_equal(preview_derived_column(source, spec).data["Result"], expected)
        default = create_derived_column(source, DerivedColumnSpec("Result", "MONTH([When])"))
        assert default["Result"].iloc[0] == "January"
        for function, expected in (
            ("WEEK", "W01"),
            ("QUARTER", "Q1"),
            ("TERTIAL", "T1"),
            ("YEARWEEK", "2026-W01"),
            ("YEARMONTH", "2026-01"),
            ("YEARQUARTER", "2026-Q1"),
            ("YEARTERTIAL", "2026-T1"),
        ):
            result = create_derived_column(
                source, DerivedColumnSpec("Result", f"{function}([When])", month_labels=labels)
            )
            assert result["Result"].iloc[0] == expected
    finally:
        qt_app.removeTranslator(translator)


def test_no_catalog_uses_english_fallback():
    assert month_capture.capture_month_labels() == DEFAULT_MONTH_LABELS


@pytest.mark.parametrize("function", ["MONTH", "MONTHSHORT"])
def test_real_dialog_captures_at_acceptance_and_worker_does_not_consult_locale(qt_app, monkeypatch, function):
    german, swedish = load_catalog("de"), load_catalog("sv")
    async_ops, apply = MagicMock(), MagicMock()
    source = pd.DataFrame({"When": pd.to_datetime(["2026-03-01", "2026-04-01", "2026-05-01", None])})
    view = QTableView()
    controller = DerivedColumnController(
        async_ops=async_ops,
        apply_to_view=apply,
        dialogs=MagicMock(),
        main_window=QWidget(),
    )
    gui_thread = get_ident()
    original_translate = month_capture.translate
    calls = []

    def translate_on_gui_thread(context, text):
        assert get_ident() == gui_thread
        calls.append((context, text))
        return original_translate(context, text)

    monkeypatch.setattr(month_capture, "translate", translate_on_gui_thread)
    captured = []

    def accept_with_language_switch(dialog):
        dialog._column_name_edit.setText(" Group ")
        dialog._formula_edit.setPlainText(f" {function}([When]) ")
        qt_app.removeTranslator(german)
        qt_app.installTranslator(swedish)
        dialog._on_accept()
        captured.append(dialog.get_result())
        return dialog.result()

    monkeypatch.setattr(DerivedColumnDialog, "exec", accept_with_language_switch)
    qt_app.installTranslator(german)
    try:
        controller.create_derived_column(view, source, 0)
        assert len(calls) == 24
        assert captured[0].month_labels.full[0] == "januari"
        qt_app.removeTranslator(swedish)
        qt_app.installTranslator(german)
        work = async_ops.run_dataframe_operation.call_args.kwargs["work"]
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(work).result()
        assert result[0]
        assert len(calls) == 24
        expected = ["mars", "april", "maj", pd.NA] if function == "MONTH" else ["mars", "apr", "maj", pd.NA]
        assert_series_equal(result[1]["Group"], pd.Series(expected, dtype="string", name="Group"))
        preview = preview_derived_column(source, captured[0])
        assert_series_equal(preview.data["Group"], result[1]["Group"])
        async_ops.run_dataframe_operation.call_args.kwargs["apply_result"](result)
        assert_series_equal(apply.call_args.args[1]["Group"], result[1]["Group"])
        assert captured[0].month_labels.full[0] == "januari"
    finally:
        qt_app.removeTranslator(german)
        qt_app.removeTranslator(swedish)


def test_rejected_dialog_does_not_capture_month_labels(monkeypatch):
    dialog = DerivedColumnDialog(
        df=pd.DataFrame({"When": pd.to_datetime(["2026-01-01"])}),
        validate_callback=lambda name, formula: pytest.fail("Blank dialog must not validate"),
    )
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.derived_column.derived_column_dialog.capture_month_labels",
        lambda: pytest.fail("Rejected dialog must not capture"),
    )
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.get_result() is None
