# Research & Lab Workflows

## Overview

How to use `mcp-openidea-search` for real lab work: literature sweeps,
dataset+code pairing, and citable paper hooks. All examples assume the server
is configured (see [setup.md](setup.md)).

## Prerequisites

- A running server with valid `OPENIDEA_API_URL` / `OPENIDEA_API_KEY`.
- An MCP client (Claude Code, Claude Desktop, Inspector).

## Workflow 1 — Literature sweep (papers, paginated)

Preset tools now accept an optional `page` for deep sweeps. Ask for page 1,
skim, then continue:

```
Use the openidea MCP: search_papers for "diffusion MRI tractography",
limit 20, page 1.
```

Then:

```
Same query, page 2 — skip any ids already seen.
```

`limit` is clamped to 1–100 server-side, so oversized requests degrade
gracefully instead of erroring upstream.

## Workflow 2 — Inspect a record (paper hook)

Search returns summaries. `get_resource` fetches the canonical record for one
hit — the paper/search hook for follow-up reads. It accepts a bare id or a
full `openidea://` URI, so it works both as a tool call and alongside resource
reads:

```json
{ "name": "get_resource", "arguments": { "ref": "openalex:W2741809807" } }
{ "name": "get_resource", "arguments": { "ref": "openidea://openalex:W2741809807" } }
```

Unknown ids raise `ValueError("No resource found for …")`, matching the
`read_resource` behavior for `openidea://` URIs (see
[api-reference.md](api-reference.md)).

Tip: when a client handles resources poorly, prefer the `get_resource` tool —
same data, no URI plumbing.

## Workflow 3 — Cite it (paper-writing hook)

`format_citation` fetches the record and formats a citation in one step:

```json
{ "name": "format_citation", "arguments": { "ref": "openalex:W2741809807", "style": "bibtex" } }
```

| Style | Output | Best for |
|---|---|---|
| `markdown` (default) | `**Title** — Authors (year). [source](url)` | Lab notes, chat summaries |
| `apa` | `Authors (year). Title. Source. url` | Drafts, reference lists |
| `bibtex` | `@misc{…}` entry keyed by sanitized id | LaTeX papers |

Missing authors render as `n.a.`, missing years as `n.d.` — the citation is
always well-formed. Verify generated BibTeX keys against your `.bib` before
submitting.

## Workflow 4 — Cross-type sweep (paper + dataset + code)

`search_all` with a `types` filter fans out one request per type
**concurrently**, dedupes by id, and returns merged `coverage`
(`requestedProviders`, `receivedCounts`, `uniqueBefore/After`, `merged`):

```json
{
  "name": "search_all",
  "arguments": { "query": "protein folding", "limit": 10, "types": ["paper", "dataset", "code"] }
}
```

Invalid type strings no longer vanish silently: they are reported back in
`ignoredTypes`, and a filter with *no* valid types raises a `ValueError`
listing the valid values. A typical lab prompt:

```
Use the openidea MCP search_all for "protein folding" across paper, dataset,
and code. For the top paper hit, get_resource + format_citation (bibtex).
```

## Workflow 5 — Resolve a paper from any identifier

`resolve_paper` accepts a DOI, arXiv id, OpenAlex id, title, or `openidea://`
URI and returns the canonical record. Direct id fetches are tried first
(`candidate_ids_for_ref` order), then a paper-search fallback:

```json
{ "name": "resolve_paper", "arguments": { "ref": "10.1234/abc" } }
{ "name": "resolve_paper", "arguments": { "ref": "Attention Is All You Need" } }
```

`method` tells you which path won (`"direct"` vs `"search"`); on the search
path the remaining hits arrive in `candidates` for disambiguation.

## Workflow 6 — Expand the graph neighbourhood

`graph_neighbours` returns the 1-hop neighbourhood for a seed paper. When the
seed record carries explicit links (`references` / `cited_by` / `related` in
`meta`), those are fetched (`strategy: "meta"`); otherwise the seed title +
first author are re-searched and merged with the seed excluded
(`strategy: "search"`):

```json
{ "name": "graph_neighbours", "arguments": { "ref": "openalex:W2741809807", "limit": 10 } }
```

Use it to snowball a literature sweep: resolve → neighbourhood → resolve the
most relevant neighbours.

## Workflow 7 — Hand off to a Lab project (Muse)

`lab_handoff` bundles resolved papers, formatted citations, your notes, and a
model hint into one payload to paste into the Lab project brief:

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

The response carries `markdown` (paste-ready), `citations[]`, `resolved[]`,
`missing[]` (unresolvable ids don't fail the bundle), and
`"suggestedModel": "muse-spark-1.3-contributor"` — Lab work here targets
**Muse** (Claude Code).

## Interpreting coverage

Each unfiltered response carries a `coverage` object from the Open Idea side;
filtered `search_all` merges one locally (see
[api-reference.md](api-reference.md)). Low `uniqueAfter` vs `uniqueBefore`
means heavy dedupe (same work mirrored across providers); a provider missing
from `receivedCounts` contributed nothing — try `search_all` unfiltered or a
narrower query.

## Troubleshooting

See [troubleshooting.md](troubleshooting.md). Research-specific notes:

| Symptom | Likely cause |
|---|---|
| Later pages repeat ids | Upstream ordering isn't stable; dedupe client-side by `id`. |
| `ValueError` on `types` filter | Typo in a type name — the error lists valid values. |
| Thin citation (n.a./n.d.) | Upstream record lacks authors/year; open the `url` to fill in manually. |
