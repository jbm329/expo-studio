from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, Qt, QTranslator
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog
from expo_jbm329.gui.dialogs.analysis.applied_configuration_header import AppliedConfigurationHeader
from expo_jbm329.gui.dialogs.analysis.correlation_view import CorrelationView
from expo_jbm329.gui.dialogs.analysis.regression_glm_view import GeneralizedRegressionView
from expo_jbm329.gui.dialogs.analysis.regression_view import RegressionView
from expo_jbm329.gui.dialogs.analysis.survival_view import SurvivalRegressionView
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.correlation import CorrelationMethod, analyze_correlation_matrix
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierMethod
from expo_jbm329.services.analysis.outliers import OutlierMethod
from expo_jbm329.services.analysis.presentation import (
    AnalysisPresentation,
    ConfigurationField,
    build_analysis_presentation,
)
from expo_jbm329.services.analysis.regression import RegressionResult
from expo_jbm329.services.analysis.regression_export import RegressionExportSnapshot
from expo_jbm329.services.analysis.regression_glm import GeneralizedRegressionResult
from expo_jbm329.utils.dataset_ref import DatasetRef
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot
from tests.analysis.test_outliers_export import multivariate_snapshot, univariate_snapshot
from tests.analysis.test_pca_export import pca_snapshot
from tests.analysis.test_regression_export import (
    cox_snapshot,
    linear_snapshot,
    logistic_snapshot,
    negative_binomial_snapshot,
    poisson_snapshot,
)
from tests.analysis.test_timeseries_export import time_series_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.services.analysis.report import ReportSnapshot

LOCALES = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales"


def _correlation_snapshot(method: CorrelationMethod) -> CorrelationExportSnapshot:
    base = correlation_snapshot()
    result = analyze_correlation_matrix(base.matrix_data, base.matrix.columns, method)
    return CorrelationExportSnapshot(result, base.matrix_data)


HEADER_CASES: list[tuple[AnalysisCategory, Callable[[], ReportSnapshot]]] = [
    (AnalysisCategory.HYPOTHESIS_TESTS, group_snapshot),
    (AnalysisCategory.HYPOTHESIS_TESTS, partial(group_snapshot, 3)),
    (AnalysisCategory.HYPOTHESIS_TESTS, chi_snapshot),
    (AnalysisCategory.HYPOTHESIS_TESTS, partial(chi_snapshot, 3)),
    (AnalysisCategory.HYPOTHESIS_TESTS, paired_snapshot),
    (AnalysisCategory.HYPOTHESIS_TESTS, partial(paired_snapshot, 3)),
    *((AnalysisCategory.CORRELATION, partial(_correlation_snapshot, method)) for method in CorrelationMethod),
    (AnalysisCategory.REGRESSION, linear_snapshot),
    (AnalysisCategory.REGRESSION, logistic_snapshot),
    (AnalysisCategory.REGRESSION, poisson_snapshot),
    (AnalysisCategory.REGRESSION, negative_binomial_snapshot),
    (AnalysisCategory.REGRESSION, cox_snapshot),
    *((AnalysisCategory.OUTLIERS, partial(univariate_snapshot, method)) for method in OutlierMethod),
    *((AnalysisCategory.OUTLIERS, partial(multivariate_snapshot, method)) for method in MultivariateOutlierMethod),
    (AnalysisCategory.PCA, pca_snapshot),
    *((AnalysisCategory.CLUSTERING, partial(clustering_snapshot, method)) for method in ClusteringMethod),
    (AnalysisCategory.TIME_SERIES, time_series_snapshot),
]


def _assert_header(header: AppliedConfigurationHeader, presentation: AnalysisPresentation) -> None:
    """Verify the approved shared appearance and every captured field."""
    assert header.frameShape() is QFrame.Shape.StyledPanel
    assert header.frameShadow() is QFrame.Shadow.Plain
    assert header.lineWidth() == 1
    layout = header.layout()
    assert layout is not None
    margins = layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (10, 8, 10, 8)
    title, *fields = header.findChildren(QLabel)
    assert title.text() == presentation.title
    assert title.font().bold()
    assert title.wordWrap()
    assert title.textFormat() is Qt.TextFormat.PlainText
    assert [label.text() for label in fields] == [
        text for field in presentation.configuration for text in (field.label, field.display_value)
    ]
    grid = layout.itemAt(1).layout()
    assert isinstance(grid, QGridLayout)
    assert grid.rowCount() == len(presentation.configuration)
    for row in range(len(presentation.configuration)):
        label, value = fields[row * 2 : row * 2 + 2]
        assert grid.itemAtPosition(row, 0).widget() is label
        assert grid.itemAtPosition(row, 1).widget() is value
        assert not label.wordWrap()
        assert value.wordWrap()
        for widget in (label, value):
            assert not widget.font().bold()
            assert widget.textFormat() is Qt.TextFormat.PlainText
            assert widget.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse


@pytest.mark.parametrize("language", ["en", "sv"])
@pytest.mark.parametrize(("category", "factory"), HEADER_CASES)
def test_all_applied_pages_use_one_header_and_clear_it_with_content(
    language: str, category: AnalysisCategory, factory: Callable[[], ReportSnapshot]
) -> None:
    translator = QTranslator()
    assert translator.load(str(LOCALES / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    dialog = AnalysisDialog(parent=None, source_dataset=DatasetRef("source", "Dataset", 100, 4))
    try:
        dialog.select_category(category)
        snapshot = factory()
        presentation = build_analysis_presentation(category, snapshot, QCoreApplication.translate)
        content: QWidget
        if isinstance(snapshot, CorrelationExportSnapshot):
            content = CorrelationView(snapshot.matrix, None)
        elif isinstance(snapshot, RegressionExportSnapshot):
            result = snapshot.result
            if isinstance(result, RegressionResult):
                content = RegressionView(result)
            elif isinstance(result, GeneralizedRegressionResult):
                content = GeneralizedRegressionView(result)
            else:
                content = SurvivalRegressionView(result)
        else:
            content = QWidget()
        dialog.set_content_widget(content)
        owns_header = isinstance(snapshot, (CorrelationExportSnapshot, RegressionExportSnapshot))
        if not owns_header:
            dialog.set_analysis_presentation(presentation)
        headers = dialog.content_panel().findChildren(AppliedConfigurationHeader)
        assert len(headers) == 1
        _assert_header(headers[0], presentation)
        assert dialog.content_widget() is content
        if not owns_header:
            old_header = headers[0]
            dialog.set_analysis_presentation(presentation)
            assert old_header.isHidden()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            headers = dialog.content_panel().findChildren(AppliedConfigurationHeader)
            assert len(headers) == 1
            _assert_header(headers[0], presentation)
        dialog.show_placeholder("Apply the new configuration")
        assert dialog._analysis_presentation_widget is None  # noqa: SLF001
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert dialog.content_panel().findChildren(AppliedConfigurationHeader) == []
        layout = dialog.content_panel().layout()
        assert layout is not None and layout.count() == 1
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.removeTranslator(translator)


@pytest.mark.parametrize(
    "category",
    [
        AnalysisCategory.HYPOTHESIS_TESTS,
        AnalysisCategory.CORRELATION,
        AnalysisCategory.REGRESSION,
        AnalysisCategory.OUTLIERS,
        AnalysisCategory.PCA,
        AnalysisCategory.CLUSTERING,
        AnalysisCategory.TIME_SERIES,
    ],
)
def test_shared_header_preserves_long_plain_text_and_aligns_whole_fields(category: AnalysisCategory) -> None:
    presentation = AnalysisPresentation(
        category.value,
        "Applied <b>title</b> & unchanged",
        (
            ConfigurationField("Long configuration label (selected order):", ("<first> & value " * 40, "second")),
            ConfigurationField("Other:", ("<a href='url'>literal</a>",)),
        ),
    )
    header = AppliedConfigurationHeader(presentation)
    header.resize(800, 300)
    header.show()
    QCoreApplication.processEvents()
    try:
        _assert_header(header, presentation)
        _, label, value, other_label, other_value = header.findChildren(QLabel)
        assert label.width() >= label.sizeHint().width()
        assert value.x() > label.geometry().right()
        assert value.x() == other_value.x()
        assert other_label.y() > label.geometry().bottom()
        assert other_value.y() > value.geometry().bottom()
    finally:
        header.close()
        header.deleteLater()
