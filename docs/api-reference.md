# API Reference

## Overview

This document describes the MCP surface exposed by `mcp-openidea-search` — every
tool, its input schema, example requests and responses, and error cases — plus
the resource scheme and the underlying data models. All behavior here is derived
directly from [server.py](../src/mcp_openidea_search/server.py),
[client.py](../src/mcp_openidea_search/client.py), and
[models.py](../src/mcp_openidea_search/models.py).

## Purpose

A precise, implementation-faithful contract for client authors, integrators, and
contributors.

## Prerequisites

- A running server (see [setup.md](setup.md)).
- Valid `OPENIDEA_API_URL` and `OPENIDEA_API_KEY`.

## Transport summary

| Transport | Endpoint(s) | Launched by |
|---|---|---|
| stdio | (process pipes) | `mcp-openidea-search stdio` |
| HTTP/SSE | `GET /sse`, `POST /messages/` | `mcp-openidea-search http` |

The MCP server name advertised to clients is **`openidea-search`**.

---

## Tools

Twelve tools are registered. Six are **presets** mapping to a single
`ResourceType`; `search_all` searches across providers; `get_resource` and
`format_citation` are single-record paper/search hooks; `resolve_paper`,
`graph_neighbours`, and `lab_handoff` are the research/Lab hooks (all
client-side over the same two HTTP endpoints, so they work with no new backend).

| Tool | Resource type | Backing providers (server-side) |
|---|---|---|
| `search_papers` | `paper` | OpenAlex, arXiv, PapersWithCode |
| `search_code` | `code` | GitHub, GitLab, Software Heritage |
| `search_datasets` | `dataset` | Zenodo, CKAN, Figshare, Kaggle |
| `search_models` | `model` | HuggingFace |
| `search_hardware` | `hardware` | open-hardware providers |
| `search_videos` | `video` | YouTube |
| `search_all` | (all) | every provider |

> Provider attribution above reflects the categories Open Idea federates for
> each type. The exact provider set for a given query is reported in the
> response `coverage` object. The authoritative `ResourceProvider` enum is:
> `openalex`, `arxiv`, `zenodo`, `swh`, `ckan`, `huggingface`, `paperswithcode`,
> `youtube`, `github`, `gitlab`, `figshare`, `kaggle`, `custom`.

### Common input schema (preset tools)

All six preset tools share `_BASE_SCHEMA`:

```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string", "description": "Search query." },
    "limit": { "type": "integer", "default": 20, "minimum": 1, "maximum": 100 },
    "page": { "type": "integer", "default": 1, "minimum": 1, "description": "Result page for deep sweeps." }
  },
  "required": ["query"]
}
```

- `query` **(required)** — free-text search string.
- `limit` *(optional)* — max results, default `20`. Clamped to `1..100`
  server-side (`clamp_limit`), so out-of-range values degrade gracefully.
- `page` *(optional)* — result page for deep literature sweeps. Omitted from
  the upstream request when not provided; `0`/negative/non-numeric values raise
  `ValueError`.

### `search_papers` / `search_code` / `search_datasets` / `search_models` / `search_hardware` / `search_videos`

**Purpose.** Search Open Idea for resources of one specific type. Each forwards
`type=<resource type>` to `GET /api/v1/search`.

**Input schema.** `_BASE_SCHEMA` (above).

**Example request** (`search_papers`):

```json
{
  "name": "search_papers",
  "arguments": { "query": "transformer architectures", "limit": 5 }
}
```

**Example response** (single `TextContent` block; `text` is JSON):

```json
{
  "results": [
    {
      "id": "openalex:W2741809807",
      "type": "paper",
      "title": "Attention Is All You Need",
      "source": "openalex",
      "url": "https://openalex.org/W2741809807",
      "authors": ["Ashish Vaswani", "Noam Shazeer"],
      "year": 2017,
      "score": 0.98
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 5,
  "hasMore": true,
  "coverage": {
    "requestedProviders": ["openalex", "arxiv"],
    "receivedCounts": { "openalex": 1, "arxiv": 0 },
    "uniqueBefore": 1,
    "uniqueAfter": 1,
    "merged": 0
  }
}
```

The payload is `SearchResponse.model_dump(mode="json", exclude_none=True)` — so
`null` fields are omitted entirely.

**Error cases.**

| Condition | Result |
|---|---|
| `query` missing/empty | `ValueError("`query` is required.")` |
| API returns 401 | `OpenIdeaAuthError` |
| API returns 429 | One automatic retry; then propagates if still failing |
| API returns other 4xx/5xx | `httpx.HTTPStatusError` (via `raise_for_status()`) |

### `search_all`

**Purpose.** Search across all providers, optionally restricted to a subset of
resource types.

**Input schema** (`_ALL_SCHEMA` = `_BASE_SCHEMA` + `types`):

```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string", "description": "Search query." },
    "limit": { "type": "integer", "default": 20, "minimum": 1, "maximum": 100 },
    "types": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["paper", "dataset", "code", "model", "hardware", "video"]
      },
      "description": "Optional filter — return only these resource types."
    }
  },
  "required": ["query"]
}
```

**Behavior.**

- **Without `types`** → a single `GET /api/v1/search?q=…&limit=…` call; returns
  the full `SearchResponse` (including `coverage`).
- **With `types`** → the server issues **one request per type concurrently**
  (`asyncio.gather`), merges all results, **de-duplicates by `id` preserving
  first-seen order**, and returns
  `{"results": [...], "total": <count>, "coverage": <merged>, "ignoredTypes?: [...]}`.
  The merged `coverage` unions `requestedProviders`, sums `receivedCounts`, and
  sets `uniqueBefore` to the pre-dedupe count. Invalid type strings are reported
  back in `ignoredTypes`; a filter with *no* valid types raises
  `ValueError("No valid resource types …")` listing the valid values.

**Example request (no filter):**

```json
{ "name": "search_all", "arguments": { "query": "protein folding", "limit": 10 } }
```

**Example request (filtered):**

```json
{
  "name": "search_all",
  "arguments": { "query": "protein folding", "limit": 10, "types": ["paper", "dataset"] }
}
```

**Example response (filtered):**

```json
{
  "results": [
    { "id": "openalex:W123", "type": "paper", "title": "…", "source": "openalex", "url": "https://…" },
    { "id": "zenodo:456", "type": "dataset", "title": "…", "source": "zenodo", "url": "https://…" }
  ],
  "total": 2,
  "coverage": {
    "requestedProviders": ["openalex", "zenodo"],
    "receivedCounts": { "openalex": 1, "zenodo": 1 },
    "uniqueBefore": 2,
    "uniqueAfter": 2,
    "merged": 0
  }
}
```

**Error cases.** Same as the preset tools. Each per-type sub-request can
independently raise `OpenIdeaAuthError` (401) or `httpx.HTTPStatusError`.

---

### `get_resource`

**Purpose.** Fetch the canonical record for one id — the tool-based
paper/search hook for inspecting a hit in full. Some clients handle tools more
reliably than resource reads; this returns the same data as `read_resource`.

**Input schema:**

```json
{
  "type": "object",
  "properties": {
    "ref": { "type": "string", "description": "Resource id or openidea:// URI." }
  },
  "required": ["ref"]
}
```

`ref` accepts a bare id (`openalex:W2741809807`) or a full URI
(`openidea://openalex:W2741809807`); surrounding whitespace is stripped.

**Example request:**

```json
{ "name": "get_resource", "arguments": { "ref": "openalex:W2741809807" } }
```

**Example response** (single `TextContent` block; `text` is the `Resource`
JSON, `null` fields omitted) — same shape as the resource-read example below.

**Error cases.**

| Condition | Result |
|---|---|
| `ref` missing/empty | `ValueError("`ref` is required …")` |
| Upstream 404 | `ValueError("No resource found for …")` |
| Upstream 401 | `OpenIdeaAuthError` |

### `format_citation`

**Purpose.** Fetch a record and format it as a citation in one step — the
paper-writing hook for drafts and lab notes.

**Input schema:**

```json
{
  "type": "object",
  "properties": {
    "ref": { "type": "string", "description": "Resource id or openidea:// URI." },
    "style": { "type": "string", "enum": ["markdown", "apa", "bibtex"], "default": "markdown" }
  },
  "required": ["ref"]
}
```

**Example request:**

```json
{ "name": "format_citation", "arguments": { "ref": "openalex:W2741809807", "style": "bibtex" } }
```

**Example responses** (plain text, not JSON):

- `markdown`: `**Attention Is All You Need** — Ashish Vaswani, Noam Shazeer (2017). [openalex](https://openalex.org/W2741809807)`
- `apa`: `Ashish Vaswani, Noam Shazeer (2017). Attention Is All You Need. openalex. https://openalex.org/W2741809807`
- `bibtex`: a `@misc{openalex_W2741809807, …}` entry with `title`/`author`/`year`/`url`/`note`.

Missing authors render as `n.a.`, missing years as `n.d.`; unknown styles raise
`ValueError`. Not-found/401 behavior matches `get_resource`.

---

### `resolve_paper`

**Purpose.** Research hook: turn whatever identifier the researcher has (DOI,
arXiv id, OpenAlex id, paper title, `openidea://` URI) into the canonical paper
record. Tries direct id fetches in `candidate_ids_for_ref` order, then falls
back to a `paper`-type search.

**Input schema:**

```json
{
  "type": "object",
  "properties": {
    "ref": { "type": "string", "description": "DOI, arXiv id, OpenAlex id, title, or openidea:// URI." },
    "limit": { "type": "integer", "default": 5, "minimum": 1, "maximum": 20 }
  },
  "required": ["ref"]
}
```

**Behavior.**

- `method: "direct"` → `resolved` came from a direct fetch; `candidateIds`
  holds the winning id.
- `method: "search"` → `resolved` is the top search hit; remaining hits are in
  `candidates`.
- No hit anywhere → `ValueError("No paper found for …")`.

**Example request:**

```json
{ "name": "resolve_paper", "arguments": { "ref": "10.1234/abc" } }
{ "name": "resolve_paper", "arguments": { "ref": "Attention Is All You Need" } }
```

### `graph_neighbours`

**Purpose.** Graph hook: 1-hop neighbourhood for a seed paper. Prefers explicit
links in `seed.meta` (`references` / `cited_by` / `related` / `neighbours`);
when the backend ships no graph links, falls back to title/author paper-search
expansion (merged, seed excluded). `depth=2` is accepted for forward-compat and
noted in the payload — expansion today is 1-hop.

**Input schema:**

```json
{
  "type": "object",
  "properties": {
    "ref": { "type": "string", "description": "Seed paper id or openidea:// URI." },
    "limit": { "type": "integer", "default": 10, "minimum": 1, "maximum": 50 },
    "depth": { "type": "integer", "default": 1, "minimum": 1, "maximum": 2 }
  },
  "required": ["ref"]
}
```

**Example request:**

```json
{ "name": "graph_neighbours", "arguments": { "ref": "openalex:W2741809807", "limit": 10 } }
```

**Example response** (JSON text):

```json
{
  "seed": { "id": "openalex:W2741809807", "type": "paper", "title": "…", "source": "openalex", "url": "https://…" },
  "neighbours": [{ "id": "openalex:W9", "type": "paper", "title": "…", "source": "openalex", "url": "https://…" }],
  "strategy": "meta | search",
  "depth": 1
}
```

Missing seed → `ValueError("No resource found for …")`; bad depth →
`ValueError("`depth` must be 1 or 2 …")`.

### `lab_handoff`

**Purpose.** Lab hook: bundle resolved papers + citations + notes into one
payload Muse can paste into a Lab project brief. Muse-first — the payload
carries `"suggestedModel": "muse-spark-1.3-contributor"`.

**Input schema:**

```json
{
  "type": "object",
  "properties": {
    "topic": { "type": "string", "description": "Lab project topic / research question." },
    "refs": { "type": "array", "items": {"type": "string"}, "description": "Paper ids or openidea:// URIs." },
    "notes": { "type": "string", "description": "Researcher context (hypothesis, constraints, next steps)." },
    "style": { "type": "string", "enum": ["markdown", "apa", "bibtex"], "default": "markdown" }
  },
  "required": ["topic", "refs"]
}
```

**Behavior.** Fetches all refs concurrently (order-preserving dedupe);
unresolvable ids are listed in `missing` rather than failing the bundle.
Returns `{topic, suggestedModel, markdown, citations[], resolved[], missing[]}`.

**Example request:**

```json
{
  "name": "lab_handoff",
  "arguments": {
    "topic": "Diffusion MRI tractography",
    "refs": ["openalex:W2741809807"],
    "notes": "Focus on open datasets + runnable code.",
    "style": "markdown"
  }
}
```

---

## Resources

### URI format

```
openidea://<provider>:<id>
```

The portion after `openidea://` is passed verbatim to
`GET /api/v1/resources/{resource_id}`.

Examples:

```
openidea://openalex:W2741809807
openidea://github:vercel/next.js
openidea://zenodo:456
```

### The `openidea://` scheme

- `read_resource(uri)` **requires** the `openidea://` prefix; any other URI
  raises `ValueError(f"URI must start with 'openidea://'; got {uri!r}")`.
- `list_resources()` returns `[]`. Resources are **addressable but not
  enumerable** — discover ids via the search tools, then read by URI.

### Resource retrieval process

1. Strip `openidea://` → `resource_id`.
2. `GET /api/v1/resources/{resource_id}`.
3. `404` → the read raises `ValueError(f"No resource found for {uri}")`.
4. Success → returns the `Resource` serialized via
   `model_dump_json(exclude_none=True)`.

### Example

Request: `read_resource("openidea://openalex:W42")`

Response (`text`):

```json
{
  "id": "openalex:W42",
  "type": "paper",
  "title": "Sample paper",
  "source": "openalex",
  "url": "https://openalex.org/W42",
  "authors": ["Alice"],
  "year": 2024
}
```

---

## Underlying HTTP API

The server calls exactly two Open Idea endpoints.

### `GET /api/v1/search`

| Query param | Source | Notes |
|---|---|---|
| `q` | `query` | Required. |
| `limit` | `limit` | Sent as a string. |
| `type` | resource type | Sent only when a type is set. |
| `page` | `page` | Sent only when provided (client supports it; tools don't surface it). |
| `cursor` | `cursor` | Sent only when provided (client supports it; tools don't surface it). |

Returns a `SearchResponse` JSON body.

> Note: the `OpenIdeaClient.search` method accepts `page` and `cursor` for
> pagination; the MCP tool layer surfaces `page` (cursor-based paging stays
> client-side for now).

### `GET /api/v1/resources/{id}`

Returns a single `Resource`, or `404` if not found.

### Request headers (all requests)

```
Authorization: Bearer <OPENIDEA_API_KEY>
User-Agent: mcp-openidea-search/0.1
Accept: application/json
```

Default request timeout: **10.0 seconds**.

---

## Data Models

Defined in [models.py](../src/mcp_openidea_search/models.py) (Pydantic v2, all
with `extra="allow"`).

### `ResourceType` (enum)

`paper`, `dataset`, `code`, `model`, `hardware`, `video`.

### `ResourceProvider` (enum)

`openalex`, `arxiv`, `zenodo`, `swh`, `ckan`, `huggingface`, `paperswithcode`,
`youtube`, `github`, `gitlab`, `figshare`, `kaggle`, `custom`.

### `Resource`

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `str` | yes | Stable id, e.g. `openalex:W42`. |
| `type` | `ResourceType` | yes | |
| `title` | `str` | yes | |
| `source` | `ResourceProvider` | yes | Origin provider. |
| `url` | `str` | yes | Canonical link. |
| `authors` | `list[str]` | no | |
| `year` | `int` | no | |
| `license` | `str` | no | |
| `description` | `str` | no | |
| `tags` | `list[str]` | no | |
| `meta` | `dict[str, Any]` | no | Provider-specific extras. |
| `score` | `float` | no | Relevance score. |

### `SearchResponse`

| Field | Type | Default | Notes |
|---|---|---|---|
| `results` | `list[Resource]` | `[]` | |
| `total` | `int` | `0` | |
| `page` | `int \| None` | `None` | |
| `limit` | `int \| None` | `None` | |
| `hasMore` | `bool \| None` | `None` | |
| `nextCursor` | `str \| None` | `None` | Pagination cursor. |
| `coverage` | `SearchCoverage \| None` | `None` | |

### `SearchCoverage`

| Field | Type | Default | Notes |
|---|---|---|---|
| `requestedProviders` | `list[str]` | `[]` | Providers queried. |
| `receivedCounts` | `dict[str, int]` | `{}` | Per-provider hit counts. |
| `uniqueBefore` | `int` | `0` | Distinct results before merge. |
| `uniqueAfter` | `int` | `0` | Distinct results after merge. |
| `merged` | `int` | `0` | Number merged out as duplicates. |

Because every model sets `extra="allow"`, fields Open Idea adds in the future
are preserved on parse and round-tripped on output.

## Common Errors

| Error | Where | Meaning |
|---|---|---|
| `ValueError("`query` is required.")` | tool call | `query` empty/missing. |
| `ValueError("`limit` must be an integer 1..100 …")` | tool call | Non-numeric `limit`. (Out-of-range ints are clamped.) |
| `ValueError("`page` must be a positive integer …")` | tool call | Bad `page`. |
| `ValueError("No valid resource types …")` | `search_all` | `types` filter has no valid entries. |
| `ValueError("No paper found for …")` | `resolve_paper` | DOI/title matched nothing. |
| `ValueError("`depth` must be 1 or 2 …")` | `graph_neighbours` | Bad depth. |
| `ValueError("`topic` is required …")` | `lab_handoff` | Missing topic. |
| `ValueError("`refs` must list …")` | `lab_handoff` | Empty/non-list refs. |
| `ValueError("`ref` is required …")` | `get_resource` / `format_citation` | `ref` empty/missing. |
| `ValueError("Unknown citation style …")` | `format_citation` | `style` not markdown/apa/bibtex. |
| `ValueError("Unknown tool: …")` | tool call | Tool name not registered. |
| `ValueError("URI must start with 'openidea://' …")` | resource read | Bad scheme. |
| `ValueError("No resource found for …")` | resource read | Upstream 404. |
| `OpenIdeaAuthError` | any request | Upstream 401. |
| `httpx.HTTPStatusError` | any request | Upstream non-2xx (other than handled 401/404/429). |

## Troubleshooting

See [troubleshooting.md](troubleshooting.md).
