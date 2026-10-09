"""Qt-free reusable rendering of logistic regression diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.ticker import NullLocator

from expo_jbm329.services.analysis.regression import TermKind
from expo_jbm329.services.analysis.regression_glm import generalized_term_name

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from expo_jbm329.services.analysis.regression_glm import GeneralizedRegressionResult


@dataclass(frozen=True, slots=True)
class LogisticChartLabels:
    """Localized chart labels and annotations supplied at the UI boundary."""

    odds_title: str
    odds_axis: str
    no_predictors: str
    unavailable_effect: str
    roc_title: str
    false_positive_axis: str
    true_positive_axis: str
    auc_annotation: str
    calibration_title: str
    probability_axis: str
    event_fraction_axis: str
    unavailable_diagnostics: str
    effect_annotations: tuple[str, ...]


def build_logistic_charts(
    figure: Figure,
    result: GeneralizedRegressionResult,
    labels: LogisticChartLabels,
) -> None:
    """Build odds ratios, ROC and calibration on an externally protected figure.

    Args:
        figure: Empty figure; callers serialize all Matplotlib mutations.
        result: Fitted result with worker-prepared full-cohort diagnostics.
        labels: Localized labels, including formatted effect and AUC annotations.
    """
    terms = tuple(term for term in result.terms if term.kind is not TermKind.INTERCEPT)
    grid = figure.add_gridspec(2, 2, height_ratios=(max(2.0, len(terms) * 0.24), 3.0))
    odds = figure.add_subplot(grid[0, :])
    roc = figure.add_subplot(grid[1, 0])
    calibration = figure.add_subplot(grid[1, 1])
    odds.set_title(labels.odds_title)
    odds.set_xlabel(labels.odds_axis)
    odds.set_xscale("log", base=math.e)
    odds.set_autoscalex_on(False)
    odds.axvline(1, color="tab:red", linestyle="--")
    odds.set_yticks(range(len(terms)), [generalized_term_name(term) for term in terms])
    for tick in odds.get_yticklabels():
        tick.set_parse_math(False)
    odds.set_ylim(len(terms) - 0.5 if terms else 0.5, -0.5)
    limits = [1.0]
    for row, term in enumerate(terms):
        low, effect, high = term.effect_ci_low, term.effect, term.effect_ci_high
        valid = all(math.isfinite(value) and value > 0 for value in (low, effect, high))
        valid = valid and low <= effect <= high
        if valid:
            odds.plot([low, high], [row, row], color="tab:blue", marker="|")
            odds.plot([effect], [row], color="tab:blue", marker="o")
            limits.extend((low, high))
        annotation = labels.effect_annotations[row] if valid else labels.unavailable_effect
        odds.text(1.01, row, annotation, transform=odds.get_yaxis_transform(), va="center", fontsize="small")
    if not terms:
        odds.text(0.5, 0.5, labels.no_predictors, transform=odds.transAxes, ha="center", va="center")
    low_limit = max(min(limits) / 1.2, float(np.nextafter(0.0, 1.0)))
    high_limit = min(max(limits), float(np.finfo(float).max) / 1.2) * 1.2
    high_limit = max(high_limit, *limits)
    odds.set_xlim(low_limit, high_limit)
    ticks = np.exp(np.linspace(math.log(low_limit), math.log(high_limit), 5))
    odds.set_xticks(ticks, [f"{value:.3g}" for value in ticks])
    odds.xaxis.set_minor_locator(NullLocator())

    for axes, title, xlabel, ylabel in (
        (roc, labels.roc_title, labels.false_positive_axis, labels.true_positive_axis),
        (calibration, labels.calibration_title, labels.probability_axis, labels.event_fraction_axis),
    ):
        axes.set_title(title)
        axes.set_xlabel(xlabel)
        axes.set_ylabel(ylabel)
        axes.set_xlim(0, 1)
        axes.set_ylim(0, 1)
        axes.plot([0, 1], [0, 1], color="tab:red", linestyle="--")
    data = result.logistic_plot_data
    if data is None:
        for axes in (roc, calibration):
            axes.text(
                0.5, 0.5, labels.unavailable_diagnostics, transform=axes.transAxes, ha="center", va="center", wrap=True
            )
        return
    roc.plot(data.false_positive_rates, data.true_positive_rates, color="tab:blue", label=labels.auc_annotation)
    roc.legend(loc="lower right")
    calibration.plot(data.mean_probabilities, data.event_fractions, marker="o", color="tab:blue")
