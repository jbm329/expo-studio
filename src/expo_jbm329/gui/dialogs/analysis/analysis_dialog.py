"""Advanced Analysis workspace dialog.

Shows the fixed source dataset and lets the user choose an analysis category.
Categories without a dedicated implementation yet show a placeholder
message (see the project's step-by-step Advanced Analysis plan); the
content panel itself is fully owned by the controller (AnalysisController),
which computes analyses in the background and swaps in the resulting view.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Literal, override

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.report_notes_dialog import ReportNotesDialog
from expo_jbm329.gui.dialogs.analysis.report_page import ReportPage
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.clustering_export import ClusteringExportRequest, ClusteringExportSnapshot
from expo_jbm329.services.analysis.correlation_export import CorrelationExportRequest, CorrelationExportSnapshot
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportRequest, HypothesisExportSnapshot
from expo_jbm329.services.analysis.outliers_export import OutlierExportRequest, OutlierExportSnapshot
from expo_jbm329.services.analysis.overview import OverviewExportRequest
from expo_jbm329.services.analysis.pca_export import PCAExportRequest, PCAExportSnapshot
from expo_jbm329.services.analysis.presentation import (
    PresentationLabel,
    analysis_category_source,
    build_analysis_presentation,
    presentation_label_source,
    translate_presentation_label,
)
from expo_jbm329.services.analysis.regression_export import RegressionExportRequest, RegressionExportSnapshot
from expo_jbm329.services.analysis.report import (
    ReportDocument,
    ReportEntry,
    ReportSnapshot,
    correlation_report_configuration,
    create_report_entry,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportRequest
from expo_jbm329.services.analysis.timeseries_export import TimeSeriesExportRequest, TimeSeriesExportSnapshot
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.overview import DatasetOverviewResult
    from expo_jbm329.services.analysis.statistics import DescriptiveStatisticsResult
    from expo_jbm329.utils.dataset_ref import DatasetRef

_CATEGORY_ROLE = Qt.ItemDataRole.UserRole


class _ComboToolTipFilter(QObject):
    """Show current dropdown text while preserving explicit item explanations."""

    def __init__(self, combo: QComboBox) -> None:
        """Attach tooltip handling to the closed picker and its popup."""
        super().__init__(combo)
        self._combo = combo
        view = combo.view()
        if view is None:
            message = "Dropdown tooltips require a popup view."
            raise RuntimeError(message)
        viewport = view.viewport()
        if viewport is None:
            message = "Dropdown tooltips require a popup viewport."
            raise RuntimeError(message)
        self._view = view
        combo.installEventFilter(self)
        viewport.installEventFilter(self)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Resolve tooltips on demand so rebuilt and renamed items stay accurate."""
        watched, event = a0, a1
        if not isinstance(event, QHelpEvent) or event.type() != QEvent.Type.ToolTip:
            return super().eventFilter(watched, event)
        if watched is self._combo:
            tooltip = self._combo.currentData(Qt.ItemDataRole.ToolTipRole)
            if not self._combo.isEnabled() and self._combo.toolTip():
                tooltip = self._combo.toolTip()
            text = self._combo.currentText()
        else:
            index = self._view.indexAt(event.pos())
            tooltip = index.data(Qt.ItemDataRole.ToolTipRole)
            text = index.data(Qt.ItemDataRole.DisplayRole)

        if not tooltip and isinstance(text, str) and text:
            tooltip = f"<qt>{escape(text)}</qt>"
        if isinstance(tooltip, str) and tooltip and isinstance(watched, QWidget):
            QToolTip.showText(event.globalPos(), tooltip, watched)
        else:
            QToolTip.hideText()
        event.accept()
        return True


def build_placeholder_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Build the centered, word-wrapped message shown instead of analysis results.

    Args:
        text: Message to show.
        parent: Optional parent widget.

    Returns:
        The placeholder label.
    """
    label = QLabel(text, parent)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


class AnalysisDialog(QDialog):
    """Dialog hosting the Advanced Analysis workspace."""

    category_changed = pyqtSignal(str)  # AnalysisCategory value
    overview_export_requested = pyqtSignal(object)  # OverviewExportRequest
    statistics_export_requested = pyqtSignal(object)  # StatisticsExportRequest
    hypothesis_export_requested = pyqtSignal(object)  # HypothesisExportRequest
    correlation_export_requested = pyqtSignal(object)  # CorrelationExportRequest
    regression_export_requested = pyqtSignal(object)  # RegressionExportRequest
    outliers_export_requested = pyqtSignal(object)  # OutlierExportRequest
    clustering_export_requested = pyqtSignal(object)  # ClusteringExportRequest
    pca_export_requested = pyqtSignal(object)  # PCAExportRequest
    time_series_export_requested = pyqtSignal(object)  # TimeSeriesExportRequest
    report_preview_requested = pyqtSignal(object)  # Captured ReportDocument
    report_save_requested = pyqtSignal(object)  # Captured ReportDocument

    def __init__(
        self,
        *,
        parent: QWidget | None,
        source_dataset: DatasetRef,
    ) -> None:
        """Initialize the Advanced Analysis dialog.

        Args:
            parent: Parent widget.
            source_dataset: Ready dataset fixed for this analysis session.
        """
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)

        self._source_dataset = source_dataset
        self._report_document = ReportDocument()
        self._export_overview: DatasetOverviewResult | None = None
        self._export_tab_id: str | None = None
        self._export_statistics: DescriptiveStatisticsResult | None = None
        self._statistics_export_tab_id: str | None = None
        self._export_hypothesis: HypothesisExportSnapshot | None = None
        self._hypothesis_export_tab_id: str | None = None
        self._export_correlation: CorrelationExportSnapshot | None = None
        self._correlation_export_tab_id: str | None = None
        self._correlation_export_revision = 0
        self._export_regression: RegressionExportSnapshot | None = None
        self._regression_export_tab_id: str | None = None
        self._export_outliers: OutlierExportSnapshot | None = None
        self._outliers_export_tab_id: str | None = None
        self._export_clustering: ClusteringExportSnapshot | None = None
        self._clustering_export_tab_id: str | None = None
        self._export_pca: PCAExportSnapshot | None = None
        self._pca_export_tab_id: str | None = None
        self._export_time_series: TimeSeriesExportSnapshot | None = None
        self._time_series_export_tab_id: str | None = None
        self._analysis_revision = 0

        self.setWindowTitle(
            self.tr("Advanced analysis — {dataset} ({rows} rows × {columns} columns)").format(  # noqa: RUF001
                dataset=self._source_dataset.title,
                rows=fmt_int(self._source_dataset.row_count),
                columns=fmt_int(self._source_dataset.column_count),
            )
        )
        self.resize(1280, 900)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        analysis_panel = self._build_analysis_panel()

        self._analysis_workspace = QWidget(self)
        analysis_layout = QVBoxLayout(self._analysis_workspace)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.setSpacing(12)
        analysis_layout.addWidget(self._build_action_bar())
        workspace = QHBoxLayout()
        workspace.setSpacing(12)
        content_panel = self._build_content_panel()
        config_panel = self._build_config_panel()
        workspace.addWidget(content_panel, 4)
        workspace.addWidget(config_panel, 1)
        analysis_layout.addLayout(workspace, 1)

        self._workspace_stack = QStackedWidget(self)
        self._workspace_stack.addWidget(self._analysis_workspace)
        self._report_page = ReportPage(self)
        self._report_page.edit_requested.connect(self._edit_report_entry)
        self._report_page.remove_requested.connect(self._remove_report_entry)
        self._report_page.move_requested.connect(self._move_report_entry)
        self._report_page.preview_requested.connect(self._request_report_preview)
        self._report_page.generate_requested.connect(self._request_report_save)
        self._workspace_stack.addWidget(self._report_page)

        root.addWidget(analysis_panel)
        root.addWidget(self._workspace_stack, 1)
        root.addWidget(self._build_button_box())

        self._connect_signals()
        self.category_changed.connect(self.invalidate_overview_export)

    @override
    def hasHeightForWidth(self) -> bool:
        """Let the user resize the window freely.

        Word-wrapped labels make every ancestor layout report a height-for-width
        equal to its preferred height. Qt applies that height to top-level windows
        while they are resized interactively, which snaps the dialog to a tall
        height that cannot be reduced. Child layouts still use height-for-width
        internally to lay out wrapped text.

        Returns:
            Always `False`.
        """
        return False

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_analysis_panel(self) -> QWidget:
        """Build the horizontal analysis-category selector."""
        category_group = QGroupBox(self.tr("Analysis"), self)
        category_layout = QVBoxLayout(category_group)

        self._category_list = QListWidget(category_group)
        self._category_list.setFlow(QListView.Flow.LeftToRight)
        self._category_list.setWrapping(False)
        self._category_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._category_list.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._category_list.setFixedHeight(36)
        for category in AnalysisCategory:
            item = QListWidgetItem(self._category_label(category))
            item.setData(_CATEGORY_ROLE, category.value)
            self._category_list.addItem(item)
        self._report_item = QListWidgetItem(self.tr("Reports(0)"))
        self._category_list.addItem(self._report_item)

        # Overview is the natural starting point for exploring a dataset.
        self.select_category(AnalysisCategory.OVERVIEW)

        category_layout.addWidget(self._category_list)
        self._analysis_panel = category_group
        return category_group

    def _build_action_bar(self) -> QWidget:
        """Build shared actions for exporting results and collecting report entries."""
        bar = QWidget(self._analysis_workspace)
        actions = QHBoxLayout(bar)
        actions.setContentsMargins(0, 0, 0, 0)
        export_button = QPushButton(self.tr("Export"), bar)
        export_button.clicked.connect(self._show_export_selection)
        actions.addWidget(export_button)
        add_button = QPushButton(self.tr("Add to report"), bar)
        add_button.clicked.connect(self._toggle_report_entry)
        button_width = max(export_button.sizeHint().width(), add_button.sizeHint().width())
        export_button.setMinimumWidth(button_width)
        add_button.setMinimumWidth(button_width)
        actions.addWidget(add_button)
        explanation = QLabel(
            self.tr("Export and Add to report are available after an analysis has been applied."),
            bar,
        )
        explanation.setWordWrap(True)
        actions.addWidget(explanation, 1)
        self._action_bar = bar
        self._report_action_button = add_button
        return bar

    def _show_export_selection(self) -> None:
        """Open grouped export choices for the currently displayed analysis."""
        overview = self.exportable_overview()
        statistics = self.exportable_statistics()
        dialog = AnalysisExportDialog(
            self,
            overview=overview,
            overview_mode=self.selected_category() is AnalysisCategory.OVERVIEW,
            statistics=statistics,
            statistics_mode=self.selected_category() is AnalysisCategory.STATISTICS,
            hypothesis=self.exportable_hypothesis(),
            hypothesis_mode=self.selected_category() is AnalysisCategory.HYPOTHESIS_TESTS,
            correlation=self.exportable_correlation(),
            correlation_mode=self.selected_category() is AnalysisCategory.CORRELATION,
            regression=self.exportable_regression(),
            regression_mode=self.selected_category() is AnalysisCategory.REGRESSION,
            outliers=self.exportable_outliers(),
            outliers_mode=self.selected_category() is AnalysisCategory.OUTLIERS,
            outliers_multivariate=isinstance(self.config_widget(), MultivariateOutliersConfigWidget),
            clustering=self.exportable_clustering(),
            clustering_mode=self.selected_category() is AnalysisCategory.CLUSTERING,
            pca=self.exportable_pca(),
            pca_mode=self.selected_category() is AnalysisCategory.PCA,
            time_series=self.exportable_time_series(),
            time_series_mode=self.selected_category() is AnalysisCategory.TIME_SERIES,
        )
        for combo in dialog.findChildren(QComboBox):
            _ComboToolTipFilter(combo)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            request = dialog.export_request()
            if isinstance(request, OverviewExportRequest) and request.result is self.exportable_overview():
                self.overview_export_requested.emit(request)
            elif isinstance(request, StatisticsExportRequest) and request.result is self.exportable_statistics():
                self.statistics_export_requested.emit(request)
            elif isinstance(request, HypothesisExportRequest) and request.snapshot is self.exportable_hypothesis():
                self.hypothesis_export_requested.emit(request)
            elif isinstance(request, CorrelationExportRequest) and request.snapshot is self.exportable_correlation():
                self.correlation_export_requested.emit(request)
            elif isinstance(request, RegressionExportRequest) and request.snapshot is self.exportable_regression():
                self.regression_export_requested.emit(request)
            elif isinstance(request, OutlierExportRequest) and request.snapshot is self.exportable_outliers():
                self.outliers_export_requested.emit(request)
            elif isinstance(request, ClusteringExportRequest) and request.snapshot is self.exportable_clustering():
                self.clustering_export_requested.emit(request)
            elif isinstance(request, PCAExportRequest) and request.snapshot is self.exportable_pca():
                self.pca_export_requested.emit(request)
            elif isinstance(request, TimeSeriesExportRequest) and request.snapshot is self.exportable_time_series():
                self.time_series_export_requested.emit(request)

    def invalidate_overview_export(self) -> None:
        """Disable real export as soon as displayed analysis becomes stale."""
        self._export_overview = None
        self._export_tab_id = None
        self._export_statistics = None
        self._statistics_export_tab_id = None
        self._export_hypothesis = None
        self._hypothesis_export_tab_id = None
        self._export_regression = None
        self._regression_export_tab_id = None
        self._export_outliers = None
        self._outliers_export_tab_id = None
        self._export_clustering = None
        self._clustering_export_tab_id = None
        self._export_pca = None
        self._pca_export_tab_id = None
        self._export_time_series = None
        self._time_series_export_tab_id = None
        self.invalidate_correlation_export()
        self._analysis_revision += 1
        self._update_report_action()

    def invalidate_correlation_export(self) -> None:
        """Invalidate only the displayed Correlation snapshot and advance its request generation."""
        self._export_correlation = None
        self._correlation_export_tab_id = None
        self._correlation_export_revision += 1

    def correlation_export_revision(self) -> int:
        """Return the request generation used to reject stale matrix jobs."""
        return self._correlation_export_revision

    def analysis_revision(self) -> int:
        """Return the generation used to reject jobs after navigation/replacement."""
        return self._analysis_revision

    def set_exportable_hypothesis(self, snapshot: HypothesisExportSnapshot) -> None:
        """Register only the successful applied result already displayed."""
        self._export_hypothesis = snapshot
        self._hypothesis_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_hypothesis(self) -> HypothesisExportSnapshot | None:
        """Return the displayed applied snapshot, independent of pending edits."""
        if (
            self.selected_category() is AnalysisCategory.HYPOTHESIS_TESTS
            and self.source_tab_id() == self._hypothesis_export_tab_id
        ):
            return self._export_hypothesis
        return None

    def set_exportable_correlation(self, snapshot: CorrelationExportSnapshot) -> None:
        """Register a successful matrix snapshot after its view is displayed."""
        self._export_correlation = snapshot
        self._correlation_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_correlation(self) -> CorrelationExportSnapshot | None:
        """Return the current applied matrix independent of pending configuration edits."""
        if (
            self.selected_category() is AnalysisCategory.CORRELATION
            and self.source_tab_id() == self._correlation_export_tab_id
        ):
            return self._export_correlation
        return None

    def set_exportable_regression(self, snapshot: RegressionExportSnapshot) -> None:
        """Register a successful fitted model after its view is displayed."""
        self._export_regression = snapshot
        self._regression_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_regression(self) -> RegressionExportSnapshot | None:
        """Return the displayed applied model, independent of pending configuration edits."""
        if (
            self.selected_category() is AnalysisCategory.REGRESSION
            and self.source_tab_id() == self._regression_export_tab_id
        ):
            return self._export_regression
        return None

    def set_exportable_outliers(self, snapshot: OutlierExportSnapshot) -> None:
        """Register a successful screening after its view is displayed or its column detail changes."""
        self._export_outliers = snapshot
        self._outliers_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_outliers(self) -> OutlierExportSnapshot | None:
        """Return the displayed applied screening, independent of pending configuration edits."""
        if (
            self.selected_category() is AnalysisCategory.OUTLIERS
            and self.source_tab_id() == self._outliers_export_tab_id
        ):
            return self._export_outliers
        return None

    def set_exportable_clustering(self, snapshot: ClusteringExportSnapshot) -> None:
        """Register a successful clustering fit after its view is displayed."""
        self._export_clustering = snapshot
        self._clustering_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_clustering(self) -> ClusteringExportSnapshot | None:
        """Return the displayed applied clustering, independent of pending configuration edits."""
        if (
            self.selected_category() is AnalysisCategory.CLUSTERING
            and self.source_tab_id() == self._clustering_export_tab_id
        ):
            return self._export_clustering
        return None

    def set_exportable_pca(self, snapshot: PCAExportSnapshot) -> None:
        """Register a successful PCA fit after its view is displayed."""
        self._export_pca = snapshot
        self._pca_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_pca(self) -> PCAExportSnapshot | None:
        """Return the displayed applied PCA, independent of pending configuration edits."""
        if self.selected_category() is AnalysisCategory.PCA and self.source_tab_id() == self._pca_export_tab_id:
            return self._export_pca
        return None

    def set_exportable_time_series(self, snapshot: TimeSeriesExportSnapshot) -> None:
        """Register a successful time-series analysis after its view is displayed."""
        self._export_time_series = snapshot
        self._time_series_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_time_series(self) -> TimeSeriesExportSnapshot | None:
        """Return the displayed applied time series, independent of pending configuration edits."""
        if (
            self.selected_category() is AnalysisCategory.TIME_SERIES
            and self.source_tab_id() == self._time_series_export_tab_id
        ):
            return self._export_time_series
        return None

    def set_exportable_overview(self, result: DatasetOverviewResult) -> None:
        """Register the successful result currently displayed by the controller."""
        self._export_overview = result
        self._export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_overview(self) -> DatasetOverviewResult | None:
        """Return only the successful snapshot for the current Overview."""
        if self.selected_category() is AnalysisCategory.OVERVIEW and self.source_tab_id() == self._export_tab_id:
            return self._export_overview
        return None

    def set_exportable_statistics(self, result: DescriptiveStatisticsResult) -> None:
        """Register the successful Statistics snapshot currently displayed."""
        self._export_statistics = result
        self._statistics_export_tab_id = self.source_tab_id()
        self._update_report_action()

    def exportable_statistics(self) -> DescriptiveStatisticsResult | None:
        """Return only the successful snapshot for the current Statistics analysis."""
        if (
            self.selected_category() is AnalysisCategory.STATISTICS
            and self.source_tab_id() == self._statistics_export_tab_id
        ):
            return self._export_statistics
        return None

    def report_document(self) -> ReportDocument:
        """Return the report draft owned by this analysis window."""
        return self._report_document

    def _request_report_preview(self) -> None:
        document = self._capture_report_document()
        if document is not None:
            self.report_preview_requested.emit(document)

    def _request_report_save(self) -> None:
        document = self._capture_report_document()
        if document is not None:
            self.report_save_requested.emit(document)

    def _capture_report_document(self) -> ReportDocument | None:
        if not self._report_document.entries:
            return None
        document = ReportDocument(
            title=self._report_page.report_title(),
            description=self._report_page.report_description(),
        )
        for entry in self._report_document.entries:
            document.upsert(entry)
        return document

    def _current_report_candidate(self) -> ReportEntry | None:
        category = self.selected_category()
        if category is None:
            return None
        snapshot: ReportSnapshot | None
        match category:
            case AnalysisCategory.OVERVIEW:
                snapshot = self.exportable_overview()
            case AnalysisCategory.STATISTICS:
                snapshot = self.exportable_statistics()
            case AnalysisCategory.HYPOTHESIS_TESTS:
                snapshot = self.exportable_hypothesis()
            case AnalysisCategory.CORRELATION:
                snapshot = self.exportable_correlation()
            case AnalysisCategory.REGRESSION:
                snapshot = self.exportable_regression()
            case AnalysisCategory.OUTLIERS:
                snapshot = self.exportable_outliers()
            case AnalysisCategory.CLUSTERING:
                snapshot = self.exportable_clustering()
            case AnalysisCategory.PCA:
                snapshot = self.exportable_pca()
            case AnalysisCategory.TIME_SERIES:
                snapshot = self.exportable_time_series()
        if snapshot is None:
            return None
        return create_report_entry(category, self._source_dataset, snapshot)

    def _update_report_action(self) -> None:
        candidate = self._current_report_candidate()
        entry = None if candidate is None else self._report_document.get(candidate.entry_id)
        if candidate is None:
            self._report_action_button.setText(self.tr("Add to report"))
            self._report_action_button.setEnabled(False)
        elif entry is None:
            self._report_action_button.setText(self.tr("Add to report"))
            self._report_action_button.setEnabled(True)
        elif candidate.category is AnalysisCategory.CORRELATION and candidate.capture_id != entry.capture_id:
            if correlation_report_configuration(candidate) != correlation_report_configuration(entry):
                self._report_action_button.setText(self.tr("Replace report result"))
            else:
                self._report_action_button.setText(self.tr("Update report result"))
            self._report_action_button.setEnabled(True)
        else:
            self._report_action_button.setText(self.tr("Remove from report"))
            self._report_action_button.setEnabled(True)

    def _toggle_report_entry(self) -> None:
        candidate = self._current_report_candidate()
        if candidate is None:
            return
        existing = self._report_document.get(candidate.entry_id)
        if existing is not None:
            if candidate.category is AnalysisCategory.CORRELATION and candidate.capture_id != existing.capture_id:
                mode: Literal["replace", "update"] = (
                    "replace"
                    if correlation_report_configuration(candidate) != correlation_report_configuration(existing)
                    else "update"
                )
                self._edit_report_candidate(candidate, existing=existing, review_mode=mode)
            else:
                self._remove_report_entry(existing.entry_id)
            return
        self._edit_report_candidate(candidate, existing=None)

    def _edit_report_entry(self, entry_id: str) -> None:
        entry = self._report_document.get(entry_id)
        if entry is not None:
            self._edit_report_candidate(entry, existing=entry)

    def _edit_report_candidate(
        self,
        candidate: ReportEntry,
        *,
        existing: ReportEntry | None,
        review_mode: Literal["replace", "update"] | None = None,
    ) -> None:
        components = candidate.components
        presentation = build_analysis_presentation(
            candidate.category,
            candidate.snapshot,
            QCoreApplication.translate,
        )
        existing_components = set() if existing is None else set(existing.selected_components)
        available_components = {component.key for component in components}
        selected = existing_components & available_components
        unavailable_components: list[str] = []
        if existing is not None and candidate.category is AnalysisCategory.CORRELATION:
            unavailable_context, _source = presentation_label_source(PresentationLabel.STRONGEST_CORRELATIONS)
            unavailable_components.extend(
                QCoreApplication.translate(unavailable_context, component.label)
                for component in existing.components
                if component.key in existing_components and component.key not in available_components
            )
        review: tuple[tuple[str, ...], tuple[str, ...]] | None = None
        action_label: str | None = None
        if review_mode is not None and existing is not None:
            old_presentation = build_analysis_presentation(
                existing.category,
                existing.snapshot,
                QCoreApplication.translate,
            )
            review = (
                (old_presentation.title, *old_presentation.summary_lines),
                (presentation.title, *presentation.summary_lines),
            )
            action_label = self.tr("Replace in report") if review_mode == "replace" else self.tr("Update result")
        component_context = (
            presentation_label_source(PresentationLabel.STRONGEST_CORRELATIONS)[0]
            if candidate.category is AnalysisCategory.CORRELATION
            else None
        )
        selected_components = tuple(component.key for component in components if component.key in selected)
        dialog = ReportNotesDialog(
            presentation.title,
            self,
            components=components,
            selected_components=selected_components or None,
            note="" if existing is None else existing.note,
            existing=existing is not None and review_mode is None,
            configuration=presentation.summary_lines,
            component_translation_context=component_context,
            review=review,
            action_label=action_label,
            unavailable_components=tuple(unavailable_components),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.remove_requested():
            self._remove_report_entry(candidate.entry_id)
            return
        updated = candidate.with_selection(dialog.selected_components(), dialog.notes())
        self._report_document.upsert(updated)
        self._refresh_report_page()

    def _remove_report_entry(self, entry_id: str) -> None:
        if self._report_document.remove(entry_id):
            self._refresh_report_page()

    def _move_report_entry(self, entry_id: str, offset: int) -> None:
        if self._report_document.move(entry_id, offset):
            self._refresh_report_page(selected_entry_id=entry_id)

    def _refresh_report_page(self, *, selected_entry_id: str | None = None) -> None:
        self._report_page.set_entries(self._report_document.entries)
        if selected_entry_id is not None:
            self._report_page.select_entry(selected_entry_id)
        self._report_item.setText(self.tr("Reports({count})").format(count=len(self._report_document.entries)))
        self._update_report_action()

    def _build_content_panel(self) -> QWidget:
        """Build the right-hand content/placeholder panel."""
        panel = QGroupBox(self.tr("Result"), self)
        self._content_panel = panel
        self._content_layout = QVBoxLayout(panel)
        self._content_widget: QWidget | None = None

        return panel

    def _build_config_panel(self) -> QWidget:
        """Build the configuration panel for the currently selected category.

        Hidden by default; categories with no configurable input (e.g.
        Overview) keep it hidden via `set_config_widget(None)`.
        """
        panel = QGroupBox(self.tr("Configuration"), self)
        panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._config_panel = panel
        self._config_layout = QVBoxLayout(panel)
        self._config_scroll = QScrollArea(panel)
        self._config_scroll.setWidgetResizable(True)
        self._config_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._config_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self._config_layout.addWidget(self._config_scroll)
        self._config_widget: QWidget | None = None
        panel.setVisible(False)

        return panel

    def _build_button_box(self) -> QDialogButtonBox:
        """Build the bottom button box with a Close action."""
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        localize_dialog_buttons(buttons)
        return buttons

    def _connect_signals(self) -> None:
        """Wire internal widget signals to this dialog's public signals."""
        self._category_list.currentItemChanged.connect(self._on_category_item_changed)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_category_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        """Switch workspace pages and emit changes only for analysis categories."""
        if current is None:
            return
        reports_selected = current is self._report_item
        self._workspace_stack.setCurrentWidget(self._report_page if reports_selected else self._analysis_workspace)
        if not reports_selected:
            self.category_changed.emit(str(current.data(_CATEGORY_ROLE)))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def source_tab_id(self) -> str:
        """Return the stable tab ID fixed for this analysis session."""
        return self._source_dataset.tab_id

    def selected_category(self) -> AnalysisCategory | None:
        """Return the currently selected analysis category, if any."""
        item = self._category_list.currentItem()
        if item is None or item is self._report_item:
            return None
        return AnalysisCategory(item.data(_CATEGORY_ROLE))

    def select_reports(self) -> None:
        """Show the persistent report preview without selecting an analysis."""
        self._category_list.setCurrentItem(self._report_item)

    def report_page(self) -> ReportPage:
        """Return the report page, which lives for the whole dialog lifetime."""
        return self._report_page

    def select_category(self, category: AnalysisCategory) -> None:
        """Select an analysis category in the sidebar list.

        Args:
            category: Category to select.
        """
        for i in range(self._category_list.count()):
            item = self._category_list.item(i)
            if item is not None and item.data(_CATEGORY_ROLE) == category.value:
                self._category_list.setCurrentRow(i)
                return

    def show_placeholder(self, text: str) -> None:
        """Display a centered placeholder message in the content panel.

        Args:
            text: Message to show instead of analysis results.
        """
        self.set_content_widget(build_placeholder_label(text, self))

    def set_content_widget(self, widget: QWidget) -> None:
        """Replace the content panel's widget with the given widget.

        The previously displayed content widget, if any, is removed and
        scheduled for deletion.

        Args:
            widget: The widget to display in the content panel.
        """
        self.invalidate_overview_export()
        if self._content_widget is not None:
            # A visible canvas removed from its layout can be repainted once
            # at zero size before deleteLater() runs.
            self._content_widget.hide()
            self._content_layout.removeWidget(self._content_widget)
            self._content_widget.deleteLater()

        self._content_layout.addWidget(widget)
        self._content_widget = widget

    def content_widget(self) -> QWidget | None:
        """Return the widget currently displayed in the content panel."""
        return self._content_widget

    def content_panel(self) -> QWidget:
        """Return the stable result-pane container widget.

        Unlike `content_widget()` (which changes every time the analysis
        content is rebuilt), this returns the same container widget for the
        dialog's whole lifetime - suitable as a busy-overlay anchor.
        """
        return self._content_panel

    def set_config_widget(self, widget: QWidget | None) -> None:
        """Replace the configuration panel's widget, or hide it.

        Args:
            widget: The widget to display in the configuration panel, or
                `None` to hide the panel entirely (categories with no
                configurable input).
        """
        if self._config_widget is not None:
            self._config_widget.hide()
            previous = self._config_scroll.takeWidget()
            if previous is not None:
                previous.deleteLater()

        self._config_widget = widget

        if widget is None:
            self._config_panel.setVisible(False)
            return

        self._prepare_config_layout(widget)
        self._config_scroll.setWidget(widget)
        self._config_panel.setVisible(True)

    @staticmethod
    def _prepare_config_layout(widget: QWidget) -> None:
        """Keep configuration controls usable within the shared workspace width."""
        layout = widget.layout()
        if layout is not None:
            layout.setContentsMargins(0, 0, 0, 0)
            if isinstance(layout, QFormLayout):
                layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for label in widget.findChildren(QLabel):
            label.setWordWrap(True)
        for form in widget.findChildren(QFormLayout):
            if not isinstance(form.parentWidget(), QGroupBox):
                form.setContentsMargins(0, 0, 0, 0)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for combo in widget.findChildren(QComboBox):
            _ComboToolTipFilter(combo)
            # Dataset names and model labels must not determine the pane width.
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def config_widget(self) -> QWidget | None:
        """Return the widget currently displayed in the configuration panel."""
        return self._config_widget

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def _category_label(self, category: AnalysisCategory) -> str:
        """Return the translated display label for an analysis category."""
        if category is AnalysisCategory.CORRELATION:
            return translate_presentation_label(PresentationLabel.CORRELATION, QCoreApplication.translate)
        return self.tr(analysis_category_source(category))
