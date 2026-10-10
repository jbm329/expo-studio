"""Controller for the Advanced Analysis workspace dialog."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QT_TR_NOOP, QT_TRANSLATE_NOOP, QTimer

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog, build_placeholder_label
from expo_jbm329.gui.dialogs.analysis.chi_square_view import ChiSquareView
from expo_jbm329.gui.dialogs.analysis.clustering_config import ClusteringConfigWidget
from expo_jbm329.gui.dialogs.analysis.clustering_view import ClusteringView
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.correlation_view import CorrelationView
from expo_jbm329.gui.dialogs.analysis.group_comparison_view import GroupComparisonView
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_config import OutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_view import MultivariateOutliersView
from expo_jbm329.gui.dialogs.analysis.outliers_view import OutliersView
from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.paired_comparison_view import PairedComparisonView
from expo_jbm329.gui.dialogs.analysis.pca_config import PCAConfigWidget
from expo_jbm329.gui.dialogs.analysis.pca_view import PCAView
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.regression_glm_view import GeneralizedRegressionView
from expo_jbm329.gui.dialogs.analysis.regression_view import RegressionView
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.gui.dialogs.analysis.survival_view import SurvivalRegressionView
from expo_jbm329.gui.dialogs.analysis.timeseries_config import TimeSeriesConfigWidget
from expo_jbm329.gui.dialogs.analysis.timeseries_view import TimeSeriesView
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import analyze_chi_square, initialize_chi_square
from expo_jbm329.services.analysis.clustering import MIN_SELECTED_COLUMNS as CLUSTERING_MIN_SELECTED_COLUMNS
from expo_jbm329.services.analysis.clustering import ClusteringMethod, analyze_clustering, initialize_clustering
from expo_jbm329.services.analysis.correlation import (
    MAX_SELECTED_COLUMNS,
    MIN_OBSERVATIONS,
    MIN_SELECTED_COLUMNS,
    SIGNIFICANCE_LEVEL,
    CorrelationMethod,
    analyze_correlation_matrix,
    analyze_correlation_pair,
    default_pair,
    initialize_correlation,
)
from expo_jbm329.services.analysis.correlation_charts import CorrelationChartLabels, render_correlation_charts
from expo_jbm329.services.analysis.correlation_export import (
    CorrelationExportComponent,
    CorrelationExportRequest,
    CorrelationExportSnapshot,
    correlation_export_table,
)
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison, initialize_group_comparison
from expo_jbm329.services.analysis.hypothesis_charts import HypothesisChartLabels, render_hypothesis_charts
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent,
    HypothesisExportRequest,
    HypothesisExportSnapshot,
    HypothesisResult,
    hypothesis_export_tables,
)
from expo_jbm329.services.analysis.multivariate_outliers import (
    MultivariateOutlierMethod,
    analyze_multivariate_outliers,
    initialize_multivariate_outliers,
)
from expo_jbm329.services.analysis.outliers import (
    OutlierMethod,
    analyze_outlier_column,
    analyze_outlier_summary,
    default_column,
    initialize_outlier_summary,
)
from expo_jbm329.services.analysis.overview import (
    DatasetOverviewResult,
    OverviewExportFormat,
    OverviewExportRequest,
    OverviewExportTable,
    analyze_dataset_overview,
    overview_export_tables,
)
from expo_jbm329.services.analysis.paired_comparison import (
    PairedComparisonResult,
    analyze_paired_comparison,
    initialize_paired_comparison,
)
from expo_jbm329.services.analysis.pca import MIN_SELECTED_COLUMNS as PCA_MIN_SELECTED_COLUMNS
from expo_jbm329.services.analysis.pca import analyze_pca, initialize_pca
from expo_jbm329.services.analysis.regression import RegressionError, analyze_regression, initialize_regression
from expo_jbm329.services.analysis.regression_glm import (
    GeneralizedRegressionResult,
    GeneralizedTargetColumns,
    RegressionModel,
    analyze_generalized_regression,
    initialize_generalized_targets,
)
from expo_jbm329.services.analysis.statistics import (
    DescriptiveStatisticsResult,
    StatisticsExportFormat,
    StatisticsExportRequest,
    StatisticsExportTable,
    analyze_descriptive_statistics,
    statistics_export_tables,
)
from expo_jbm329.services.analysis.statistics_charts import StatisticsChartLabels, render_statistics_charts
from expo_jbm329.services.analysis.survival import (
    SurvivalColumns,
    SurvivalResult,
    analyze_cox_regression,
    initialize_survival_columns,
)
from expo_jbm329.services.analysis.timeseries import analyze_time_series, initialize_time_series
from expo_jbm329.utils.format_utils import fmt_int, fmt_num
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.services.analysis.chi_square import ChiSquareResult
    from expo_jbm329.services.analysis.clustering import ClusteringResult
    from expo_jbm329.services.analysis.correlation import CorrelationMatrixResult, CorrelationPairDetail
    from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
    from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierResult
    from expo_jbm329.services.analysis.outliers import OutlierColumnDetail, OutlierSummaryResult
    from expo_jbm329.services.analysis.pca import PCAResult
    from expo_jbm329.services.analysis.regression import RegressionResult
    from expo_jbm329.services.analysis.timeseries import TimeSeriesResult
    from expo_jbm329.services.excel_chart import ExcelChartImage
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.export_controller import ExportController
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import (
        ResultTabManager,
    )


# Matches AsyncOperationController's default overlay watchdog.
_DEFAULT_TIMEOUT_MS = 60_000
_HYPOTHESIS_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Test results"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Test statistic"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "p-value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Degrees of freedom"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Mean difference"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "95% CI lower"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "95% CI upper"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Effect size"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Effect value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Numeric column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Grouping column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Row column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Column column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Sample count"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Yates' continuity correction"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cochran's rule violated"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Fraction of expected counts below 5"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Minimum expected count"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Odds ratio"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Total subjects"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Excluded subjects"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Notes"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Measurement"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Welch's t-test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Student's t-test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Mann-Whitney U"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "One-way ANOVA"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Kruskal-Wallis"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Pearson's chi-square test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Fisher's exact test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Wilcoxon signed-rank test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Friedman test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cohen's d"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Rank-biserial correlation"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Eta²"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Epsilon²"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cramér's V"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Kendall's W"),
    QT_TRANSLATE_NOOP("ChiSquareView", "Contingency table"),
)
_CORRELATION_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Least-squares line: y = ({slope}) x + ({intercept})"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Strongest correlations"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Correlation method"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Coefficient"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Significant after Holm"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Ranking and Holm explanation"),
    QT_TRANSLATE_NOOP(
        "AnalysisExportDialog",
        "Pairs are ranked by absolute coefficient. Significance is based on "
        "p < {alpha} after Holm adjustment for {count} tests.",
    ),
)
# Cancelable jobs report real progress and can be stopped by the user, so
# they get a far longer watchdog before the "taking too long" warning.
_CANCELABLE_TIMEOUT_MS = 600_000


@dataclass(frozen=True, slots=True)
class _JobCallbacks:
    """Cooperative progress/cancellation hooks injected into a background job.

    Attributes:
        progress_cb: Receives the completed percentage (0-100), or `None`.
        cancel_cb: Returns True once the user has asked to cancel, or `None`.
    """

    progress_cb: Callable[[int], None] | None = None
    cancel_cb: Callable[[], bool] | None = None


def _ignore_callbacks(compute: Callable[[pd.DataFrame], object]) -> Callable[[pd.DataFrame, _JobCallbacks], object]:
    """Adapt a computation that neither reports progress nor supports cancellation."""

    def _compute(df: pd.DataFrame, _callbacks: _JobCallbacks) -> object:
        return compute(df)

    return _compute


@dataclass(frozen=True, slots=True)
class _CategoryHandler:
    """Pairs a category's background computation with its GUI rendering.

    Kept as two separate callables because Qt widgets must only ever be
    created on the GUI thread, while `compute` runs on a background pool
    thread via JobManager/AsyncOperationController.

    Attributes:
        compute: Background-safe callable turning a DataFrame (plus the
            job's progress/cancellation hooks) into a plain (non-Qt) result
            object, or `None` if it was cancelled.
        render: GUI-thread callable turning that result object (plus the
            active dialog, so config widgets needing to trigger their own
            recompute - see `AnalysisController._recompute_content` - can
            be wired up here) into ``(content_widget, config_widget)`` -
            the widgets to display in the dialog's result pane and
            configuration pane, respectively. `config_widget` is `None`
            for categories with no configurable input (the configuration
            pane is then hidden).
        cancelable: Whether `compute` reports progress and honors
            cancellation - the busy overlay then shows a progress bar and
            a Cancel button.
        initialize: Optional GUI-thread-cheap callable turning a DataFrame
            into a metadata-only result (column lists and defaults, no
            model fitting). When set, opening the category renders this
            result synchronously - no background job or busy overlay -
            and `compute` is not run; computation then starts only when
            the user applies a configuration.
    """

    compute: Callable[[pd.DataFrame, _JobCallbacks], object]
    render: Callable[[object, AnalysisDialog], tuple[QWidget, QWidget | None]]
    cancelable: bool = False
    initialize: Callable[[pd.DataFrame], object] | None = None


@dataclass(frozen=True, slots=True)
class _HypothesisTestsDefaults:
    """Every hypothesis test's default configuration, without any test computed.

    The Hypothesis Tests category's initial result, so each test's column
    pickers in `HypothesisTestsConfigWidget` can be populated up front.
    """

    group_comparison: GroupComparisonResult
    chi_square: ChiSquareResult
    paired_comparison: PairedComparisonResult


@dataclass(frozen=True, slots=True)
class _RegressionDefaults:
    """Regression defaults and eligible outcome metadata for all model families."""

    linear: RegressionResult
    generalized_targets: GeneralizedTargetColumns
    survival_columns: SurvivalColumns


@dataclass(frozen=True, slots=True)
class _CorrelationOutcome:
    """A correlation matrix plus the detail of its selected pair.

    Attributes:
        matrix: The computed correlation matrix.
        pair_detail: The selected pair's detail, or `None` when the matrix
            has an error (and so no pair to show).
        export_snapshot: Owned selected numeric columns for the successful matrix.
    """

    matrix: CorrelationMatrixResult
    pair_detail: CorrelationPairDetail | None
    export_snapshot: CorrelationExportSnapshot | None = None


@dataclass(frozen=True, slots=True)
class _OutliersOutcome:
    """An outlier summary plus the detail of its selected column.

    Attributes:
        summary: The per-column outlier summary.
        detail: The selected column's detail, or `None` when the summary
            has an error (and so no column to show).
    """

    summary: OutlierSummaryResult
    detail: OutlierColumnDetail | None


class AnalysisController:
    """Controller responsible for the Advanced Analysis workspace workflow.

    Each analysis category is backed by a `_CategoryHandler`. Automatic
    categories (Overview, Statistics) compute as soon as they are opened;
    computation always runs as a background job (JobManager, via
    AsyncOperationController) with a busy overlay shown over the dialog's
    result pane, so large datasets never freeze the GUI thread.
    Apply-first categories only build their configuration when opened and
    compute once the user applies it. Categories without a registered
    handler fall back to the not-implemented placeholder.
    """

    TR_NOT_IMPLEMENTED = QT_TR_NOOP("This analysis is not implemented yet.")
    TR_ANALYSIS_ERROR = QT_TR_NOOP("An error occurred while generating this analysis.")
    TR_RUNNING_ANALYSIS = QT_TR_NOOP("Running analysis…")
    TR_ANALYSIS_OPERATION = QT_TR_NOOP("generate analysis")
    TR_ANALYSIS_CANCELLED = QT_TR_NOOP("Analysis cancelled.")
    TR_APPLY_PROMPT = QT_TR_NOOP("Choose settings and click Apply.")

    @staticmethod
    def _tr(text: str) -> str:
        """Translate a UI string for this controller."""
        return tr("AnalysisController", text)

    def __init__(
        self,
        *,
        results: ResultTabManager,
        async_ops: AsyncOperationController,
        export_controller: ExportController | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the analysis controller.

        Args:
            results: ResultTabManager instance.
            async_ops: Controller running analyses as background jobs.
            export_controller: Shared exporter receiving per-call analysis dialog context.
            logger: Optional logger instance.
        """
        self._results = results
        self._async_ops = async_ops
        self._export_controller = export_controller
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        self._category_handlers: dict[AnalysisCategory, _CategoryHandler] = {
            AnalysisCategory.OVERVIEW: _CategoryHandler(
                compute=_ignore_callbacks(analyze_dataset_overview),
                render=self._render_overview,
            ),
            AnalysisCategory.STATISTICS: _CategoryHandler(
                compute=_ignore_callbacks(analyze_descriptive_statistics),
                render=self._render_statistics,
            ),
            AnalysisCategory.HYPOTHESIS_TESTS: _CategoryHandler(
                compute=_ignore_callbacks(self._initialize_hypothesis_tests),
                render=self._render_hypothesis_tests,
                initialize=self._initialize_hypothesis_tests,
            ),
            AnalysisCategory.CORRELATION: _CategoryHandler(
                compute=self._compute_correlation,
                render=self._render_correlation,
                cancelable=True,
                initialize=initialize_correlation,
            ),
            AnalysisCategory.REGRESSION: _CategoryHandler(
                compute=_ignore_callbacks(analyze_regression),
                render=self._render_regression,
                initialize=self._initialize_regression,
            ),
            AnalysisCategory.OUTLIERS: _CategoryHandler(
                compute=_ignore_callbacks(self._compute_outliers),
                render=self._render_outliers,
                initialize=initialize_outlier_summary,
            ),
            AnalysisCategory.CLUSTERING: _CategoryHandler(
                compute=_ignore_callbacks(analyze_clustering),
                render=self._render_clustering,
                initialize=initialize_clustering,
            ),
            AnalysisCategory.PCA: _CategoryHandler(
                compute=_ignore_callbacks(analyze_pca),
                render=self._render_pca,
                initialize=initialize_pca,
            ),
            AnalysisCategory.TIME_SERIES: _CategoryHandler(
                compute=_ignore_callbacks(analyze_time_series),
                render=self._render_time_series,
                initialize=initialize_time_series,
            ),
        }

    def open_dialog(self, parent: QWidget) -> None:
        """Open the Advanced Analysis dialog.

        Args:
            parent: Parent widget for the dialog.
        """
        datasets = self._results.list_ready_datasets()
        if not datasets:
            return

        dialog = AnalysisDialog(
            parent=parent,
            datasets=datasets,
            active_tab_id=self._results.active_tab_id(),
        )
        if self._export_controller is not None:
            exporter = self._export_controller

            def _handle_export(request: object) -> None:
                self._export_overview(dialog, exporter, request)

            def _handle_statistics_export(request: object) -> None:
                self._export_statistics(dialog, exporter, request)

            def _handle_hypothesis_export(request: object) -> None:
                self._export_hypothesis(dialog, exporter, request)

            def _handle_correlation_export(request: object) -> None:
                self._export_correlation(dialog, exporter, request)

            dialog.overview_export_requested.connect(_handle_export)
            dialog.statistics_export_requested.connect(_handle_statistics_export)
            dialog.hypothesis_export_requested.connect(_handle_hypothesis_export)
            dialog.correlation_export_requested.connect(_handle_correlation_export)

        refresh_started = False

        def _refresh_after_interaction() -> None:
            nonlocal refresh_started
            refresh_started = True
            self._refresh_content(dialog)

        def _handle_category_changed(_category_value: str) -> None:
            _refresh_after_interaction()

        def _handle_dataset_changed(_tab_id: str) -> None:
            _refresh_after_interaction()

        dialog.category_changed.connect(_handle_category_changed)
        dialog.dataset_changed.connect(_handle_dataset_changed)

        # Overview is already selected by the time the dialog is constructed
        # (see AnalysisDialog), but that self-emission happens before the
        # connections above exist. Deferred by one event-loop tick so the
        # dialog is already shown (and correctly sized) once the initial
        # busy overlay is created - showing an overlay on a not-yet-shown
        # widget would compute its geometry against a stale/default size.
        def _refresh_initial_content() -> None:
            if not refresh_started:
                self._refresh_content(dialog)

        QTimer.singleShot(0, _refresh_initial_content)

        dialog.exec()

    def _export_overview(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Validate snapshot identity and route owned frames to existing exporters."""
        if not isinstance(request, OverviewExportRequest) or request.result is not dialog.exportable_overview():
            return
        if not any(request.format is format_choice for format_choice in OverviewExportFormat):
            return
        if request.format is not OverviewExportFormat.EXCEL and len(request.tables) != 1:
            return
        try:
            sheets = overview_export_tables(request.result, request.tables)
            localized_sheets = {}
            for name, frame in sheets.items():
                table = OverviewExportTable(name)
                sheet_name = tr("OverviewView", table.value)
                if sheet_name in localized_sheets:
                    self._logger.warning("Rejected Overview export because translated sheet names are not unique.")
                    return
                match table:
                    case OverviewExportTable.COLUMNS:
                        headers = {
                            "column": tr("OverviewView", "Column"),
                            "type": tr("OverviewView", "Type"),
                            "storage_type": tr("OverviewView", "Storage type"),
                            "missing_count": tr("OverviewView", "Missing"),
                            "missing_fraction": tr("OverviewView", "Missing fraction"),
                            "unique_count": tr("OverviewView", "Unique"),
                        }
                    case OverviewExportTable.SUMMARY:
                        headers = {
                            "section": tr("OverviewView", "Section"),
                            "metric": tr("OverviewView", "Metric"),
                            "column": tr("OverviewView", "Column"),
                            "count": tr("OverviewView", "Count"),
                            "fraction": tr("OverviewView", "Fraction"),
                        }
                    case OverviewExportTable.SAMPLE:
                        headers = {}
                localized_sheets[sheet_name] = frame.rename(columns=headers)
            sheets = localized_sheets
        except (TypeError, ValueError):
            self._logger.warning("Rejected unavailable Overview export selection.")
            return
        # Frames belong to this export only and remain stable for the async job.
        match request.format:
            case OverviewExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case OverviewExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case OverviewExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    def _export_statistics(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Route validated Statistics snapshots to existing asynchronous exporters."""
        if not isinstance(request, StatisticsExportRequest) or request.result is not dialog.exportable_statistics():
            return
        if request.format not in tuple(StatisticsExportFormat):
            return
        if len(set(request.tables)) != len(request.tables):
            return
        charts_selected = StatisticsExportTable.CHARTS in request.tables
        table_choices = tuple(table for table in request.tables if table is not StatisticsExportTable.CHARTS)
        if not charts_selected and not table_choices:
            return
        if request.format is not StatisticsExportFormat.EXCEL and (charts_selected or len(table_choices) != 1):
            return

        try:
            tables = statistics_export_tables(request.result, table_choices) if table_choices else {}
            localized_sheets: dict[str, pd.DataFrame] = {}
            for name, frame in tables.items():
                table = StatisticsExportTable(name)
                sheet_name = tr("StatisticsView", table.value)
                if sheet_name.casefold() in {existing.casefold() for existing in localized_sheets}:
                    self._logger.warning("Rejected Statistics export because translated sheet names are not unique.")
                    return
                match table:
                    case StatisticsExportTable.CONTINUOUS:
                        headers = {
                            "column": "Column",
                            "count": "Count",
                            "missing_count": "Missing count",
                            "missing_fraction": "Missing fraction",
                            "mean": "Mean",
                            "median": "Median",
                            "std": "Std Dev",
                            "variance": "Variance",
                            "minimum": "Min",
                            "maximum": "Max",
                            "range": "Range",
                            "q1": "Q1",
                            "q3": "Q3",
                            "iqr": "IQR",
                            "skewness": "Skewness",
                            "kurtosis": "Kurtosis",
                            "mean_sd_summary": "Mean ± SD",
                            "median_iqr_summary": "Median (Q1 to Q3)",
                            "shapiro_statistic": "Shapiro-Wilk W",
                            "shapiro_p_value": "Shapiro-Wilk p-value",
                            "recommended_summary_method": "Recommended summary",
                        }
                    case StatisticsExportTable.CATEGORICAL:
                        headers = {
                            "column": "Column",
                            "value": "Category",
                            "count": "Count",
                            "fraction": "Fraction (non-missing)",
                            "valid_count": "Valid count",
                            "missing_count": "Missing count",
                            "missing_fraction": "Missing fraction",
                        }
                    case _:
                        return
                localized_sheets[sheet_name] = frame.rename(
                    columns={key: tr("StatisticsView", value) for key, value in headers.items()}
                )
        except (TypeError, ValueError):
            self._logger.warning("Rejected unavailable Statistics export selection.")
            return

        match request.format:
            case StatisticsExportFormat.EXCEL:
                chart_sheet_name = tr("StatisticsView", StatisticsExportTable.CHARTS.value)
                chart_factory: (
                    Callable[
                        [Callable[[int], None] | None, Callable[[], bool] | None],
                        tuple[ExcelChartImage, ...],
                    ]
                    | None
                ) = None
                if charts_selected:
                    labels = StatisticsChartLabels(
                        histogram=tr("StatisticsView", "Histogram"),
                        boxplot=tr("StatisticsView", "Boxplot"),
                        no_data=tr("StatisticsView", "No data"),
                    )

                    def make_chart_images(
                        progress_cb: Callable[[int], None] | None,
                        cancel_cb: Callable[[], bool] | None,
                    ) -> tuple[ExcelChartImage, ...]:
                        return render_statistics_charts(
                            request.result.columns,
                            labels,
                            progress_cb=progress_cb,
                            cancel_cb=cancel_cb,
                        )

                    chart_factory = make_chart_images

                exporter.export_excel(
                    sheets=localized_sheets,
                    chart_factory=chart_factory,
                    chart_sheet_name=chart_sheet_name if charts_selected else None,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(localized_sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(localized_sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    def _export_hypothesis(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Localize owned applied-result tables and render worker-owned Excel charts."""
        if not isinstance(request, HypothesisExportRequest) or request.snapshot is not dialog.exportable_hypothesis():
            return
        snapshot = request.snapshot
        charts = HypothesisExportComponent.CHARTS in request.components
        table_choices = tuple(item for item in request.components if item is not HypothesisExportComponent.CHARTS)
        contexts = {
            HypothesisTest.GROUP_COMPARISON: "GroupComparisonView",
            HypothesisTest.CHI_SQUARE: "ChiSquareView",
            HypothesisTest.PAIRED_COMPARISON: "PairedComparisonView",
        }
        context = contexts[snapshot.test]
        summaries = {
            HypothesisTest.GROUP_COMPARISON: "Group summary",
            HypothesisTest.CHI_SQUARE: "Contingency table",
            HypothesisTest.PAIRED_COMPARISON: "Measurement summary",
        }
        common_headers = {
            "group": "Group",
            "count": "Count",
            "mean": "Mean",
            "median": "Median",
            "std": "Std Dev",
            "shapiro_statistic": "Shapiro W",
            "shapiro_p_value": "Shapiro p",
            "normal": "Normal?",
            "measurement": "Measurement",
            "q1": "Q1",
            "q3": "Q3",
        }
        result_headers = {
            "test": "Test",
            "statistic": "Test statistic",
            "p_value": "p-value",
            "degrees_of_freedom": "Degrees of freedom",
            "mean_difference": "Mean difference",
            "ci_low": "95% CI lower",
            "ci_high": "95% CI upper",
            "effect_name": "Effect size",
            "effect_size": "Effect value",
            "numeric_column": "Numeric column",
            "grouping_column": "Grouping column",
            "row_column": "Row column",
            "column_column": "Column column",
            "sample_count": "Sample count",
            "yates_correction": "Yates' continuity correction",
            "cochran_violated": "Cochran's rule violated",
            "low_expected_fraction": "Fraction of expected counts below 5",
            "min_expected": "Minimum expected count",
            "odds_ratio": "Odds ratio",
            "total_subjects": "Total subjects",
            "excluded_subjects": "Excluded subjects",
            "notes": "Notes",
        }
        tables = hypothesis_export_tables(snapshot, table_choices) if table_choices else {}
        sheets: dict[str, pd.DataFrame] = {}
        for component, source_frame in tables.items():
            frame = source_frame
            name = summaries[snapshot.test] if component is HypothesisExportComponent.SUMMARY else "Test results"
            sheet_name = tr(context, name)
            if sheet_name.casefold() in {existing.casefold() for existing in sheets}:
                message = "Translated hypothesis sheet names must be unique."
                raise ValueError(message)
            if component is HypothesisExportComponent.SUMMARY:
                if snapshot.test is HypothesisTest.CHI_SQUARE:
                    frame.columns = [
                        snapshot.columns[0],
                        *cast("ChiSquareResult", snapshot.result).column_labels,
                        tr(context, "Total"),
                    ]
                    frame.iloc[-1, 0] = tr(context, "Total")
                else:
                    frame = frame.rename(columns={key: tr(context, text) for key, text in common_headers.items()})
            else:
                frame = frame.rename(
                    columns={
                        key: tr("AnalysisExportDialog", result_headers.get(key, "Measurement"))
                        + (f" {key.removeprefix('measurement_')}" if key.startswith("measurement_") else "")
                        for key in frame.columns
                    }
                )
                # Test names are presentation labels; applied dataset column names stay literal.
                test_header = tr("AnalysisExportDialog", "Test")
                effect_header = tr("AnalysisExportDialog", "Effect size")
                frame[test_header] = frame[test_header].map(
                    lambda value: tr("AnalysisExportDialog", value) if isinstance(value, str) else value
                )
                if effect_header in frame:
                    frame[effect_header] = frame[effect_header].map(
                        lambda value: tr("AnalysisExportDialog", value) if isinstance(value, str) else value
                    )
            sheets[sheet_name] = frame
        if request.format is StatisticsExportFormat.EXCEL:
            labels = HypothesisChartLabels(
                distribution=tr(
                    context,
                    "Distribution by group"
                    if snapshot.test is HypothesisTest.GROUP_COMPARISON
                    else "Distribution by occasion",
                ),
                residuals=tr("ChiSquareView", "Adjusted standardized residuals"),
                trajectories=tr("PairedComparisonView", "Subject trajectories"),
                value=tr("PairedComparisonView", "Value"),
                occasion=tr("PairedComparisonView", "Measurement occasion"),
                residual_annotations=(
                    ChiSquareView.chart_annotations(cast("ChiSquareResult", snapshot.result))
                    if snapshot.test is HypothesisTest.CHI_SQUARE
                    else ()
                ),
            )

            def make_images(
                progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
            ) -> tuple[ExcelChartImage, ...]:
                return render_hypothesis_charts(snapshot, labels, progress_cb=progress_cb, cancel_cb=cancel_cb)

            exporter.export_excel(
                sheets=sheets,
                chart_factory=make_images if charts else None,
                chart_sheet_name=tr("AnalysisExportDialog", "Charts") if charts else None,
                parent_widget=dialog,
                operation_target=dialog.content_panel(),
                show_success_dialog=True,
            )
        elif request.format is StatisticsExportFormat.CSV:
            exporter.export_csv(
                df=next(iter(sheets.values())),
                parent_widget=dialog,
                operation_target=dialog.content_panel(),
                show_success_dialog=True,
            )
        else:
            exporter.export_data(
                df=next(iter(sheets.values())),
                parent_widget=dialog,
                operation_target=dialog.content_panel(),
                show_success_dialog=True,
            )

    def _localized_correlation_table(self, snapshot: CorrelationExportSnapshot) -> pd.DataFrame:
        """Localize the ranked table while preserving numeric statistics."""
        frame = correlation_export_table(snapshot, (CorrelationExportComponent.STRONGEST_CORRELATIONS,))

        methods = {
            CorrelationMethod.PEARSON: tr("CorrelationView", "Pearson"),
            CorrelationMethod.SPEARMAN: tr("CorrelationView", "Spearman"),
            CorrelationMethod.KENDALL: tr("CorrelationView", "Kendall's tau-b"),
        }
        strengths = {
            "negligible": tr("CorrelationView", "Negligible"),
            "weak": tr("CorrelationView", "Weak"),
            "moderate": tr("CorrelationView", "Moderate"),
            "strong": tr("CorrelationView", "Strong"),
        }
        frame["strength"] = frame["strength"].map(
            lambda value: strengths[value] if isinstance(value, str) else tr("CorrelationView", "N/A")
        )
        frame["method"] = frame["method"].map(lambda value: methods[CorrelationMethod(str(value))])
        frame["ranking_explanation"] = tr(
            "AnalysisExportDialog",
            "Pairs are ranked by absolute coefficient. Significance is based on "
            "p < {alpha} after Holm adjustment for {count} tests.",
        ).format(alpha=fmt_num(SIGNIFICANCE_LEVEL), count=fmt_int(len(snapshot.matrix.pairs)))
        headers = {
            "variable_1": tr("CorrelationView", "Variable 1"),
            "variable_2": tr("CorrelationView", "Variable 2"),
            "coefficient": tr("AnalysisExportDialog", "Coefficient"),
            "ci_low": tr("AnalysisExportDialog", "95% CI lower"),
            "ci_high": tr("AnalysisExportDialog", "95% CI upper"),
            "p_value": tr("CorrelationView", "p"),
            "adjusted_p_value": tr("CorrelationView", "Holm p"),
            "n": tr("CorrelationView", "n"),
            "strength": tr("CorrelationView", "Strength"),
            "significant": tr("AnalysisExportDialog", "Significant after Holm"),
            "method": tr("AnalysisExportDialog", "Correlation method"),
            "ranking_explanation": tr("AnalysisExportDialog", "Ranking and Holm explanation"),
        }
        return frame.rename(columns=headers)

    def _export_correlation(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Export applied tables and worker-owned chart images from one snapshot."""
        if not isinstance(request, CorrelationExportRequest) or request.snapshot is not dialog.exportable_correlation():
            return
        snapshot = request.snapshot
        sheet_name = tr("AnalysisExportDialog", "Strongest correlations")
        sheets = (
            {sheet_name: self._localized_correlation_table(snapshot)}
            if CorrelationExportComponent.STRONGEST_CORRELATIONS in request.components
            else {}
        )
        charts = tuple(
            component
            for component in request.components
            if component is not CorrelationExportComponent.STRONGEST_CORRELATIONS
        )
        method_names = {
            CorrelationMethod.PEARSON: tr("CorrelationView", "Pearson"),
            CorrelationMethod.SPEARMAN: tr("CorrelationView", "Spearman"),
            CorrelationMethod.KENDALL: tr("CorrelationView", "Kendall's tau-b"),
        }
        method_name = method_names[snapshot.matrix.method]
        labels = CorrelationChartLabels(
            matrix_title=tr("CorrelationView", "{method} correlation").format(method=method_name),
            scatter_heading="{x} / {y} (" + method_name + ")",
            line_equation=tr("AnalysisExportDialog", "Least-squares line: y = ({slope}) x + ({intercept})"),
            descriptive_line=tr(
                "CorrelationView",
                "The line is a linear fit shown for reference. {method} measures monotonic, "
                "not necessarily linear, association.",
            ).format(method=method_name),
            sampling=tr(
                "CorrelationView", "Showing a random sample of {shown} of {total} points. Statistics use all points."
            ),
            insufficient_observations=tr(
                "CorrelationView",
                "Fewer than {minimum} rows have values in both columns, so no correlation can be computed.",
            ).format(minimum=fmt_int(MIN_OBSERVATIONS)),
            constant_input=tr(
                "CorrelationView",
                "At least one of the columns is constant over the rows with values in both, "
                "so no correlation can be computed.",
            ),
            number_format=fmt_num,
            count_format=fmt_int,
            matrix_annotations=CorrelationView.chart_annotations(snapshot.matrix),
        )

        def make_images(
            progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
        ) -> tuple[ExcelChartImage, ...]:
            return render_correlation_charts(snapshot, charts, labels, progress_cb=progress_cb, cancel_cb=cancel_cb)

        match request.format:
            case StatisticsExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    chart_factory=make_images if charts else None,
                    chart_sheet_name=tr("AnalysisExportDialog", "Charts") if charts else None,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    # ------------------------------------------------------------------
    # Renderers (GUI thread only)
    # ------------------------------------------------------------------

    def _render_overview(self, result: object, _dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Dataset Overview view. Must run on the GUI thread."""
        return OverviewView(cast("DatasetOverviewResult", result)), None

    def _render_statistics(self, result: object, _dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render full-width Statistics with column selection owned by its table.

        Must run on the GUI thread.
        """
        stats_result = cast("DescriptiveStatisticsResult", result)
        content = StatisticsView(stats_result)

        return content, None

    def _render_hypothesis_tests(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Hypothesis Tests Apply prompt and its test/column-picker config.

        Must run on the GUI thread. Nothing is computed until the user
        clicks Apply; the configuration widget's `apply_requested` signal is
        wired to `_recompute_content`, which dispatches a background job and
        replaces only the content pane, leaving this exact configuration
        widget instance (and the user's picks) in place. Switching test
        replaces the previous test's result with the prompt again.
        """
        defaults = cast("_HypothesisTestsDefaults", result)
        config = HypothesisTestsConfigWidget(
            defaults.group_comparison,
            defaults.chi_square,
            defaults.paired_comparison,
        )

        def _unapplied_content() -> QWidget:
            test = config.selected_test()
            initial_by_test: dict[HypothesisTest, GroupComparisonResult | ChiSquareResult | PairedComparisonResult] = {
                HypothesisTest.GROUP_COMPARISON: defaults.group_comparison,
                HypothesisTest.CHI_SQUARE: defaults.chi_square,
                HypothesisTest.PAIRED_COMPARISON: defaults.paired_comparison,
            }
            initial = initial_by_test[test]
            if initial.error is None:
                return self._apply_prompt()
            return self._render_hypothesis_test_content(test, initial)

        def _handle_apply_requested() -> None:
            configuration = config.applied_configuration()
            if configuration is None:
                return
            test, selection = configuration

            def apply_displayed_result(value: object) -> None:
                """Register a snapshot only after the accepted result is displayed."""
                content = self._render_hypothesis_test_content(test, value)
                dialog.set_content_widget(content)
                typed_result: HypothesisResult
                columns: tuple[str, ...]
                if isinstance(content, GroupComparisonView):
                    typed_result = cast("GroupComparisonResult", value)
                    columns = (typed_result.numeric_column, typed_result.grouping_column)
                    notes = content.export_notes(typed_result)
                elif isinstance(content, ChiSquareView):
                    chi_result = cast("ChiSquareResult", value)
                    columns = (chi_result.row_column, chi_result.column_column)
                    notes = content.export_notes(chi_result)
                    typed_result = chi_result
                else:
                    paired_result = cast("PairedComparisonResult", value)
                    columns = paired_result.columns
                    notes = cast("PairedComparisonView", content).export_notes(paired_result)
                    typed_result = paired_result
                if typed_result.error is not None:
                    return
                snapshot = HypothesisExportSnapshot(
                    test,
                    typed_result,
                    selection if selection is not None else columns,
                    notes,
                )
                dialog.set_exportable_hypothesis(snapshot)

            self._recompute_content(
                dialog,
                category=AnalysisCategory.HYPOTHESIS_TESTS,
                scope_suffix=":".join((test.value, *(selection or ()))),
                compute=lambda df, _callbacks: self._compute_hypothesis_test(df, test, selection),
                apply_result=apply_displayed_result,
                is_stale=lambda: (
                    config.applied_configuration() is not configuration or config.selected_test() is not test
                ),
            )

        config.test_changed.connect(lambda: dialog.set_content_widget(_unapplied_content()))
        config.apply_requested.connect(_handle_apply_requested)
        return _unapplied_content(), config

    @staticmethod
    def _initialize_hypothesis_tests(df: pd.DataFrame) -> _HypothesisTestsDefaults:
        """Return every hypothesis test's default configuration without computing a test."""
        return _HypothesisTestsDefaults(
            group_comparison=initialize_group_comparison(df),
            chi_square=initialize_chi_square(df),
            paired_comparison=initialize_paired_comparison(df),
        )

    @staticmethod
    def _compute_hypothesis_test(
        df: pd.DataFrame,
        test: HypothesisTest,
        selection: tuple[str, ...] | None,
    ) -> object:
        """Compute one hypothesis test for `selection`, or its defaults when `None`."""
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return (
                    analyze_group_comparison(df)
                    if selection is None
                    else analyze_group_comparison(df, selection[0], selection[1])
                )
            case HypothesisTest.CHI_SQUARE:
                return (
                    analyze_chi_square(df) if selection is None else analyze_chi_square(df, selection[0], selection[1])
                )
            case HypothesisTest.PAIRED_COMPARISON:
                return analyze_paired_comparison(df, selection or ())

    @staticmethod
    def _render_hypothesis_test_content(test: HypothesisTest, result: object) -> QWidget:
        """Build the content view for one computed hypothesis test (GUI thread only)."""
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return GroupComparisonView(cast("GroupComparisonResult", result))
            case HypothesisTest.CHI_SQUARE:
                return ChiSquareView(cast("ChiSquareResult", result))
            case HypothesisTest.PAIRED_COMPARISON:
                return PairedComparisonView(cast("PairedComparisonResult", result))

    @staticmethod
    def _compute_correlation(
        df: pd.DataFrame,
        callbacks: _JobCallbacks,
        *,
        method: CorrelationMethod = CorrelationMethod.PEARSON,
        columns: tuple[str, ...] | None = None,
        pair: tuple[str, str] | None = None,
    ) -> _CorrelationOutcome | None:
        """Compute a correlation matrix and its pair detail (background-safe).

        Args:
            df: The DataFrame to analyze.
            callbacks: The job's progress/cancellation hooks.
            method: The correlation coefficient to compute.
            columns: Matrix columns, or `None` for the service's default.
            pair: The pair to detail, or `None` for the matrix's strongest.

        Returns:
            The outcome, or `None` if cancelled.
        """
        configuration = initialize_correlation(df)
        selected = configuration.columns if columns is None else tuple(columns)
        selection_is_valid = (
            len(selected) <= MAX_SELECTED_COLUMNS
            and len(selected) >= MIN_SELECTED_COLUMNS
            and len(set(selected)) == len(selected)
            and all(column in configuration.available_columns for column in selected)
        )
        if not selection_is_valid:
            # The public analyzer returns a structured selection error without
            # indexing the frame; retain that behavior for invalid requests.
            matrix = analyze_correlation_matrix(
                df,
                columns,
                method,
                progress_cb=callbacks.progress_cb,
                cancel_cb=callbacks.cancel_cb,
            )
            if matrix is None:
                return None
            return _CorrelationOutcome(matrix=matrix, pair_detail=None)

        matrix_data = df.loc[:, list(selected)].copy(deep=True)
        matrix = analyze_correlation_matrix(
            matrix_data,
            selected,
            method,
            progress_cb=callbacks.progress_cb,
            cancel_cb=callbacks.cancel_cb,
        )
        if matrix is None:
            return None
        if matrix.error is not None:
            return _CorrelationOutcome(matrix=matrix, pair_detail=None)
        matrix = replace(matrix, available_columns=configuration.available_columns)

        detail_pair = (
            pair
            if pair is not None and pair[0] != pair[1] and all(column in matrix.columns for column in pair)
            else default_pair(matrix)
        )
        pair_detail = analyze_correlation_pair(matrix_data, *detail_pair, method) if detail_pair is not None else None
        snapshot = CorrelationExportSnapshot(matrix=matrix, matrix_data=matrix_data)
        return _CorrelationOutcome(matrix=matrix, pair_detail=pair_detail, export_snapshot=snapshot)

    def _render_correlation(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Correlation Explorer's initial state: the Apply prompt and its config.

        Must run on the GUI thread. `result` is the configuration-only
        `initialize_correlation` matrix; nothing is computed until the user
        applies a method and column selection, which recomputes the whole
        matrix (a cancelable job replacing the view). Once a matrix is
        shown, a pair change recomputes only the pair detail (a quick job
        updating the current view's pair panel in place).
        """
        matrix = cast("CorrelationMatrixResult", result)
        if len(matrix.available_columns) < MIN_SELECTED_COLUMNS:
            return CorrelationView(matrix, None), None

        config = CorrelationConfigWidget(matrix)

        def _handle_matrix_requested() -> None:
            self._recompute_correlation_matrix(dialog, config)

        config.matrix_requested.connect(_handle_matrix_requested)
        return self._apply_prompt(), config

    def _build_correlation_view(self, outcome: _CorrelationOutcome, dialog: AnalysisDialog) -> CorrelationView:
        """Build a Correlation Explorer view whose table rows request pair details."""
        view = CorrelationView(outcome.matrix, outcome.pair_detail)

        def _handle_pair_activated(x_column: str, y_column: str) -> None:
            if dialog.content_widget() is view:
                self._recompute_correlation_pair(dialog, x_column, y_column)

        view.pair_activated.connect(_handle_pair_activated)
        return view

    def _recompute_correlation_matrix(self, dialog: AnalysisDialog, config: CorrelationConfigWidget) -> None:
        """Recompute the whole correlation matrix for the config's applied method and columns.

        Preserve the table-selected pair when it remains in the applied
        columns; otherwise detail the new matrix's strongest pair.
        """
        dialog.invalidate_correlation_export()
        request_revision = dialog.correlation_export_revision()
        configuration = config.matrix_configuration()
        method, columns = configuration
        view = dialog.content_widget()
        pair = view.selected_pair() if isinstance(view, CorrelationView) else None

        def _apply(result: object) -> None:
            outcome = cast("_CorrelationOutcome", result)
            current_view = dialog.content_widget()
            latest_pair = current_view.selected_pair() if isinstance(current_view, CorrelationView) else None
            new_view = self._build_correlation_view(outcome, dialog)
            dialog.set_content_widget(new_view)
            if outcome.matrix.error is not None:
                return
            if outcome.export_snapshot is None:
                message = "A successful correlation matrix must retain its worker-owned export snapshot."
                raise ValueError(message)
            dialog.set_exportable_correlation(outcome.export_snapshot)
            if (
                latest_pair is not None
                and latest_pair != new_view.selected_pair()
                and all(column in outcome.matrix.columns for column in latest_pair)
            ):
                # A table selection made during the matrix job still takes precedence.
                new_view.select_pair(*latest_pair)

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CORRELATION,
            scope_suffix=f"matrix:{method.value}",
            compute=lambda df, callbacks: self._compute_correlation(
                df, callbacks, method=method, columns=columns, pair=pair
            ),
            apply_result=_apply,
            is_stale=lambda: (
                config.matrix_configuration() != configuration
                or dialog.correlation_export_revision() != request_revision
            ),
            cancelable=True,
        )

    def _recompute_correlation_pair(
        self,
        dialog: AnalysisDialog,
        x_column: str,
        y_column: str,
    ) -> None:
        """Recompute only the pair detail, updating the current view's pair panel in place."""
        view = dialog.content_widget()
        if (
            not isinstance(view, CorrelationView)
            or view.table() is None
            or x_column == y_column
            or x_column not in view.columns()
            or y_column not in view.columns()
        ):
            # Pair selection is only available in a successful displayed matrix.
            return

        # The displayed matrix's method, not the config's: a pending method
        # change will bring its own pair detail with the new matrix.
        method = view.method()
        selection_revision = view.pair_selection_revision()

        def _apply(result: object) -> None:
            view.set_pair_detail(cast("CorrelationPairDetail", result))

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CORRELATION,
            scope_suffix=f"pair:{method.value}:{x_column}:{y_column}",
            compute=lambda df, _callbacks: analyze_correlation_pair(df, x_column, y_column, method),
            apply_result=_apply,
            is_stale=lambda: (
                dialog.content_widget() is not view
                or view.selected_pair() != (x_column, y_column)
                or view.pair_selection_revision() != selection_revision
            ),
            target=view.pair_panel(),
        )

    def _render_regression(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render regression model results and the shared target/predictor config.

        Must run on the GUI thread. Linear regression remains the default;
        all configuration edits wait for Apply before refitting in a
        background job without recreating the configuration widget.
        """
        defaults = cast("_RegressionDefaults", result)
        regression = defaults.linear
        content = RegressionView(regression)
        if (
            regression.error is RegressionError.NO_NUMERIC_COLUMN
            and not defaults.generalized_targets.binary
            and not defaults.generalized_targets.count
        ):
            return content, None

        config = RegressionConfigWidget(regression, defaults.generalized_targets, defaults.survival_columns)

        def _handle_model_requested() -> None:
            configuration = config.model_configuration()
            model, target, predictors = configuration
            event = config.applied_event()
            revision = config.configuration_revision()
            if model is RegressionModel.LINEAR:
                scope_parts = (target, *predictors)
            elif model is RegressionModel.COX:
                scope_parts = (model.value, target, event, *predictors)
            else:
                scope_parts = (model.value, target, *predictors)

            def _compute(df: pd.DataFrame, _callbacks: _JobCallbacks) -> object:
                if model is RegressionModel.LINEAR:
                    return analyze_regression(df, target, predictors)
                if model is RegressionModel.COX:
                    return analyze_cox_regression(df, target, event, predictors)
                return analyze_generalized_regression(df, model, target, predictors)

            def _apply_result(computed: object) -> None:
                if model is RegressionModel.LINEAR:
                    dialog.set_content_widget(RegressionView(cast("RegressionResult", computed)))
                elif model is RegressionModel.COX:
                    dialog.set_content_widget(SurvivalRegressionView(cast("SurvivalResult", computed)))
                else:
                    dialog.set_content_widget(GeneralizedRegressionView(cast("GeneralizedRegressionResult", computed)))

            self._recompute_content(
                dialog,
                category=AnalysisCategory.REGRESSION,
                scope_suffix=":".join(scope_parts),
                compute=_compute,
                apply_result=_apply_result,
                is_stale=lambda: (
                    dialog.config_widget() is not config
                    or config.configuration_revision() != revision
                    or config.model_configuration() != configuration
                    or config.applied_event() != event
                ),
            )

        config.configuration_changed.connect(lambda: dialog.set_content_widget(self._apply_prompt()))
        config.model_requested.connect(_handle_model_requested)
        return content, config

    @staticmethod
    def _initialize_regression(df: pd.DataFrame) -> _RegressionDefaults:
        """Build configuration defaults for linear, binary and count regression."""
        return _RegressionDefaults(
            linear=initialize_regression(df),
            generalized_targets=initialize_generalized_targets(df),
            survival_columns=initialize_survival_columns(df),
        )

    @staticmethod
    def _compute_outliers(
        df: pd.DataFrame,
        method: OutlierMethod = OutlierMethod.IQR,
        threshold: float | None = None,
        column: str | None = None,
    ) -> _OutliersOutcome:
        """Compute an outlier summary and one column's detail (background-safe).

        Args:
            df: The DataFrame to analyze.
            method: The detection method.
            threshold: The method's threshold, or `None` for its default.
            column: The column to detail, or `None` for the summary's
                top-ranked one.

        Returns:
            The outcome.
        """
        summary = analyze_outlier_summary(df, method, threshold)
        if summary.error is not None:
            return _OutliersOutcome(summary=summary, detail=None)

        detail_column = column if column is not None else default_column(summary)
        detail = (
            analyze_outlier_column(df, detail_column, method, summary.threshold) if detail_column is not None else None
        )
        return _OutliersOutcome(summary=summary, detail=detail)

    def _render_outliers(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Outlier Explorer's initial state: the Apply prompt and its config.

        Must run on the GUI thread. `result` is the configuration-only
        `initialize_outlier_summary` result; nothing is computed until the
        user applies a method and threshold, which recomputes the whole
        summary (a job replacing the view). Once a summary is shown, a
        column change recomputes only the column detail (a job updating the
        current view's detail panel in place).
        """
        summary = cast("OutlierSummaryResult", result)
        if not summary.available_columns:
            return OutliersView(summary, None), None

        config = OutliersConfigWidget(summary, None)

        def _handle_summary_requested() -> None:
            self._recompute_outlier_summary(dialog, config)

        def _handle_column_changed(column: str) -> None:
            self._recompute_outlier_column(dialog, config, column)

        config.summary_requested.connect(_handle_summary_requested)
        config.column_changed.connect(_handle_column_changed)
        config.multivariate_requested.connect(lambda: self._switch_to_multivariate_outliers(dialog))
        return self._apply_prompt(), config

    @staticmethod
    def _build_outliers_view(outcome: _OutliersOutcome, config: OutliersConfigWidget) -> OutliersView:
        """Build an Outlier Explorer view whose table rows select the config's column."""
        view = OutliersView(outcome.summary, outcome.detail)
        view.column_activated.connect(config.set_column)
        return view

    def _recompute_outlier_summary(self, dialog: AnalysisDialog, config: OutliersConfigWidget) -> None:
        """Recompute the whole outlier summary for the config's applied method and threshold.

        Before the first summary is shown, the column picker is disabled and
        only holds a placeholder column, so the summary's top-ranked column
        is detailed instead and then synced back into the picker.
        """
        configuration = config.summary_configuration()
        method, threshold = configuration
        column = (config.current_column() or None) if config.is_column_selection_enabled() else None

        def _apply(result: object) -> None:
            outcome = cast("_OutliersOutcome", result)
            dialog.set_content_widget(self._build_outliers_view(outcome, config))
            if outcome.detail is None:
                return
            detailed_column = outcome.detail.summary.column
            if column is None:
                config.set_column(detailed_column, notify=False)
            config.set_column_selection_enabled(enabled=True)
            # The column may have changed while the summary was computing;
            # its own recompute was skipped (no current view), so catch up now.
            current_column = config.current_column()
            if current_column and current_column != detailed_column:
                self._recompute_outlier_column(dialog, config, current_column)

        self._recompute_content(
            dialog,
            category=AnalysisCategory.OUTLIERS,
            scope_suffix=f"summary:{method.value}:{threshold}",
            compute=lambda df, _callbacks: self._compute_outliers(df, method, threshold, column),
            apply_result=_apply,
            is_stale=lambda: config.summary_configuration() != configuration,
        )

    def _recompute_outlier_column(self, dialog: AnalysisDialog, config: OutliersConfigWidget, column: str) -> None:
        """Recompute only the column detail, updating the current view's detail panel in place."""
        view = dialog.content_widget()
        if not isinstance(view, OutliersView) or view.table() is None:
            # No summary is shown (still computing or failed); the next
            # summary result will include the current column.
            return

        # The displayed summary's configuration, not the config's: a pending
        # method/threshold change will bring its own detail with the new summary.
        method, threshold = view.configuration()

        def _apply(result: object) -> None:
            view.set_column_detail(cast("OutlierColumnDetail", result))

        self._recompute_content(
            dialog,
            category=AnalysisCategory.OUTLIERS,
            scope_suffix=f"column:{method.value}:{threshold}:{column}",
            compute=lambda df, _callbacks: analyze_outlier_column(df, column, method, threshold),
            apply_result=_apply,
            is_stale=lambda: dialog.content_widget() is not view or config.current_column() != column,
            target=view.detail_panel(),
        )

    def _switch_to_multivariate_outliers(self, dialog: AnalysisDialog) -> None:
        """Show the multivariate configuration after the mode switch, without fitting.

        Like every apply-first category, the model is only fitted once the
        user applies a configuration. When the dataset cannot support
        multivariate screening, its explanatory error view is shown instead
        of the Apply prompt, but the configuration is kept so the user can
        switch back to univariate mode.
        """
        df = self._load_selected_dataset(dialog, AnalysisCategory.OUTLIERS)
        if df is None:
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        multivariate_result = initialize_multivariate_outliers(df)
        multivariate_config = MultivariateOutliersConfigWidget(multivariate_result)
        multivariate_config.analysis_requested.connect(
            lambda: self._recompute_multivariate_outliers(dialog, multivariate_config)
        )
        multivariate_config.univariate_requested.connect(lambda: self._refresh_content(dialog))
        content = (
            self._apply_prompt() if multivariate_result.error is None else MultivariateOutliersView(multivariate_result)
        )
        dialog.set_content_widget(content)
        dialog.set_config_widget(multivariate_config)

    def _recompute_multivariate_outliers(
        self,
        dialog: AnalysisDialog,
        config: MultivariateOutliersConfigWidget,
    ) -> None:
        """Refit multivariate screening while preserving its configuration widget."""
        configuration = config.analysis_configuration()
        columns, method, standardize, contamination, lof_neighbors = configuration
        scope_parts = [
            "multivariate",
            method.value,
            "standardized" if standardize else "raw",
            f"contamination:{contamination}",
        ]
        if method is MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR:
            scope_parts.append(f"neighbors:{lof_neighbors}")
        scope_parts.extend(columns)

        self._recompute_content(
            dialog,
            category=AnalysisCategory.OUTLIERS,
            scope_suffix=":".join(scope_parts),
            compute=lambda df, _callbacks: analyze_multivariate_outliers(
                df,
                columns=columns,
                method=method,
                standardize=standardize,
                contamination=contamination,
                lof_neighbors=lof_neighbors,
            ),
            apply_result=lambda result: dialog.set_content_widget(
                MultivariateOutliersView(cast("MultivariateOutlierResult", result))
            ),
            is_stale=lambda: dialog.config_widget() is not config or config.analysis_configuration() != configuration,
        )

    def _render_pca(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render PCA's initial state: the Apply prompt and its feature/scaling config.

        `result` is the configuration-only `initialize_pca` result; the fit
        only runs once the user applies a configuration. When the dataset
        cannot support PCA, its explanatory error view is shown instead.
        """
        pca_result = cast("PCAResult", result)
        if len(pca_result.available_columns) < PCA_MIN_SELECTED_COLUMNS:
            return PCAView(pca_result), None

        config = PCAConfigWidget(pca_result)
        config.analysis_requested.connect(lambda: self._recompute_pca(dialog, config))
        return self._apply_prompt(), config

    def _recompute_pca(self, dialog: AnalysisDialog, config: PCAConfigWidget) -> None:
        """Run PCA for an applied feature/scaling configuration."""
        configuration = config.analysis_configuration()
        columns, standardize = configuration

        self._recompute_content(
            dialog,
            category=AnalysisCategory.PCA,
            scope_suffix=f"fit:{'standardized' if standardize else 'raw'}:{':'.join(columns)}",
            compute=lambda df, _callbacks: analyze_pca(df, columns, standardize=standardize),
            apply_result=lambda result: dialog.set_content_widget(PCAView(cast("PCAResult", result))),
            is_stale=lambda: config.analysis_configuration() != configuration,
        )

    def _render_clustering(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render clustering's initial state: the Apply prompt and its config.

        `result` is the configuration-only `initialize_clustering` result;
        the fit only runs once the user applies a configuration. When the
        dataset cannot support clustering, its explanatory error view is
        shown instead.
        """
        clustering_result = cast("ClusteringResult", result)
        if len(clustering_result.available_columns) < CLUSTERING_MIN_SELECTED_COLUMNS:
            return ClusteringView(clustering_result), None

        config = ClusteringConfigWidget(clustering_result)
        config.analysis_requested.connect(lambda: self._recompute_clustering(dialog, config))
        return self._apply_prompt(), config

    def _recompute_clustering(self, dialog: AnalysisDialog, config: ClusteringConfigWidget) -> None:
        """Run clustering for the latest applied config."""
        configuration = config.analysis_configuration()
        columns, method, standardize, cluster_count, dbscan_epsilon, dbscan_min_samples = configuration
        parameters = (
            f"eps:{dbscan_epsilon}:min_samples:{dbscan_min_samples}"
            if method is ClusteringMethod.DBSCAN
            else f"clusters:{cluster_count}"
        )
        scale = "standardized" if standardize else "raw"
        scope_suffix = f"fit:{method.value}:{scale}:{parameters}:{':'.join(columns)}"

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CLUSTERING,
            scope_suffix=scope_suffix,
            compute=lambda df, _callbacks: analyze_clustering(
                df,
                columns,
                method=method,
                standardize=standardize,
                cluster_count=cluster_count,
                dbscan_epsilon=dbscan_epsilon,
                dbscan_min_samples=dbscan_min_samples,
            ),
            apply_result=lambda result: dialog.set_content_widget(ClusteringView(cast("ClusteringResult", result))),
            is_stale=lambda: config.analysis_configuration() != configuration,
        )

    def _render_time_series(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Time Series Explorer's initial state: the Apply prompt and its config.

        `result` is the configuration-only `initialize_time_series` result;
        the series is only analyzed once the user applies a configuration.
        When the dataset lacks a datetime or numeric column, the explanatory
        error view is shown instead.
        """
        series_result = cast("TimeSeriesResult", result)
        if not series_result.available_datetime_columns or not series_result.available_value_columns:
            return TimeSeriesView(series_result), None

        config = TimeSeriesConfigWidget(series_result)
        config.analysis_requested.connect(lambda: self._recompute_time_series(dialog, config))
        return self._apply_prompt(), config

    def _recompute_time_series(self, dialog: AnalysisDialog, config: TimeSeriesConfigWidget) -> None:
        """Analyze one applied Time Series Explorer configuration."""
        configuration = config.analysis_configuration()
        datetime_column, value_column, frequency, period, model = configuration
        frequency_scope = frequency or "original"
        period_scope = str(period) if period is not None else "auto"

        self._recompute_content(
            dialog,
            category=AnalysisCategory.TIME_SERIES,
            scope_suffix=f"fit:{datetime_column}:{value_column}:{frequency_scope}:{period_scope}:{model.value}",
            compute=lambda df, _callbacks: analyze_time_series(
                df,
                datetime_column,
                value_column,
                resample_frequency=frequency,
                seasonal_period=period,
                decomposition_model=model,
            ),
            apply_result=lambda result: dialog.set_content_widget(TimeSeriesView(cast("TimeSeriesResult", result))),
            is_stale=lambda: config.analysis_configuration() != configuration,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _refresh_content(self, dialog: AnalysisDialog) -> None:
        """Rebuild the content panel for the currently selected category/dataset.

        Apply-first categories (with an `initialize` callable) only render
        their configuration here, synchronously. Every other category's
        computation runs as a background job with a busy overlay shown over
        the dialog's result pane, so large datasets or heavier analyses
        never freeze the GUI thread.

        Args:
            dialog: Active Advanced Analysis dialog.
        """
        category = dialog.selected_category()
        if category is None:
            return

        handler = self._category_handlers.get(category)
        if handler is None:
            self._show_placeholder(dialog, self._tr(self.TR_NOT_IMPLEMENTED))
            return

        tab_id = dialog.selected_dataset_tab_id()
        if tab_id is None:
            # Defensive only: open_dialog() never opens without a dataset,
            # so the combo box always has a selection in practice.
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        df = self._load_dataset(category, tab_id)
        if df is None:
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        if handler.initialize is not None:
            self._initialize_category(dialog, category, handler.initialize, handler.render, df)
            return

        self._run_analysis(dialog, category, handler, tab_id, df)

    def _initialize_category(
        self,
        dialog: AnalysisDialog,
        category: AnalysisCategory,
        initialize: Callable[[pd.DataFrame], object],
        render: Callable[[object, AnalysisDialog], tuple[QWidget, QWidget | None]],
        df: pd.DataFrame,
    ) -> None:
        """Render an apply-first category's configuration synchronously.

        Initializers only inspect column metadata, so they are cheap enough
        for the GUI thread and need neither a background job nor a busy
        overlay; the actual computation starts when the user clicks Apply.

        Args:
            dialog: Active Advanced Analysis dialog.
            category: The category being opened (for logging).
            initialize: Metadata-only initializer for the category.
            render: The category's renderer.
            df: The DataFrame to analyze.
        """
        try:
            result = initialize(df)
        except (KeyError, TypeError, ValueError):
            self._logger.exception("AnalysisController: failed to initialize category '%s'.", category)
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        content_widget, config_widget = render(result, dialog)
        dialog.set_content_widget(content_widget)
        dialog.set_config_widget(config_widget)

    def _apply_prompt(self) -> QWidget:
        """Build the content shown by an apply-first category before its first Apply."""
        return build_placeholder_label(self._tr(self.TR_APPLY_PROMPT))

    def _load_dataset(self, category: AnalysisCategory, tab_id: str) -> pd.DataFrame | None:
        """Return the dataset of `tab_id`, or `None` (logged) if it cannot be loaded.

        Args:
            category: The category needing the dataset (for logging).
            tab_id: The dataset's result tab ID.
        """
        try:
            return self._results.get_df_by_tab_id(tab_id)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.exception(
                "AnalysisController: failed to load dataset for category '%s' (tab_id=%s).",
                category,
                tab_id,
            )
            return None

    def _load_selected_dataset(self, dialog: AnalysisDialog, category: AnalysisCategory) -> pd.DataFrame | None:
        """Return the dialog's selected dataset, or `None` if none is selected or it cannot be loaded.

        Args:
            dialog: Active Advanced Analysis dialog.
            category: The category needing the dataset (for logging).
        """
        tab_id = dialog.selected_dataset_tab_id()
        if tab_id is None:
            return None
        return self._load_dataset(category, tab_id)

    def _show_placeholder(self, dialog: AnalysisDialog, text: str) -> None:
        """Show a placeholder message and hide any stale configuration widget.

        Args:
            dialog: Active Advanced Analysis dialog.
            text: Message to show instead of analysis results.
        """
        dialog.show_placeholder(text)
        dialog.set_config_widget(None)

    def _run_analysis(
        self,
        dialog: AnalysisDialog,
        category: AnalysisCategory,
        handler: _CategoryHandler,
        tab_id: str,
        df: pd.DataFrame,
    ) -> None:
        """Run a category's computation in the background with a busy overlay."""
        corr_id = uuid.uuid4().hex
        dialog.invalidate_overview_export()
        revision = dialog.analysis_revision()

        # Hide any configuration widget left over from the previous category
        # immediately - it isn't covered by the busy overlay (which only
        # covers the result pane), so it would otherwise stay visible and
        # irrelevant while this job runs.
        dialog.set_config_widget(None)

        def _is_stale() -> bool:
            """Discard results once the user has moved on to something else."""
            return (
                dialog.selected_category() != category
                or dialog.selected_dataset_tab_id() != tab_id
                or dialog.analysis_revision() != revision
            )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> object:
            if cancel_cb is not None and cancel_cb():
                return None
            return handler.compute(df, _JobCallbacks(progress_cb=progress_cb, cancel_cb=cancel_cb))

        def _on_result(result: object) -> None:
            if _is_stale():
                return
            if result is None:
                if handler.cancelable:
                    self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_CANCELLED))
                return
            content_widget, config_widget = handler.render(result, dialog)
            dialog.set_content_widget(content_widget)
            dialog.set_config_widget(config_widget)
            if category is AnalysisCategory.OVERVIEW and isinstance(result, DatasetOverviewResult):
                dialog.set_exportable_overview(result)
            elif category is AnalysisCategory.STATISTICS and isinstance(result, DescriptiveStatisticsResult):
                dialog.set_exportable_statistics(result)

        def _on_error(_traceback: str) -> None:
            if _is_stale():
                return
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))

        self._async_ops.run_target_overlay_operation(
            target=dialog.content_panel(),
            runner="pool",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=self._tr(self.TR_RUNNING_ANALYSIS),
            scope=f"analysis:{category.value}",
            operation_name=self._tr(self.TR_ANALYSIS_OPERATION),
            stale_check=_is_stale,
            corr_id=corr_id,
            cancelable=handler.cancelable,
            indeterminate=not handler.cancelable,
            timeout_ms=self._overlay_timeout_ms(cancelable=handler.cancelable),
        )

    @staticmethod
    def _overlay_timeout_ms(*, cancelable: bool) -> int:
        """Return the busy overlay's watchdog timeout for a job.

        Cancelable jobs report real progress and show a Cancel button
        (their overlay is determinate), so they get a longer timeout.
        """
        return _CANCELABLE_TIMEOUT_MS if cancelable else _DEFAULT_TIMEOUT_MS

    def _recompute_content(
        self,
        dialog: AnalysisDialog,
        *,
        category: AnalysisCategory,
        scope_suffix: str,
        compute: Callable[[pd.DataFrame, _JobCallbacks], object],
        apply_result: Callable[[object], None],
        is_stale: Callable[[], bool],
        target: QWidget | None = None,
        cancelable: bool = False,
    ) -> None:
        """Recompute and redraw only the content pane for a config-driven category.

        Used by categories whose configuration widget selects *what* to
        compute (e.g. which columns to compare) rather than merely *how*
        to redraw already-computed data (contrast the Statistics table,
        which only switches which precomputed column is shown). A
        configuration change therefore needs a new background computation,
        but the configuration widget itself - and the user's current picks
        - must be left alone, unlike `_run_analysis`, which always
        replaces both the content and configuration widgets.

        Args:
            dialog: Active Advanced Analysis dialog.
            category: The category this recompute belongs to - checked
                (alongside the dataset) to detect that the user has since
                navigated away entirely, not just changed the
                configuration again.
            scope_suffix: Appended to the async job's scope, so each
                distinct configuration gets its own job identity for
                cancellation/logging purposes.
            compute: Background-safe callable turning the DataFrame (plus
                the job's progress/cancellation hooks) into a plain (non-Qt)
                result object for the current configuration, or `None` if
                cancelled.
            apply_result: GUI-thread callable displaying that result -
                typically by replacing the content widget. Must not build
                a configuration widget - the existing one is left in place.
            is_stale: Checked (in addition to category/dataset staleness)
                before applying a result or error - typically compares the
                configuration widget's *current* selection against the one
                this recompute was triggered for.
            target: Widget covered by the busy overlay. Defaults to the
                dialog's whole content panel.
            cancelable: Whether `compute` reports progress and honors
                cancellation (see `_CategoryHandler.cancelable`).
        """
        tab_id = dialog.selected_dataset_tab_id()
        if tab_id is None:
            return

        df = self._load_dataset(category, tab_id)
        if df is None:
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))
            return

        corr_id = uuid.uuid4().hex
        if category is AnalysisCategory.HYPOTHESIS_TESTS:
            dialog.invalidate_overview_export()
        revision = dialog.analysis_revision()

        def _combined_is_stale() -> bool:
            """Discard results once the user has moved on from this exact configuration."""
            return (
                dialog.selected_category() != category
                or dialog.selected_dataset_tab_id() != tab_id
                or (
                    category in {AnalysisCategory.HYPOTHESIS_TESTS, AnalysisCategory.REGRESSION}
                    and dialog.analysis_revision() != revision
                )
                or is_stale()
            )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> object:
            if cancel_cb is not None and cancel_cb():
                return None
            return compute(df, _JobCallbacks(progress_cb=progress_cb, cancel_cb=cancel_cb))

        def _on_result(result: object) -> None:
            if _combined_is_stale():
                return
            if result is None:
                if cancelable:
                    dialog.show_placeholder(self._tr(self.TR_ANALYSIS_CANCELLED))
                return
            apply_result(result)

        def _on_error(_traceback: str) -> None:
            if _combined_is_stale():
                return
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))

        self._async_ops.run_target_overlay_operation(
            target=target if target is not None else dialog.content_panel(),
            runner="pool",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=self._tr(self.TR_RUNNING_ANALYSIS),
            scope=f"analysis:{category.value}:{scope_suffix}",
            operation_name=self._tr(self.TR_ANALYSIS_OPERATION),
            stale_check=_combined_is_stale,
            corr_id=corr_id,
            cancelable=cancelable,
            indeterminate=not cancelable,
            timeout_ms=self._overlay_timeout_ms(cancelable=cancelable),
        )
