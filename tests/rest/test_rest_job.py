from __future__ import annotations

import pandas as pd

from expo_jbm329.services.job_result import JobResult
from expo_jbm329.services.rest.models import RestPaginationConfig, RestRequestConfig
from expo_jbm329.services.rest.rest_job import fetch_rest_dataset


def test_fetch_rest_dataset_cancellation(monkeypatch):
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)
    result = fetch_rest_dataset(cfg, cancel_cb=lambda: True)

    assert isinstance(result, JobResult)
    assert result.cancelled is True


def test_fetch_rest_dataset_success(monkeypatch):
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.fetch_json_pages",
        lambda *args, **kwargs: ([{"items": [{"a": 1}]}], 0.1),
    )
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.normalize_json_to_df",
        lambda payload, response_path=None: pd.DataFrame(payload["items"]),
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
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.normalize_json_to_df",
        lambda payload, response_path=None: pd.DataFrame(payload["items"]),
    )

    result = fetch_rest_dataset(cfg)

    assert result.ok is True
    assert result.data is not None
    assert result.data["a"].tolist() == [1, 2]
