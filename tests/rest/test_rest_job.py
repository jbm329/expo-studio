from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from expo_jbm329.services.job_result import JobResult
from expo_jbm329.services.rest.models import RestRequestConfig
from expo_jbm329.services.rest.rest_job import fetch_rest_dataset


def test_fetch_rest_dataset_cancellation(monkeypatch):
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)
    result = fetch_rest_dataset(cfg, cancel_cb=lambda: True)

    assert isinstance(result, JobResult)
    assert result.cancelled is True


def test_fetch_rest_dataset_success(monkeypatch):
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.fetch_json",
        lambda *args, **kwargs: ({"items": [{"a": 1}]}, 0.1),
    )
    monkeypatch.setattr(
        "expo_jbm329.services.rest.rest_job.normalize_json_to_df",
        lambda payload, response_path=None: pd.DataFrame(payload["items"]),
    )

    result = fetch_rest_dataset(cfg)

    assert result.ok is True
    assert isinstance(result.data, pd.DataFrame)
    assert list(result.data.columns) == ["a"]

