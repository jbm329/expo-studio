"""Grouped Overview export selection and unavailable previews for other analyses."""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.clustering_export import (
    CLUSTERING_COMPONENTS,
    ClusteringExportComponent,
    ClusteringExportRequest,
    ClusteringExportSnapshot,
)
from expo_jbm329.services.analysis.correlation_export import (
    CorrelationExportComponent,
    CorrelationExportRequest,
    CorrelationExportSnapshot,
)
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent,
    HypothesisExportRequest,
    HypothesisExportSnapshot,
)
from expo_jbm329.services.analysis.outliers_export import (
    MULTIVARIATE_COMPONENTS,
    UNIVARIATE_COMPONENTS,
    MultivariateOutlierExportSnapshot,
    OutlierExportComponent,
    OutlierExportRequest,
    OutlierExportSnapshot,
)
from expo_jbm329.services.analysis.overview import (
    DatasetOverviewResult,
    OverviewExportFormat,
    OverviewExportRequest,
    OverviewExportTable,
    overview_export_tables,
)
from expo_jbm329.services.analysis.pca_export import (
    PCA_COMPONENTS,
    PCAExportComponent,
    PCAExportRequest,
    PCAExportSnapshot,
)
from expo_jbm329.services.analysis.presentation import (
    PresentationLabel,
    build_analysis_presentation,
    clustering_component_label,
    hypothesis_component_label,
    outlier_component_label,
    pca_component_label,
    regression_component_label,
    time_series_component_label,
    translate_presentation_label,
)
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportRequest,
    RegressionExportSnapshot,
)
from expo_jbm329.services.analysis.regression_glm import RegressionModel
from expo_jbm329.services.analysis.statistics import (
    DescriptiveStatisticsResult,
    StatisticsExportFormat,
    StatisticsExportRequest,
    StatisticsExportTable,
)
from expo_jbm329.services.analysis.timeseries_export import (
    TIME_SERIES_COMPONENTS,
    TimeSeriesExportComponent,
    TimeSeriesExportRequest,
    TimeSeriesExportSnapshot,
)


class AnalysisExportDialog(QDialog):
    """Select components from the currently displayed analysis."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        overview: DatasetOverviewResult | None = None,
        overview_mode: bool = False,
        statistics: DescriptiveStatisticsResult | None = None,
        statistics_mode: bool = False,
        hypothesis: HypothesisExportSnapshot | None = None,
        hypothesis_mode: bool = False,
        correlation: CorrelationExportSnapshot | None = None,
        correlation_mode: bool = False,
        regression: RegressionExportSnapshot | None = None,
        regression_mode: bool = False,
        outliers: OutlierExportSnapshot | None = None,
        outliers_mode: bool = False,
        outliers_multivariate: bool = False,
        clustering: ClusteringExportSnapshot | None = None,
        clustering_mode: bool = False,
        pca: PCAExportSnapshot | None = None,
        pca_mode: bool = False,
        time_series: TimeSeriesExportSnapshot | None = None,
        time_series_mode: bool = False,
    ) -> None:
        """Build grouped export choices and a format selector.

        Args:
            parent: Optional parent widget.
            overview: Successful displayed Overview snapshot, if available.
            overview_mode: Show disabled Overview choices even without a result.
            statistics: Successful displayed Statistics snapshot, if available.
            statistics_mode: Show Statistics export choices.
            hypothesis: Successfully displayed applied hypothesis selection.
            hypothesis_mode: Show hypothesis choices even before Apply.
            correlation: Successfully displayed applied correlation matrix.
            correlation_mode: Show correlation choices even before Apply.
            regression: Successfully displayed applied regression model.
            regression_mode: Show regression choices even before Apply.
            outliers: Successfully displayed applied outlier screening.
            outliers_mode: Show outlier choices even before Apply.
            outliers_multivariate: Show multivariate rather than univariate
                choices before Apply; a snapshot decides by its own type.
            clustering: Successfully displayed applied clustering fit.
            clustering_mode: Show clustering choices even before Apply.
            pca: Successfully displayed applied PCA fit.
            pca_mode: Show PCA choices even before Apply.
            time_series: Successfully displayed applied time-series analysis.
            time_series_mode: Show time-series choices even before Apply.

        Raises:
            ValueError: If not exactly one analysis result is represented.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export"))
        self.resize(540, 540)
        self._overview = overview
        self._statistics = statistics
        self._hypothesis = hypothesis
        self._hypothesis_mode = hypothesis_mode or hypothesis is not None
        self._correlation = correlation
        self._correlation_mode = correlation_mode or correlation is not None
        self._regression = regression
        self._regression_mode = regression_mode or regression is not None
        self._outliers = outliers
        self._outliers_mode = outliers_mode or outliers is not None
        self._outliers_multivariate = (
            outliers_multivariate if outliers is None else isinstance(outliers, MultivariateOutlierExportSnapshot)
        )
        self._clustering = clustering
        self._clustering_mode = clustering_mode or clustering is not None
        self._pca = pca
        self._pca_mode = pca_mode or pca is not None
        self._time_series = time_series
        self._time_series_mode = time_series_mode or time_series is not None
        self._hypothesis_choices: dict[HypothesisExportComponent, QCheckBox] = {}
        self._correlation_choices: dict[CorrelationExportComponent, QCheckBox] = {}
        self._regression_choices: dict[RegressionExportComponent, QCheckBox] = {}
        self._outliers_choices: dict[OutlierExportComponent, QCheckBox] = {}
        self._clustering_choices: dict[ClusteringExportComponent, QCheckBox] = {}
        self._pca_choices: dict[PCAExportComponent, QCheckBox] = {}
        self._time_series_choices: dict[TimeSeriesExportComponent, QCheckBox] = {}
        self._table_choices: dict[OverviewExportTable, QCheckBox] = {}
        self._statistics_choices: dict[StatisticsExportTable, QCheckBox] = {}
        self._overview_mode = overview_mode or overview is not None
        self._statistics_mode = statistics_mode or statistics is not None
        if (
            sum((
                self._overview_mode,
                self._statistics_mode,
                self._hypothesis_mode,
                self._correlation_mode,
                self._regression_mode,
                self._outliers_mode,
                self._clustering_mode,
                self._pca_mode,
                self._time_series_mode,
            ))
            != 1
        ):
            message = "An export dialog must represent exactly one analysis result."
            raise ValueError(message)
        layout = QVBoxLayout(self)
        explanation = QLabel(self._explanation_text(), self)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        if self._overview_mode:
            self._build_overview_choices(layout)
        elif self._statistics_mode:
            self._build_statistics_choices(layout)
        elif self._hypothesis_mode:
            self._build_hypothesis_choices(layout)
        elif self._correlation_mode:
            self._build_correlation_choices(layout)
        elif self._regression_mode:
            self._build_regression_choices(layout)
        elif self._outliers_mode:
            self._build_outliers_choices(layout)
        elif self._clustering_mode:
            self._build_clustering_choices(layout)
        elif self._pca_mode:
            self._build_pca_choices(layout)
        else:
            self._build_time_series_choices(layout)
        formats = QFormLayout()
        self._format_combo = QComboBox(self)
        format_type = StatisticsExportFormat if self._uses_component_export() else OverviewExportFormat
        self._format_combo.addItem("CSV", format_type.CSV)
        self._format_combo.addItem(self.tr("Excel workbook (.xlsx)"), format_type.EXCEL)
        self._format_combo.addItem(self.tr("Binary data file (Parquet / Feather / Pickle)"), format_type.BINARY)
        self._format_combo.setCurrentIndex(self._format_combo.findData(format_type.EXCEL))
        self._format_combo.currentIndexChanged.connect(self._update_export_enabled)
        formats.addRow(self.tr("Format"), self._format_combo)
        layout.addLayout(formats)
        self._selection_explanation = QLabel(self)
        self._selection_explanation.setWordWrap(True)
        layout.addWidget(self._selection_explanation)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self._export_button = QPushButton(self.tr("Export"), buttons)
        buttons.addButton(self._export_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        localize_dialog_buttons(buttons)
        layout.addWidget(buttons)
        choices = (
            self._hypothesis_choices
            if self._hypothesis_mode
            else self._correlation_choices
            if self._correlation_mode
            else self._regression_choices
            if self._regression_mode
            else self._outliers_choices
            if self._outliers_mode
            else self._clustering_choices
            if self._clustering_mode
            else self._pca_choices
            if self._pca_mode
            else self._time_series_choices
            if self._time_series_mode
            else self._statistics_choices
            if self._statistics_mode
            else self._table_choices
        )
        first_available = next((choice for choice in choices.values() if choice.isEnabled()), None)
        if first_available is not None:
            first_available.setChecked(True)
        self._update_export_enabled()

    def _uses_component_export(self) -> bool:
        """Return whether the mode uses component checkboxes with Excel-only charts."""
        return (
            self._statistics_mode
            or self._hypothesis_mode
            or self._correlation_mode
            or self._regression_mode
            or self._outliers_mode
            or self._clustering_mode
            or self._pca_mode
            or self._time_series_mode
        )

    def _explanation_text(self) -> str:
        """Return the translated description of what the current mode exports."""
        if self._overview_mode:
            return self.tr(
                "Export the Overview Summary, Columns metadata, or Sample (first/last 10 rows), "
                "not the original dataset."
            )
        if self._statistics_mode:
            return self.tr("Export the available Statistics tables and numeric-column charts.")
        if self._hypothesis_mode:
            return self.tr("Export computed tables and charts for the applied test, not the original dataset.")
        if self._correlation_mode:
            return self.tr("Export the strongest-correlations table for the applied matrix.")
        if self._regression_mode:
            return self.tr(
                "Export the coefficients, model metrics and charts of the applied model, not the original dataset."
            )
        if self._outliers_mode:
            return self.tr(
                "Export the displayed outlier tables and charts of the applied screening, not the original dataset."
            )
        if self._clustering_mode:
            return self.tr(
                "Export the cluster sizes, model summary and chart of the applied clustering, not the original dataset."
            )
        if self._pca_mode:
            return self.tr(
                "Export the feature loadings, explained variance, model summary and charts of the applied PCA, "
                "not the original dataset."
            )
        return self.tr(
            "Export the prepared series, autocorrelation, model summary and charts of the applied time series, "
            "not the original dataset."
        )

    def _build_overview_choices(self, layout: QVBoxLayout) -> None:
        """Offer only available structured Overview tables, never the dataset."""
        result = self._overview
        data = QGroupBox(self.tr("Data"), self)
        data_layout = QVBoxLayout(data)
        results = QGroupBox(self.tr("Results"), self)
        results_layout = QVBoxLayout(results)
        sample_available = False
        if result is not None:
            try:
                overview_export_tables(result, (OverviewExportTable.SAMPLE,))
                sample_available = True
            except ValueError:
                # Partial legacy snapshots cannot supply the actual last rows.
                sample_available = False
        availability = {
            OverviewExportTable.COLUMNS: result is not None and bool(result.columns),
            OverviewExportTable.SAMPLE: sample_available,
            OverviewExportTable.SUMMARY: result is not None,
        }
        labels = {
            OverviewExportTable.COLUMNS: self.tr("Columns metadata"),
            OverviewExportTable.SAMPLE: self.tr("Sample (first/last 10 rows)"),
            OverviewExportTable.SUMMARY: self.tr("Summary"),
        }
        for table, available in availability.items():
            is_summary = table is OverviewExportTable.SUMMARY
            parent = results if is_summary else data
            choice = QCheckBox(labels[table], parent)
            choice.setEnabled(available)
            if is_summary:
                choice.setToolTip(
                    self.tr(
                        "Dataset metrics, column-type counts, and high-missing-value warnings. "
                        "Fractions are numeric values from 0 to 1."
                    )
                )
            if not available:
                choice.setToolTip(
                    self.tr("Run Overview successfully before exporting.")
                    if result is None
                    else self.tr("The first/last sample is unavailable in this captured result.")
                    if table is OverviewExportTable.SAMPLE
                    else self.tr("This table is empty and cannot be exported.")
                )
            self._table_choices[table] = choice
            choice.toggled.connect(self._update_export_enabled)
            (results_layout if is_summary else data_layout).addWidget(choice)
        layout.addWidget(data)
        layout.addWidget(results)

    def _build_statistics_choices(self, layout: QVBoxLayout) -> None:
        """Offer available Statistics tables and a separate Excel chart component."""
        result = self._statistics
        data = QGroupBox(self.tr("Data"), self)
        data_layout = QVBoxLayout(data)
        results = QGroupBox(self.tr("Results"), self)
        results_layout = QVBoxLayout(results)
        availability = {
            StatisticsExportTable.CONTINUOUS: result is not None and bool(result.columns),
            StatisticsExportTable.CATEGORICAL: result is not None and bool(result.categorical_columns),
            StatisticsExportTable.CHARTS: result is not None and bool(result.columns),
        }
        labels = {
            StatisticsExportTable.CONTINUOUS: self.tr("Continuous"),
            StatisticsExportTable.CATEGORICAL: self.tr("Categorical"),
            StatisticsExportTable.CHARTS: self.tr("Charts"),
        }
        for component, available in availability.items():
            is_chart = component is StatisticsExportTable.CHARTS
            parent = results if is_chart else data
            choice = QCheckBox(labels[component], parent)
            choice.setEnabled(available)
            if component is StatisticsExportTable.CATEGORICAL and available:
                choice.setToolTip(self.tr("Counts are numeric, and fractions range from 0 to 1."))
            elif not available:
                choice.setToolTip(
                    self.tr("Run Statistics successfully before exporting.")
                    if result is None
                    else self.tr("This component is empty and cannot be exported.")
                )
            self._statistics_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            (results_layout if is_chart else data_layout).addWidget(choice)
        layout.addWidget(data)
        layout.addWidget(results)

    def _build_hypothesis_choices(self, layout: QVBoxLayout) -> None:
        """List applied identity plainly, independently of pending configuration edits."""
        snapshot = self._hypothesis
        if snapshot is not None:
            presentation = build_analysis_presentation(
                AnalysisCategory.HYPOTHESIS_TESTS,
                snapshot,
                QCoreApplication.translate,
            )
            identity = QLabel("\n".join((presentation.title, *presentation.summary_lines)), self)
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)
        for title, components in (
            (self.tr("Data"), (HypothesisExportComponent.SUMMARY,)),
            (self.tr("Results"), (HypothesisExportComponent.TEST_RESULTS, HypothesisExportComponent.CHARTS)),
        ):
            group = QGroupBox(title, self)
            contents = QVBoxLayout(group)
            for component in components:
                label = (
                    hypothesis_component_label(snapshot, component, QCoreApplication.translate)
                    if component is HypothesisExportComponent.SUMMARY and snapshot is not None
                    else self.tr("Summary / statistics tables")
                    if component is HypothesisExportComponent.SUMMARY
                    else hypothesis_component_label(snapshot, component, QCoreApplication.translate)
                    if component is HypothesisExportComponent.CHARTS and snapshot is not None
                    else self.tr(component.value)
                )
                choice = QCheckBox(label, group)
                choice.setEnabled(snapshot is not None)
                if snapshot is None:
                    choice.setToolTip(self.tr("Apply a hypothesis test successfully before exporting."))
                self._hypothesis_choices[component] = choice
                choice.toggled.connect(self._update_export_enabled)
                contents.addWidget(choice)
            layout.addWidget(group)

    def _build_correlation_choices(self, layout: QVBoxLayout) -> None:
        """Offer applied tables and independent Excel chart components."""
        snapshot = self._correlation
        if snapshot is not None:
            presentation = build_analysis_presentation(
                AnalysisCategory.CORRELATION,
                snapshot,
                QCoreApplication.translate,
            )
            identity = QLabel(
                "\n".join((presentation.title, *presentation.summary_lines)),
                self,
            )
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)

        results = QGroupBox(self.tr("Results"), self)
        contents = QVBoxLayout(results)
        scatter_label = translate_presentation_label(
            PresentationLabel.SCATTERPLOTS,
            QCoreApplication.translate,
        )
        labels = {
            CorrelationExportComponent.STRONGEST_CORRELATIONS: translate_presentation_label(
                PresentationLabel.STRONGEST_CORRELATIONS, QCoreApplication.translate
            ),
            CorrelationExportComponent.MATRIX_PLOT: translate_presentation_label(
                PresentationLabel.CORRELATION_MATRIX, QCoreApplication.translate
            ),
            CorrelationExportComponent.SCATTERPLOTS: scatter_label,
        }
        for component, label in labels.items():
            choice = QCheckBox(label, results)
            choice.setEnabled(snapshot is not None)
            if snapshot is None:
                choice.setToolTip(self.tr("Apply a correlation matrix successfully before exporting."))
            self._correlation_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            contents.addWidget(choice)
        layout.addWidget(results)

    def _build_regression_choices(self, layout: QVBoxLayout) -> None:
        """List the applied model plainly and offer its result tables and charts."""
        snapshot = self._regression
        if snapshot is not None:
            presentation = build_analysis_presentation(
                AnalysisCategory.REGRESSION,
                snapshot,
                QCoreApplication.translate,
            )
            identity = QLabel(
                "\n".join((presentation.title, *presentation.summary_lines)),
                self,
            )
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)

        results = QGroupBox(self.tr("Results"), self)
        contents = QVBoxLayout(results)
        labels = {
            component: regression_component_label(
                snapshot.model if snapshot is not None else RegressionModel.LINEAR,
                component,
                QCoreApplication.translate,
            )
            for component in RegressionExportComponent
        }
        for component, label in labels.items():
            choice = QCheckBox(label, results)
            if snapshot is None:
                choice.setEnabled(False)
                choice.setToolTip(self.tr("Apply a regression model successfully before exporting."))
            elif component is RegressionExportComponent.CHARTS and not snapshot.has_charts:
                choice.setEnabled(False)
                choice.setToolTip(self.tr("This component is empty and cannot be exported."))
            elif component is RegressionExportComponent.MODEL_METRICS:
                choice.setToolTip(self.tr("Fit statistics and diagnostics with the displayed model comments."))
            self._regression_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            contents.addWidget(choice)
        layout.addWidget(results)

    def _build_outliers_choices(self, layout: QVBoxLayout) -> None:
        """List the applied screening plainly and offer its displayed tables and charts."""
        snapshot = self._outliers
        if snapshot is not None:
            presentation = build_analysis_presentation(
                AnalysisCategory.OUTLIERS,
                snapshot,
                QCoreApplication.translate,
            )
            identity = QLabel("\n".join((presentation.title, *presentation.summary_lines)), self)
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)

        results = QGroupBox(self.tr("Results"), self)
        contents = QVBoxLayout(results)
        components = (
            snapshot.components
            if snapshot is not None
            else MULTIVARIATE_COMPONENTS
            if self._outliers_multivariate
            else UNIVARIATE_COMPONENTS
        )
        for component in components:
            choice = QCheckBox(
                outlier_component_label(
                    component,
                    QCoreApplication.translate,
                    multivariate=self._outliers_multivariate,
                ),
                results,
            )
            if snapshot is None:
                choice.setEnabled(False)
                choice.setToolTip(self.tr("Apply an outlier screening successfully before exporting."))
            elif not snapshot.is_available(component):
                choice.setEnabled(False)
                choice.setToolTip(self.tr("This component is empty and cannot be exported."))
            elif component is OutlierExportComponent.POTENTIAL_OUTLIERS:
                choice.setToolTip(self.tr("The displayed rows, at most 100, most extreme first."))
            self._outliers_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            contents.addWidget(choice)
        layout.addWidget(results)

    def _build_clustering_choices(self, layout: QVBoxLayout) -> None:
        """List the applied clustering plainly and offer its displayed tables and chart."""
        snapshot = self._clustering
        if snapshot is not None:
            presentation = build_analysis_presentation(
                AnalysisCategory.CLUSTERING, snapshot, QCoreApplication.translate
            )
            identity = QLabel(
                "\n".join((presentation.title, *presentation.summary_lines)),
                self,
            )
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)

        results = QGroupBox(self.tr("Results"), self)
        contents = QVBoxLayout(results)
        for component in CLUSTERING_COMPONENTS:
            choice = QCheckBox(clustering_component_label(component, QCoreApplication.translate), results)
            if snapshot is None:
                choice.setEnabled(False)
                choice.setToolTip(self.tr("Apply a clustering successfully before exporting."))
            elif component is ClusteringExportComponent.MODEL_SUMMARY:
                choice.setToolTip(self.tr("Settings, row counts and silhouette with the displayed model comments."))
            self._clustering_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            contents.addWidget(choice)
        layout.addWidget(results)

    def _build_pca_choices(self, layout: QVBoxLayout) -> None:
        """List the applied PCA features plainly and offer its displayed tables and charts."""
        snapshot = self._pca
        if snapshot is not None:
            presentation = build_analysis_presentation(AnalysisCategory.PCA, snapshot, QCoreApplication.translate)
            identity = QLabel("\n".join((presentation.title, *presentation.summary_lines)), self)
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)

        results = QGroupBox(self.tr("Results"), self)
        contents = QVBoxLayout(results)
        labels = {component: pca_component_label(component, QCoreApplication.translate) for component in PCA_COMPONENTS}
        for component in PCA_COMPONENTS:
            choice = QCheckBox(labels[component], results)
            if snapshot is None:
                choice.setEnabled(False)
                choice.setToolTip(self.tr("Apply a PCA successfully before exporting."))
            elif component is PCAExportComponent.EXPLAINED_VARIANCE:
                choice.setToolTip(self.tr("Variance, share and cumulative share per component, as in the scree plot."))
            elif component is PCAExportComponent.MODEL_SUMMARY:
                choice.setToolTip(self.tr("Feature and row counts with the displayed model comments."))
            self._pca_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            contents.addWidget(choice)
        layout.addWidget(results)

    def _build_time_series_choices(self, layout: QVBoxLayout) -> None:
        """List the applied series plainly and offer its prepared data, tables and charts."""
        snapshot = self._time_series
        if snapshot is not None:
            presentation = build_analysis_presentation(
                AnalysisCategory.TIME_SERIES,
                snapshot,
                QCoreApplication.translate,
            )
            identity = QLabel("\n".join((presentation.title, *presentation.summary_lines)), self)
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)

        data = QGroupBox(self.tr("Data"), self)
        data_layout = QVBoxLayout(data)
        results = QGroupBox(self.tr("Results"), self)
        results_layout = QVBoxLayout(results)
        labels = {
            component: time_series_component_label(component, QCoreApplication.translate)
            for component in TIME_SERIES_COMPONENTS
        }
        for component in TIME_SERIES_COMPONENTS:
            is_data = component is TimeSeriesExportComponent.SERIES
            choice = QCheckBox(labels[component], data if is_data else results)
            if snapshot is None:
                choice.setEnabled(False)
                choice.setToolTip(self.tr("Apply a time series successfully before exporting."))
            elif component not in snapshot.components:
                choice.setEnabled(False)
                choice.setToolTip(snapshot.autocorrelation_note)
            elif is_data:
                choice.setToolTip(
                    self.tr(
                        "One row per time point after averaging duplicate timestamps and any resampling, "
                        "with the decomposition when available."
                    )
                )
            elif component is TimeSeriesExportComponent.MODEL_SUMMARY:
                choice.setToolTip(self.tr("Row diagnostics and seasonal period with the displayed model comments."))
            elif component is TimeSeriesExportComponent.CHARTS:
                choice.setToolTip(self.tr("The series and, when available, the autocorrelation and decomposition."))
            self._time_series_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            (data_layout if is_data else results_layout).addWidget(choice)
        layout.addWidget(data)
        layout.addWidget(results)

    def export_request(
        self,
    ) -> (
        OverviewExportRequest
        | StatisticsExportRequest
        | HypothesisExportRequest
        | CorrelationExportRequest
        | RegressionExportRequest
        | OutlierExportRequest
        | ClusteringExportRequest
        | PCAExportRequest
        | TimeSeriesExportRequest
        | None
    ):
        """Return a validated selection, or None for invalid choices."""
        if self._time_series_mode:
            if self._time_series is None:
                return None
            time_series_components = tuple(
                component
                for component, choice in self._time_series_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not time_series_components:
                return None
            try:
                return TimeSeriesExportRequest(self._time_series, time_series_components, format_choice)
            except ValueError:
                return None
        if self._pca_mode:
            if self._pca is None:
                return None
            pca_components = tuple(
                component
                for component, choice in self._pca_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not pca_components:
                return None
            try:
                return PCAExportRequest(self._pca, pca_components, format_choice)
            except ValueError:
                return None
        if self._clustering_mode:
            if self._clustering is None:
                return None
            clustering_components = tuple(
                component
                for component, choice in self._clustering_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not clustering_components:
                return None
            try:
                return ClusteringExportRequest(self._clustering, clustering_components, format_choice)
            except ValueError:
                return None
        if self._outliers_mode:
            if self._outliers is None:
                return None
            outlier_components = tuple(
                component
                for component, choice in self._outliers_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not outlier_components:
                return None
            try:
                return OutlierExportRequest(self._outliers, outlier_components, format_choice)
            except ValueError:
                return None
        if self._regression_mode:
            if self._regression is None:
                return None
            regression_components = tuple(
                component
                for component, choice in self._regression_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not regression_components:
                return None
            try:
                return RegressionExportRequest(self._regression, regression_components, format_choice)
            except ValueError:
                return None
        if self._correlation_mode:
            if self._correlation is None:
                return None
            correlation_components = tuple(
                component
                for component, choice in self._correlation_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not correlation_components:
                return None
            try:
                return CorrelationExportRequest(self._correlation, correlation_components, format_choice)
            except ValueError:
                return None
        if self._hypothesis_mode:
            if self._hypothesis is None:
                return None
            hypothesis_components = tuple(
                component
                for component, choice in self._hypothesis_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat):
                return None
            try:
                return HypothesisExportRequest(self._hypothesis, hypothesis_components, format_choice)
            except ValueError:
                return None
        if self._statistics_mode:
            if self._statistics is None:
                return None
            statistics_choices: dict[StatisticsExportTable, QCheckBox] = self._statistics_choices
            statistics_components = tuple(
                component
                for component, choice in statistics_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not statistics_components:
                return None
            chart_selected = StatisticsExportTable.CHARTS in statistics_components
            table_count = sum(component is not StatisticsExportTable.CHARTS for component in statistics_components)
            if format_choice is not StatisticsExportFormat.EXCEL and (chart_selected or table_count != 1):
                return None
            return StatisticsExportRequest(self._statistics, statistics_components, format_choice)
        if self._overview is None:
            return None
        tables = tuple(
            table for table, choice in self._table_choices.items() if choice.isEnabled() and choice.isChecked()
        )
        format_choice = self._format_combo.currentData()
        if not isinstance(format_choice, OverviewExportFormat) or not tables:
            return None
        if format_choice is not OverviewExportFormat.EXCEL and len(tables) != 1:
            return None
        return OverviewExportRequest(self._overview, tables, format_choice)

    def _update_export_enabled(self) -> None:
        """Preserve picks across formats and explain disabled exports."""
        if self._uses_component_export():
            self._update_statistics_export_enabled()
            return
        excel = self._format_combo.currentData() is OverviewExportFormat.EXCEL
        format_explanation = (
            self.tr("Excel exports selected tables as separate sheets in one workbook.")
            if excel
            else self.tr(
                "Choose exactly one table for CSV or binary export. "
                "For binary files, choose Parquet, Feather or Pickle in the save dialog."
            )
        )
        request = self.export_request()
        if self._overview is None:
            reason = self.tr("Run Overview successfully before exporting.")
        elif not any(choice.isEnabled() for choice in self._table_choices.values()):
            reason = self.tr("This table is empty and cannot be exported.")
        elif not any(choice.isEnabled() and choice.isChecked() for choice in self._table_choices.values()):
            reason = self.tr("Select at least one available table to export.")
        elif request is None:
            reason = self.tr("Choose exactly one table for CSV or binary export.")
        else:
            reason = ""
        self._selection_explanation.setText(f"{reason}\n{format_explanation}" if reason else format_explanation)
        self._export_button.setEnabled(request is not None)
        self._export_button.setToolTip(reason)

    def _update_statistics_export_enabled(self) -> None:
        """Preserve Statistics picks and explain format-specific constraints."""
        excel = self._format_combo.currentData() is StatisticsExportFormat.EXCEL
        format_explanation = (
            self.tr("Excel exports selected tables as separate sheets and charts on one Charts sheet.")
            if excel
            else self.tr(
                "Choose exactly one table for CSV or binary export. "
                "Charts are available only in Excel; uncheck Charts to continue."
            )
        )
        request = self.export_request()
        choices = (
            self._hypothesis_choices
            if self._hypothesis_mode
            else self._correlation_choices
            if self._correlation_mode
            else self._regression_choices
            if self._regression_mode
            else self._outliers_choices
            if self._outliers_mode
            else self._clustering_choices
            if self._clustering_mode
            else self._pca_choices
            if self._pca_mode
            else self._time_series_choices
            if self._time_series_mode
            else self._statistics_choices
        )
        selected = any(choice.isEnabled() and choice.isChecked() for choice in choices.values())
        available = any(choice.isEnabled() for choice in choices.values())
        chart_choice = (
            self._hypothesis_choices.get(HypothesisExportComponent.CHARTS)
            if self._hypothesis_mode
            else None
            if self._correlation_mode
            else self._regression_choices.get(RegressionExportComponent.CHARTS)
            if self._regression_mode
            else self._outliers_choices.get(OutlierExportComponent.CHARTS)
            if self._outliers_mode
            else self._clustering_choices.get(ClusteringExportComponent.CHARTS)
            if self._clustering_mode
            else self._pca_choices.get(PCAExportComponent.CHARTS)
            if self._pca_mode
            else self._time_series_choices.get(TimeSeriesExportComponent.CHARTS)
            if self._time_series_mode
            else self._statistics_choices.get(StatisticsExportTable.CHARTS)
        )
        chart_selected = chart_choice is not None and chart_choice.isEnabled() and chart_choice.isChecked()
        if self._correlation_mode:
            chart_selected = any(
                choice.isChecked()
                for component, choice in self._correlation_choices.items()
                if component is not CorrelationExportComponent.STRONGEST_CORRELATIONS
            )
        if self._hypothesis_mode and self._hypothesis is None:
            reason = self.tr("Apply a hypothesis test successfully before exporting.")
        elif self._correlation_mode and self._correlation is None:
            reason = self.tr("Apply a correlation matrix successfully before exporting.")
        elif self._regression_mode and self._regression is None:
            reason = self.tr("Apply a regression model successfully before exporting.")
        elif self._outliers_mode and self._outliers is None:
            reason = self.tr("Apply an outlier screening successfully before exporting.")
        elif self._clustering_mode and self._clustering is None:
            reason = self.tr("Apply a clustering successfully before exporting.")
        elif self._pca_mode and self._pca is None:
            reason = self.tr("Apply a PCA successfully before exporting.")
        elif self._time_series_mode and self._time_series is None:
            reason = self.tr("Apply a time series successfully before exporting.")
        elif self._statistics_mode and self._statistics is None:
            reason = self.tr("Run Statistics successfully before exporting.")
        elif not available:
            reason = self.tr("This component is empty and cannot be exported.")
        elif not selected:
            reason = self.tr("Select at least one available component to export.")
        elif not excel and chart_selected:
            reason = self.tr("Charts are available only in Excel. Uncheck Charts to continue.")
        elif request is None:
            reason = self.tr("Choose exactly one table for CSV or binary export.")
        else:
            reason = ""
        self._selection_explanation.setText(f"{reason}\n{format_explanation}" if reason else format_explanation)
        self._export_button.setEnabled(request is not None)
        self._export_button.setToolTip(reason)
