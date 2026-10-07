"""Result view for logistic and count regression."""

from __future__ import annotations

import html
from itertools import chain
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.regression import MAX_MODEL_TERMS, MAX_PREDICTORS, TermKind
from expo_jbm329.services.analysis.regression_glm import (
    OVERDISPERSION_THRESHOLD,
    CountPlotError,
    GeneralizedRegressionError,
    RegressionModel,
    generalized_term_name,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.regression_glm import GeneralizedRegressionResult


class GeneralizedRegressionView(QWidget):
    """Display exponentiated coefficients, fit summary and count diagnostics."""

    def __init__(self, result: GeneralizedRegressionResult, parent: QWidget | None = None) -> None:
        """Initialize the generalized regression result view.

        Args:
            result: Fitted generalized regression or a structured error.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._result = result
        self._table: QTableWidget | None = None
        self._summary_label: QLabel | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            label = QLabel(self.error_text(result), self)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return

        self._table = self._build_coefficient_table()
        self._summary_label = QLabel(self._summary_text(), self)
        self._summary_label.setTextFormat(Qt.TextFormat.RichText)
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if result.model in {RegressionModel.POISSON, RegressionModel.NEGATIVE_BINOMIAL}:
            splitter = QSplitter(Qt.Orientation.Vertical, self)
            splitter.setChildrenCollapsible(False)
            table_panel, table_layout = self._build_section(self.tr("Model coefficients"))
            table_layout.addWidget(self._table)
            summary_panel, summary_layout = self._build_section(self.tr("Model comments"))
            summary_layout.addWidget(self._summary_label)
            splitter.addWidget(table_panel)
            splitter.addWidget(self._build_chart_section())
            splitter.addWidget(summary_panel)
            splitter.setStretchFactor(0, 2)
            splitter.setStretchFactor(1, 3)
            splitter.setStretchFactor(2, 1)
            splitter.setSizes([250, 350, 160])
            layout.addWidget(splitter, 1)
        else:
            layout.addWidget(self._table, 2)
            layout.addWidget(self._summary_label, 1)

    def _build_section(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        """Build a titled section matching the Hypothesis Tests layout."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title, panel)
        label.setTextFormat(Qt.TextFormat.PlainText)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)
        return panel, layout

    def _build_chart_section(self) -> QWidget:
        """Render response-scale fit and variance-aware residual diagnostics."""
        panel, layout = self._build_section(self.tr("Count-model diagnostics"))
        data = self._result.plot_data
        if data is None:
            if self._result.plot_error is CountPlotError.INVALID_PREDICTIONS:
                text = self.tr("Charts unavailable: fitted counts are not finite and strictly positive.")
            elif self._result.plot_error is CountPlotError.INVALID_RESIDUALS:
                text = self.tr("Charts unavailable: Pearson residuals are not finite.")
            elif self._result.plot_error is CountPlotError.INVALID_VARIANCE:
                text = self.tr("Charts unavailable: the fitted Negative Binomial variance is invalid.")
            else:
                text = self.tr("No count-model chart data are available.")
            label = QLabel(text, panel)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label)
            return panel
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumHeight(260)
        comparison = figure.add_subplot(121)
        residuals = figure.add_subplot(122)
        comparison.scatter(data.fitted, data.observed, alpha=0.35, s=12)
        upper = max(chain(data.fitted, data.observed))
        comparison.plot([0, upper], [0, upper], linestyle="--", color="tab:red")
        comparison.set_title(self.tr("Observed versus fitted counts"))
        comparison.set_xlabel(self.tr("Fitted count"))
        comparison.set_ylabel(self.tr("Observed count"))
        residuals.scatter(data.fitted, data.pearson_residuals, alpha=0.35, s=12)
        residuals.axhline(0, linestyle="--", color="tab:red")
        residuals.set_title(self.tr("Pearson residuals versus fitted counts"))
        residuals.set_xlabel(self.tr("Fitted count"))
        residuals.set_ylabel(self.tr("Pearson residual"))
        layout.addWidget(canvas)
        return panel

    def result(self) -> GeneralizedRegressionResult:
        """Return the displayed result."""
        return self._result

    def table(self) -> QTableWidget | None:
        """Return the coefficient table, or `None` when fitting failed."""
        return self._table

    def summary_label(self) -> QLabel | None:
        """Return the model summary, or `None` when fitting failed."""
        return self._summary_label

    def error_text(self, result: GeneralizedRegressionResult) -> str:
        """Translate a structured fitting error."""
        column = result.error_column or ""
        match result.error:
            case GeneralizedRegressionError.NO_TARGET:
                return self.tr("Select an outcome column for this regression model.")
            case GeneralizedRegressionError.INVALID_TARGET:
                return self.tr(
                    "The selected outcome is invalid. Logistic regression needs two outcome levels; "
                    "count regression needs non-negative integer values."
                )
            case GeneralizedRegressionError.NO_PREDICTORS_SELECTED:
                return self.tr("Select one or more predictors and click Apply.")
            case GeneralizedRegressionError.TOO_MANY_PREDICTORS:
                return self.tr("Select at most {maximum} predictors.").format(maximum=fmt_int(MAX_PREDICTORS))
            case GeneralizedRegressionError.INVALID_COLUMN:
                return self.tr("Choose a valid outcome and one or more other columns as predictors.")
            case GeneralizedRegressionError.TOO_MANY_TERMS:
                return self.tr(
                    "The model would have more than {maximum} terms after categorical predictors are dummy-coded. "
                    "Remove predictors or use columns with fewer levels."
                ).format(maximum=fmt_int(MAX_MODEL_TERMS))
            case GeneralizedRegressionError.NOT_ENOUGH_OBSERVATIONS:
                return self.tr("Only {count} complete rows are available, which is too few to fit this model.").format(
                    count=fmt_int(result.n_used)
                )
            case GeneralizedRegressionError.CONSTANT_TARGET:
                return self.tr("The outcome {column} has only one value in the complete rows.").format(column=column)
            case GeneralizedRegressionError.CONSTANT_PREDICTOR:
                return self.tr("The predictor {column} has the same value in every complete row.").format(column=column)
            case GeneralizedRegressionError.PERFECT_MULTICOLLINEARITY:
                return self.tr(
                    "Some predictors are exact linear combinations of others, so the model cannot be estimated."
                )
            case GeneralizedRegressionError.FIT_FAILED:
                return self.tr(
                    "The model could not be fitted. Check for sparse outcomes, separation, or redundant predictors."
                )
            case None:
                return ""

    def _build_coefficient_table(self) -> QTableWidget:
        """Build the non-selectable coefficient and effect table."""
        if self._result.model is RegressionModel.LOGISTIC:
            effect_label = self.tr("Odds ratio")
        else:
            effect_label = self.tr("Rate ratio")
        table = QTableWidget(len(self._result.terms), 5, self)
        table.setHorizontalHeaderLabels([
            self.tr("Term"),
            self.tr("Coefficient"),
            effect_label,
            self.tr("95% effect CI"),
            self.tr("p-value"),
        ])
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        header = table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        for row, term in enumerate(self._result.terms):
            name = self.tr("(Intercept)") if term.kind is TermKind.INTERCEPT else generalized_term_name(term)
            values = (
                name,
                fmt_num(term.estimate),
                fmt_num(term.effect),
                f"{fmt_num(term.effect_ci_low)} to {fmt_num(term.effect_ci_high)}",
                fmt_p_value(term.p_value),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        return table

    def _summary_text(self) -> str:
        """Build the translated summary and dispersion guidance."""
        result = self._result
        if result.model is RegressionModel.LOGISTIC:
            model_name = self.tr("Logistic regression")
            outcome_note = self.tr("Outcome coding: {zero} = 0; {one} = 1.").format(
                zero=html.escape(result.target_levels[0]),
                one=html.escape(result.target_levels[1]),
            )
        elif result.model is RegressionModel.POISSON:
            model_name = self.tr("Poisson regression")
            outcome_note = ""
        else:
            model_name = self.tr("Negative binomial regression")
            outcome_note = ""
        lines = [
            self.tr("<b>{model}</b>").format(model=model_name),
            self.tr("Target: <b>{target}</b>").format(target=html.escape(result.target)),
            self.tr("Rows used: {used} ({dropped} dropped because of missing values)").format(
                used=fmt_int(result.n_used),
                dropped=fmt_int(result.n_dropped),
            ),
        ]
        if outcome_note:
            lines.append(outcome_note)
        lines.extend([
            self.tr("Log-likelihood = {value}; McFadden pseudo R<sup>2</sup> = {pseudo}").format(
                value=fmt_num(result.log_likelihood),
                pseudo=fmt_num(result.pseudo_r_squared, sig=3),
            ),
            self.tr("AIC = {aic}").format(aic=fmt_num(result.aic)),
        ])
        if result.model in {RegressionModel.POISSON, RegressionModel.NEGATIVE_BINOMIAL}:
            if result.plot_error in {CountPlotError.INVALID_PREDICTIONS, CountPlotError.INVALID_RESIDUALS}:
                lines.append(
                    self.tr("Dispersion diagnostic unavailable because fitted counts or residuals are invalid.")
                )
            else:
                if result.overdispersed:
                    dispersion_text = self.tr(
                        "Pearson dispersion = {value}, above the {threshold} guideline; consider Negative Binomial."
                    )
                else:
                    dispersion_text = self.tr(
                        "Pearson dispersion = {value}; it does not exceed the {threshold} guideline for overdispersion."
                    )
                lines.append(
                    dispersion_text.format(
                        value=fmt_num(result.dispersion_ratio),
                        threshold=fmt_num(OVERDISPERSION_THRESHOLD),
                    )
                )
            lines.append(self.tr("This diagnostic is advisory; the selected model was not changed."))
        if result.model is RegressionModel.NEGATIVE_BINOMIAL and result.negative_binomial_alpha is not None:
            lines.append(
                self.tr("Fitted NB2 alpha = {alpha}; this is distinct from the advisory Pearson dispersion.").format(
                    alpha=fmt_num(result.negative_binomial_alpha),
                )
            )
        if (
            result.model in {RegressionModel.POISSON, RegressionModel.NEGATIVE_BINOMIAL}
            and result.plot_data is not None
        ):
            lines.append(
                self.tr("Charts describe the fitted rows (in-sample), not out-of-sample predictive performance.")
            )
            if result.model is RegressionModel.POISSON:
                lines.append(self.tr("Poisson Pearson residuals use variance equal to the fitted count."))
            else:
                lines.append(
                    self.tr(
                        "Negative Binomial Pearson residuals use NB2 variance: "
                        "fitted count + alpha * fitted count squared."
                    )
                )
            if result.plot_data.sampled:
                lines.append(
                    self.tr("Charts show a deterministic sample of {shown} of {total} fitted rows.").format(
                        shown=fmt_int(len(result.plot_data.observed)),
                        total=fmt_int(result.n_used),
                    )
                )
                lines.append(self.tr("Coefficient estimates and dispersion diagnostics use all fitted rows."))
        return "<br>".join(lines)
