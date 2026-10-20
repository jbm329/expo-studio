"""Focused tests for metadata-only analysis computation diagnostics."""

from __future__ import annotations

import inspect
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from statsmodels.duration.hazard_regression import PHReg

from expo_jbm329.services.analysis import overview, statistics
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.chi_square import analyze_chi_square
from expo_jbm329.services.analysis.clustering import analyze_clustering
from expo_jbm329.services.analysis.correlation import (
    analyze_correlation_matrix,
    analyze_correlation_pair,
)
from expo_jbm329.services.analysis.diagnostics import AnalysisDiagnostic, analysis_job_scope, analysis_log_component
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison
from expo_jbm329.services.analysis.multivariate_outliers import analyze_multivariate_outliers
from expo_jbm329.services.analysis.outliers import analyze_outlier_column, analyze_outlier_summary
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.paired_comparison import analyze_paired_comparison
from expo_jbm329.services.analysis.pca import analyze_pca
from expo_jbm329.services.analysis.regression import analyze_regression
from expo_jbm329.services.analysis.regression_glm import RegressionModel, analyze_generalized_regression
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.analysis.survival import analyze_cox_regression
from expo_jbm329.services.analysis.timeseries import analyze_time_series

_GLM_EXCEPTION_MESSAGE = "sensitive exception detail"
_COX_EXCEPTION_MESSAGE = "sensitive cox failure"

_ANALYSES = (
    analyze_dataset_overview,
    analyze_descriptive_statistics,
    analyze_group_comparison,
    analyze_chi_square,
    analyze_paired_comparison,
    analyze_correlation_matrix,
    analyze_correlation_pair,
    analyze_regression,
    analyze_generalized_regression,
    analyze_cox_regression,
    analyze_outlier_summary,
    analyze_outlier_column,
    analyze_multivariate_outliers,
    analyze_clustering,
    analyze_pca,
    analyze_time_series,
)


@pytest.mark.parametrize("analyze", _ANALYSES)
def test_analysis_entry_points_accept_keyword_only_correlation_id(analyze):
    corr_id = inspect.signature(analyze).parameters["corr_id"]
    assert corr_id.kind is inspect.Parameter.KEYWORD_ONLY
    assert corr_id.default is None


def test_debug_outcomes_distinguish_unavailable_and_cancelled_without_dataset_text(caplog):
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    frame = pd.DataFrame({
        "private_feature": [4.0, 8.0, 12.0],
        "private_label": ["classified_value", "classified_value", "classified_value"],
    })

    unavailable = analyze_group_comparison(frame, corr_id="operation-unavailable")
    cancelled = analyze_correlation_matrix(
        pd.DataFrame({
            "private_a": [1.0, 2.0, 4.0],
            "private_b": [3.0, 7.0, 9.0],
            "private_c": [2.0, 5.0, 8.0],
        }),
        cancel_cb=lambda: True,
        corr_id="operation-cancelled",
    )

    assert unavailable.error is not None
    assert cancelled is None
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "operation-unavailable" in messages
    assert "outcome=unavailable" in messages
    assert "operation-cancelled" in messages
    assert "outcome=cancelled" in messages
    assert " ms=" in messages
    assert "private_feature" not in messages
    assert "private_label" not in messages
    assert "classified_value" not in messages
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_concurrent_analyses_keep_correlation_ids_isolated(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    barrier = Barrier(2)
    overview_compute = overview._compute_dataset_overview
    statistics_compute = statistics._compute_descriptive_statistics

    def compute_overview(df):
        barrier.wait()
        return overview_compute(df)

    def compute_statistics(df):
        barrier.wait()
        return statistics_compute(df)

    monkeypatch.setattr(overview, "_compute_dataset_overview", compute_overview)
    monkeypatch.setattr(statistics, "_compute_descriptive_statistics", compute_statistics)
    frame = pd.DataFrame({"feature": [1.0, 3.0, 7.0]})

    with ThreadPoolExecutor(max_workers=2) as executor:
        overview_future = executor.submit(analyze_dataset_overview, frame, corr_id="overview-correlation")
        statistics_future = executor.submit(analyze_descriptive_statistics, frame, corr_id="statistics-correlation")
        overview_future.result()
        statistics_future.result()

    records = [record.getMessage() for record in caplog.records]
    assert sum("corr=overview-correlation, operation=overview" in message for message in records) == 1
    assert sum("corr=statistics-correlation, operation=statistics" in message for message in records) == 1
    assert not any(
        ("corr=overview-correlation" in message and "operation=statistics" in message)
        or ("corr=statistics-correlation" in message and "operation=overview" in message)
        for message in records
    )


def test_computation_logs_one_convention_line_without_none_fields(caplog):
    caplog.set_level(logging.DEBUG, logger="applogger.service")

    analyze_dataset_overview(pd.DataFrame({"feature": [1.0, 2.0]}), corr_id="single-line")

    messages = [record.getMessage() for record in caplog.records if record.name == "applogger.service"]
    assert len(messages) == 1
    assert messages[0].startswith(
        "Advanced analysis (Overview): computation finished (corr=single-line, operation=overview, outcome=success,"
    )
    assert messages[0].endswith(")")
    assert "none" not in messages[0].lower()


def test_correlation_pair_logs_rows_used_without_duplicate_item_count(caplog):
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 4.0, 6.0]})

    result = analyze_correlation_pair(frame, "x", "y", corr_id="pair-count")

    assert result.error is None
    messages = [record.getMessage() for record in caplog.records if record.name == "applogger.service"]
    assert len(messages) == 1
    assert "rows_used=3" in messages[0]
    assert "items=" not in messages[0]


@pytest.mark.parametrize(
    ("operation", "section"),
    [
        ("overview", "Overview"),
        ("statistics", "Statistics"),
        ("group_comparison", "Hypothesis Tests"),
        ("chi_square", "Hypothesis Tests"),
        ("paired_comparison", "Hypothesis Tests"),
        ("correlation_matrix", "Correlation"),
        ("correlation_pair", "Correlation"),
        ("regression", "Regression"),
        ("regression_glm", "Regression"),
        ("survival_cox", "Regression"),
        ("outlier_summary", "Outliers"),
        ("outlier_column", "Outliers"),
        ("multivariate_outliers", "Outliers"),
        ("clustering", "Clustering"),
        ("pca", "PCA"),
        ("timeseries", "Time Series"),
    ],
)
@pytest.mark.parametrize("outcome", ["success", "unavailable", "cancelled"])
def test_completion_prefix_covers_every_analysis_operation(caplog, operation, section, outcome):
    caplog.set_level(logging.DEBUG, logger="applogger.service")

    AnalysisDiagnostic(operation, "section-operation", row_count=3, column_count=2).finish(outcome)

    messages = [record.getMessage() for record in caplog.records if record.name == "applogger.service"]
    assert len(messages) == 1
    assert messages[0].startswith(
        f"Advanced analysis ({section}): computation finished (corr=section-operation, operation={operation},"
    )
    assert f"outcome={outcome}" in messages[0]


@pytest.mark.parametrize("category", list(AnalysisCategory))
def test_section_prefix_is_stable_english(category):
    section = "PCA" if category is AnalysisCategory.PCA else category.value.replace("_", " ").title()
    assert analysis_log_component(category) == f"Advanced analysis ({section})"


def test_job_scope_is_restored_after_nested_failure(caplog):
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    with analysis_job_scope("analysis:regression:fit:linear"):
        with pytest.raises(ValueError, match="test failure"):
            with analysis_job_scope("analysis:regression:fit:logistic"):
                raise ValueError("test failure")
        diagnostic = AnalysisDiagnostic("regression", "outer", row_count=3, column_count=2, method="ols")
    diagnostic.finish("success")
    AnalysisDiagnostic("overview", "standalone", row_count=3, column_count=2).finish("success")

    messages = [record.getMessage() for record in caplog.records if record.name == "applogger.service"]
    assert "corr=outer, scope=analysis:regression:fit:linear," in messages[0]
    assert "operation=" not in messages[0]
    assert "method=" not in messages[0]
    assert "corr=standalone, operation=overview," in messages[1]
    assert "scope=" not in messages[1]


def test_concurrent_jobs_keep_distinct_scopes(caplog):
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    barrier = Barrier(2)

    def finish_computation(scope):
        with analysis_job_scope(scope):
            barrier.wait()
            AnalysisDiagnostic("regression", scope, row_count=3, column_count=2).finish("success")

    scopes = ["analysis:regression:fit:linear", "analysis:regression:fit:logistic"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(finish_computation, scopes))

    messages = [record.getMessage() for record in caplog.records if record.name == "applogger.service"]
    assert len(messages) == 2
    for scope in scopes:
        assert sum(f"corr={scope}, scope={scope}," in message for message in messages) == 1


@pytest.mark.parametrize(
    ("scope", "operations", "steps"),
    [
        ("analysis:correlation:matrix:pearson", ("correlation_matrix", "correlation_pair"), ("matrix", "pair")),
        ("analysis:outliers:summary:iqr", ("outlier_summary", "outlier_column"), ("summary", "column")),
    ],
)
@pytest.mark.parametrize("outcome", ["success", "unavailable", "cancelled"])
def test_shared_job_computations_have_distinct_steps(caplog, scope, operations, steps, outcome):
    caplog.set_level(logging.DEBUG, logger="applogger.service")

    with analysis_job_scope(scope):
        for operation in operations:
            AnalysisDiagnostic(operation, "shared-job", row_count=3, column_count=2).finish(outcome)

    messages = [record.getMessage() for record in caplog.records if record.name == "applogger.service"]
    assert len(messages) == 2
    for message, step in zip(messages, steps, strict=True):
        assert f"corr=shared-job, scope={scope}, step={step}, outcome={outcome}," in message
        assert "operation=" not in message
        assert "method=" not in message


def test_computations_nested_in_summary_scope_are_silent(caplog):
    from expo_jbm329.services.analysis.diagnostics import summary_scope

    caplog.set_level(logging.DEBUG, logger="applogger.service")

    with summary_scope() as outermost:
        assert outermost
        with summary_scope() as nested:
            assert not nested
        analyze_dataset_overview(pd.DataFrame({"feature": [1.0, 2.0]}), corr_id="nested")
    analyze_dataset_overview(pd.DataFrame({"feature": [1.0, 2.0]}), corr_id="top-level")

    messages = [record.getMessage() for record in caplog.records if record.name == "applogger.service"]
    assert not any("corr=nested" in message for message in messages)
    assert sum("corr=top-level" in message for message in messages) == 1


def test_glm_fit_warning_contains_reason_and_exception_class_only(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="applogger.service")

    def fail_fit(self, *args, **kwargs):
        raise ValueError(_GLM_EXCEPTION_MESSAGE)

    monkeypatch.setattr(sm.Logit, "fit", fail_fit)
    frame = pd.DataFrame({
        "private_target": ["case", "control"] * 8,
        "private_predictor": np.arange(16, dtype=float),
    })

    result = analyze_generalized_regression(
        frame,
        RegressionModel.LOGISTIC,
        "private_target",
        ["private_predictor"],
        corr_id="glm-operation",
    )

    assert result.error is not None
    warning = next(record for record in caplog.records if record.levelno == logging.WARNING)
    assert warning.name == "applogger.service"
    assert warning.getMessage().startswith("AnalysisService: model fit failed (corr=glm-operation,")
    assert "model=logistic" in warning.getMessage()
    assert "reason=fit_exception" in warning.getMessage()
    assert "exception_class=ValueError" in warning.getMessage()
    assert "sensitive exception detail" not in warning.getMessage()
    assert "private_target" not in warning.getMessage()
    assert "private_predictor" not in warning.getMessage()


def test_cox_fit_warning_contains_reason_and_exception_class_only(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="applogger.service")

    def fail_fit(self, *args, **kwargs):
        raise RuntimeError(_COX_EXCEPTION_MESSAGE)

    monkeypatch.setattr(PHReg, "fit", fail_fit)
    frame = pd.DataFrame({
        "private_duration": np.arange(1.0, 13.0),
        "private_event": [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0],
        "private_predictor": np.linspace(-1.0, 1.0, 12),
    })

    result = analyze_cox_regression(
        frame,
        "private_duration",
        "private_event",
        ["private_predictor"],
        corr_id="cox-operation",
    )

    assert result.error is not None
    warning = next(record for record in caplog.records if record.levelno == logging.WARNING)
    assert warning.name == "applogger.service"
    assert "model=cox" in warning.getMessage()
    assert "reason=fit_exception" in warning.getMessage()
    assert "exception_class=RuntimeError" in warning.getMessage()
    assert "sensitive cox failure" not in warning.getMessage()
    assert "private_duration" not in warning.getMessage()
    assert "private_predictor" not in warning.getMessage()
