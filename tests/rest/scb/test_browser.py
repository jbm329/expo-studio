from __future__ import annotations

from typing import Any, Self

from expo_jbm329.services.rest.scb.browser import (
    fetch_scb_table_metadata,
    fetch_scb_tables,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict[str, object] | list[dict[str, object]]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def get(self, url: str, params: dict[str, object] | None = None) -> _FakeResponse:
        self.calls.append((url, params))
        if isinstance(self.payload, list):
            page_number = int((params or {}).get("pageNumber", 1))
            return _FakeResponse(self.payload[page_number - 1])
        return _FakeResponse(self.payload)


def test_fetch_scb_tables_parses_index(monkeypatch: Any) -> None:
    payload = [
        {
            "tables": [
                {
                    "id": "TAB4707",
                    "label": "Antal anställda",
                    "description": "Example",
                    "firstPeriod": "2015M04",
                    "lastPeriod": "2026M06",
                }
            ],
            "page": {"pageNumber": 1, "totalPages": 2},
        },
        {
            "tables": [
                {
                    "id": "TAB4714",
                    "label": "Antal anställda per näringsgren",
                    "description": "",
                    "firstPeriod": "2015M04",
                    "lastPeriod": "2026M06",
                }
            ],
            "page": {"pageNumber": 2, "totalPages": 2},
        },
    ]
    fake_client = _FakeClient(payload)

    monkeypatch.setattr(
        "expo_jbm329.services.rest.scb.browser.httpx.Client",
        lambda *args, **kwargs: fake_client,
    )

    tables = fetch_scb_tables(lang="sv")

    assert len(tables) == 2
    assert tables[0].table_id == "TAB4707"
    assert tables[0].label == "Antal anställda"
    assert tables[1].table_id == "TAB4714"
    assert fake_client.calls[0][1] == {"lang": "sv", "pageNumber": 1, "pageSize": 200}
    assert fake_client.calls[1][1] == {"lang": "sv", "pageNumber": 2, "pageSize": 200}


def test_fetch_scb_table_metadata_parses_dimensions(monkeypatch):
    payload = {
        "label": "Example table",
        "description": "Example metadata",
        "dimension": {
            "Sektor": {
                "label": "sektor",
                "category": {
                    "label": {
                        "010": "samtliga sektorer",
                        "030": "näringslivet",
                    }
                },
            },
            "Kon": {
                "label": "kön",
                "category": {
                    "label": {
                        "1": "män",
                        "2": "kvinnor",
                    }
                },
            },
        },
    }

    monkeypatch.setattr(
        "expo_jbm329.services.rest.scb.browser.httpx.Client",
        lambda *args, **kwargs: _FakeClient(payload),
    )

    metadata = fetch_scb_table_metadata(table_id="TAB4707", lang="sv")

    assert metadata.label == "Example table"
    assert metadata.variables[0].name == "Sektor"
    assert metadata.variables[0].display_name == "sektor"
    assert metadata.variables[0].values[0].code == "010"
    assert metadata.variables[0].values[0].label == "samtliga sektorer"
    assert metadata.variables[1].name == "Kon"


def test_fetch_scb_tables_passes_selected_language(monkeypatch):
    payload = {
        "tables": [
            {
                "id": "TAB4707",
                "label": "Employees",
            }
        ],
        "page": {"pageNumber": 1, "totalPages": 1},
    }
    fake_client = _FakeClient(payload)

    monkeypatch.setattr(
        "expo_jbm329.services.rest.scb.browser.httpx.Client",
        lambda *args, **kwargs: fake_client,
    )

    fetch_scb_tables(lang="en")

    assert fake_client.calls[0][1] == {"lang": "en", "pageNumber": 1, "pageSize": 200}
