from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.job_result import JobResult
from expo_jbm329.services.rest.models import RestPaginationConfig, RestRequestConfig
from expo_jbm329.services.rest.rest_job import fetch_rest_dataset


def test_fetch_rest_dataset_cancellation(monkeypatch):
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)
    result = fetch_rest_dataset(cfg, cancel_cb=lambda: True)

    assert isinstance(result, JobResult)
    assert result.cancelled is True


def test_fetch_rest_dataset_success(monkeypatch):
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None, response_path="items")
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.fetch_json_pages",
        lambda *args, **kwargs: ([{"items": [{"a": 1}]}], 0.1),
    )

    result = fetch_rest_dataset(cfg)

    assert result.ok is True
    assert isinstance(result.data, pd.DataFrame)
    assert list(result.data.columns) == ["a"]


def test_fetch_rest_dataset_accumulates_page_number_payloads(monkeypatch):
    cfg = RestRequestConfig(
        name="Example",
        url="https://example.com",
        json_body=None,
        response_path="items",
        pagination=RestPaginationConfig(
            type="page_number",
            page_param="page",
            start_page=1,
            max_pages=3,
        ),
    )
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.fetch_json_pages",
        lambda *args, **kwargs: (
            [
                {"items": [{"a": 1}]},
                {"items": [{"a": 2}]},
            ],
            0.2,
        ),
    )

    result = fetch_rest_dataset(cfg)

    assert result.ok is True
    assert result.data is not None
    assert result.data["a"].tolist() == [1, 2]


def test_rest_job_preserves_exact_values_across_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = RestRequestConfig(name="Example", url="https://example.com", response_path="items", json_body=None)
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.fetch_json_pages",
        lambda *args, **kwargs: (
            [{"items": [{"value": 2**53 + 1, "flag": True}]}, {"items": [{"value": None, "flag": None}]}],
            0.2,
        ),
    )
    result = fetch_rest_dataset(cfg, corr_id="nullable-rest")
    assert result.ok and not result.cancelled
    assert result.corr_id == "nullable-rest"
    assert result.data.dtypes.astype(str).tolist() == ["Int64", "boolean"]
    assert result.data["value"].iloc[0] == 2**53 + 1


def test_rest_job_cancellation_during_normalization_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.fetch_json_pages",
        lambda *args, **kwargs: ([[{"value": 1}, {"value": None}]], 0.1),
    )
    checks = iter([False] * 5)
    result = fetch_rest_dataset(cfg, cancel_cb=lambda: next(checks, True), corr_id="cancel")
    assert result.cancelled and not result.ok
    assert result.data is None
    assert result.error is None
    assert result.corr_id == "cancel"


@pytest.mark.parametrize("payloads", [[], [{"missing": []}]])
def test_rest_job_normalization_errors_remain_explicit(monkeypatch: pytest.MonkeyPatch, payloads: list[object]) -> None:
    cfg = RestRequestConfig(name="Example", url="https://example.com", response_path="items", json_body=None)
    monkeypatch.setattr("expo_jbm329.services.rest.rest_job.fetch_json_pages", lambda *args, **kwargs: (payloads, 0.1))
    result = fetch_rest_dataset(cfg)
    assert not result.ok and not result.cancelled
    assert result.error
