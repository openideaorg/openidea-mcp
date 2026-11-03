"""Build the MCP Server, register tools and resource handlers."""
from __future__ import annotations

import asyncio
import json
import re

from mcp.server import Server
from mcp.types import (
    Resource as MCPResource,
    TextContent,
    Tool,
)

from .client import OpenIdeaClient
from .models import Resource, ResourceType

URI_PREFIX = "openidea://"

SEARCH_PRESETS: dict[str, ResourceType] = {
    "search_papers": ResourceType.paper,
    "search_code": ResourceType.code,
    "search_datasets": ResourceType.dataset,
    "search_models": ResourceType.model,
    "search_hardware": ResourceType.hardware,
    "search_videos": ResourceType.video,
}

CITATION_STYLES = ("markdown", "apa", "bibtex")

# Muse is the primary client for this server; Lab handoffs carry this hint.
SUGGESTED_MODEL = "muse-spark-1.3-contributor"

_BASE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query."},
        "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        "page": {
            "type": "integer",
            "default": 1,
            "minimum": 1,
            "description": "Result page for deep literature sweeps (page 1 omits the param).",
        },
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

_RESOURCE_REF_SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {
            "type": "string",
            "description": "Resource id (e.g. 'openalex:W2741809807') or openidea:// URI.",
        },
    },
    "required": ["ref"],
}

_CITATION_SCHEMA = {
    "type": "object",
    "properties": {
        **_RESOURCE_REF_SCHEMA["properties"],
        "style": {
            "type": "string",
            "enum": list(CITATION_STYLES),
            "default": "markdown",
            "description": "Citation format for paper/lab-note use.",
        },
    },
    "required": ["ref"],
}

_RESOLVE_SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {
            "type": "string",
            "description": "DOI, arXiv id, OpenAlex id, title, or openidea:// URI to resolve to the canonical paper record.",
        },
        "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
    },
    "required": ["ref"],
}

_NEIGHBOURS_SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {
            "type": "string",
            "description": "Seed paper id (e.g. 'openalex:W2741809807') or openidea:// URI.",
        },
        "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
        "depth": {
            "type": "integer",
            "default": 1,
            "minimum": 1,
            "maximum": 2,
            "description": "Graph expansion depth. Currently 1-hop is expanded; depth=2 is accepted and noted for forward-compat.",
        },
    },
    "required": ["ref"],
}

_HANDOFF_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {
            "type": "string",
            "description": "Lab project topic / research question the handoff belongs to.",
        },
        "refs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Paper ids or openidea:// URIs to include (resolved + cited).",
        },
        "notes": {
            "type": "string",
            "description": "Free-text context from the researcher (hypothesis, constraints, next steps).",
        },
        "style": {
            "type": "string",
            "enum": list(CITATION_STYLES),
            "default": "markdown",
            "description": "Citation format embedded in the handoff bundle.",
        },
    },
    "required": ["topic", "refs"],
}


def clamp_limit(value: object, default: int = 20) -> int:
    """Coerce a limit argument to an int clamped to 1..100.

    JSON-Schema enforcement depends on the client, so harden it here too.
    """
    if value is None:
        return default
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"`limit` must be an integer 1..100; got {value!r}")
    return max(1, min(100, n))


def parse_page(value: object) -> int | None:
    """Coerce a page argument to a positive int, or None when omitted."""
    if value is None:
        return None
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"`page` must be a positive integer; got {value!r}")
    if n < 1:
        raise ValueError(f"`page` must be a positive integer; got {value!r}")
    return n


def strip_resource_ref(ref: str) -> str:
    """Accept a bare id ('openalex:W42') or an openidea:// URI; return the id."""
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("`ref` is required (resource id or openidea:// URI).")
    if ref.startswith(URI_PREFIX):
        ref = ref[len(URI_PREFIX):]
    if not ref:
        raise ValueError("`ref` is required (resource id or openidea:// URI).")
    return ref


def _author_list(resource: Resource) -> str:
    authors = resource.authors or []
    if not authors:
        return "n.a."
    if len(authors) <= 3:
        return ", ".join(authors)
    return ", ".join(authors[:3]) + ", et al."


def format_citation(resource: Resource, style: str = "markdown") -> str:
    """Format a Resource as a citation for papers/lab notes (pure function)."""
    if style not in CITATION_STYLES:
        raise ValueError(f"Unknown citation style {style!r}; expected one of {CITATION_STYLES}.")
    authors = _author_list(resource)
    year = str(resource.year) if resource.year is not None else "n.d."
    if style == "apa":
        return f"{authors} ({year}). {resource.title}. {resource.source.value}. {resource.url}"
    if style == "bibtex":
        key = resource.id.replace(":", "_").replace("/", "_")
        fields = [f"  title={{{resource.title}}}"]
        if resource.authors:
            fields.append(f"  author={{{' and '.join(resource.authors)}}}")
        if resource.year is not None:
            fields.append(f"  year={{{resource.year}}}")
        fields.append(f"  url={{{resource.url}}}")
        fields.append(f"  note={{{resource.id}; via Open Idea ({resource.source.value})}}")
        return f"@misc{{{key},\n" + ",\n".join(fields) + "\n}"
    # markdown (default): lab-note friendly one-liner
    return f"**{resource.title}** — {authors} ({year}). [{resource.source.value}]({resource.url})"


def merge_resources(lists: list[list[Resource]]) -> tuple[list[Resource], dict]:
    """Dedupe per-type result lists by id (order-preserving) + merged coverage."""
    seen: set[str] = set()
    merged: list[Resource] = []
    requested: list[str] = []
    received: dict[str, int] = {}
    unique_before = 0
    for sub in lists:
        unique_before += len(sub)
        for r in sub:
            received[r.source.value] = received.get(r.source.value, 0) + 1
            if r.source.value not in requested:
                requested.append(r.source.value)
            if r.id in seen:
                continue
            seen.add(r.id)
            merged.append(r)
    coverage = {
        "requestedProviders": requested,
        "receivedCounts": received,
        "uniqueBefore": unique_before,
        "uniqueAfter": len(merged),
        "merged": unique_before - len(merged),
    }
    return merged, coverage


def normalize_paper_ref(ref: str) -> str:
    """Strip URI scheme, DOI/arXiv prefixes, and URL wrappers to a bare ref."""
    ref = strip_resource_ref(ref)
    lowered = ref.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://arxiv.org/abs/", "doi:", "arxiv:"):
        if lowered.startswith(prefix):
            ref = ref[len(prefix):]
            lowered = ref.lower()
            break
    return ref.strip()


def candidate_ids_for_ref(ref: str) -> list[str]:
    """Ordered candidate canonical ids to try direct-fetch for a paper ref.

    Pure function so resolution order is unit-testable without HTTP.
    """
    base = normalize_paper_ref(ref)
    cands: list[str] = [base]
    low = base.lower()
    if low.startswith("10.") and "/" in base:
        # DOI shape (10.xxxx/...) — try the doi:-namespaced id as well.
        namespaced = f"doi:{base}"
        if namespaced not in cands:
            cands.append(namespaced)
    if low.startswith("w") and base[1:2].isdigit():
        # Bare OpenAlex id ("W2741809807") — try the namespaced form.
        namespaced = f"openalex:{base}"
        if namespaced not in cands:
            cands.append(namespaced)
    if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", base):
        namespaced = f"arxiv:{base}"
        if namespaced not in cands:
            cands.append(namespaced)
    # De-dupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def seed_search_queries(seed: Resource, max_words: int = 12) -> list[str]:
    """Fallback search queries for graph expansion when seed.meta has no links.

    Pure function: title-first, then first-author + title-head.
    """
    words = seed.title.split()
    title_q = " ".join(words[:max_words])
    queries = [title_q]
    if seed.authors:
        head = " ".join(words[:6])
        author_q = f"{seed.authors[0]} {head}".strip()
        if author_q and author_q not in queries:
            queries.append(author_q)
    return queries


def meta_link_ids(seed: Resource) -> list[str]:
    """Collect neighbour ids from seed.meta link fields (references/cited_by/related)."""
    meta = seed.meta or {}
    ids: list[str] = []
    for key in ("references", "cited_by", "citedBy", "related", "related_ids", "neighbours", "neighbors"):
        val = meta.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    ids.append(item.strip())
                elif isinstance(item, dict):
                    for k in ("id", "ref", "uri"):
                        if isinstance(item.get(k), str) and item[k].strip():
                            ids.append(item[k].strip())
                            break
    # De-dupe preserving order, excluding the seed itself.
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i == seed.id or i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


def build_handoff_markdown(
    topic: str,
    entries: list[tuple[Resource, str]],
    notes: str = "",
    missing: list[str] | None = None,
) -> str:
    """Build the Lab-ready markdown bundle (pure function)."""
    missing = missing or []
    lines = [
        f"# Lab handoff: {topic}",
        "",
        f"_Suggested model: {SUGGESTED_MODEL} (Muse)_",
        "",
        "## Papers",
        "",
    ]
    if not entries:
        lines.append("_No papers resolved — add refs and re-run._")
    for r, cite in entries:
        lines.append(f"- {cite}")
        lines.append(f"  - id: `{r.id}` · url: {r.url}")
    lines += ["", "## Notes", "", notes.strip() or "_No notes provided._", ""]
    if missing:
        lines += ["## Unresolved refs", ""]
        lines += [f"- `{m}`" for m in missing]
        lines.append("")
    lines += [
        "## Suggested next steps in Lab",
        "",
        "1. Create (or open) the Lab project for this topic and paste this bundle into the project brief.",
        "2. Ask Muse to expand each paper into problem/method/results/limits.",
        "3. File follow-up `graph_neighbours` expansions as Lab tasks.",
        "",
    ]
    return "\n".join(lines)


async def resolve_paper_ref(client: OpenIdeaClient, ref: str, limit: int = 5) -> dict:
    """Resolve a DOI/arXiv/OpenAlex/title ref to the canonical paper record.

    Strategy: try direct id fetches in candidate order, else fall back to a
    paper-type search and return the top hit plus candidates.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError(f"`limit` must be an integer 1..20; got {limit!r}")
    limit = max(1, min(20, limit))
    raw = (ref or "").strip()
    if not raw:
        raise ValueError("`ref` is required (DOI, arXiv id, OpenAlex id, title, or openidea:// URI).")
    for cid in candidate_ids_for_ref(raw):
        # get_resource returns None on 404 (miss → try next candidate) and
        # raises on 401/429/5xx so auth/transport failures still surface.
        hit = await client.get_resource(cid)
        if hit is not None:
            return {
                "resolved": hit.model_dump(mode="json", exclude_none=True),
                "method": "direct",
                "candidateIds": [cid],
            }
    # Fallback: free-text paper search; titles/DOIs usually surface the record.
    resp = await client.search(normalize_paper_ref(raw), type=ResourceType.paper, limit=limit)
    if not resp.results:
        raise ValueError(f"No paper found for {raw!r}")
    top, rest = resp.results[0], resp.results[1:]
    return {
        "resolved": top.model_dump(mode="json", exclude_none=True),
        "method": "search",
        "candidateIds": candidate_ids_for_ref(raw),
        "candidates": [r.model_dump(mode="json", exclude_none=True) for r in rest],
    }


async def neighbourhood_for(
    client: OpenIdeaClient, ref: str, limit: int = 10, depth: int = 1
) -> dict:
    """Return the 1-hop graph neighbourhood for a seed paper.

    Prefers explicit links in seed.meta; falls back to title/author search so
    the tool is useful even when the backend ships no graph endpoint yet.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError(f"`limit` must be an integer 1..50; got {limit!r}")
    limit = max(1, min(50, limit))
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        raise ValueError(f"`depth` must be 1 or 2; got {depth!r}")
    if depth < 1 or depth > 2:
        raise ValueError(f"`depth` must be 1 or 2; got {depth!r}")
    seed_id = strip_resource_ref(ref)
    seed = await client.get_resource(seed_id)
    if seed is None:
        raise ValueError(f"No resource found for {seed_id!r}")
    linked = meta_link_ids(seed)[: limit * 2]
    neighbours: list[Resource] = []
    strategy = "search"
    if linked:
        fetched = await asyncio.gather(*[client.get_resource(i) for i in linked])
        seen: set[str] = {seed.id}
        for r in fetched:
            if r is None or r.id in seen:
                continue
            seen.add(r.id)
            neighbours.append(r)
        strategy = "meta"
    if not neighbours:
        queries = seed_search_queries(seed)
        subs = await asyncio.gather(*[
            client.search(q, type=ResourceType.paper, limit=limit) for q in queries
        ])
        merged, _ = merge_resources([s.results for s in subs])
        neighbours = [r for r in merged if r.id != seed.id][:limit]
    else:
        neighbours = neighbours[:limit]
    payload: dict = {
        "seed": seed.model_dump(mode="json", exclude_none=True),
        "neighbours": [r.model_dump(mode="json", exclude_none=True) for r in neighbours],
        "strategy": strategy,
        "depth": depth,
    }
    if depth == 2:
        payload["note"] = "depth=2 accepted; expansion is currently 1-hop (2-hop fan-out lands with the backend graph endpoint)."
    return payload


async def lab_handoff_bundle(
    client: OpenIdeaClient,
    topic: str,
    refs: list[str],
    notes: str = "",
    style: str = "markdown",
) -> dict:
    """Fetch + cite each ref and assemble the Lab project handoff bundle."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("`topic` is required (Lab project topic / research question).")
    if not refs:
        raise ValueError("`refs` must list at least one paper id or openidea:// URI.")
    if style not in CITATION_STYLES:
        raise ValueError(f"Unknown citation style {style!r}; expected one of {CITATION_STYLES}.")
    if notes is None:
        notes = ""
    elif not isinstance(notes, str):
        notes = str(notes)
    for r in refs:
        if not isinstance(r, str) or not r.strip():
            raise ValueError("`refs` must list at least one paper id or openidea:// URI.")
    cleaned = [strip_resource_ref(r) for r in refs]
    # De-dupe preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for c in cleaned:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    fetched = await asyncio.gather(*[client.get_resource(c) for c in ordered])
    entries: list[tuple[Resource, str]] = []
    missing: list[str] = []
    resolved_json: list[dict] = []
    for cid, r in zip(ordered, fetched):
        if r is None:
            missing.append(cid)
            continue
        cite = format_citation(r, style)
        entries.append((r, cite))
        resolved_json.append(r.model_dump(mode="json", exclude_none=True))
    markdown = build_handoff_markdown(topic, entries, notes, missing)
    return {
        "topic": topic,
        "suggestedModel": SUGGESTED_MODEL,
        "markdown": markdown,
        "citations": [c for _, c in entries],
        "resolved": resolved_json,
        "missing": missing,
    }


def _dump_response(response) -> str:
    return json.dumps(response.model_dump(mode="json", exclude_none=True))


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
        tools.append(Tool(
            name="get_resource",
            description="Fetch the canonical record for one id (e.g. 'openalex:W2741809807') or openidea:// URI. Use after search to inspect a paper/dataset/code record in full.",
            inputSchema=_RESOURCE_REF_SCHEMA,
        ))
        tools.append(Tool(
            name="format_citation",
            description="Fetch a record and format it as a citation (markdown, apa, bibtex) for papers and lab notes.",
            inputSchema=_CITATION_SCHEMA,
        ))
        tools.append(Tool(
            name="resolve_paper",
            description="Resolve a DOI, arXiv id, OpenAlex id, paper title, or openidea:// URI to the canonical paper record (direct fetch, then paper-search fallback).",
            inputSchema=_RESOLVE_SCHEMA,
        ))
        tools.append(Tool(
            name="graph_neighbours",
            description="Return the 1-hop graph neighbourhood for a seed paper (explicit meta links when present, else title/author search expansion).",
            inputSchema=_NEIGHBOURS_SCHEMA,
        ))
        tools.append(Tool(
            name="lab_handoff",
            description="Assemble a Lab project handoff bundle: resolve refs, format citations, and render markdown with a Muse model hint.",
            inputSchema=_HANDOFF_SCHEMA,
        ))
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        query = arguments.get("query", "")
        if name in SEARCH_PRESETS or name == "search_all":
            if not query:
                raise ValueError("`query` is required.")
            limit = clamp_limit(arguments.get("limit", 20))
            page = parse_page(arguments.get("page"))

        if name in SEARCH_PRESETS:
            response = await client.search(
                query, type=SEARCH_PRESETS[name], limit=limit, page=page
            )
            return [TextContent(type="text", text=_dump_response(response))]

        if name == "search_all":
            requested_types = arguments.get("types") or []
            if not requested_types:
                response = await client.search(query, limit=limit, page=page)
                return [TextContent(type="text", text=_dump_response(response))]

            # Fan out one request per type filter concurrently, merge by id.
            rtypes: list[ResourceType] = []
            invalid: list[str] = []
            for t in requested_types:
                try:
                    rtypes.append(ResourceType(t))
                except ValueError:
                    invalid.append(t)
            if not rtypes:
                valid = sorted(t.value for t in ResourceType)
                raise ValueError(
                    f"No valid resource types in `types` {requested_types!r}; "
                    f"expected a subset of {valid}."
                )
            subs = await asyncio.gather(*[
                client.search(query, type=rtype, limit=limit, page=page)
                for rtype in rtypes
            ])
            merged, coverage = merge_resources([s.results for s in subs])
            payload = {
                "results": [r.model_dump(mode="json", exclude_none=True) for r in merged],
                "total": len(merged),
                "coverage": coverage,
            }
            if invalid:
                payload["ignoredTypes"] = invalid
            return [TextContent(type="text", text=json.dumps(payload))]

        if name == "get_resource":
            resource_id = strip_resource_ref(arguments.get("ref", ""))
            resource = await client.get_resource(resource_id)
            if resource is None:
                raise ValueError(f"No resource found for {resource_id!r}")
            return [
                TextContent(
                    type="text",
                    text=resource.model_dump_json(exclude_none=True),
                )
            ]

        if name == "format_citation":
            resource_id = strip_resource_ref(arguments.get("ref", ""))
            style = arguments.get("style", "markdown")
            resource = await client.get_resource(resource_id)
            if resource is None:
                raise ValueError(f"No resource found for {resource_id!r}")
            return [TextContent(type="text", text=format_citation(resource, style))]

        if name == "resolve_paper":
            raw = (arguments.get("ref", "") or "").strip()
            if not raw:
                raise ValueError("`ref` is required.")
            limit = clamp_limit(arguments.get("limit", 5), default=5)
            limit = max(1, min(20, limit))
            payload = await resolve_paper_ref(client, raw, limit=limit)
            return [TextContent(type="text", text=json.dumps(payload))]

        if name == "graph_neighbours":
            raw = (arguments.get("ref", "") or "").strip()
            if not raw:
                raise ValueError("`ref` is required.")
            limit = clamp_limit(arguments.get("limit", 10), default=10)
            limit = max(1, min(50, limit))
            try:
                depth = int(arguments.get("depth", 1))
            except (TypeError, ValueError):
                raise ValueError(f"`depth` must be 1 or 2; got {arguments.get('depth')!r}")
            payload = await neighbourhood_for(client, raw, limit=limit, depth=depth)
            return [TextContent(type="text", text=json.dumps(payload))]

        if name == "lab_handoff":
            topic = (arguments.get("topic", "") or "").strip()
            refs = arguments.get("refs", [])
            notes = arguments.get("notes", "") or ""
            style = arguments.get("style", "markdown")
            if not topic:
                raise ValueError("`topic` is required.")
            if not refs or not isinstance(refs, list):
                raise ValueError("`refs` must list at least one paper id or openidea:// URI.")
            payload = await lab_handoff_bundle(client, topic, refs, notes=notes, style=style)
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
