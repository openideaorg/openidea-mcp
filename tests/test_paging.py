"""Tests for relevance-aware paging, multi-type merge and the tool payloads."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from mcp_openidea_search import paging
from mcp_openidea_search.client import OpenIdeaClient
from mcp_openidea_search.models import ResourceType
from mcp_openidea_search.server import run_search

BASE = "https://api.example.test"
KEY = "oi_live_testkey"
SEARCH = f"{BASE}/api/v1/search"


def res(rid: str, *, score=None, relevance=None, type="paper", source="openalex", **extra) -> dict:
    body = {"id": rid, "type": type, "title": f"T {rid}", "source": source, "url": f"https://x/{rid}"}
    if score is not None:
        body["score"] = score
    if relevance is not None:
        body["relevance"] = relevance
    body.update(extra)
    return body


def page(items, *, cursor=None, total=1000) -> httpx.Response:
    return httpx.Response(200, json={"items": items, "total": total, "nextCursor": cursor,
                                     "hasMore": cursor is not None})


@pytest.fixture
async def client():
    async with OpenIdeaClient(base_url=BASE, api_key=KEY) as c:
        yield c


@respx.mock
async def test_auto_follows_cursor_until_no_more_pages(client):
    route = respx.get(SEARCH).mock(side_effect=[
        page([res("a", relevance=0.9), res("b", relevance=0.8)], cursor="c2"),
        page([res("c", relevance=0.7)], cursor=None),
    ])
    got = await paging.collect(client, "q", max_results=50)
    assert [s.resource.id for s in got.results] == ["a", "b", "c"]
    assert got.stopped_because == paging.STOP_EXHAUSTED
    assert route.call_count == 2
    assert route.calls[1].request.url.params["cursor"] == "c2"
    assert route.calls[0].request.url.params["limit"] == "50"
    # 50 asked, 2 received: second page asks only for what is left.
    assert route.calls[1].request.url.params["limit"] == "48"


@respx.mock
async def test_auto_stops_at_max_results(client):
    route = respx.get(SEARCH).mock(side_effect=[
        page([res(f"a{i}", relevance=0.9) for i in range(100)], cursor="c2"),
        page([res(f"b{i}", relevance=0.9) for i in range(100)], cursor="c3"),
    ])
    got = await paging.collect(client, "q", max_results=150)
    assert len(got.results) == 150
    assert got.stopped_because == paging.STOP_MAX_RESULTS
    assert route.calls[0].request.url.params["limit"] == "100"
    assert route.calls[1].request.url.params["limit"] == "50"
    assert got.next_cursor == "c3"


@respx.mock
async def test_auto_stops_when_whole_page_below_threshold(client):
    route = respx.get(SEARCH).mock(side_effect=[
        page([res("a", relevance=0.9), res("b", relevance=0.2)], cursor="c2"),
        page([res("c", relevance=0.3), res("d", relevance=0.1)], cursor="c3"),
        page([res("e", relevance=0.9)], cursor=None),
    ])
    got = await paging.collect(client, "q", max_results=50, min_relevance=0.35)
    # b dropped individually; page 2 entirely below 0.35 stops paging.
    assert [s.resource.id for s in got.results] == ["a"]
    assert got.stopped_because == paging.STOP_BELOW_THRESHOLD
    assert route.call_count == 2
    assert route.calls[0].request.url.params["minRelevance"] == "0.35"


@respx.mock
async def test_min_relevance_zero_disables_filter(client):
    route = respx.get(SEARCH).mock(side_effect=[
        page([res("a", relevance=0.05)], cursor=None),
    ])
    got = await paging.collect(client, "q", min_relevance=0)
    assert [s.resource.id for s in got.results] == ["a"]
    assert "minRelevance" not in route.calls[0].request.url.params


@respx.mock
async def test_fallback_relevance_from_score_on_old_server(client):
    # Old server: no `relevance`, scores on an arbitrary scale.
    respx.get(SEARCH).mock(side_effect=[
        page([res("a", score=40.0), res("b", score=20.0), res("c", score=8.0)], cursor="c2"),
        page([res("d", score=4.0)], cursor=None),
    ])
    got = await paging.collect(client, "q", min_relevance=0.35)
    rel = {s.resource.id: s.relevance for s in got.results}
    assert rel == {"a": 1.0, "b": 0.5}
    # page 2: 4/40 = 0.1, whole page below threshold
    assert got.stopped_because == paging.STOP_BELOW_THRESHOLD


@respx.mock
async def test_page_mode_single_request(client):
    route = respx.get(SEARCH).mock(return_value=page([res("a", relevance=0.9)], cursor="c9"))
    got = await paging.collect(client, "q", mode="page", page=3, max_results=20)
    assert route.call_count == 1
    assert route.calls[0].request.url.params["page"] == "3"
    assert got.stopped_because == paging.STOP_SINGLE_PAGE
    assert got.next_cursor == "c9"


@respx.mock
async def test_old_server_without_cursor_steps_page_number(client):
    route = respx.get(SEARCH).mock(side_effect=[
        httpx.Response(200, json={"results": [res("a", score=1.0)], "page": 1, "hasMore": True}),
        httpx.Response(200, json={"results": [res("b", score=0.9)], "page": 2, "hasMore": False}),
    ])
    got = await paging.collect(client, "q")
    assert [s.resource.id for s in got.results] == ["a", "b"]
    assert route.calls[1].request.url.params["page"] == "2"


@respx.mock
async def test_sources_sent_and_applied_locally(client):
    # An old server ignores `sources`; the filter still holds.
    route = respx.get(SEARCH).mock(return_value=page([
        res("a", relevance=0.9, source="arxiv"),
        res("b", relevance=0.9, source="github"),
    ]))
    got = await paging.collect(client, "q", sources=["arxiv", "openalex"])
    assert route.calls[0].request.url.params["sources"] == "arxiv,openalex"
    assert [s.resource.id for s in got.results] == ["a"]


@respx.mock
async def test_multi_type_merge_sorted_and_deduped(client):
    def by_type(request: httpx.Request) -> httpx.Response:
        t = request.url.params["type"]
        if t == "paper":
            return page([res("p1", relevance=0.6), res("shared", relevance=0.4)])
        return page([
            res("c1", relevance=0.95, type="code", source="github"),
            res("shared", relevance=0.7, type="code", source="github"),
        ])

    route = respx.get(SEARCH).mock(side_effect=by_type)
    payload = await run_search(client, "q", [ResourceType.paper, ResourceType.code], {"query": "q"})
    assert route.call_count == 2
    assert [r["id"] for r in payload["results"]] == ["c1", "shared", "p1"]
    assert [r["relevance"] for r in payload["results"]] == [0.95, 0.7, 0.6]
    assert set(payload["by_type"]) == {"paper", "code"}


@respx.mock
async def test_compact_output_shape(client):
    long = "word " * 100
    respx.get(SEARCH).mock(return_value=page([
        res("a", relevance=0.876, description=long, authors=["A", "B", "C", "D"], year=2024,
            tags=["x"], meta={"k": 1}),
    ]))
    payload = await run_search(client, "q", [ResourceType.paper], {"query": "q"})
    assert set(payload) >= {"query", "total_returned", "stopped_because", "results", "next_cursor"}
    item = payload["results"][0]
    assert item["relevance"] == 0.88
    assert item["authors"] == ["A", "B", "C"]
    assert len(item["description"]) <= 200
    assert "meta" not in item and "tags" not in item
    json.dumps(payload)


@respx.mock
async def test_full_detail_keeps_all_fields(client):
    respx.get(SEARCH).mock(return_value=page([res("a", relevance=0.9, meta={"k": 1})]))
    payload = await run_search(client, "q", None, {"query": "q", "detail": "full"})
    assert payload["results"][0]["meta"] == {"k": 1}


@respx.mock
async def test_legacy_limit_maps_to_max_results(client):
    route = respx.get(SEARCH).mock(return_value=page([res("a", relevance=0.9)]))
    await run_search(client, "q", None, {"query": "q", "limit": 7})
    assert route.calls[0].request.url.params["limit"] == "7"
