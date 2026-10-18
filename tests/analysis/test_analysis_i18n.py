from __future__ import annotations

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, QTranslator
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton, QTabWidget, QWidget

from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog
from expo_jbm329.gui.dialogs.analysis.clustering_view import ClusteringView
from expo_jbm329.gui.dialogs.analysis.correlation_view import CorrelationView
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.report_notes_dialog import ReportNotesDialog
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.chi_square import initialize_chi_square
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.clustering_export import ClusteringExportSnapshot
from expo_jbm329.services.analysis.correlation import (
    SCATTER_SAMPLE_SIZE,
    CorrelationMethod,
    analyze_correlation_matrix,
    analyze_correlation_pair,
)
from expo_jbm329.services.analysis.correlation_charts import (
    build_correlation_chart_labels,
    build_correlation_pair_presentation,
)
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.group_comparison import initialize_group_comparison
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.paired_comparison import initialize_paired_comparison
from expo_jbm329.services.analysis.presentation import build_analysis_presentation, presentation_label_sources
from expo_jbm329.services.analysis.report import (
    ReportDocument,
    capture_report_labels,
    create_report_entry,
    prepare_report_content,
    render_prepared_report_html,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat, analyze_descriptive_statistics
from expo_jbm329.services.analysis.statistics_charts import build_statistics_chart_presentation
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.utils.format_utils import capture_chart_numeric_locale
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportSnapshot

LOCALES = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales"


@pytest.mark.parametrize("language", ["en", "sv"])
@pytest.mark.parametrize(
    "factory",
    [
        group_snapshot,
        lambda: group_snapshot(3),
        chi_snapshot,
        lambda: chi_snapshot(3),
        paired_snapshot,
        lambda: paired_snapshot(3),
    ],
)
def test_hypothesis_family_identity_matches_configuration_dialogs_and_report(
    language: str, factory: Callable[[], HypothesisExportSnapshot]
) -> None:
    translator = QTranslator()
    assert translator.load(str(LOCALES / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    frame = pd.DataFrame({"value": [1.0, 2.0, 3.0], "other": [2.0, 4.0, 5.0], "group": ["a", "a", "b"]})
    snapshot = factory()
    widgets: list[QWidget] = []
    try:
        config = HypothesisTestsConfigWidget(
            initialize_group_comparison(frame),
            initialize_chi_square(frame),
            initialize_paired_comparison(frame),
        )
        presentation = build_analysis_presentation(
            AnalysisCategory.HYPOTHESIS_TESTS, snapshot, QCoreApplication.translate
        )
        selector = config.findChild(QComboBox)
        assert selector is not None
        family = selector.itemText(selector.findData(snapshot.test.value))
        assert presentation.title == f"{presentation.category} — {family}"
        computed_label = QCoreApplication.translate("HypothesisPresentation", "Tests computed:")
        assert presentation.configuration[-1].label == computed_label
        assert presentation.configuration[-1].items
        entry = create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DatasetRef("source", "Dataset", 3, 3), snapshot)
        export = AnalysisExportDialog(hypothesis=snapshot)
        notes = ReportNotesDialog(
            presentation.title,
            components=entry.components,
            configuration=presentation.summary_lines,
            component_translation_context="HypothesisPresentation",
        )
        widgets.extend((config, export, notes))
        identity = "\n".join((presentation.title, *presentation.summary_lines))
        assert identity in [label.text() for label in export.findChildren(QLabel)]
        assert presentation.title in [label.text() for label in notes.findChildren(QLabel)]
        assert "\n".join(presentation.summary_lines) in [label.text() for label in notes.findChildren(QLabel)]
        assert [choice.text() for choice in export.findChildren(QCheckBox)] == [
            choice.text() for choice in notes.findChildren(QCheckBox)
        ]
        document = ReportDocument()
        document.upsert(entry.with_selection(("test_results",), ""))
        captured = capture_report_labels(QCoreApplication.translate)
    finally:
        QCoreApplication.removeTranslator(translator)
        for widget in widgets:
            widget.close()
    prepared = prepare_report_content(document, labels=captured)
    assert prepared.entries[0].title == presentation.title
    assert prepared.entries[0].configuration == presentation.configuration
    html = render_prepared_report_html(prepared)
    assert f"<h2>{presentation.title}</h2>" in html
    assert f"<dt>{computed_label}</dt>" in html


def test_compiled_swedish_shared_labels_match_finished_catalog() -> None:
    translator = QTranslator()
    assert translator.load(str(LOCALES / "app_sv.qm"))
    catalog = ElementTree.parse(LOCALES / "app_sv.ts").getroot()
    translations = {
        (context.findtext("name"), message.findtext("source")): message.findtext("translation")
        for context in catalog.findall("context")
        for message in context.findall("message")
        if message.find("translation") is not None
        and message.find("translation").get("type") not in ("unfinished", "obsolete", "vanished")
    }

    assert QCoreApplication.installTranslator(translator)
    try:
        for context, source in presentation_label_sources():
            assert translations[context, source]
            assert QCoreApplication.translate(context, source) == translations[context, source]
    finally:
        QCoreApplication.removeTranslator(translator)


@pytest.mark.parametrize("language", ["en", "sv"])
def test_recent_analysis_labels_translate_in_views_dialogs_and_captured_reports(language: str) -> None:
    translator = QTranslator()
    assert translator.load(str(LOCALES / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    swedish = language == "sv"
    metadata = "Kolumnmetadata" if swedish else "Columns metadata"
    continuous = "Kontinuerliga" if swedish else "Continuous"
    categorical = "Kategoriska" if swedish else "Categorical"
    distribution = "Fördelning" if swedish else "Distribution"
    histogram = "Histogram"
    boxplot = "Boxplot"
    count_header = "Antal (% icke-saknade)" if swedish else "Count (% non-missing)"
    frame = pd.DataFrame({
        "value": [1.0, None, 3.0],
        "empty": pd.Series([None, None, None], dtype="float64"),
        "group": ["a", "a", "b"],
    })
    source = DatasetRef("source", "Dataset", 3, 2)
    overview = analyze_dataset_overview(frame)
    statistics = analyze_descriptive_statistics(frame)
    document = ReportDocument()
    document.upsert(create_report_entry(AnalysisCategory.OVERVIEW, source, overview).with_selection(("Columns",), ""))
    statistics_entry = create_report_entry(AnalysisCategory.STATISTICS, source, statistics)
    document.upsert(statistics_entry.with_selection(("Continuous", "Categorical", "Charts"), ""))
    widgets = []
    try:
        overview_view = OverviewView(overview)
        statistics_view = StatisticsView(statistics)
        export = AnalysisExportDialog(statistics=statistics)
        notes = ReportNotesDialog(
            "Statistics",
            components=statistics_entry.components,
            component_translation_context="StatisticsView",
        )
        widgets.extend((overview_view, statistics_view, export, notes))
        assert [axis.get_title() for axis in statistics_view._figure.axes] == [histogram, boxplot]  # noqa: SLF001
        empty_presentation = build_statistics_chart_presentation(statistics.columns[1], QCoreApplication.translate)
        assert empty_presentation.no_data_label == ("Ingen data" if swedish else "No data")
        statistics_view.show_distribution_for("empty")
        assert [text.get_text() for axis in statistics_view._figure.axes for text in axis.texts] == [
            empty_presentation.no_data_label,
            empty_presentation.no_data_label,
        ]  # noqa: SLF001
        assert metadata in [label.text() for label in overview_view.findChildren(QLabel)]
        assert distribution in [label.text() for label in statistics_view.findChildren(QLabel)]
        tabs = statistics_view.findChild(QTabWidget)
        assert tabs is not None
        assert [tabs.tabText(index) for index in range(tabs.count())] == [continuous, categorical]
        assert [choice.text() for choice in notes.findChildren(QCheckBox)] == [continuous, categorical, distribution]
        choices = {choice.text(): choice for choice in export.findChildren(QCheckBox)}
        assert set(choices) == {continuous, categorical, distribution}
        choices[distribution].setChecked(True)
        formats = export.findChild(QComboBox)
        assert formats is not None
        formats.setCurrentIndex(formats.findData(StatisticsExportFormat.CSV))
        export_button = next(
            button
            for button in export.findChildren(QPushButton)
            if button.text() == ("Exportera" if swedish else "Export")
        )
        expected_reason = (
            "Fördelning är endast tillgänglig i Excel. Avmarkera Fördelning för att fortsätta."
            if swedish
            else "Distribution is available only in Excel. Uncheck Distribution to continue."
        )
        assert export_button.toolTip() == expected_reason
        captured = capture_report_labels(QCoreApplication.translate)
    finally:
        QCoreApplication.removeTranslator(translator)
        for widget in widgets:
            widget.close()

    prepared = prepare_report_content(document, labels=captured)
    html = render_prepared_report_html(prepared)
    charts = next(component for component in prepared.entries[1].components if component.key == "Charts")
    assert charts.show_chart_captions
    assert charts.charts[0].heading == ""
    assert charts.charts[0].captions == ()
    assert charts.charts[0].accessible_name == "value"
    assert f"<h3>{metadata}</h3>" in html
    assert f"<h3>{continuous}</h3>" in html
    assert f"<h3>{categorical}</h3>" in html
    assert f"<h3>{distribution}</h3>" in html
    assert f'<th scope="col">{count_header}</th>' in html
    assert 'alt="value"' in html
    assert "<figcaption>" not in html


@pytest.mark.parametrize("language", ["en", "sv"])
@pytest.mark.parametrize("method", list(CorrelationMethod))
def test_correlation_compiled_chart_labels_captions_and_accessibility_survive_capture(language, method):
    translator = QTranslator()
    assert translator.load(str(LOCALES / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    x = np.arange(SCATTER_SAMPLE_SIZE + 1, dtype=float)
    frame = pd.DataFrame({"x <one>": x, "y & two": x * 1.23456 + 0.56789})
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), method)
    assert matrix is not None and matrix.error is None
    detail = analyze_correlation_pair(frame, *frame.columns, method)
    document = ReportDocument()
    document.upsert(
        create_report_entry(
            AnalysisCategory.CORRELATION,
            DatasetRef("source", "Dataset", len(frame), 2),
            CorrelationExportSnapshot(matrix, frame),
        ).with_selection(("matrix_plot", "scatterplots"), "")
    )
    view = None
    try:
        view = CorrelationView(matrix, detail)
        labels = build_correlation_chart_labels(matrix, QCoreApplication.translate, capture_chart_numeric_locale())
        presentation = build_correlation_pair_presentation(detail, labels)
        captured = capture_report_labels(QCoreApplication.translate)
        statistics = "\n".join(label.text() for label in view.pair_panel().findChildren(QLabel))
        assert all(escape(caption) in statistics for caption in presentation.metadata.captions)
        expected_matrix = "Korrelationsmatris" if language == "sv" else "Correlation matrix"
        assert labels.matrix_title == expected_matrix
        assert presentation.metadata.captions[0].startswith(
            "Minsta kvadratlinje:" if language == "sv" else "Least-squares line:"
        )
        assert len(presentation.metadata.captions) == (2 if method is CorrelationMethod.PEARSON else 3)
    finally:
        QCoreApplication.removeTranslator(translator)
        if view is not None:
            view.close()
    prepared = prepare_report_content(document, labels=captured)
    matrix_image = prepared.entries[0].components[0].charts[0]
    pair_image = prepared.entries[0].components[1].charts[0]
    assert matrix_image.heading == pair_image.heading == ""
    assert matrix_image.accessible_name == labels.matrix_title
    assert matrix_image.captions == ()
    assert pair_image.accessible_name == presentation.title
    assert pair_image.captions == presentation.metadata.captions
    html = render_prepared_report_html(prepared)
    assert f'alt="{escape(presentation.title, quote=True)}"' in html
    assert f'alt="{expected_matrix}"' in html
    assert f"<h3>{expected_matrix}</h3>" in html
    assert html.count("<figcaption>") == 1
    caption_html = html.split("<figcaption>", 1)[1].split("</figcaption>", 1)[0]
    assert escape(presentation.title) not in caption_html
    assert all(escape(caption) in caption_html for caption in presentation.metadata.captions)


@pytest.mark.parametrize("language", ["en", "sv"])
@pytest.mark.parametrize("method", list(ClusteringMethod))
def test_clustering_compiled_chart_presentation_matches_view_and_report(language, method):
    translator = QTranslator()
    assert translator.load(str(LOCALES / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    sampled_snapshot = clustering_snapshot(method, sampled=True, dbscan_min_samples=3)
    view = None
    try:
        view = ClusteringView(sampled_snapshot.result)
        labels = view.chart_labels()
        snapshot = ClusteringExportSnapshot(
            sampled_snapshot.result,
            labels,
            sampled_snapshot.notes,
            sampled_snapshot.capture_id,
        )
        live_axes = view.findChildren(FigureCanvasQTAgg)[0].figure.axes[0]
        legend = live_axes.get_legend()
        assert legend is not None
        expected_legend = tuple(
            labels.cluster_name(label) for label in sorted(set(sampled_snapshot.result.sample_labels))
        )
        assert live_axes.get_title() == labels.metadata.accessible_name
        assert live_axes.get_xlabel() == labels.pc1_axis
        assert live_axes.get_ylabel() == labels.pc2_axis
        assert tuple(text.get_text() for text in legend.get_texts()) == expected_legend

        document = ReportDocument()
        entry = create_report_entry(AnalysisCategory.CLUSTERING, DatasetRef("source", "Dataset", 10, 2), snapshot)
        document.upsert(entry.with_selection(("charts",), ""))
        captured = capture_report_labels(QCoreApplication.translate)
        expected_caption = labels.metadata.captions[0]
        expected_title = labels.metadata.accessible_name
        expected_component_label = QCoreApplication.translate("ClusteringPresentation", "Cluster projection")
    finally:
        QCoreApplication.removeTranslator(translator)
        if view is not None:
            view.close()

    prepared = prepare_report_content(document, labels=captured)
    image = prepared.entries[0].components[0].charts[0]
    html = render_prepared_report_html(prepared)
    assert image.heading == ""
    assert image.accessible_name == expected_title
    assert image.captions == (expected_caption,)
    assert f'alt="{escape(expected_title, quote=True)}"' in html
    assert f"<p>{escape(expected_caption)}</p>" in html
    assert f"<h3>{expected_component_label}</h3>" in html
    assert expected_title not in html.split("<figcaption>", 1)[1].split("</figcaption>", 1)[0]
