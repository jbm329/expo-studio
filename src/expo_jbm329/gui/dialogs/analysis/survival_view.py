"""Result view for Cox proportional-hazards regression."""

from __future__ import annotations

import html
import math
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator
from matplotlib.transforms import Bbox
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.regression import MAX_MODEL_TERMS, MAX_PREDICTORS, TermKind
from expo_jbm329.services.analysis.survival import SurvivalError, survival_term_name
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from matplotlib.axes import Axes

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
        summary_layout.addWidget(self._summary_label, 1)
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
        grid = figure.add_gridspec(2, 2, height_ratios=[5, 1])
        self._draw_forest(figure.add_subplot(grid[:, 0]))
        self._draw_survival(figure.add_subplot(grid[0, 1]))
        self._draw_risk_counts(figure.add_subplot(grid[1, 1]))
        layout.addWidget(canvas, 1)
        return panel

    def _draw_forest(self, axis: Axes) -> None:
        """Show every term or explicitly explain why a log-scale plot is unavailable."""
        terms = self._result.terms
        axis.set_title(self.tr("Hazard ratios with 95% intervals"))
        if not terms or any(
            not all(
                math.isfinite(value) and value > 0
                for value in (
                    term.hazard_ratio,
                    term.hazard_ratio_ci_low,
                    term.hazard_ratio_ci_high,
                )
            )
            or not term.hazard_ratio_ci_low <= term.hazard_ratio <= term.hazard_ratio_ci_high
            for term in terms
        ):
            axis.text(
                0.5,
                0.5,
                self.tr("Forest plot unavailable:\nall hazard ratios and intervals must be finite and positive."),
                transform=axis.transAxes,
                ha="center",
                va="center",
                wrap=True,
            )
            axis.set_axis_off()
            return
        ratios = [term.hazard_ratio for term in terms]
        positions = list(range(len(terms)))
        axis.set_xscale("log")
        lower = min(1.0, *(term.hazard_ratio_ci_low for term in terms))
        upper = max(1.0, *(term.hazard_ratio_ci_high for term in terms))
        if lower == upper:
            lower, upper = 0.5, 2.0
        # Fixed ticks avoid automatic log locators overflowing on extreme finite intervals.
        log_low, log_high = math.log(lower), math.log(upper)
        ticks = [math.exp(log_low + (log_high - log_low) * index / 4) for index in range(5)]
        axis.xaxis.set_major_locator(FixedLocator(ticks))
        axis.xaxis.set_major_formatter(FixedFormatter([fmt_num(value, sig=2) for value in ticks]))
        axis.xaxis.set_minor_locator(NullLocator())
        lows = [term.hazard_ratio_ci_low for term in terms]
        highs = [term.hazard_ratio_ci_high for term in terms]
        # Draw endpoints directly; reconstructing them from xerr can lose tiny bounds.
        axis.hlines(positions, lows, highs, color="tab:blue")
        axis.plot(ratios, positions, linestyle="none", marker="o", color="tab:blue")
        axis.plot(lows, positions, linestyle="none", marker="|", color="tab:blue")
        axis.plot(highs, positions, linestyle="none", marker="|", color="tab:blue")
        axis.axvline(1.0, linestyle="--", color="tab:red")
        axis.set_xlim(lower, upper)
        axis.set_yticks(positions, [survival_term_name(term) for term in terms])
        axis.set_ylim(len(terms) - 0.5, -0.5)
        axis.set_xlabel(self.tr("Hazard ratio (log scale)"))

    def _draw_survival(self, axis: Axes) -> None:
        """Draw all unique follow-up times with censor marks and selected risk counts."""
        axis.set_title(self.tr("Overall Kaplan-Meier survival (unadjusted)"))
        data = self._result.plot_data
        if data is None:
            axis.text(
                0.5,
                0.5,
                self.tr("No survival chart data are available."),
                transform=axis.transAxes,
                ha="center",
                va="center",
            )
            axis.set_axis_off()
            return
        axis.step(data.times, data.survival, where="post", color="tab:blue")
        censor_indices = [index for index, count in enumerate(data.censored) if count > 0]
        axis.plot(
            [data.times[index] for index in censor_indices],
            [data.survival[index] for index in censor_indices],
            linestyle="none",
            marker="+",
            color="tab:blue",
        )
        axis.set_ylim(0, 1.05)
        axis.set_xlim(0, data.times[-1])
        axis.set_xlabel(self.tr("Duration: {column}").format(column=self._result.duration))
        axis.set_ylabel(self.tr("Survival probability"))
        axis.set_xticks(data.risk_times)
        axis.tick_params(axis="x", labelrotation=30)

    def _draw_risk_counts(self, axis: Axes) -> None:
        """Show uniformly spaced follow-up times and their exact risk counts."""
        axis.set_axis_off()
        data = self._result.plot_data
        if data is None:
            return
        axis.set_title(self.tr("At risk immediately before time"), fontsize=9)
        table = axis.table(
            cellText=[[fmt_int(count) for count in data.risk_counts]],
            colLabels=[fmt_num(time, sig=3) for time in data.risk_times],
            loc="center",
            bbox=Bbox.from_bounds(0, 0, 1, 1),
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)

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
