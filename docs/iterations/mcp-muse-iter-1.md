# Iteration 1 — Research + Lab handoff for Muse

Date: 2026-11-02 · Package: `mcp-openidea-search` 0.2.0 → **0.3.0** · Client: **Muse** (Claude Code) · Preferred model: `muse-spark-1.3-contributor`

## Goal

Make openidea-mcp directly useful for research and Lab project work with three
new tools, all client-side over the existing `GET /api/v1/search` +
`GET /api/v1/resources/{id}` endpoints (no new backend dependency):

1. `resolve_paper` — DOI / arXiv / OpenAlex / title / URI → canonical paper record.
2. `graph_neighbours` — 1-hop neighbourhood for a seed paper (meta links, else title/author expansion).
3. `lab_handoff` — Lab project bundle (resolved papers + citations + notes + Muse model hint).

## Changes

| File | What |
|---|---|
| `src/mcp_openidea_search/server.py` | 3 tool schemas + registrations + `_call_tool` branches; pure/testable helpers (`normalize_paper_ref`, `candidate_ids_for_ref`, `seed_search_queries`, `meta_link_ids`, `build_handoff_markdown`) and async workers (`resolve_paper_ref`, `neighbourhood_for`, `lab_handoff_bundle`); `SUGGESTED_MODEL = "muse-spark-1.3-contributor"`. |
| `src/mcp_openidea_search/__init__.py` | Version `0.3.0`. |
| `tests/test_server.py` | 10 new tests: ref normalization/candidates, query/meta/handoff helpers, direct + fallback resolve, meta + search neighbourhood, handoff with missing ref. |
| `README.md` | Tools table + Muse-first note. |
| `docs/api-reference.md` | Full schemas/behavior for the 3 tools (9 → 12 tools). |
| `docs/research.md` | Workflows 5–7 (resolve → neighbourhood → Lab handoff). |
| `docs/claude-code.md` | Tool count + Muse/model preference note. |

## Test steps

### A. Unit tests (no API key needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Expect: all tests pass (10 pre-existing + 10 new).

> Note: this iteration was written without a live run — the sandbox blocks
> `pytest` execution. CI (`pytest -q`) is the gate before merge.

### B. Inspector smoke test (needs `OPENIDEA_API_KEY`)

```bash
OPENIDEA_API_URL=https://www.openidea.world \
OPENIDEA_API_KEY=oi_live_xxx \
npx @modelcontextprotocol/inspector mcp-openidea-search stdio
```

Run in order:

1. `search_papers` `{"query": "diffusion MRI tractography", "limit": 5}` → note a paper id.
2. `resolve_paper` `{"ref": "<paste a DOI or title from step 1>"}` → expect `method` + `resolved.id`.
3. `get_resource` + `graph_neighbours` on the resolved id → expect `seed` + `neighbours[]`, `strategy` meta or search.
4. `format_citation` on one neighbour (`bibtex`) → well-formed entry.
5. `lab_handoff` `{"topic": "…", "refs": ["<id1>", "<id2>"], "notes": "…", "style": "markdown"}` → `markdown` renders, `suggestedModel` is `muse-spark-1.3-contributor`, unknown ids land in `missing`.

### C. Muse verification (Claude Code, model `muse-spark-1.3-contributor`)

```
> use the openidea MCP: resolve "Attention Is All You Need", then graph_neighbours on it (limit 5), then a lab_handoff on the topic "transformer architectures" with the top 3 refs and notes "focus on open weights".
```

Accept when: resolve returns a canonical id, neighbours exclude the seed,
handoff markdown contains citations + model hint, and no tool raises on
well-formed input.

## Known limits / next iterations

- `graph_neighbours` is 1-hop today; `depth=2` is accepted but noted, not fanned out. When the backend ships a graph endpoint, swap `neighbourhood_for` to call it with the search-expansion as fallback.
- `lab_handoff` returns a paste-ready bundle; a future `POST /api/v1/lab/handoffs` could make it one-click.
- `development.md` module docs still describe the 2-endpoint client; update when the client grows new methods.
