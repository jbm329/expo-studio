from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton

from expo_jbm329.gui.dialogs.analysis.report_page import ReportPage
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.presentation import build_analysis_presentation
from expo_jbm329.services.analysis.report import ReportComponent, ReportEntry, create_report_entry
from expo_jbm329.utils.dataset_ref import DatasetRef
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
from tests.analysis.test_pca_export import pca_snapshot
from tests.analysis.test_regression_export import linear_snapshot


def _entry(entry_id: str, dataset: str) -> ReportEntry:
    snapshot = pca_snapshot()
    components = (ReportComponent("feature_loadings", "Feature loadings", "table"),)
    return ReportEntry(
        entry_id=entry_id,
        dataset_id=f"tab-{dataset}",
        dataset_name=dataset,
        dataset_rows=10,
        dataset_columns=2,
        category=AnalysisCategory.PCA,
        analysis_date="2026-10-12",
        app_version="1.0.0",
        snapshot=snapshot,
        components=components,
        selected_components=("feature_loadings",),
        capture_id=snapshot.capture_id,
    )


def test_report_page_starts_with_empty_details_and_no_entries():
    page = ReportPage()

    assert page.report_title() == ""
    assert page.report_description() == ""
    assert page.findChild(QListWidget).count() == 0
    assert any("No analyses have been added" in label.text() for label in page.findChildren(QLabel))


@pytest.mark.parametrize("method", list(ClusteringMethod))
def test_clustering_report_list_uses_configured_title_and_applied_settings(method):
    snapshot = clustering_snapshot(method)
    presentation = build_analysis_presentation(AnalysisCategory.CLUSTERING, snapshot, lambda _context, source: source)
    entry = create_report_entry(AnalysisCategory.CLUSTERING, DatasetRef("tab", "Source", 10, 2), snapshot)
    page = ReportPage()
    page.set_entries((entry,))
    item = page.findChild(QListWidget).item(0)
    assert item.text() == "\n".join((f"{presentation.title} - Source", *presentation.summary_lines))


def test_report_page_collects_only_plain_text_details():
    page = ReportPage()
    page.findChild(QLineEdit).setText("<b>Report title</b>")
    page.findChild(QPlainTextEdit).setPlainText("<script>description</script>\nSecond line")

    assert page.report_title() == "<b>Report title</b>"
    assert page.report_description() == "<script>description</script>\nSecond line"
    assert page.findChild(QListWidget).count() == 0


def test_report_processing_controls_are_disabled_and_explained():
    page = ReportPage()
    buttons = page.findChildren(QPushButton)

    assert {button.text() for button in buttons} == {
        "Move up",
        "Move down",
        "Edit entry",
        "Remove",
        "Generate HTML report",
        "Preview",
    }
    assert all(not button.isEnabled() for button in buttons)
    assert not page._generate_button.toolTip()  # noqa: SLF001


def test_report_page_lists_metadata_and_enables_entry_actions():
    page = ReportPage()
    entries = (_entry("one", "Employees"), _entry("two", "Sales"))

    page.set_entries(entries)

    listing = page.findChild(QListWidget)
    assert listing.count() == 2
    assert listing.item(0).text().splitlines() == [
        "PCA - Employees",
        "Features: x, y, z",
        "Standardization: Standardized",
    ]
    assert "10 rows x 2 columns" in listing.item(0).toolTip()
    assert not page._move_up_button.isEnabled()  # noqa: SLF001
    assert page._move_down_button.isEnabled()  # noqa: SLF001
    assert page._edit_button.isEnabled()  # noqa: SLF001
    assert page._remove_button.isEnabled()  # noqa: SLF001
    assert page._preview_button.isEnabled()  # noqa: SLF001
    assert page._generate_button.isEnabled()  # noqa: SLF001
    assert not page._empty_message.isVisible()  # noqa: SLF001


def test_correlation_report_list_shows_configured_title_and_ordered_columns():
    page = ReportPage()
    entry = create_report_entry(
        AnalysisCategory.CORRELATION,
        DatasetRef("correlation-tab", "Employees", 12, 4),
        correlation_snapshot(),
    )

    page.set_entries((entry,))

    item = page.findChild(QListWidget).item(0)
    assert item.text().startswith("Correlation — Pearson - Employees\nColumns: ")
    assert item.text().splitlines()[1] == f"Columns: {', '.join(entry.snapshot.matrix.columns)}"
    assert item.sizeHint().height() > 24


def test_regression_report_list_shows_applied_model_and_configuration_roles():
    page = ReportPage()
    entry = create_report_entry(
        AnalysisCategory.REGRESSION,
        DatasetRef("regression-tab", "Employees", 100, 4),
        linear_snapshot(),
    )

    page.set_entries((entry,))

    text = page.findChild(QListWidget).item(0).text()
    assert text.startswith("Regression — Linear regression - Employees")
    assert "Outcome: y" in text
    assert "Predictors: x, g" in text
    assert "Reference levels: g = b" in text
    assert "Modeled terms: (Intercept)" in text


def test_report_page_emits_selected_entry_actions_and_preserves_selection():
    page = ReportPage()
    entries = (_entry("one", "Employees"), _entry("two", "Sales"))
    edits: list[str] = []
    removals: list[str] = []
    moves: list[tuple[str, int]] = []
    page.edit_requested.connect(edits.append)
    page.remove_requested.connect(removals.append)
    page.move_requested.connect(lambda entry_id, offset: moves.append((entry_id, offset)))
    page.set_entries(entries)
    page.select_entry("two")

    page._edit_button.click()  # noqa: SLF001
    page._move_down_button.click()  # noqa: SLF001
    page._move_up_button.click()  # noqa: SLF001
    page._remove_button.click()  # noqa: SLF001

    assert edits == ["two"]
    assert removals == ["two"]
    assert moves == [("two", -1)]


def test_report_preview_is_enabled_only_for_nonempty_idle_reports():
    page = ReportPage()
    requests: list[bool] = []
    page.preview_requested.connect(lambda: requests.append(True))

    page._preview_button.click()  # noqa: SLF001
    assert requests == []
    page.set_entries((_entry("one", "Employees"),))
    page._preview_button.click()  # noqa: SLF001
    assert requests == [True]
    page.set_preview_busy(True)
    assert not page._generate_button.isEnabled()  # noqa: SLF001
    page.set_entries((_entry("two", "Sales"),))
    assert not page._preview_button.isEnabled()  # noqa: SLF001
    page._preview_button.click()  # noqa: SLF001
    assert requests == [True]
    page.set_preview_busy(False)
    assert page._generate_button.isEnabled()  # noqa: SLF001
    assert page._preview_button.isEnabled()  # noqa: SLF001
    page.set_entries(())
    assert not page._preview_button.isEnabled()  # noqa: SLF001
    assert not page._generate_button.isEnabled()  # noqa: SLF001


def test_report_generate_emits_only_when_report_is_nonempty_and_idle():
    page = ReportPage()
    requests: list[bool] = []
    page.generate_requested.connect(lambda: requests.append(True))
    page._generate_button.click()  # noqa: SLF001
    assert requests == []
    page.set_entries((_entry("one", "Employees"),))
    page._generate_button.click()  # noqa: SLF001
    assert requests == [True]
    page.set_preview_busy(True)
    page._generate_button.click()  # noqa: SLF001
    assert requests == [True]
