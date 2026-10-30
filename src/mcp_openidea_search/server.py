"""Build the MCP Server, register tools and resource handlers."""
from __future__ import annotations

import json
from typing import Any

from mcp.server import Server
from mcp.types import (
    Resource as MCPResource,
    TextContent,
    Tool,
)

from . import paging
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

_PRESET_BLURB: dict[ResourceType, str] = {
    ResourceType.paper: "research papers (e.g. OpenAlex, arXiv)",
    ResourceType.code: "code repositories (e.g. GitHub, GitLab, Software Heritage)",
    ResourceType.dataset: "datasets (e.g. Zenodo, CKAN, Figshare, Kaggle)",
    ResourceType.model: "ML models (e.g. HuggingFace)",
    ResourceType.hardware: "open hardware designs",
    ResourceType.video: "videos (e.g. YouTube)",
}

_USAGE = (
    " Ask for as many results as the task needs: `max_results` goes up to 500"
    " (default 50). In the default `auto` mode the tool pages through results"
    " for you and stops once they stop being relevant (relevance below"
    " `min_relevance`, default 0.35; set 0 to keep everything), so a large"
    " `max_results` is cheap when only a few results match. Use `mode: \"page\"`"
    " with `page` or `cursor` to fetch one page at a time instead. To restrict"
    " providers, pass `sources` (e.g. [\"arxiv\", \"openalex\"]); call"
    " `list_sources` for the names and packs this server offers. Results are"
    " compact (title, url, year, source, relevance, short description, first"
    " authors); pass `detail: \"full\"` for complete records."
)

_SEARCH_PROPERTIES: dict[str, Any] = {
    "query": {"type": "string", "description": "Search query."},
    "max_results": {
        "type": "integer",
        "default": paging.DEFAULT_MAX_RESULTS,
        "minimum": 1,
        "maximum": paging.MAX_RESULTS_CAP,
        "description": "Most results to return (up to 500). Auto mode may return fewer if relevance runs out.",
    },
    "min_relevance": {
        "type": "number",
        "default": paging.DEFAULT_MIN_RELEVANCE,
        "minimum": 0,
        "maximum": 1,
        "description": "Drop results below this 0..1 relevance and stop paging when a whole page falls below it. 0 disables.",
    },
    "mode": {
        "type": "string",
        "enum": ["auto", "page"],
        "default": "auto",
        "description": "auto: page until max_results or results stop being relevant. page: fetch a single page (use page/cursor).",
    },
    "sources": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Only search these providers, e.g. [\"arxiv\", \"github\"]. See list_sources.",
    },
    "page": {"type": "integer", "minimum": 1, "description": "Page number (page mode)."},
    "cursor": {"type": "string", "description": "next_cursor from a previous response (page mode, or to continue)."},
    "detail": {
        "type": "string",
        "enum": ["compact", "full"],
        "default": "compact",
        "description": "compact: key fields only. full: every field the server returns.",
    },
    "limit": {
        "type": "integer",
        "minimum": 1,
        "maximum": paging.MAX_RESULTS_CAP,
        "description": "Deprecated alias for max_results.",
    },
}

_BASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": _SEARCH_PROPERTIES,
    "required": ["query"],
}

_ALL_SCHEMA: dict[str, Any] = {
    **_BASE_SCHEMA,
    "properties": {
        **_SEARCH_PROPERTIES,
        "types": {
            "type": "array",
            "items": {"type": "string", "enum": [t.value for t in ResourceType]},
            "description": "Only these resource types. Each type is searched in parallel and the results are merged by relevance.",
        },
    },
}

_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

SOURCES_UNSUPPORTED = (
    "This Open Idea server does not provide /api/v1/sources yet, so the source"
    " list is unavailable. Search still works. You can still pass provider names"
    " in `sources` (e.g. openalex, arxiv, github, huggingface, zenodo); results"
    " are filtered to those providers on this side."
)


def _text(payload: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


def _parse_sources(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    cleaned = [str(s).strip() for s in items if str(s).strip()]
    return cleaned or None


def _search_options(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_max = arguments.get("max_results", arguments.get("limit", paging.DEFAULT_MAX_RESULTS))
    max_results = max(1, min(int(raw_max), paging.MAX_RESULTS_CAP))
    min_relevance = float(arguments.get("min_relevance", paging.DEFAULT_MIN_RELEVANCE))
    min_relevance = max(0.0, min(min_relevance, 1.0))
    mode = arguments.get("mode", "auto")
    if mode not in ("auto", "page"):
        raise ValueError("`mode` must be \"auto\" or \"page\".")
    page = arguments.get("page")
    return {
        "max_results": max_results,
        "min_relevance": min_relevance,
        "mode": mode,
        "sources": _parse_sources(arguments.get("sources")),
        "page": int(page) if page is not None else None,
        "cursor": arguments.get("cursor") or None,
    }


def _detail(arguments: dict[str, Any]) -> str:
    detail = arguments.get("detail", "compact")
    if detail not in ("compact", "full"):
        raise ValueError("`detail` must be \"compact\" or \"full\".")
    return detail


async def run_search(
    client: OpenIdeaClient,
    query: str,
    types: list[ResourceType] | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute a search tool call and build its JSON payload."""
    opts = _search_options(arguments)
    detail = _detail(arguments)

    if types and len(types) > 1:
        if opts["cursor"]:
            raise ValueError("`cursor` belongs to a single type; pass one type with it.")
        merged, by_type = await paging.collect_many(client, query, types, **opts)
        trimmed = len(merged) > opts["max_results"]
        merged = merged[: opts["max_results"]]
        return {
            "query": query,
            "total_returned": len(merged),
            "stopped_because": paging.STOP_MAX_RESULTS if trimmed else "per_type",
            "results": [paging.render(s, detail) for s in merged],
            "next_cursor": None,
            "by_type": by_type,
        }

    got = await paging.collect(client, query, type=types[0] if types else None, **opts)
    payload: dict[str, Any] = {
        "query": query,
        "total_returned": len(got.results),
        "stopped_because": got.stopped_because,
        "results": [paging.render(s, detail) for s in got.results],
        "next_cursor": got.next_cursor,
    }
    if got.total_available is not None:
        payload["total_available"] = got.total_available
    return payload


def build_server(client: OpenIdeaClient) -> Server:
    """Build an MCP Server bound to `client`. Caller owns lifecycle."""
    server: Server = Server("openidea-search")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        tools: list[Tool] = []
        for name, rtype in SEARCH_PRESETS.items():
            tools.append(Tool(
                name=name,
                description=f"Search Open Idea for {_PRESET_BLURB[rtype]}." + _USAGE,
                inputSchema=_BASE_SCHEMA,
            ))
        tools.append(Tool(
            name="search_all",
            description=(
                "Search Open Idea across every resource type (papers, code, datasets,"
                " models, hardware, videos). Pass `types` to search several types at"
                " once; they run in parallel and merge by relevance." + _USAGE
            ),
            inputSchema=_ALL_SCHEMA,
        ))
        tools.append(Tool(
            name="list_sources",
            description=(
                "List the providers (sources) this Open Idea server can search, with"
                " the resource types each covers and whether your plan unlocks it,"
                " plus named packs of sources. Use the names in the search tools'"
                " `sources` argument."
            ),
            inputSchema=_EMPTY_SCHEMA,
        ))
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        arguments = arguments or {}
        if name == "list_sources":
            listing = await client.list_sources()
            if listing is None:
                return _text({"supported": False, "message": SOURCES_UNSUPPORTED})
            return _text({"supported": True, **listing.model_dump(mode="json", exclude_none=True)})

        if name not in SEARCH_PRESETS and name != "search_all":
            raise ValueError(f"Unknown tool: {name}")
        query = arguments.get("query", "")
        if not query:
            raise ValueError("`query` is required.")

        if name in SEARCH_PRESETS:
            types: list[ResourceType] | None = [SEARCH_PRESETS[name]]
        else:
            types = []
            for t in arguments.get("types") or []:
                try:
                    rtype = ResourceType(t)
                except ValueError:
                    continue
                if rtype not in types:
                    types.append(rtype)
        return _text(await run_search(client, query, types or None, arguments))

    @server.list_resources()
    async def _list_resources() -> list[MCPResource]:
        # Resources are addressable but not enumerable.
        return []

    @server.read_resource()
    async def _read_resource(uri: str) -> str:
        uri = str(uri)
        if not uri.startswith(URI_PREFIX):
            raise ValueError(f"URI must start with {URI_PREFIX!r}; got {uri!r}")
        resource_id = uri[len(URI_PREFIX):]
        resource = await client.get_resource(resource_id)
        if resource is None:
            raise ValueError(f"No resource found for {uri}")
        return resource.model_dump_json(exclude_none=True)

    return server
