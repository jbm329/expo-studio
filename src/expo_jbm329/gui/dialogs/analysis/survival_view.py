"""Result view for Cox proportional-hazards regression."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.regression import MAX_MODEL_TERMS, MAX_PREDICTORS, TermKind
from expo_jbm329.services.analysis.survival import SurvivalError, survival_term_name
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.survival import SurvivalResult


class SurvivalRegressionView(QWidget):
    """Display Cox coefficients, hazard ratios, and fitting caveats."""

    def __init__(self, result: SurvivalResult, parent: QWidget | None = None) -> None:
        """Initialize the Cox result view.

        Args:
            result: A fitted Cox model or a structured error.
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

    def result(self) -> SurvivalResult:
        """Return the displayed Cox result."""
        return self._result

    def table(self) -> QTableWidget | None:
        """Return the coefficient table, or ``None`` when fitting failed."""
        return self._table

    def summary_label(self) -> QLabel | None:
        """Return the model summary, or ``None`` when fitting failed."""
        return self._summary_label

    def error_text(self, result: SurvivalResult) -> str:
        """Translate a structured Cox fitting error."""
        column = result.error_column or ""
        match result.error:
            case SurvivalError.NO_DURATION:
                return self.tr("Select a duration column for Cox regression.")
            case SurvivalError.NO_EVENT:
                return self.tr("Select a binary event column for Cox regression.")
            case SurvivalError.NO_PREDICTORS_SELECTED:
                return self.tr("Select one or more predictors and click Apply.")
            case SurvivalError.TOO_MANY_PREDICTORS:
                return self.tr("Select at most {maximum} predictors.").format(maximum=fmt_int(MAX_PREDICTORS))
            case SurvivalError.INVALID_COLUMN:
                return self.tr("Choose valid, distinct duration and event columns and other columns as predictors.")
            case SurvivalError.INVALID_DURATION:
                return self.tr(
                    "Duration {column} contains a non-missing value that is not finite and strictly positive."
                ).format(column=column)
            case SurvivalError.INVALID_EVENT:
                return self.tr(
                    "Event {column} must contain only 0 and 1 or boolean values; 1 means event and 0 means censored."
                ).format(column=column)
            case SurvivalError.TOO_MANY_TERMS:
                return self.tr(
                    "The model would have more than {maximum} terms after categorical predictors are dummy-coded. "
                    "Remove predictors or use columns with fewer levels."
                ).format(maximum=fmt_int(MAX_MODEL_TERMS))
            case SurvivalError.NOT_ENOUGH_OBSERVATIONS:
                return self.tr("Only {count} complete rows are available, which is too few to fit this model.").format(
                    count=fmt_int(result.n_used)
                )
            case SurvivalError.NOT_ENOUGH_EVENTS:
                return self.tr("There are too few events relative to the model terms to estimate this model.")
            case SurvivalError.CONSTANT_PREDICTOR:
                return self.tr("The predictor {column} has the same value in every complete row.").format(column=column)
            case SurvivalError.PERFECT_MULTICOLLINEARITY:
                return self.tr(
                    "Some predictors are exact linear combinations of others, so the model cannot be estimated."
                )
            case SurvivalError.FIT_FAILED:
                return self.tr(
                    "The model could not be fitted reliably. Check for sparse events, separation, redundant "
                    "predictors, or numerical problems."
                )
            case None:
                return ""

    def _build_coefficient_table(self) -> QTableWidget:
        """Build a non-editable table of Cox coefficient estimates."""
        table = QTableWidget(len(self._result.terms), 5, self)
        table.setHorizontalHeaderLabels([
            self.tr("Term"),
            self.tr("Coefficient"),
            self.tr("Hazard ratio"),
            self.tr("95% hazard-ratio CI"),
            self.tr("p-value"),
        ])
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        header = table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        for row, term in enumerate(self._result.terms):
            name = self.tr("(Intercept)") if term.kind is TermKind.INTERCEPT else survival_term_name(term)
            values = (
                name,
                fmt_num(term.estimate),
                fmt_num(term.hazard_ratio),
                f"{fmt_num(term.hazard_ratio_ci_low)} to {fmt_num(term.hazard_ratio_ci_high)}",
                fmt_p_value(term.p_value),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        return table

    def _summary_text(self) -> str:
        """Build counts, categorical references, and explicit Cox caveats."""
        result = self._result
        lines = [
            self.tr("<b>Cox proportional-hazards regression</b>"),
            self.tr("Duration: <b>{duration}</b>; event: <b>{event}</b>").format(
                duration=html.escape(result.duration),
                event=html.escape(result.event),
            ),
            self.tr("Event coding: 1 = event; 0 = censored."),
            self.tr("Rows used: {used} ({dropped} excluded by listwise missing-value handling)").format(
                used=fmt_int(result.n_used),
                dropped=fmt_int(result.n_dropped),
            ),
            self.tr("Events: {events}; censored: {censored}").format(
                events=fmt_int(result.n_events),
                censored=fmt_int(result.n_censored),
            ),
        ]
        lines.extend(
            self.tr("Reference for {column}: {level}").format(
                column=html.escape(reference.column),
                level=html.escape(reference.reference_level),
            )
            for reference in result.references
        )
        lines.extend([
            self.tr("Efron method was used to handle tied event times."),
            self.tr("The proportional-hazards assumption was not assessed."),
        ])
        return "<br>".join(lines)
