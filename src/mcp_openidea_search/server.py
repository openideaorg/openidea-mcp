"""Build the MCP Server, register tools and resource handlers."""
from __future__ import annotations

import json

from mcp.server import Server
from mcp.types import (
    Resource as MCPResource,
    TextContent,
    Tool,
)

from .client import OpenIdeaClient
from .models import ResourceType

URI_PREFIX = "openidea://"

SEARCH_PRESETS: dict[str, ResourceType] = {
    "search_papers": ResourceType.paper,
    "search_code": ResourceType.code,
    "search_datasets": ResourceType.dataset,
    "search_models": ResourceType.model,
    "search_hardware": ResourceType.hardware,
    "search_videos": ResourceType.video,
}

_BASE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query."},
        "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
    },
    "required": ["query"],
}

_ALL_SCHEMA = {
    **_BASE_SCHEMA,
    "properties": {
        **_BASE_SCHEMA["properties"],
        "types": {
            "type": "array",
            "items": {"type": "string", "enum": [t.value for t in ResourceType]},
            "description": "Optional filter — return only these resource types.",
        },
    },
}


def build_server(client: OpenIdeaClient) -> Server:
    """Build an MCP Server bound to `client`. Caller owns lifecycle."""
    server: Server = Server("openidea-search")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        tools: list[Tool] = []
        for name, rtype in SEARCH_PRESETS.items():
            tools.append(Tool(
                name=name,
                description=f"Search Open Idea for {rtype.value} resources.",
                inputSchema=_BASE_SCHEMA,
            ))
        tools.append(Tool(
            name="search_all",
            description="Search Open Idea across all providers (papers, code, datasets, models, hardware, videos).",
            inputSchema=_ALL_SCHEMA,
        ))
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        query = arguments.get("query", "")
        if not query:
            raise ValueError("`query` is required.")
        limit = int(arguments.get("limit", 20))

        if name in SEARCH_PRESETS:
            response = await client.search(query, type=SEARCH_PRESETS[name], limit=limit)
            payload = response.model_dump(mode="json", exclude_none=True)
            return [TextContent(type="text", text=json.dumps(payload))]

        if name == "search_all":
            requested_types = arguments.get("types") or []
            if not requested_types:
                response = await client.search(query, limit=limit)
                payload = response.model_dump(mode="json", exclude_none=True)
                return [TextContent(type="text", text=json.dumps(payload))]

            # Fan out one request per type filter, merge by id.
            seen: set[str] = set()
            merged = []
            for t in requested_types:
                try:
                    rtype = ResourceType(t)
                except ValueError:
                    continue
                sub = await client.search(query, type=rtype, limit=limit)
                for r in sub.results:
                    if r.id in seen:
                        continue
                    seen.add(r.id)
                    merged.append(r)
            payload = {
                "results": [r.model_dump(mode="json", exclude_none=True) for r in merged],
                "total": len(merged),
            }
            return [TextContent(type="text", text=json.dumps(payload))]

        raise ValueError(f"Unknown tool: {name}")

    @server.list_resources()
    async def _list_resources() -> list[MCPResource]:
        # Resources are addressable but not enumerable.
        return []

    @server.read_resource()
    async def _read_resource(uri: str) -> str:
        if not uri.startswith(URI_PREFIX):
            raise ValueError(f"URI must start with {URI_PREFIX!r}; got {uri!r}")
        resource_id = uri[len(URI_PREFIX):]
        resource = await client.get_resource(resource_id)
        if resource is None:
            raise ValueError(f"No resource found for {uri}")
        return resource.model_dump_json(exclude_none=True)

    return server
