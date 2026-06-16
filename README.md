# mcp-openidea-search

An MCP server that exposes [Open Idea](https://openidea.app)'s federated
search — across 10 open-knowledge providers (OpenAlex, arXiv, Zenodo, Software
Heritage, GitHub, HuggingFace, YouTube, OSHWA, Wikifactory, generic hardware)
— to MCP-compatible clients (Claude Desktop, Claude Code, Cursor, the MCP
Inspector, etc.).

This package is a **thin client** over the Open Idea v1 HTTP API. All the
federation, deduplication, normalization, and caching happen on Open Idea's
side. This repo is fully standalone — no dependency on the Open Idea codebase.

## Install

Requires Python 3.10+.

```bash
# from PyPI (once published)
pipx install mcp-openidea-search

# or directly from source
pip install -e .
```

## Configure

The server reads two environment variables:

| Variable | Required | Description |
|---|---|---|
| `OPENIDEA_API_URL` | yes | Base URL of the Open Idea API (`https://openidea.app` in production). |
| `OPENIDEA_API_KEY` | yes | Personal Bearer key. Mint one at `https://openidea.app/developer/api-keys` while signed in. The plaintext is shown only once at creation. |

## Run

### stdio (Claude Desktop / Claude Code)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or the equivalent on your OS:

```json
{
  "mcpServers": {
    "openidea": {
      "command": "mcp-openidea-search",
      "args": ["stdio"],
      "env": {
        "OPENIDEA_API_URL": "https://openidea.app",
        "OPENIDEA_API_KEY": "oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

For Claude Code, add to `~/.mcp.json`:

```json
{
  "mcpServers": {
    "openidea": {
      "command": "mcp-openidea-search",
      "args": ["stdio"],
      "env": {
        "OPENIDEA_API_URL": "https://openidea.app",
        "OPENIDEA_API_KEY": "oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

Restart your client and ask: *"use the openidea MCP to search for transformer architectures"*.

### HTTP/SSE (remote)

```bash
OPENIDEA_API_URL=https://openidea.app \
OPENIDEA_API_KEY=oi_live_xxx \
mcp-openidea-search http --host 0.0.0.0 --port 8000
```

Verify with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/sse
```

## Tools and resources

### Tools

| Name | Description |
|---|---|
| `search_papers` | Search for papers (OpenAlex + arXiv). |
| `search_code` | Search for code repos (GitHub + SWH). |
| `search_datasets` | Search for datasets (Zenodo + others). |
| `search_models` | Search for ML models (HuggingFace). |
| `search_hardware` | Search for open hardware (OSHWA + Wikifactory). |
| `search_videos` | Search for educational videos (YouTube). |
| `search_all` | Search across all providers. Accepts optional `types: string[]` filter. |

Each tool takes `query: string` and optional `limit: integer` (default 20).
Returns a JSON payload `{ results: Resource[], total: number, … }`.

### Resources

Single items addressable by URI:

```
openidea://openalex:W2741809807
openidea://github:vercel/next.js
```

Listing resources returns an empty array — they're addressable but not
enumerable. Use the search tools to discover ids, then `read_resource` to
fetch the canonical record.

## Develop

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401 unauthorized` errors | Key is missing, malformed, or has been revoked. Mint a new one. |
| `429 rate_limited` | More than 60 requests/minute on this key. Wait or use a second key. |
| Empty results | Upstream provider down, or `type` filter excludes all results. Try `search_all`. |
| `connection refused` | `OPENIDEA_API_URL` doesn't point to a running Open Idea instance. |

## License

MIT.
