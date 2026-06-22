# mcp-openidea-search

An MCP server that exposes [Open Idea](https://www.openidea.world)'s federated
search — across open-knowledge providers (OpenAlex, arXiv, Zenodo, Software
Heritage, GitHub, GitLab, HuggingFace, PapersWithCode, YouTube, CKAN, Figshare,
Kaggle) — to MCP-compatible clients (Claude Desktop, Claude Code, the MCP
Inspector, Cursor, etc.).

This package is a **thin client** over the Open Idea v1 HTTP API. All the
federation, deduplication, normalization, and caching happen on Open Idea's
side. This repo is fully standalone — no dependency on the Open Idea codebase.

## Documentation

| Doc | Contents |
|---|---|
| [docs/setup.md](docs/setup.md) | Install, configure, and run the server. |
| [docs/architecture.md](docs/architecture.md) | Components, flows, and a Mermaid diagram. |
| [docs/api-reference.md](docs/api-reference.md) | Every tool, resource, and data model. |
| [docs/claude-desktop.md](docs/claude-desktop.md) | Claude Desktop configuration (macOS/Windows/Linux). |
| [docs/claude-code.md](docs/claude-code.md) | Claude Code registration & verification. |
| [docs/mcp-inspector.md](docs/mcp-inspector.md) | Testing with the MCP Inspector. |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 401s, newline keys, startup failures, and more. |
| [docs/development.md](docs/development.md) | Repo layout, env setup, tests, workflow. |

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
| `OPENIDEA_API_URL` | yes | Base URL of the Open Idea API (`https://www.openidea.world` in production). A trailing slash is stripped automatically. |
| `OPENIDEA_API_KEY` | yes | Personal Bearer key. Mint one at `https://www.openidea.world/developer/api-keys` while signed in. The plaintext is shown only once at creation. |

Both values are whitespace/newline-trimmed before use.

## Run

### stdio (Claude Desktop / Claude Code)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or the equivalent on your OS (see
[docs/claude-desktop.md](docs/claude-desktop.md)):

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

For Claude Code, register it with the CLI (see
[docs/claude-code.md](docs/claude-code.md)):

```bash
claude mcp add openidea \
  -e OPENIDEA_API_URL=https://www.openidea.world \
  -e OPENIDEA_API_KEY=oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  -- mcp-openidea-search stdio
```

Restart your client and ask: *"use the openidea MCP to search for transformer architectures"*.

### HTTP/SSE (remote)

```bash
OPENIDEA_API_URL=https://www.openidea.world \
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
| `search_papers` | Search for papers (OpenAlex, arXiv, PapersWithCode). |
| `search_code` | Search for code repos (GitHub, GitLab, Software Heritage). |
| `search_datasets` | Search for datasets (Zenodo, CKAN, Figshare, Kaggle). |
| `search_models` | Search for ML models (HuggingFace). |
| `search_hardware` | Search for open hardware. |
| `search_videos` | Search for educational videos (YouTube). |
| `search_all` | Search across all providers. Accepts an optional `types: string[]` filter. |

Each tool takes `query: string` and optional `limit: integer` (default 20,
range 1–100). Returns a JSON payload `{ results: Resource[], total: number, … }`.
Full schemas and response shapes are in
[docs/api-reference.md](docs/api-reference.md).

### Resources

Single items addressable by URI (`openidea://<provider>:<id>`):

```
openidea://openalex:W2741809807
openidea://github:vercel/next.js
```

Listing resources returns an empty array — they're addressable but not
enumerable. Use the search tools to discover ids, then `read_resource` to fetch
the canonical record.

## Develop

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

See [docs/development.md](docs/development.md) for the full contributor guide.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401 unauthorized` errors | Key is missing, malformed, has a stray newline, or has been revoked. Mint a new one. |
| `429 rate_limited` | Throughput limit on this key (server retries once). Wait or use a second key. |
| Empty results | Upstream provider down, or `type` filter excludes all results. Try `search_all`. |
| `connection refused` | `OPENIDEA_API_URL` doesn't point to a running Open Idea instance. |

Full guide: [docs/troubleshooting.md](docs/troubleshooting.md).

## License

MIT.
