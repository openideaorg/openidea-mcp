# Claude Code Guide

## Overview

This guide registers `mcp-openidea-search` with [Claude Code](https://claude.com/claude-code),
Anthropic's CLI, as a local stdio MCP server. After registration, the OpenIdea
search tools are available in any Claude Code session.

## Purpose

Show the two supported registration methods (the `claude mcp` CLI and a manual
`.mcp.json` file) and the commands to verify the server is wired correctly.

## Prerequisites

- Claude Code installed (`claude --version`).
- `mcp-openidea-search` installed and on `PATH` (see [setup.md](setup.md)).
- A valid `OPENIDEA_API_KEY`.

## Installation

Install the package so the console script resolves:

```bash
pipx install mcp-openidea-search
# or, from source:
pip install -e .
```

Confirm:

```bash
mcp-openidea-search --help
```

## MCP Registration

### Method A — `claude mcp add` (recommended)

Register the server, passing both env vars with `-e`. Everything after `--` is
the command Claude Code will launch:

```bash
claude mcp add openidea \
  -e OPENIDEA_API_URL=https://www.openidea.world \
  -e OPENIDEA_API_KEY=oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  -- mcp-openidea-search stdio
```

To register at a specific scope (project-local vs. user-global), add `-s`:

```bash
# available to you across all projects
claude mcp add openidea -s user \
  -e OPENIDEA_API_URL=https://www.openidea.world \
  -e OPENIDEA_API_KEY=oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  -- mcp-openidea-search stdio
```

### Method B — manual `.mcp.json`

Create `.mcp.json` in the project root (or `~/.mcp.json` for a global entry):

```json
{
  "mcpServers": {
    "openidea": {
      "command": "mcp-openidea-search",
      "args": ["stdio"],
      "env": {
        "OPENIDEA_API_URL": "https://www.openidea.world",
        "OPENIDEA_API_KEY": "oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

If the console script is not on `PATH`, use the interpreter from your venv:

```json
{
  "mcpServers": {
    "openidea": {
      "command": "/abs/path/to/.venv/bin/python",
      "args": ["-m", "mcp_openidea_search.cli", "stdio"],
      "env": {
        "OPENIDEA_API_URL": "https://www.openidea.world",
        "OPENIDEA_API_KEY": "oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

## Configuration / Environment Variables

| Variable | Required | Value |
|---|---|---|
| `OPENIDEA_API_URL` | yes | `https://www.openidea.world` |
| `OPENIDEA_API_KEY` | yes | Your `oi_live_…` key |

Pass them via `-e` (Method A) or the `env` block (Method B). The client trims
whitespace/newlines from both values.

## Verification Commands

```bash
# List all registered MCP servers and their connection status
claude mcp list

# Inspect a single server's resolved command, args, and env
claude mcp get openidea
```

Expected `claude mcp list` output (shape):

```
openidea   ✓ connected   mcp-openidea-search stdio
```

Expected `claude mcp get openidea` output (shape):

```
openidea:
  scope: local
  command: mcp-openidea-search
  args: ["stdio"]
  env:
    OPENIDEA_API_URL=https://www.openidea.world
    OPENIDEA_API_KEY=oi_live_********
```

To remove the server:

```bash
claude mcp remove openidea
```

## Examples

Inside a Claude Code session:

```
> use the openidea MCP to find recent papers on retrieval-augmented generation
> search openidea for github repos implementing MCP servers
```

You can also confirm tool discovery with the `/mcp` command inside a session.

## Expected Outputs

- `claude mcp list` shows `openidea` as **connected**.
- The 12 tools (`search_papers` … `search_all`, plus `get_resource`,
  `format_citation`, `resolve_paper`, `graph_neighbours`, `lab_handoff`) are
  available to the model.
- Tool calls return JSON payloads (`{ "results": [...], "total": N }`).

> Lab work here targets **Muse** — prefer model `muse-spark-1.3-contributor`.
> `lab_handoff` bundles already carry this as `suggestedModel`.

## Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| `claude mcp list` shows "failed" / "disconnected" | Command not found or env missing | Verify `mcp-openidea-search --help`; re-add with absolute path. |
| Server connects then drops | Missing env var → process exits with code 2 | Re-add with both `-e` flags. |
| Every tool call returns 401 | Key invalid or contains a newline | Mint a fresh key; re-add it on a single line. |
| Registration "succeeds" but tools absent | Wrong scope / not reloaded | Check `claude mcp get openidea`; restart the session. |

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for registration failures and 401
handling. To validate the server independently, use the
[MCP Inspector](mcp-inspector.md).
