# Claude Desktop Guide

## Overview

This guide wires `mcp-openidea-search` into [Claude Desktop](https://claude.ai/download)
as a local stdio MCP server. Once configured, Claude can call the OpenIdea
search tools directly in a conversation.

## Purpose

Give a reliable, copy-pasteable configuration for macOS, Windows, and Linux,
including the platform-specific config file locations.

## Prerequisites

- Claude Desktop installed.
- `mcp-openidea-search` installed and on `PATH` (see [setup.md](setup.md)). Run
  `mcp-openidea-search --help` to confirm.
- A valid `OPENIDEA_API_KEY` (format `oi_live_…`).

## Installation Steps

1. Install the package so the `mcp-openidea-search` console script exists:

   ```bash
   pipx install mcp-openidea-search
   # or, from source:
   pip install -e .
   ```

2. Locate the absolute path to the executable — Claude Desktop does not always
   inherit your shell `PATH`, so an absolute `command` is the most robust:

   ```bash
   # macOS / Linux
   which mcp-openidea-search

   # Windows (PowerShell)
   (Get-Command mcp-openidea-search).Source
   ```

3. Edit `claude_desktop_config.json` (paths below) and restart Claude Desktop.

## Configuration

### Configuration file paths

| OS | Path |
|---|---|
| **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` (e.g. `C:\Users\<you>\AppData\Roaming\Claude\claude_desktop_config.json`) |
| **Linux** | `~/.config/Claude/claude_desktop_config.json` |

If the file does not exist, create it with the content below.

### Working configuration (PATH-resolved command)

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

### Working configuration (absolute path — most robust)

macOS / Linux:

```json
{
  "mcpServers": {
    "openidea": {
      "command": "/Users/you/.local/bin/mcp-openidea-search",
      "args": ["stdio"],
      "env": {
        "OPENIDEA_API_URL": "https://www.openidea.world",
        "OPENIDEA_API_KEY": "oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

Windows (note the doubled backslashes required by JSON):

```json
{
  "mcpServers": {
    "openidea": {
      "command": "C:\\Users\\you\\.local\\bin\\mcp-openidea-search.exe",
      "args": ["stdio"],
      "env": {
        "OPENIDEA_API_URL": "https://www.openidea.world",
        "OPENIDEA_API_KEY": "oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### Running via the Python module (no console script)

If the console script is not resolvable, invoke the module through the
interpreter from your virtual environment:

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

## Environment Variables

These go in the `env` block (not your shell), because Claude Desktop launches the
server itself:

| Variable | Required | Value |
|---|---|---|
| `OPENIDEA_API_URL` | yes | `https://www.openidea.world` |
| `OPENIDEA_API_KEY` | yes | Your `oi_live_…` key |

> **Do not embed newlines** in the key. JSON string values must be single-line.
> A trailing `\n` is the most common cause of a `401` and the reason the client
> `.strip()`s the key — see [troubleshooting.md](troubleshooting.md).

## Examples

After restarting Claude Desktop, try:

> *"Use the openidea MCP to search for papers on transformer architectures."*

> *"Search OpenIdea for open-source datasets about protein folding and list the
> top 5 with links."*

## Expected Outputs

- The server appears in Claude Desktop's tool/MCP indicator (hammer/plug icon).
- Claude offers to call tools such as `search_papers`, `search_all`, etc.
- Tool results return JSON payloads that Claude summarizes with titles, authors,
  and URLs.

## Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| Server not listed after restart | Malformed JSON or wrong config path | Validate the JSON; confirm the path for your OS. |
| "server failed to start" | `command` not found | Use an absolute path or the `python -m` form. |
| Tools listed but every call 401s | Bad/whitespace-laden key | Re-paste the key on one line; mint a fresh one. |
| Server starts then immediately exits | Missing env var (exit code 2) | Ensure both `OPENIDEA_API_URL` and `OPENIDEA_API_KEY` are in `env`. |

## Troubleshooting

For detailed fixes (Claude Desktop not detecting the MCP, missing executable
path, newline-in-key, etc.), see [troubleshooting.md](troubleshooting.md). To
test the server independently of Claude Desktop, use the
[MCP Inspector](mcp-inspector.md).
