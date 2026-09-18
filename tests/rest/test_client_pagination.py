from __future__ import annotations

from expo_jbm329.services.rest.client import fetch_json_pages
from expo_jbm329.services.rest.models import RestPaginationConfig, RestRequestConfig


def test_fetch_json_pages_uses_page_number_parameters(monkeypatch):
    seen_pages: list[dict[str, str]] = []

    def fake_fetch_json(config, **kwargs):
        seen_pages.append(dict(config.query_params))
        page = int(config.query_params["page"])
        if page <= 2:
            return {"items": [{"page": page}]}, 0.1
        return {"items": []}, 0.1

    monkeypatch.setattr(
        "expo_jbm329.services.rest.client.fetch_json",
        fake_fetch_json,
    )

    payloads, elapsed = fetch_json_pages(
        RestRequestConfig(
            name="Example",
            url="https://example.com",
            json_body=None,
            query_params={"base": "x"},
            pagination=RestPaginationConfig(
                type="page_number",
                page_param="page",
                start_page=1,
                page_size_param="limit",
                page_size=50,
                max_pages=5,
            ),
        )
    )

    assert [params["page"] for params in seen_pages] == ["1", "2", "3"]
    assert all(params["limit"] == "50" for params in seen_pages)
    assert all(params["base"] == "x" for params in seen_pages)
    assert len(payloads) == 3
    assert elapsed > 0


def test_fetch_json_pages_stops_on_cancellation(monkeypatch):
    call_count = 0

    def fake_fetch_json(config, **kwargs):
        return {"items": [{"page": 1}]}, 0.1

    def cancel_cb() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 1

    monkeypatch.setattr(
        "expo_jbm329.services.rest.client.fetch_json",
        fake_fetch_json,
    )

    try:
        fetch_json_pages(
            RestRequestConfig(
                name="Example",
                url="https://example.com",
                json_body=None,
                pagination=RestPaginationConfig(
                    type="page_number",
                    page_param="page",
                    start_page=1,
                    max_pages=3,
                ),
            ),
            cancel_cb=cancel_cb,
        )
    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        assert str(exc) == "Request cancelled"
    else:
        raise AssertionError("Expected cancellation")
