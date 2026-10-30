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

Eight tools are registered. Six are **presets** mapping to a single
`ResourceType`; `search_all` searches across types; `list_sources` lists the
providers the server can search.

| Tool | Resource type | Example providers (server-side) |
|---|---|---|
| `search_papers` | `paper` | OpenAlex, arXiv |
| `search_code` | `code` | GitHub, GitLab, Software Heritage |
| `search_datasets` | `dataset` | Zenodo, CKAN, Figshare, Kaggle |
| `search_models` | `model` | HuggingFace |
| `search_hardware` | `hardware` | open-hardware providers |
| `search_videos` | `video` | YouTube |
| `search_all` | (all) | every provider |
| `list_sources` | — | — |

> Open Idea adds providers server-side, so the provider list is not fixed in
> this package. `list_sources` returns the live list on servers that support
> `GET /api/v1/sources`; the response `source` field of any result is the
> provider name.

### Common input schema (search tools)

| Input | Type | Default | Notes |
|---|---|---|---|
| `query` | string | — | **Required.** |
| `max_results` | integer 1–500 | `50` | Most results to return. Auto mode may return fewer. |
| `min_relevance` | number 0–1 | `0.35` | Drop results below this relevance; stop paging when a whole page is below it. `0` disables. |
| `mode` | `"auto"` \| `"page"` | `"auto"` | See below. |
| `sources` | string[] | — | Only these providers, e.g. `["arxiv", "openalex"]`. |
| `page` | integer ≥1 | — | Page number (page mode). |
| `cursor` | string | — | `next_cursor` from an earlier response. |
| `detail` | `"compact"` \| `"full"` | `"compact"` | Output size, see below. |
| `limit` | integer | — | Deprecated alias for `max_results` (used only when `max_results` is absent). |

`search_all` also takes `types: string[]` (values `paper`, `dataset`, `code`,
`model`, `hardware`, `video`; unknown values are ignored).

### Modes

**`auto` (default).** The tool requests pages of `min(remaining, 100)` results
and follows `nextCursor` until one of:

| `stopped_because` | Meaning |
|---|---|
| `max_results` | `max_results` results collected. |
| `no_more_pages` | The server has no further page (no `nextCursor`, `hasMore` false), or a page repeated only results already seen. |
| `below_threshold` | Every result on the latest page was below `min_relevance` (or a newer server filtered the whole page out). |
| `page_cap` | Safety stop after 25 pages. |

The server's plan limit may return fewer results per page than requested
(free 30, student 50, plus 100, enterprise 200); auto mode keeps paging, so
`max_results` still applies. When the server sends no `nextCursor` but
`hasMore: true` (older servers), the next request steps `page` instead.

**`page`.** One request with the given `page` / `cursor` and
`limit = min(max_results, 100)`. `stopped_because` is `single_page`; pass
`next_cursor` back to continue.

### Relevance

Each result gets a `relevance` in 0..1:

- the server's `relevance` field when present (newer servers);
- otherwise `score / top score of the first page` (older servers, whose scores
  are on provider-specific scales), clamped to 1;
- otherwise unknown (`relevance` omitted). Results with unknown relevance are
  kept.

When `min_relevance > 0` it is also sent as `minRelevance`; older servers ignore
it and the filter above applies on this side. In page mode the fallback is
relative to the fetched page's best score.

### Sources

`sources` is sent as `sources=a,b,c`. Results whose `source` is not in the list
are also dropped on this side (case-insensitive), so the restriction holds on
older servers that ignore the parameter.

### Output

Single `TextContent` block whose `text` is JSON.

```json
{
  "query": "transformer architectures",
  "total_returned": 2,
  "stopped_because": "below_threshold",
  "results": [
    {
      "id": "openalex:W2741809807",
      "type": "paper",
      "title": "Attention Is All You Need",
      "url": "https://openalex.org/W2741809807",
      "year": 2017,
      "source": "openalex",
      "relevance": 0.98,
      "description": "The dominant sequence transduction models are based on…",
      "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]
    }
  ],
  "next_cursor": "eyJvIjoxMDB9",
  "total_available": 1840
}
```

- **compact** (default): `id`, `type`, `title`, `url`, `year`, `source`,
  `relevance` (2 decimals), `description` (≤200 characters, whitespace
  collapsed), `authors` (first 3). Missing fields are omitted.
- **full**: every field the server returned for the result, plus the computed
  `relevance`.
- `total_available` is the server's `total` from the first page, when sent.
- `next_cursor` continues after the last fetched page. If auto mode stopped on
  `max_results` partway through a page, the rest of that page is skipped when
  continuing from this cursor.

### `search_papers` / `search_code` / `search_datasets` / `search_models` / `search_hardware` / `search_videos`

Each forwards `type=<resource type>` to `GET /api/v1/search` with the inputs
above.

```json
{
  "name": "search_papers",
  "arguments": { "query": "protein folding", "max_results": 200, "sources": ["arxiv"] }
}
```

### `search_all`

- **Without `types`, or with one type** → the same behavior as a preset (one
  type filter, or none).
- **With several `types`** → one auto/page collection **per type, run
  concurrently**. Results are merged, **de-duplicated by `id`** (the higher
  relevance copy wins), sorted by relevance descending (unknown last), and
  trimmed to `max_results`. The payload adds `by_type`, e.g.
  `{"paper": {"returned": 40, "stopped_because": "below_threshold", "next_cursor": "…"}}`;
  top-level `next_cursor` is `null` and `stopped_because` is `max_results`
  (trimmed) or `per_type`. A type whose request failed shows
  `{"error": "…"}` in `by_type` while the others still return; if every type
  fails, or the key is rejected (401), the call fails. `cursor` cannot be
  combined with several types.

> Fallback relevance (older servers) is normalized per type, so cross-type
> ordering is approximate there.

```json
{
  "name": "search_all",
  "arguments": { "query": "protein folding", "types": ["paper", "dataset"], "max_results": 100 }
}
```

### `list_sources`

No inputs. On servers with `GET /api/v1/sources`:

```json
{
  "supported": true,
  "sources": [
    { "name": "arxiv", "label": "arXiv", "pillar": "research", "types": ["paper"],
      "tier": "free", "unlocked": true, "configured": true }
  ],
  "packs": [
    { "id": "ml", "label": "Machine learning", "description": "…", "sources": ["arxiv", "huggingface", "github"] }
  ]
}
```

On older servers (404) the tool succeeds with
`{"supported": false, "message": "This Open Idea server does not provide /api/v1/sources yet, …"}`.

### Error cases

| Condition | Result |
|---|---|
| `query` missing/empty | `ValueError("`query` is required.")` |
| `mode` / `detail` not an allowed value | `ValueError` |
| `cursor` with several `types` | `ValueError` |
| API returns 401 | `OpenIdeaAuthError` |
| API returns 429 | One retry after `Retry-After` (capped at 5s); then `httpx.HTTPStatusError` |
| API returns 5xx, or the connection fails | One retry after 0.5s; then the error propagates |
| Other 4xx | `httpx.HTTPStatusError` |

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

The server calls three Open Idea endpoints.

### `GET /api/v1/search`

| Query param | Source | Notes |
|---|---|---|
| `q` | `query` | Required. |
| `limit` | page size | `min(remaining, 100)` in auto mode; the plan limit may cap it lower. |
| `type` | resource type | Sent only when a type is set. |
| `page` | `page` | Page mode, or auto mode on servers without cursors. |
| `cursor` | `cursor` / `nextCursor` | Sent only when known. |
| `minRelevance` | `min_relevance` | Sent only when > 0. Older servers ignore it. |
| `sources` | `sources` | Comma-separated. Sent only when given. Older servers ignore it. |

Returns a `SearchResponse` JSON body.

### `GET /api/v1/resources/{id}`

Returns a single `Resource`, or `404` if not found.

### `GET /api/v1/sources`

Returns a `SourcesResponse`. Older servers return `404`, which
`OpenIdeaClient.list_sources()` maps to `None`.

### Request headers (all requests)

```
Authorization: Bearer <OPENIDEA_API_KEY>
User-Agent: mcp-openidea-search/<version>
Accept: application/json
```

Default request timeout: **30 seconds**, overridable with `OPENIDEA_TIMEOUT`
(seconds).

---

## Data Models

Defined in [models.py](../src/mcp_openidea_search/models.py) (Pydantic v2, all
with `extra="allow"`).

### `ResourceType` (enum)

`paper`, `dataset`, `code`, `model`, `hardware`, `video`.

### `ResourceProvider` (enum, documentation only)

Providers known at release: `openalex`, `arxiv`, `zenodo`, `swh`, `ckan`,
`huggingface`, `youtube`, `github`, `gitlab`, `figshare`, `kaggle`, `custom`.
`Resource.source` is a plain string, so results from providers added later
still validate.

### `Resource`

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `str` | yes | Stable id, e.g. `openalex:W42`. |
| `type` | `ResourceType` | yes | |
| `title` | `str` | yes | |
| `source` | `str` | yes | Origin provider name (any string). |
| `url` | `str` | yes | Canonical link. |
| `authors` | `list[str]` | no | |
| `year` | `int` | no | |
| `license` | `str` | no | |
| `description` | `str` | no | |
| `tags` | `list[str]` | no | |
| `meta` | `dict[str, Any]` | no | Provider-specific extras. |
| `score` | `float` | no | Provider-scale ranking score. |
| `relevance` | `float` | no | Normalized 0..1 relevance (newer servers). |

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
| `ranking` | any | `None` | Ranking metadata, passed through. |

### `SearchCoverage`

| Field | Type | Default | Notes |
|---|---|---|---|
| `requestedProviders` | `list[str]` | `[]` | Providers queried. |
| `receivedCounts` | `dict[str, int]` | `{}` | Per-provider hit counts. |
| `uniqueBefore` | `int` | `0` | Distinct results before merge. |
| `uniqueAfter` | `int` | `0` | Distinct results after merge. |
| `merged` | `int` | `0` | Number merged out as duplicates. |

### `SourcesResponse`

| Field | Type | Notes |
|---|---|---|
| `sources` | `list[Source]` | `name`, `label`, `pillar`, `types`, `tier`, `unlocked`, `configured`. |
| `packs` | `list[SourcePack]` | `id`, `label`, `description`, `sources` (provider names). |

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
| `httpx.HTTPStatusError` | any request | Upstream non-2xx after the retry (other than handled 401/404). |

## Troubleshooting

See [troubleshooting.md](troubleshooting.md).
