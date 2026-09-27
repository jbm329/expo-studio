"""Controller for the Advanced Analysis workspace dialog."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QT_TR_NOOP, QTimer

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog
from expo_jbm329.gui.dialogs.analysis.chi_square_view import ChiSquareView
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.correlation_view import CorrelationView
from expo_jbm329.gui.dialogs.analysis.group_comparison_view import GroupComparisonView
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.regression_view import RegressionView
from expo_jbm329.gui.dialogs.analysis.statistics_config import StatisticsConfigWidget
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import analyze_chi_square
from expo_jbm329.services.analysis.correlation import (
    MIN_SELECTED_COLUMNS,
    CorrelationMethod,
    analyze_correlation_matrix,
    analyze_correlation_pair,
    default_pair,
)
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.regression import RegressionError, analyze_regression
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.services.analysis.chi_square import ChiSquareResult
    from expo_jbm329.services.analysis.correlation import CorrelationMatrixResult, CorrelationPairDetail
    from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
    from expo_jbm329.services.analysis.overview import DatasetOverviewResult
    from expo_jbm329.services.analysis.regression import RegressionResult
    from expo_jbm329.services.analysis.statistics import DescriptiveStatisticsResult
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import (
        ResultTabManager,
    )


# Matches AsyncOperationController's default overlay watchdog.
_DEFAULT_TIMEOUT_MS = 60_000
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
    """

    compute: Callable[[pd.DataFrame, _JobCallbacks], object]
    render: Callable[[object, AnalysisDialog], tuple[QWidget, QWidget | None]]
    cancelable: bool = False


@dataclass(frozen=True, slots=True)
class _HypothesisTestsDefaults:
    """Every hypothesis test computed with its default columns.

    The Hypothesis Tests category's initial result, so each test's column
    pickers in `HypothesisTestsConfigWidget` can be populated up front.
    """

    group_comparison: GroupComparisonResult
    chi_square: ChiSquareResult


@dataclass(frozen=True, slots=True)
class _CorrelationOutcome:
    """A correlation matrix plus the detail of its selected pair.

    Attributes:
        matrix: The computed correlation matrix.
        pair_detail: The selected pair's detail, or `None` when the matrix
            has an error (and so no pair to show).
    """

    matrix: CorrelationMatrixResult
    pair_detail: CorrelationPairDetail | None


class AnalysisController:
    """Controller responsible for the Advanced Analysis workspace workflow.

    Each analysis category is backed by a `_CategoryHandler`. Computation
    always runs as a background job (JobManager, via
    AsyncOperationController) with a busy overlay shown over the dialog's
    result pane, so large datasets never freeze the GUI thread. Categories
    without a registered handler fall back to the not-implemented
    placeholder.
    """

    TR_NOT_IMPLEMENTED = QT_TR_NOOP("This analysis is not implemented yet.")
    TR_ANALYSIS_ERROR = QT_TR_NOOP("An error occurred while generating this analysis.")
    TR_RUNNING_ANALYSIS = QT_TR_NOOP("Running analysis…")
    TR_ANALYSIS_OPERATION = QT_TR_NOOP("generate analysis")
    TR_ANALYSIS_CANCELLED = QT_TR_NOOP("Analysis cancelled.")

    @staticmethod
    def _tr(text: str) -> str:
        """Translate a UI string for this controller."""
        return tr("AnalysisController", text)

    def __init__(
        self,
        *,
        results: ResultTabManager,
        async_ops: AsyncOperationController,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the analysis controller.

        Args:
            results: ResultTabManager instance.
            async_ops: Controller running analyses as background jobs.
            logger: Optional logger instance.
        """
        self._results = results
        self._async_ops = async_ops
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
                compute=_ignore_callbacks(self._compute_hypothesis_tests_defaults),
                render=self._render_hypothesis_tests,
            ),
            AnalysisCategory.CORRELATION: _CategoryHandler(
                compute=self._compute_correlation,
                render=self._render_correlation,
                cancelable=True,
            ),
            AnalysisCategory.REGRESSION: _CategoryHandler(
                compute=_ignore_callbacks(analyze_regression),
                render=self._render_regression,
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

        def _handle_category_changed(_category_value: str) -> None:
            self._refresh_content(dialog)

        def _handle_dataset_changed(_tab_id: str) -> None:
            self._refresh_content(dialog)

        dialog.category_changed.connect(_handle_category_changed)
        dialog.dataset_changed.connect(_handle_dataset_changed)

        # Overview is already selected by the time the dialog is constructed
        # (see AnalysisDialog), but that self-emission happens before the
        # connections above exist. Deferred by one event-loop tick so the
        # dialog is already shown (and correctly sized) once the initial
        # busy overlay is created - showing an overlay on a not-yet-shown
        # widget would compute its geometry against a stale/default size.
        QTimer.singleShot(0, lambda: self._refresh_content(dialog))

        dialog.exec()

    # ------------------------------------------------------------------
    # Renderers (GUI thread only)
    # ------------------------------------------------------------------

    def _render_overview(self, result: object, _dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Dataset Overview view. Must run on the GUI thread."""
        return OverviewView(cast("DatasetOverviewResult", result)), None

    def _render_statistics(self, result: object, _dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Descriptive Statistics view and its column-picker config.

        Must run on the GUI thread.
        """
        stats_result = cast("DescriptiveStatisticsResult", result)
        content = StatisticsView(stats_result)

        if not stats_result.columns:
            return content, None

        config = StatisticsConfigWidget(stats_result)
        config.column_changed.connect(content.show_distribution_for)
        return content, config

    def _render_hypothesis_tests(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Hypothesis Tests content and its test/column-picker config.

        Must run on the GUI thread. The initial content is always the
        default test (Group Comparison). Unlike Overview/Statistics, the
        configuration here determines *what* to compute (which test, which
        columns), so the configuration widget's `configuration_changed`
        signal is wired to `_recompute_content`, which dispatches a new
        background job and replaces only the content pane, leaving this
        exact configuration widget instance (and the user's picks) in place.
        """
        defaults = cast("_HypothesisTestsDefaults", result)
        content: QWidget = GroupComparisonView(defaults.group_comparison)
        config = HypothesisTestsConfigWidget(defaults.group_comparison, defaults.chi_square)

        def _handle_configuration_changed() -> None:
            configuration = config.current_configuration()
            test, selection = configuration
            self._recompute_content(
                dialog,
                category=AnalysisCategory.HYPOTHESIS_TESTS,
                scope_suffix=":".join((test.value, *(selection or ()))),
                compute=lambda df, _callbacks: self._compute_hypothesis_test(df, test, selection),
                apply_result=lambda r: dialog.set_content_widget(self._render_hypothesis_test_content(test, r)),
                is_stale=lambda: config.current_configuration() != configuration,
            )

        config.configuration_changed.connect(_handle_configuration_changed)
        return content, config

    @staticmethod
    def _compute_hypothesis_tests_defaults(df: pd.DataFrame) -> _HypothesisTestsDefaults:
        """Compute every hypothesis test with its default columns (background-safe).

        Both are computed up front so each test's column pickers can be
        populated immediately, without a further job when switching tests.
        """
        return _HypothesisTestsDefaults(
            group_comparison=analyze_group_comparison(df),
            chi_square=analyze_chi_square(df),
        )

    @staticmethod
    def _compute_hypothesis_test(
        df: pd.DataFrame,
        test: HypothesisTest,
        selection: tuple[str, str] | None,
    ) -> object:
        """Compute one hypothesis test for `selection`, or its defaults when `None`."""
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return analyze_group_comparison(df) if selection is None else analyze_group_comparison(df, *selection)
            case HypothesisTest.CHI_SQUARE:
                return analyze_chi_square(df) if selection is None else analyze_chi_square(df, *selection)

    @staticmethod
    def _render_hypothesis_test_content(test: HypothesisTest, result: object) -> QWidget:
        """Build the content view for one computed hypothesis test (GUI thread only)."""
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return GroupComparisonView(cast("GroupComparisonResult", result))
            case HypothesisTest.CHI_SQUARE:
                return ChiSquareView(cast("ChiSquareResult", result))

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
        matrix = analyze_correlation_matrix(
            df,
            columns,
            method,
            progress_cb=callbacks.progress_cb,
            cancel_cb=callbacks.cancel_cb,
        )
        if matrix is None:
            return None
        if matrix.error is not None:
            return _CorrelationOutcome(matrix=matrix, pair_detail=None)

        detail_pair = pair if pair is not None else default_pair(matrix)
        pair_detail = analyze_correlation_pair(df, *detail_pair, method) if detail_pair is not None else None
        return _CorrelationOutcome(matrix=matrix, pair_detail=pair_detail)

    def _render_correlation(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Correlation Explorer view and its method/column/pair config.

        Must run on the GUI thread. Like Hypothesis Tests, the configuration
        determines what to compute: a method change or applied column
        selection recomputes the whole matrix (a cancelable job replacing
        the view), while a pair change recomputes only the pair detail
        (a quick job updating the current view's pair panel in place).
        """
        outcome = cast("_CorrelationOutcome", result)
        if len(outcome.matrix.available_columns) < MIN_SELECTED_COLUMNS:
            return CorrelationView(outcome.matrix, None), None

        initial_pair = (
            (outcome.pair_detail.pair.x_column, outcome.pair_detail.pair.y_column)
            if outcome.pair_detail is not None
            else default_pair(outcome.matrix)
        )
        config = CorrelationConfigWidget(outcome.matrix, initial_pair)
        content = self._build_correlation_view(outcome, config)

        def _handle_matrix_requested() -> None:
            self._recompute_correlation_matrix(dialog, config)

        def _handle_pair_changed(x_column: str, y_column: str) -> None:
            self._recompute_correlation_pair(dialog, config, x_column, y_column)

        config.matrix_requested.connect(_handle_matrix_requested)
        config.pair_changed.connect(_handle_pair_changed)
        return content, config

    @staticmethod
    def _build_correlation_view(outcome: _CorrelationOutcome, config: CorrelationConfigWidget) -> CorrelationView:
        """Build a Correlation Explorer view whose table rows select the config's pair."""
        view = CorrelationView(outcome.matrix, outcome.pair_detail)
        view.pair_activated.connect(config.set_pair)
        return view

    def _recompute_correlation_matrix(self, dialog: AnalysisDialog, config: CorrelationConfigWidget) -> None:
        """Recompute the whole correlation matrix for the config's method and applied columns."""
        configuration = config.matrix_configuration()
        method, columns = configuration
        pair = config.current_pair()

        def _apply(result: object) -> None:
            outcome = cast("_CorrelationOutcome", result)
            dialog.set_content_widget(self._build_correlation_view(outcome, config))
            # The pair may have changed while the matrix was computing; its
            # own recompute was skipped (no current view), so catch up now.
            current_pair = config.current_pair()
            if outcome.pair_detail is not None and current_pair is not None and current_pair != pair:
                self._recompute_correlation_pair(dialog, config, *current_pair)

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CORRELATION,
            scope_suffix=f"matrix:{method.value}",
            compute=lambda df, callbacks: self._compute_correlation(
                df, callbacks, method=method, columns=columns, pair=pair
            ),
            apply_result=_apply,
            is_stale=lambda: config.matrix_configuration() != configuration,
            cancelable=True,
        )

    def _recompute_correlation_pair(
        self,
        dialog: AnalysisDialog,
        config: CorrelationConfigWidget,
        x_column: str,
        y_column: str,
    ) -> None:
        """Recompute only the pair detail, updating the current view's pair panel in place."""
        view = dialog.content_widget()
        if not isinstance(view, CorrelationView) or view.table() is None:
            # No matrix is shown (still computing, cancelled or failed);
            # the next matrix result will include the current pair.
            return

        # The displayed matrix's method, not the config's: a pending method
        # change will bring its own pair detail with the new matrix.
        method = view.method()

        def _apply(result: object) -> None:
            view.set_pair_detail(cast("CorrelationPairDetail", result))

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CORRELATION,
            scope_suffix=f"pair:{method.value}:{x_column}:{y_column}",
            compute=lambda df, _callbacks: analyze_correlation_pair(df, x_column, y_column, method),
            apply_result=_apply,
            is_stale=lambda: dialog.content_widget() is not view or config.current_pair() != (x_column, y_column),
            target=view.pair_panel(),
        )

    def _render_regression(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Linear Regression view and its target/predictor config.

        Must run on the GUI thread. The initial result has no predictors
        selected, so the view prompts the user to choose some. Like
        Hypothesis Tests, the configuration determines what to compute: a
        target change or applied predictor selection refits the model in
        a background job replacing only the content pane.
        """
        regression = cast("RegressionResult", result)
        content = RegressionView(regression)
        if regression.error is RegressionError.NO_NUMERIC_COLUMN:
            return content, None

        config = RegressionConfigWidget(regression)

        def _handle_model_requested() -> None:
            configuration = config.model_configuration()
            target, predictors = configuration
            self._recompute_content(
                dialog,
                category=AnalysisCategory.REGRESSION,
                scope_suffix=":".join((target, *predictors)),
                compute=lambda df, _callbacks: analyze_regression(df, target, predictors),
                apply_result=lambda r: dialog.set_content_widget(RegressionView(cast("RegressionResult", r))),
                is_stale=lambda: config.model_configuration() != configuration,
            )

        config.model_requested.connect(_handle_model_requested)
        return content, config

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _refresh_content(self, dialog: AnalysisDialog) -> None:
        """Rebuild the content panel for the currently selected category/dataset.

        The actual computation always runs as a background job with a busy
        overlay shown over the dialog's result pane, so large datasets or
        heavier analyses never freeze the GUI thread.

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

        try:
            df = self._results.get_df_by_tab_id(tab_id)
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
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        self._run_analysis(dialog, category, handler, tab_id, df)

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

        # Hide any configuration widget left over from the previous category
        # immediately - it isn't covered by the busy overlay (which only
        # covers the result pane), so it would otherwise stay visible and
        # irrelevant while this job runs.
        dialog.set_config_widget(None)

        def _is_stale() -> bool:
            """Discard results once the user has moved on to something else."""
            return dialog.selected_category() != category or dialog.selected_dataset_tab_id() != tab_id

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
            if result is None:
                if handler.cancelable:
                    self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_CANCELLED))
                return
            content_widget, config_widget = handler.render(result, dialog)
            dialog.set_content_widget(content_widget)
            dialog.set_config_widget(config_widget)

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
        to redraw already-computed data (contrast `StatisticsConfigWidget`,
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

        try:
            df = self._results.get_df_by_tab_id(tab_id)
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
                "AnalysisController: failed to reload dataset for category '%s' (tab_id=%s).",
                category,
                tab_id,
            )
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))
            return

        corr_id = uuid.uuid4().hex

        def _combined_is_stale() -> bool:
            """Discard results once the user has moved on from this exact configuration."""
            return dialog.selected_category() != category or dialog.selected_dataset_tab_id() != tab_id or is_stale()

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
