# Development Guide

## Overview

This guide is for contributors working **on** `mcp-openidea-search`. It covers
the repository layout, environment setup, the test suite, and the local
development workflow, plus a module-by-module explanation of the source.

## Purpose

Let a new contributor go from a fresh clone to running tests and making a
confident change in minutes.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python `>= 3.10` | Declared in [pyproject.toml](../pyproject.toml). |
| `git` | To clone and branch. |
| A virtual environment tool | `venv` (stdlib) is sufficient. |

The Open Idea API key is **not** required to run the test suite — all HTTP is
mocked with `respx`. You only need a real key to exercise the server against the
live API.

## Repository Structure

```
OpenIdeaMcp-/
├── pyproject.toml                      # Project metadata, deps, console script, pytest config
├── README.md                           # Top-level overview / quickstart
├── docs/                               # This documentation set
│   ├── setup.md
│   ├── architecture.md
│   ├── api-reference.md
│   ├── claude-desktop.md
│   ├── claude-code.md
│   ├── mcp-inspector.md
│   ├── troubleshooting.md
│   ├── development.md
│   └── research.md                   # lab workflows (sweeps, citations)
├── src/
│   └── mcp_openidea_search/
│       ├── __init__.py                 # Package version (0.1.0)
│       ├── client.py                   # Async HTTP client over the Open Idea API
│       ├── models.py                   # Pydantic models for the API contract
│       ├── server.py                   # MCP server: tools + resource handlers
│       └── cli.py                      # CLI entrypoint: stdio / http transports
└── tests/
    ├── __init__.py
    ├── test_client.py                  # Client tests (respx-mocked transport)
    └── test_server.py                  # Server construction / surface tests
```

The build uses `hatchling`; the wheel packages `src/mcp_openidea_search`
(`[tool.hatch.build.targets.wheel]`).

## Python Environment Setup

### Virtual environment creation

```bash
git clone <repository-url>
cd OpenIdeaMcp-
python -m venv .venv
```

Activate it:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### Dependency installation

Install the package in editable mode with the `dev` extras (pulls in `pytest`,
`pytest-asyncio`, and `respx`):

```bash
pip install -e ".[dev]"
```

Runtime dependencies (`mcp`, `httpx`, `pydantic`, `uvicorn`, `starlette`) are
installed automatically.

## Running Tests

The test configuration lives in `[tool.pytest.ini_options]` in
[pyproject.toml](../pyproject.toml): `asyncio_mode = "auto"` (so `async` tests
need no per-test marker beyond what's present) and `testpaths = ["tests"]`.

```bash
pytest -q          # quiet run
pytest             # default
pytest -v          # verbose, per-test names
pytest tests/test_client.py::test_401_raises_auth_error   # single test
```

### What the tests cover

`tests/test_client.py` (transport mocked with `respx`):

- `test_search_returns_resources` — verifies the `Authorization` header, query
  params (`q`, `type`, `limit`), and parsing into `SearchResponse`.
- `test_get_resource_returns_resource` — happy-path resource fetch.
- `test_get_resource_404_returns_none` — 404 maps to `None`.
- `test_401_raises_auth_error` — 401 raises `OpenIdeaAuthError`.
- `test_429_retries_once` — 429 then 200 results in exactly two calls.

`tests/test_server.py`:

- `test_search_presets_cover_all_resource_types_except_all` — `SEARCH_PRESETS`
  covers every `ResourceType`.
- `test_uri_prefix_is_openidea_scheme` — `URI_PREFIX == "openidea://"`.
- `test_build_server_returns_named_server` — server name is `openidea-search`.

> End-to-end MCP transport behavior is intentionally **not** unit-tested (it
> would require a full client+server stdio pair). Validate it manually with the
> [MCP Inspector](mcp-inspector.md).

## Local Development Workflow

1. Create a branch off `main`.
2. Make your change under `src/mcp_openidea_search/`.
3. Run `pytest -q` — keep it green.
4. Smoke-test against the live API with the Inspector:

   ```bash
   OPENIDEA_API_URL=https://www.openidea.world \
   OPENIDEA_API_KEY=oi_live_xxx \
   npx @modelcontextprotocol/inspector mcp-openidea-search stdio
   ```

5. Update the relevant docs in `docs/` and the [README](../README.md) if you
   change the public surface (tools, env vars, CLI flags).
6. Commit and open a PR.

Because the install is editable (`pip install -e .`), source edits take effect
immediately — no reinstall needed.

## Module-by-Module Explanation

### `src/mcp_openidea_search/client.py`

The async HTTP client. Key points:

- `OpenIdeaClient.__init__` resolves `OPENIDEA_API_URL` / `OPENIDEA_API_KEY`
  (constructor arg → env var), `.strip()`s both, and raises `RuntimeError` if
  either is empty. It builds an `httpx.AsyncClient` with a default `timeout`
  (10.0s) and the `Authorization: Bearer …`, `User-Agent`, and `Accept` headers.
- `_request` is the single choke point for HTTP: it retries once on `429`
  (honoring `Retry-After`, capped at 5s) and converts `401` into
  `OpenIdeaAuthError`.
- `search(query, type=, limit=, page=, cursor=)` → `GET /api/v1/search`, parsed
  into `SearchResponse`. (`page`/`cursor` support pagination but are not yet
  surfaced by the tools.)
- `get_resource(id)` → `GET /api/v1/resources/{id}`; returns `None` on `404`.
- Implements the async context-manager protocol (`__aenter__` / `__aexit__`)
  and `aclose()` for clean shutdown.

To add a new endpoint, add a method here that calls `_request` and validates the
response into a model — keep all HTTP concerns in this file.

### `src/mcp_openidea_search/server.py`

Builds the MCP server. Key points:

- `build_server(client)` returns a `Server("openidea-search")` and registers
  four handlers (`list_tools`, `call_tool`, `list_resources`, `read_resource`).
  The caller owns the client lifecycle.
- `SEARCH_PRESETS` maps each preset tool name to a `ResourceType`. A test
  asserts this dict covers every `ResourceType`, so **adding a new resource type
  requires adding its preset here** (or updating that test deliberately).
- `_BASE_SCHEMA` / `_ALL_SCHEMA` are the JSON Schemas advertised for tool input
  (`query`, `limit`, `page`, plus `types` on `search_all`).
- `_call_tool` validates `query`, clamps `limit` (`clamp_limit`), parses `page`
  (`parse_page`), dispatches presets to `client.search(type=…)`, and implements
  the `search_all` concurrent fan-out (`asyncio.gather`) + merge/dedupe.
- Pure, unit-tested helpers live at module level: `clamp_limit`, `parse_page`,
  `strip_resource_ref` (bare id or `openidea://` URI), `format_citation`
  (markdown/apa/bibtex), `merge_resources` (order-preserving dedupe + merged
  coverage). Keep new tool logic in this style so `tests/test_server.py` can
  cover it without MCP transport.
- `_read_resource` enforces the `openidea://` prefix (`URI_PREFIX`) and maps a
  missing resource to a `ValueError`. The `get_resource` tool is the same fetch
  via tool-call instead of resource-read.

To add a new tool: register it in `_list_tools` with an input schema, and handle
its name in `_call_tool`.

### `src/mcp_openidea_search/models.py`

The Pydantic v2 data contract, written from the public API docs (deliberately
not imported from any Open Idea repo, to keep this package standalone):

- `ResourceType` and `ResourceProvider` enums.
- `Resource`, `SearchResponse`, `SearchCoverage` models, all with
  `extra="allow"` so unknown fields from the API survive a round-trip.

When the API contract changes, update these models. `extra="allow"` means new
fields won't break parsing in the meantime.

### `src/mcp_openidea_search/cli.py`

The console entrypoint (`mcp-openidea-search`, mapped via
`[project.scripts]`):

- `_build_parser` defines two subcommands: `stdio` and `http`
  (`--host`/`--port`).
- `main` constructs the `OpenIdeaClient` first; on `RuntimeError` (missing env
  var) it prints to stderr and returns exit code 2.
- `_run_stdio` runs the server over `stdio_server()`.
- `_run_http` wraps the server in a Starlette app with `SseServerTransport`
  (`/sse` + `/messages/`) and serves it via `uvicorn`.
- Both paths `aclose()` the client in a `finally`.

## Configuration / Environment Variables

For development the only env vars are the two runtime ones
(`OPENIDEA_API_URL`, `OPENIDEA_API_KEY`), and only when running against the live
API. See [setup.md](setup.md).

## Examples

```bash
# full dev loop
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Expected Outputs

- `pytest -q` reports all tests passing.
- Edits to source are picked up immediately under the editable install.

## Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: mcp_openidea_search` | Not installed in the active venv | `pip install -e ".[dev]"` |
| Async tests error about event loop / fixtures | `pytest-asyncio` missing | Install dev extras; `asyncio_mode = "auto"` is already set. |
| `respx`-related import error | Dev extras not installed | `pip install -e ".[dev]"` |
| Tests pass but live calls 401 | Real key/whitespace issue | See [troubleshooting.md](troubleshooting.md). |

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for runtime issues and
[architecture.md](architecture.md) for the internal design.
