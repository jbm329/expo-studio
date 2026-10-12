"""Result view for Cox proportional-hazards regression."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.section_layout import build_section_scroll_area, rich_text_lines
from expo_jbm329.services.analysis.regression import MAX_MODEL_TERMS, MAX_PREDICTORS, TermKind
from expo_jbm329.services.analysis.regression_charts import CoxChartLabels, RegressionChartLabels, draw_cox_charts
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
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        table_panel, table_layout = self._build_section(self.tr("Model coefficients"))
        table_layout.addWidget(self._table)
        summary_panel, summary_layout = self._build_section(self.tr("Model comments"))
        # Only the text scrolls, so the section title stays visible.
        summary_layout.addWidget(build_section_scroll_area(self._summary_label, summary_panel), 1)
        splitter.addWidget(table_panel)
        splitter.addWidget(self._build_chart_section())
        splitter.addWidget(summary_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([250, 350, 160])
        layout.addWidget(splitter, 1)

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
        """Render model effects and unadjusted survival from prepared cohort data."""
        panel, layout = self._build_section(self.tr("Effects and survival"))
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumHeight(300)
        draw_cox_charts(figure, self._result, self._cox_chart_labels())
        # Charts keep a readable minimum height and scroll when their section is smaller.
        layout.addWidget(build_section_scroll_area(canvas, panel), 1)
        return panel

    def _cox_chart_labels(self) -> CoxChartLabels:
        """Return the translated forest, survival and risk-table chart text."""
        return CoxChartLabels(
            forest_title=self.tr("Hazard ratios with 95% intervals"),
            forest_unavailable=self.tr(
                "Forest plot unavailable:\nall hazard ratios and intervals must be finite and positive."
            ),
            hazard_axis=self.tr("Hazard ratio (log scale)"),
            survival_title=self.tr("Overall Kaplan-Meier survival (unadjusted)"),
            survival_unavailable=self.tr("No survival chart data are available."),
            duration_axis=self.tr("Duration: {column}").format(column=self._result.duration),
            survival_axis=self.tr("Survival probability"),
            risk_title=self.tr("At risk immediately before time"),
            tick_format=lambda value: fmt_num(value, sig=2),
            time_format=lambda value: fmt_num(value, sig=3),
            count_format=fmt_int,
        )

    def result(self) -> SurvivalResult:
        """Return the displayed Cox result."""
        return self._result

    def table(self) -> QTableWidget | None:
        """Return the coefficient table, or ``None`` when fitting failed."""
        return self._table

    def summary_label(self) -> QLabel | None:
        """Return the model summary, or ``None`` when fitting failed."""
        return self._summary_label

    def chart_labels(self) -> RegressionChartLabels:
        """Return the translated chart text shared by the displayed and exported charts."""
        result = self._result
        return RegressionChartLabels(
            heading=self.tr("Cox proportional-hazards regression: {duration} / {event}").format(
                duration=result.duration, event=result.event
            ),
            model=self._cox_chart_labels(),
        )

    def export_notes(self) -> tuple[str, ...]:
        """Return the displayed model comments as plain-text lines."""
        if self._result.error is not None:
            return ()
        return rich_text_lines((self._summary_text(),))

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
            header.setStretchLastSection(False)
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
        if result.plot_data is not None:
            lines.extend([
                self.tr(
                    "Kaplan-Meier uses the same complete-case subjects as the Cox fit, without covariate adjustment."
                ),
                self.tr("The survival curve is not a Cox prediction or a proportional-hazards diagnostic."),
                self.tr("Plus signs mark censoring times; tied censor marks may overlap."),
                self.tr("All complete subjects are used; no survival sampling or confidence bands are applied."),
            ])
        return "<br>".join(lines)
