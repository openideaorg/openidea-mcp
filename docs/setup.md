# Setup Guide

## Overview

`mcp-openidea-search` is a [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) server that exposes [Open Idea](https://www.openidea.world)'s federated
search to any MCP-compatible client (Claude Desktop, Claude Code, the MCP
Inspector, Cursor, etc.).

The package is a **thin client** over the Open Idea v1 HTTP API. All federation,
deduplication, normalization, and caching happen on the Open Idea side. This
repository is fully standalone — it has no dependency on the Open Idea
application codebase.

## Purpose

This document covers everything required to install, configure, and start the
server for the first time. For client-specific wiring, see
[claude-desktop.md](claude-desktop.md), [claude-code.md](claude-code.md), and
[mcp-inspector.md](mcp-inspector.md).

## Prerequisites

| Requirement | Version / Notes |
|---|---|
| Python | `>= 3.10` (declared in [pyproject.toml](../pyproject.toml)) |
| pip / pipx | Any recent version. `pipx` recommended for global installs. |
| An Open Idea account | Needed to mint an API key. |
| An Open Idea API key | Bearer key, format `oi_live_…`. |
| Network access | The host must be able to reach `https://www.openidea.world`. |

The runtime dependencies (installed automatically) are declared in
[pyproject.toml](../pyproject.toml):

- `mcp>=1.0.0`
- `httpx>=0.27.0`
- `pydantic>=2.5.0`
- `uvicorn>=0.27.0` (only used by the `http` transport)
- `starlette>=0.36.0` (only used by the `http` transport)

## Installation Steps

### Option A — from PyPI (once published)

```bash
pipx install mcp-openidea-search
```

### Option B — from source (recommended for development)

```bash
git clone <repository-url>
cd OpenIdeaMcp-
python -m venv .venv

# Activate the virtual environment
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -e .
```

Installing the package registers a console script named `mcp-openidea-search`
(declared under `[project.scripts]` in [pyproject.toml](../pyproject.toml),
mapped to `mcp_openidea_search.cli:main`).

Verify the entry point resolves:

```bash
mcp-openidea-search --help
```

Expected output:

```
usage: mcp-openidea-search [-h] {stdio,http} ...

MCP server for Open Idea federated search.

positional arguments:
  {stdio,http}
    stdio       Run over stdio (default for Claude Desktop / Claude Code).
    http        Run over HTTP+SSE (for remote clients).
```

## Configuration

The server is configured **entirely through environment variables**. There is no
configuration file. Both variables are required; the server exits with code `2`
if either is missing.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENIDEA_API_URL` | yes | Base URL of the Open Idea API. Production value: `https://www.openidea.world`. A trailing slash is stripped automatically. |
| `OPENIDEA_API_KEY` | yes | Personal Bearer key. Mint one at `https://openidea.world/developer/api-keys` while signed in. The plaintext is shown only once at creation. |
| `OPENIDEA_TIMEOUT` | no | Request timeout in seconds (default 30). |

Both values are read in [client.py](../src/mcp_openidea_search/client.py) and are
`.strip()`-ed, so surrounding whitespace and trailing newlines (a common
copy-paste hazard — see [troubleshooting.md](troubleshooting.md)) are tolerated.

> **Note on the base URL.** The URL is never hardcoded; it is always read from
> `OPENIDEA_API_URL`. Earlier examples in the repository referenced
> `https://openidea.app`. The current production endpoint is
> `https://www.openidea.world`. Set whichever value matches the environment you
> are targeting.

## Running the Server

### stdio (Claude Desktop / Claude Code)

Most desktop clients launch the server themselves over stdio and inject the
environment variables. To run it manually for a smoke test:

```bash
export OPENIDEA_API_URL=https://www.openidea.world
export OPENIDEA_API_KEY=oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
mcp-openidea-search stdio
```

A correctly started stdio server **prints nothing** to stdout and waits for an
MCP client to speak the protocol over the pipe. It is not meant to be used
interactively from a terminal.

### HTTP / SSE (remote clients)

```bash
OPENIDEA_API_URL=https://www.openidea.world \
OPENIDEA_API_KEY=oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx \
mcp-openidea-search http --host 0.0.0.0 --port 8000
```

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Interface to bind. |
| `--port` | `8000` | TCP port. |

The HTTP transport exposes an SSE endpoint at `/sse` and a message sink at
`/messages/` (see [architecture.md](architecture.md)).

## Examples

Quick end-to-end check with the MCP Inspector (stdio):

```bash
npx @modelcontextprotocol/inspector mcp-openidea-search stdio
```

Then, in the Inspector UI, call the `search_papers` tool with
`{"query": "transformer architectures", "max_results": 5}`.

## Expected Outputs

- `mcp-openidea-search --help` prints the usage banner shown above.
- `mcp-openidea-search stdio` with valid env vars produces no stdout and stays
  running.
- A tool call returns a single text content block containing a JSON object of
  the shape `{"results": [...], "total": N, ...}` (see
  [api-reference.md](api-reference.md)).

## Common Errors

| Message | Cause | Fix |
|---|---|---|
| `error: OPENIDEA_API_URL is required (env var or constructor arg).` | `OPENIDEA_API_URL` unset/empty. | Export the variable or add it to the client `env` block. |
| `error: OPENIDEA_API_KEY is required (env var or constructor arg).` | `OPENIDEA_API_KEY` unset/empty. | Export the variable or add it to the client `env` block. |
| `command not found: mcp-openidea-search` | Package not installed, or venv not on `PATH`. | Re-run `pip install -e .`, or use the absolute path to the console script. |
| `Open Idea rejected the API key (401).` | Key missing, malformed, or revoked. | Mint a fresh key; see [troubleshooting.md](troubleshooting.md). |

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for a full catalogue of issues
(401 errors, newline-in-key problems, client detection failures, etc.). For the
internal design, see [architecture.md](architecture.md).
