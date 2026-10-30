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
async def test_search_maps_items_to_results():
    # The live API returns hits under `items` alongside an empty `results`.
    respx.get(f"{BASE}/api/v1/search").mock(
        return_value=httpx.Response(200, json={
            "results": [],
            "total": 2,
            "items": [_fake_resource("openalex:W1"), _fake_resource("openalex:W2")],
        })
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        resp = await client.search("transformers", type=ResourceType.paper)
    assert [r.id for r in resp.results] == ["openalex:W1", "openalex:W2"]
    dumped = resp.model_dump(mode="json", exclude_none=True)
    assert len(dumped["results"]) == 2
    assert "items" not in dumped  # folded in, not leaked back out


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


@pytest.fixture
def no_sleep(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("mcp_openidea_search.client.asyncio.sleep", fake_sleep)
    return slept


@pytest.mark.asyncio
@respx.mock
async def test_429_honors_retry_after_capped(no_sleep):
    route = respx.get(f"{BASE}/api/v1/search").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "60"}),
            httpx.Response(200, json={"results": [_fake_resource()], "total": 1}),
        ]
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        resp = await client.search("x")
    assert route.call_count == 2
    assert no_sleep == [5.0]
    assert resp.total == 1


@pytest.mark.asyncio
@respx.mock
async def test_429_twice_raises(no_sleep):
    respx.get(f"{BASE}/api/v1/search").mock(return_value=httpx.Response(429))
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.search("x")


@pytest.mark.asyncio
@respx.mock
async def test_5xx_retries_once(no_sleep):
    route = respx.get(f"{BASE}/api/v1/search").mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json={"results": [], "total": 0})]
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        await client.search("x")
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_connect_error_retries_once(no_sleep):
    route = respx.get(f"{BASE}/api/v1/search").mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={"results": []})]
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        await client.search("x")
    assert route.call_count == 2


def test_timeout_default_and_env(monkeypatch):
    monkeypatch.delenv("OPENIDEA_TIMEOUT", raising=False)
    assert OpenIdeaClient(base_url=BASE, api_key=KEY).timeout == 30.0
    monkeypatch.setenv("OPENIDEA_TIMEOUT", "45")
    assert OpenIdeaClient(base_url=BASE, api_key=KEY).timeout == 45.0


@pytest.mark.asyncio
@respx.mock
async def test_search_sends_min_relevance_and_sources():
    route = respx.get(f"{BASE}/api/v1/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        await client.search("x", min_relevance=0.5, sources=["arxiv", " github "])
    params = route.calls.last.request.url.params
    assert params["minRelevance"] == "0.5"
    assert params["sources"] == "arxiv,github"


@pytest.mark.asyncio
@respx.mock
async def test_search_omits_new_params_by_default():
    route = respx.get(f"{BASE}/api/v1/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        await client.search("x")
    params = route.calls.last.request.url.params
    assert "minRelevance" not in params and "sources" not in params


@pytest.mark.asyncio
@respx.mock
async def test_list_sources_parses():
    respx.get(f"{BASE}/api/v1/sources").mock(return_value=httpx.Response(200, json={
        "sources": [{"name": "arxiv", "label": "arXiv", "pillar": "research", "types": ["paper"],
                     "tier": "free", "unlocked": True, "configured": True}],
        "packs": [{"id": "ml", "label": "ML", "description": "ML stack", "sources": ["arxiv"]}],
    }))
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        listing = await client.list_sources()
    assert listing is not None
    assert listing.sources[0].name == "arxiv"
    assert listing.packs[0].sources == ["arxiv"]


@pytest.mark.asyncio
@respx.mock
async def test_list_sources_404_returns_none():
    respx.get(f"{BASE}/api/v1/sources").mock(return_value=httpx.Response(404))
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        assert await client.list_sources() is None


@pytest.mark.asyncio
@respx.mock
async def test_unknown_provider_and_relevance_parse():
    body = {**_fake_resource(), "source": "some_new_provider", "relevance": 0.42}
    respx.get(f"{BASE}/api/v1/search").mock(
        return_value=httpx.Response(200, json={"items": [body], "total": 1})
    )
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as client:
        resp = await client.search("x")
    assert resp.results[0].source == "some_new_provider"
    assert resp.results[0].relevance == 0.42
