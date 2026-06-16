"""Tests for OpenIdeaClient — mocked transport via respx."""
from __future__ import annotations

import httpx
import pytest
import respx

from mcp_openidea_search.client import OpenIdeaAuthError, OpenIdeaClient
from mcp_openidea_search.models import ResourceType


BASE = "https://api.example.test"
KEY = "oi_live_testkey"


def _fake_resource(rid: str = "openalex:W1") -> dict:
    return {
        "id": rid,
        "type": "paper",
        "title": "Sample paper",
        "source": "openalex",
        "url": "https://openalex.org/W1",
        "authors": ["Alice"],
        "year": 2024,
    }


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_resources():
    route = respx.get(f"{BASE}/api/v1/search").mock(
        return_value=httpx.Response(200, json={"results": [_fake_resource()], "total": 1})
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        resp = await client.search("transformers", type=ResourceType.paper, limit=5)
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert sent.url.params["q"] == "transformers"
    assert sent.url.params["type"] == "paper"
    assert sent.url.params["limit"] == "5"
    assert len(resp.results) == 1
    assert resp.results[0].id == "openalex:W1"
    assert resp.results[0].type == ResourceType.paper


@pytest.mark.asyncio
@respx.mock
async def test_get_resource_returns_resource():
    rid = "openalex:W42"
    respx.get(f"{BASE}/api/v1/resources/{rid}").mock(
        return_value=httpx.Response(200, json=_fake_resource(rid))
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        r = await client.get_resource(rid)
    assert r is not None
    assert r.id == rid


@pytest.mark.asyncio
@respx.mock
async def test_get_resource_404_returns_none():
    respx.get(f"{BASE}/api/v1/resources/missing").mock(
        return_value=httpx.Response(404, json={"error": "not_found"})
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        r = await client.get_resource("missing")
    assert r is None


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_error():
    respx.get(f"{BASE}/api/v1/search").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        with pytest.raises(OpenIdeaAuthError):
            await client.search("x")


@pytest.mark.asyncio
@respx.mock
async def test_429_retries_once(monkeypatch):
    # First call → 429, second call → 200
    route = respx.get(f"{BASE}/api/v1/search").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "rate_limited"}),
            httpx.Response(200, json={"results": [], "total": 0}),
        ]
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        resp = await client.search("x")
    assert route.call_count == 2
    assert resp.total == 0
