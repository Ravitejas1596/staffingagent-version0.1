import json
from pathlib import Path

import httpx
import pytest

from src.api import gateway


def test_extract_list_payload_handles_list_and_dict():
    assert gateway._extract_list_payload([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert gateway._extract_list_payload({"results": [{"id": "1"}]}) == [{"id": "1"}]
    assert gateway._extract_list_payload({"rows": [{"id": "x"}]}, preferred_keys=["rows"]) == [
        {"id": "x"}
    ]
    assert gateway._extract_list_payload({"unexpected": "shape"}) == []


def test_read_records_file_reads_json_array(tmp_path: Path):
    fixture = tmp_path / "records.json"
    fixture.write_text(json.dumps([{"id": "x"}, {"id": "y"}]), encoding="utf-8")
    rows = gateway._read_records_file(str(fixture))
    assert rows == [{"id": "x"}, {"id": "y"}]


@pytest.mark.asyncio
async def test_nbrain_query_parses_results(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NBRAIN_API_URL", "https://nbrain.example.com")
    monkeypatch.setenv("NBRAIN_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/query"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"results": [{"chunk": "alpha"}]})

    transport = httpx.MockTransport(handler)

    real_async_client = httpx.AsyncClient

    class MockClient:
        def __init__(self, **kwargs):
            self.client = real_async_client(transport=transport, **kwargs)

        async def __aenter__(self):
            await self.client.__aenter__()
            return self.client

        async def __aexit__(self, exc_type, exc, tb):
            await self.client.__aexit__(exc_type, exc, tb)

    monkeypatch.setattr(gateway.httpx, "AsyncClient", MockClient)
    rows = await gateway.nbrain_query("default", "open invoices")
    assert rows == [{"chunk": "alpha"}]


@pytest.mark.asyncio
async def test_bullhorn_rest_uses_static_bearer_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BULLHORN_REST_URL", "https://rest.example.com")
    monkeypatch.setenv("BULLHORN_BEARER_TOKEN", "bh-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/query/Placement"
        assert request.headers["authorization"] == "Bearer bh-token"
        return httpx.Response(200, json={"data": [{"id": 123}]})

    transport = httpx.MockTransport(handler)

    real_async_client = httpx.AsyncClient

    class MockClient:
        def __init__(self, **kwargs):
            self.client = real_async_client(transport=transport, **kwargs)

        async def __aenter__(self):
            await self.client.__aenter__()
            return self.client

        async def __aexit__(self, exc_type, exc, tb):
            await self.client.__aexit__(exc_type, exc, tb)

    monkeypatch.setattr(gateway.httpx, "AsyncClient", MockClient)
    payload = await gateway.bullhorn_rest("default", "GET", "/query/Placement")
    assert payload == {"data": [{"id": 123}]}
