"""Tests for the MCP server module.

We can't easily round-trip through the MCP SDK's transport in unit tests without
a full client+server stdio pair, so these tests cover:
  1. build_server() returns a usable Server with the expected name.
  2. The SEARCH_PRESETS dict matches the documented tool surface.
  3. The URI prefix is what callers expect.
End-to-end transport behavior is verified via the MCP Inspector in the README.
"""
from __future__ import annotations

import pytest

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
