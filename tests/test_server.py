"""Tests for the MCP server module.

Tool calls go through the registered request handlers directly (no stdio
pair). Transport behavior is verified via the MCP Inspector in the README.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from mcp_openidea_search.client import OpenIdeaClient
from mcp_openidea_search.models import ResourceType
from mcp_openidea_search.server import SEARCH_PRESETS, URI_PREFIX, build_server


def test_search_presets_cover_all_resource_types_except_all():
    assert set(SEARCH_PRESETS.values()) == set(ResourceType)


def test_uri_prefix_is_openidea_scheme():
    assert URI_PREFIX == "openidea://"


@pytest.mark.asyncio
async def test_build_server_returns_named_server():
    async with OpenIdeaClient(base_url="https://example.test", api_key="oi_live_test") as client:
        server = build_server(client)
    assert server.name == "openidea-search"


async def _call(server, name, arguments):
    handler = server.request_handlers[CallToolRequest]
    result = await handler(CallToolRequest(
        method="tools/call", params=CallToolRequestParams(name=name, arguments=arguments)
    ))
    return result.root


async def _tools(server):
    result = await server.request_handlers[ListToolsRequest](ListToolsRequest(method="tools/list"))
    return {t.name: t for t in result.root.tools}


@pytest.mark.asyncio
async def test_tool_surface_includes_list_sources_and_paging_inputs():
    async with OpenIdeaClient(base_url="https://example.test", api_key="oi_live_test") as client:
        tools = await _tools(build_server(client))
    assert "list_sources" in tools
    props = tools["search_papers"].inputSchema["properties"]
    assert props["max_results"]["maximum"] == 500
    assert {"min_relevance", "mode", "sources", "page", "cursor", "detail"} <= set(props)
    assert "500" in tools["search_all"].description


@pytest.mark.asyncio
@respx.mock
async def test_list_sources_tool_on_old_server_explains():
    respx.get("https://example.test/api/v1/sources").mock(return_value=httpx.Response(404))
    async with OpenIdeaClient(base_url="https://example.test", api_key="oi_live_test") as client:
        result = await _call(build_server(client), "list_sources", {})
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["supported"] is False
    assert "does not provide /api/v1/sources" in payload["message"]


@pytest.mark.asyncio
@respx.mock
async def test_search_tool_end_to_end():
    respx.get("https://example.test/api/v1/search").mock(return_value=httpx.Response(200, json={
        "items": [{"id": "x:1", "type": "paper", "title": "T", "source": "brand_new",
                   "url": "https://x", "relevance": 0.8}],
    }))
    async with OpenIdeaClient(base_url="https://example.test", api_key="oi_live_test") as client:
        result = await _call(build_server(client), "search_papers", {"query": "q"})
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["results"][0]["source"] == "brand_new"
    assert payload["stopped_because"] == "no_more_pages"
