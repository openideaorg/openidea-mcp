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

Seven tools are registered. Six are **presets** mapping to a single
`ResourceType`; the seventh, `search_all`, searches across providers.

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
    "limit": { "type": "integer", "default": 20, "minimum": 1, "maximum": 100 }
  },
  "required": ["query"]
}
```

- `query` **(required)** — free-text search string.
- `limit` *(optional)* — max results, default `20`, clamped by the schema to
  `1..100`.

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
- **With `types`** → the server issues **one request per type**, merges all
  results, **de-duplicates by `id`**, and returns
  `{"results": [...], "total": <count>}`. Type strings that are not valid
  `ResourceType` values are silently ignored. Note: this branch does **not**
  include a `coverage` object.

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
  "total": 2
}
```

**Error cases.** Same as the preset tools. Each per-type sub-request can
independently raise `OpenIdeaAuthError` (401) or `httpx.HTTPStatusError`.

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
> pagination, but the MCP tool layer does not currently expose them — tools pass
> only `query`, `type`, and `limit`.

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
| `ValueError("Unknown tool: …")` | tool call | Tool name not registered. |
| `ValueError("URI must start with 'openidea://' …")` | resource read | Bad scheme. |
| `ValueError("No resource found for …")` | resource read | Upstream 404. |
| `OpenIdeaAuthError` | any request | Upstream 401. |
| `httpx.HTTPStatusError` | any request | Upstream non-2xx (other than handled 401/404/429). |

## Troubleshooting

See [troubleshooting.md](troubleshooting.md).
