"""Linear Regression view widget (model summary, coefficients, diagnostics, plots)."""

from __future__ import annotations

import html
import math
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.analysis.applied_configuration_header import AppliedConfigurationHeader
from expo_jbm329.gui.dialogs.analysis.section_layout import build_section_scroll_area, rich_text_lines
from expo_jbm329.services.analysis.presentation import (
    build_regression_result_presentation,
    regression_component_label,
    regression_intercept_label,
)
from expo_jbm329.services.analysis.regression import (
    CONFIDENCE_LEVEL,
    DURBIN_WATSON_HIGH,
    DURBIN_WATSON_LOW,
    HIGH_VIF_THRESHOLD,
    MAX_MODEL_TERMS,
    MAX_PREDICTORS,
    SIGNIFICANCE_LEVEL,
    RegressionError,
    RegressionWarningReason,
    TermKind,
    term_name,
)
from expo_jbm329.services.analysis.regression_charts import (
    LinearChartLabels,
    RegressionChartLabels,
    build_regression_chart_labels,
    draw_actual_vs_predicted,
    draw_normal_qq,
    draw_residuals_vs_fitted,
)
from expo_jbm329.services.analysis.regression_export import RegressionExportComponent
from expo_jbm329.services.analysis.regression_glm import RegressionModel
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.regression import (
        RegressionDiagnostics,
        RegressionResult,
        RegressionTerm,
        RegressionWarning,
    )
    from expo_jbm329.services.analysis.regression_glm import GeneralizedRegressionResult
    from expo_jbm329.services.analysis.survival import SurvivalResult

# Above this many rows, normality tests flag even negligible deviations.
LARGE_SAMPLE_SIZE = 5_000

_TERM_COLUMN = 0
_TITLE_FONT_SIZE = 10
_LABEL_FONT_SIZE = 9
_TICK_FONT_SIZE = 8


def _esc(text: str) -> str:
    """Escape `text` for use in rich text."""
    return html.escape(text)


def build_regression_presentation_header(
    result: RegressionResult | GeneralizedRegressionResult | SurvivalResult,
    parent: QWidget,
) -> AppliedConfigurationHeader:
    """Adapt a fitted regression result to the shared applied header."""
    presentation = build_regression_result_presentation(result, QCoreApplication.translate)
    return AppliedConfigurationHeader(presentation, parent)


class RegressionView(QWidget):
    """Displays a fitted linear regression, or why none could be fitted.

    The coefficient table spans the top of the view. Three diagnostic plots
    (residuals vs fitted, actual vs predicted and a normal Q-Q plot of the
    residuals) sit side by side below it, followed by the model summary,
    diagnostics and warnings. A new result always means a new view instance.
    """

    def __init__(self, result: RegressionResult, parent: QWidget | None = None) -> None:
        """Initialize the Linear Regression view.

        Args:
            result: The regression result to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._result = result
        self._chart_labels = build_regression_chart_labels(
            result,
            QCoreApplication.translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )
        self._table: QTableWidget | None = None
        self._summary_label: QLabel | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            label = QLabel(self.error_text(result), self)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label)
            return

        layout.addWidget(build_regression_presentation_header(result, self))
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_coefficients_panel(result))
        splitter.addWidget(self._build_plots_panel(result))
        splitter.addWidget(self._build_summary(result))
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([250, 400, 160])
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def result(self) -> RegressionResult:
        """Return the displayed regression result."""
        return self._result

    def table(self) -> QTableWidget | None:
        """Return the coefficient table, or `None` when the result has an error."""
        return self._table

    def summary_label(self) -> QLabel | None:
        """Return the summary/diagnostics label, or `None` when the result has an error."""
        return self._summary_label

    def chart_labels(self) -> RegressionChartLabels:
        """Return the translated chart text shared by the displayed and exported charts."""
        return self._chart_labels

    def export_notes(self) -> tuple[str, ...]:
        """Return the displayed model comments and reference levels as plain-text lines."""
        result = self._result
        if result.error is not None:
            return ()
        return rich_text_lines((self._summary_text(result), "<br>".join(self._reference_lines(result))))

    def error_text(self, result: RegressionResult) -> str:
        """Return the translated message for `result`'s structured error.

        Args:
            result: A result whose `error` is set.
        """
        column = result.error_column or ""
        match result.error:
            case RegressionError.NO_NUMERIC_COLUMN:
                return self.tr("A linear regression needs at least one numeric column to use as the target.")
            case RegressionError.NO_PREDICTORS_SELECTED:
                return self.tr("Select one or more predictors and click Apply.")
            case RegressionError.TOO_MANY_PREDICTORS:
                return self.tr("Select at most {maximum} predictors.").format(maximum=fmt_int(MAX_PREDICTORS))
            case RegressionError.INVALID_COLUMN:
                return self.tr("Choose a numeric target and one or more other columns as predictors.")
            case RegressionError.TOO_MANY_TERMS:
                return self.tr(
                    "The model would have more than {maximum} terms once the categorical predictors are "
                    "dummy-coded. Remove predictors, or use categorical predictors with fewer levels."
                ).format(maximum=fmt_int(MAX_MODEL_TERMS))
            case RegressionError.NOT_ENOUGH_OBSERVATIONS:
                return self.tr(
                    "Only {count} rows have values in the target and every predictor, "
                    "which is too few to fit this model."
                ).format(count=fmt_int(result.n_used))
            case RegressionError.CONSTANT_TARGET:
                return self.tr(
                    "The target {column} has the same value in every row used, so there is nothing to explain."
                ).format(column=result.target)
            case RegressionError.CONSTANT_PREDICTOR:
                return self.tr(
                    "The predictor {column} has the same value in every row used, so its effect can't be estimated."
                ).format(column=column)
            case RegressionError.PERFECT_MULTICOLLINEARITY:
                return self.tr(
                    "Some predictors are exact linear combinations of others (perfect multicollinearity), "
                    "so the coefficients can't be estimated. Remove the redundant predictors."
                )
            case None:
                return ""

    def warning_text(self, warning: RegressionWarning) -> str:
        """Return the translated (plain) text of a non-blocking model caveat."""
        match warning.reason:
            case RegressionWarningReason.HIGH_MULTICOLLINEARITY:
                return self.tr(
                    "High multicollinearity (VIF above {threshold}) for: {terms}. "
                    "Their coefficients and p-values are unstable."
                ).format(threshold=fmt_num(HIGH_VIF_THRESHOLD), terms=", ".join(warning.terms))
            case RegressionWarningReason.HETEROSCEDASTICITY:
                return self.tr(
                    "The residual variance is not constant (heteroscedasticity), "
                    "so standard errors and p-values may be unreliable."
                )
            case RegressionWarningReason.NON_NORMAL_RESIDUALS:
                return self.tr(
                    "The residuals are not normally distributed. With few rows, "
                    "p-values and confidence intervals may be unreliable."
                )
            case RegressionWarningReason.AUTOCORRELATION:
                return self.tr("The residuals appear autocorrelated in row order, so standard errors may be too small.")

    # ------------------------------------------------------------------
    # Summary and diagnostics
    # ------------------------------------------------------------------

    def _build_summary(self, result: RegressionResult) -> QWidget:
        """Build the model summary section with a fixed title above scrollable text."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            self._build_section_title(
                regression_component_label(
                    RegressionModel.LINEAR,
                    RegressionExportComponent.MODEL_METRICS,
                    QCoreApplication.translate,
                ),
                panel,
            )
        )

        label = QLabel(self._summary_text(result))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._summary_label = label

        # Only the text scrolls, so the section title stays visible.
        scroll = build_section_scroll_area(label, panel)
        scroll.setMinimumWidth(260)
        layout.addWidget(scroll, 1)
        return panel

    def _summary_text(self, result: RegressionResult) -> str:
        """Return the rich text for the model summary, diagnostics and warnings."""
        lines = [
            f"<b>{_esc(self.tr('Linear regression'))}</b>",
            self.tr("Target: <b>{target}</b>").format(target=_esc(result.target)),
            self.tr("Rows used: {used} ({dropped} dropped because of missing values)").format(
                used=fmt_int(result.n_used), dropped=fmt_int(result.n_dropped)
            ),
            self.tr("R<sup>2</sup> = {r2}, adjusted R<sup>2</sup> = {adjusted}").format(
                r2=fmt_num(result.r_squared, sig=3), adjusted=fmt_num(result.adjusted_r_squared, sig=3)
            ),
            self.tr("F({df_model}, {df_residual}) = {f}, p {p}").format(
                df_model=fmt_int(result.df_model),
                df_residual=fmt_int(result.df_residual),
                f=fmt_num(result.f_statistic),
                p=_esc(self._p_relation(result.f_p_value)),
            ),
            self.tr("RMSE = {rmse}, AIC = {aic}").format(rmse=fmt_num(result.rmse), aic=fmt_num(result.aic)),
        ]

        if result.diagnostics is not None:
            lines += ["", self.tr("<b>Diagnostics</b>"), *self._diagnostic_lines(result, result.diagnostics)]

        if result.warnings:
            warning_lines = [
                '<span style="color: #cc6600;">'
                + self.tr("⚠ {warning}").format(warning=_esc(self.warning_text(warning)))
                + "</span>"
                for warning in result.warnings
            ]
            lines += ["", self.tr("<b>Warnings</b>"), *warning_lines]

        return "<br>".join(lines)

    def _diagnostic_lines(self, result: RegressionResult, diagnostics: RegressionDiagnostics) -> list[str]:
        """Return the rich-text lines describing each diagnostic with a verdict."""
        heteroscedastic = diagnostics.breusch_pagan_p_value < SIGNIFICANCE_LEVEL
        non_normal = diagnostics.jarque_bera_p_value < SIGNIFICANCE_LEVEL

        lines = [
            self.tr("Breusch-Pagan: LM = {statistic}, p {p} - {verdict}").format(
                statistic=fmt_num(diagnostics.breusch_pagan_statistic),
                p=_esc(self._p_relation(diagnostics.breusch_pagan_p_value)),
                verdict=self.tr("non-constant residual variance")
                if heteroscedastic
                else self.tr("no evidence of non-constant residual variance"),
            ),
            self.tr("Jarque-Bera: JB = {statistic}, p {p} - {verdict}").format(
                statistic=fmt_num(diagnostics.jarque_bera_statistic),
                p=_esc(self._p_relation(diagnostics.jarque_bera_p_value)),
                verdict=self.tr("residuals not normally distributed")
                if non_normal
                else self.tr("residuals consistent with a normal distribution"),
            ),
        ]
        if non_normal and result.n_used > LARGE_SAMPLE_SIZE:
            lines.append(
                self.tr(
                    "<i>With many rows even negligible deviations from normality are significant. "
                    "Judge by the Q-Q plot instead.</i>"
                )
            )

        lines += [
            self.tr("Durbin-Watson = {statistic} - {verdict}").format(
                statistic=fmt_num(diagnostics.durbin_watson, sig=3),
                verdict=self._durbin_watson_verdict(diagnostics.durbin_watson),
            ),
            self.tr(
                "<i>Durbin-Watson is only meaningful when the row order is meaningful (e.g. rows sorted by time).</i>"
            ),
            self.tr("Largest VIF = {vif} - {verdict}").format(
                vif=fmt_num(diagnostics.max_vif, sig=3),
                verdict=self.tr("high multicollinearity")
                if diagnostics.max_vif > HIGH_VIF_THRESHOLD
                else self.tr("no problematic multicollinearity"),
            ),
        ]
        return lines

    def _durbin_watson_verdict(self, statistic: float) -> str:
        """Return the translated verdict for a Durbin-Watson statistic."""
        if statistic < DURBIN_WATSON_LOW:
            return self.tr("positive autocorrelation")
        if statistic > DURBIN_WATSON_HIGH:
            return self.tr("negative autocorrelation")
        return self.tr("no evidence of autocorrelation")

    @staticmethod
    def _p_relation(p_value: float) -> str:
        """Return ``"= p"`` or ``"< threshold"`` for use after "p"."""
        text = fmt_p_value(p_value)
        return text if text.startswith("<") else f"= {text}"

    # ------------------------------------------------------------------
    # Coefficients
    # ------------------------------------------------------------------

    def _build_coefficients_panel(self, result: RegressionResult) -> QWidget:
        """Build the coefficient table with its caption."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        coefficient_label = regression_component_label(
            RegressionModel.LINEAR,
            RegressionExportComponent.COEFFICIENTS,
            QCoreApplication.translate,
        )
        title = QLabel(f"<b>{_esc(coefficient_label)}</b>", panel)
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)

        table_panel = QFrame(panel)
        table_panel.setFrameShape(QFrame.Shape.NoFrame)
        table_panel.setBackgroundRole(QPalette.ColorRole.Button)
        table_panel.setAutoFillBackground(True)
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self._table = self._build_table(result, table_panel)
        table_layout.addWidget(self._table, 1)

        caption = QLabel(self._coefficients_caption(result), table_panel)
        caption.setTextFormat(Qt.TextFormat.RichText)
        caption.setWordWrap(True)
        table_layout.addWidget(caption)
        layout.addWidget(table_panel, 1)

        return panel

    def _build_table(self, result: RegressionResult, parent: QWidget) -> QTableWidget:
        """Build the table of every model term."""
        headers = [
            self.tr("Term"),
            self.tr("Estimate"),
            self.tr("Std. error"),
            self.tr("t"),
            self.tr("p"),
            self.tr("{confidence}% CI").format(confidence=fmt_int(round(CONFIDENCE_LEVEL * 100))),
            self.tr("VIF"),
        ]

        table = QTableWidget(parent)
        table.setColumnCount(len(headers))
        table.setRowCount(len(result.terms))
        table.setHorizontalHeaderLabels(headers)

        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)

        for row, term in enumerate(result.terms):
            for col, text in enumerate(self._term_row(term)):
                item = QTableWidgetItem(text)
                if col > _TERM_COLUMN:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, col, item)

        table.resizeColumnsToContents()

        hheader = table.horizontalHeader()
        if hheader is not None:
            hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        return table

    def _term_row(self, term: RegressionTerm) -> list[str]:
        """Return the formatted table cells for one term."""
        significant = not math.isnan(term.p_value) and term.p_value < SIGNIFICANCE_LEVEL
        return [
            regression_intercept_label(QCoreApplication.translate)
            if term.kind is TermKind.INTERCEPT
            else term_name(term),
            fmt_num(term.estimate),
            fmt_num(term.std_error),
            fmt_num(term.t_statistic, sig=3),
            fmt_p_value(term.p_value) + (" *" if significant else ""),
            self._interval_text(term),
            "" if math.isnan(term.vif) else fmt_num(term.vif, sig=3),
        ]

    def _interval_text(self, term: RegressionTerm) -> str:
        """Return the formatted confidence interval, or "N/A" when undefined."""
        if math.isnan(term.ci_low) or math.isnan(term.ci_high):
            return self.tr("N/A")
        return self.tr("{low} to {high}").format(low=fmt_num(term.ci_low), high=fmt_num(term.ci_high))

    def _coefficients_caption(self, result: RegressionResult) -> str:
        """Return the rich-text caption explaining significance marks and reference levels."""
        lines = [
            self.tr("* marks coefficients significant at p &lt; {alpha}.").format(alpha=fmt_num(SIGNIFICANCE_LEVEL)),
            *self._reference_lines(result),
        ]
        return "<br>".join(lines)

    def _reference_lines(self, result: RegressionResult) -> list[str]:
        """Return rich-text lines naming each categorical predictor's reference level."""
        if not result.references:
            return []
        return [
            self.tr("Each categorical level is compared with its column's reference level (the most frequent level):"),
            *(
                self.tr("{column}: reference level <b>{level}</b> ({count} levels)").format(
                    column=_esc(reference.column),
                    level=_esc(reference.reference_level),
                    count=fmt_int(reference.level_count),
                )
                for reference in result.references
            ),
        ]

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------

    def _build_plots_panel(self, result: RegressionResult) -> QWidget:
        """Build the three diagnostic plots side by side, with a sampling note."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            self._build_section_title(
                regression_component_label(
                    RegressionModel.LINEAR,
                    RegressionExportComponent.CHARTS,
                    QCoreApplication.translate,
                ),
                panel,
            )
        )

        plot = result.plot
        if plot is None:
            return panel

        labels = self._chart_labels.model
        if not isinstance(labels, LinearChartLabels):
            message = "Linear regression view received chart labels for another model."
            raise TypeError(message)
        splitter = QSplitter(Qt.Orientation.Horizontal, panel)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_canvas(lambda ax: draw_residuals_vs_fitted(ax, plot, labels)))
        splitter.addWidget(self._build_canvas(lambda ax: draw_actual_vs_predicted(ax, plot, labels)))
        splitter.addWidget(self._build_canvas(lambda ax: draw_normal_qq(ax, plot, labels)))
        # Charts keep a readable minimum size and scroll when their section is smaller.
        layout.addWidget(build_section_scroll_area(splitter, panel), 1)

        if plot.sampled:
            caption = QLabel("\n".join(self._chart_labels.metadata.captions), panel)
            caption.setWordWrap(True)
            layout.addWidget(caption)

        return panel

    @staticmethod
    def _build_section_title(text: str, parent: QWidget) -> QLabel:
        """Build a bold title for a regression section."""
        label = QLabel(text, parent)
        label.setStyleSheet("font-weight: bold;")
        return label

    @staticmethod
    def _build_canvas(draw: Callable[[Axes], None]) -> QWidget:
        """Build a matplotlib canvas with one axes drawn by `draw`."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(200, 180)
        ax = figure.add_subplot(111)
        draw(ax)
        ax.title.set_fontsize(_TITLE_FONT_SIZE)
        ax.xaxis.label.set_fontsize(_LABEL_FONT_SIZE)
        ax.yaxis.label.set_fontsize(_LABEL_FONT_SIZE)
        ax.tick_params(labelsize=_TICK_FONT_SIZE)
        return canvas
