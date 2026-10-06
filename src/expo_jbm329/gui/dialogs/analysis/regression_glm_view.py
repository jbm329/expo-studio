"""Result view for logistic and count regression."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.regression import MAX_MODEL_TERMS, MAX_PREDICTORS, TermKind
from expo_jbm329.services.analysis.regression_glm import (
    OVERDISPERSION_THRESHOLD,
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
        layout.addWidget(self._table, 2)
        layout.addWidget(self._summary_label, 1)

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
        return "<br>".join(lines)
