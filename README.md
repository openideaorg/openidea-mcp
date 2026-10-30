# mcp-openidea-search

An MCP server that exposes [Open Idea](https://www.openidea.world)'s federated
search — across open-knowledge providers (OpenAlex, arXiv, Zenodo, Software
Heritage, GitHub, GitLab, HuggingFace, YouTube, CKAN, Figshare, Kaggle, and
more as Open Idea adds them) — to MCP-compatible clients (Claude Desktop, Claude Code, the MCP
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

## 🚀 Getting Started

This tool connects Claude directly to Open Idea's academic and data search
engines. It runs entirely on your local machine using your personal API key.
Follow these 4 simple steps to get set up.

### Prerequisites

Make sure you have Python 3.10 or higher installed on your computer. You can
check this by running `python --version` in your terminal.

---

### Step 1: Get Your Free Open Idea API Key

Because this tool queries live databases on your behalf, you need a personal
access key.

1. Go to [openidea.world](https://www.openidea.world) and sign up or log in.
2. Navigate to the Developer Dashboard at
   [openidea.world/developer/api-keys](https://openidea.world/developer/api-keys).
3. Click **Create New Key**.
4. ⚠️ **Copy the key immediately** (it starts with `oi_live_...`). It will only
   be shown to you once.

---

### Step 2: Install the Search Tool

Open your terminal (Terminal on Mac/Linux, or PowerShell/Command Prompt on
Windows) and run the following command to safely install the tool:

```bash
pipx install mcp-openidea-search
```

*(If you do not have `pipx` configured, you can use
`pip install mcp-openidea-search` instead).*

---

### Step 3: Connect It to Your Claude Client

Choose the instructions below depending on whether you use **Claude Code** (in
your terminal) or the **Claude Desktop App**.

#### Option A: For Claude Code (Terminal)

1. Close any active Claude sessions by typing `exit`.
2. Run this exact command in your terminal (make sure to replace `YOUR_KEY_HERE`
   with the actual key you copied in Step 1):

```bash
claude mcp add openidea \
  -e OPENIDEA_API_URL=https://www.openidea.world \
  -e OPENIDEA_API_KEY=YOUR_KEY_HERE \
  -- mcp-openidea-search stdio
```

#### Option B: For Claude Desktop (App)

1. Open your Claude Desktop configuration file. Paste the path below into your
   file explorer or terminal to open it:
   * **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   * **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
2. Open the file in a text editor (like Notepad or VS Code) and add the
   following configuration block inside the `"mcpServers"` section (replace
   `YOUR_KEY_HERE` with your actual key):

```json
{
  "mcpServers": {
    "openidea": {
      "command": "mcp-openidea-search",
      "args": ["stdio"],
      "env": {
        "OPENIDEA_API_URL": "https://www.openidea.world",
        "OPENIDEA_API_KEY": "YOUR_KEY_HERE"
      }
    }
  }
}
```

3. Completely **restart** your Claude Desktop application.

---

### Step 4: Try It Out!

You are all set! You do not need to run this tool manually; Claude will wake it
up when needed. Open a chat with Claude and ask a natural question:

💬 *"Use the openidea MCP to find recent papers on transformer architectures."*

Claude will automatically look up the records, pull data from arXiv, GitHub, or
HuggingFace, and summarize the answers for you!

## Install

Requires Python 3.10+.

```bash
# from PyPI (once published)
pipx install mcp-openidea-search

# or directly from source
pip install -e .
```

## Configure

The server reads these environment variables:

| Variable | Required | Description |
|---|---|---|
| `OPENIDEA_API_URL` | yes | Base URL of the Open Idea API (`https://www.openidea.world` in production). A trailing slash is stripped automatically. |
| `OPENIDEA_API_KEY` | yes | Personal Bearer key. Mint one at `https://openidea.world/developer/api-keys` while signed in. The plaintext is shown only once at creation. |
| `OPENIDEA_TIMEOUT` | no | Request timeout in seconds (default 30). |

The URL and key are whitespace/newline-trimmed before use.

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
| `search_papers` | Search for papers (OpenAlex, arXiv). |
| `search_code` | Search for code repos (GitHub, GitLab, Software Heritage). |
| `search_datasets` | Search for datasets (Zenodo, CKAN, Figshare, Kaggle). |
| `search_models` | Search for ML models (HuggingFace). |
| `search_hardware` | Search for open hardware. |
| `search_videos` | Search for educational videos (YouTube). |
| `search_all` | Search across all providers. Optional `types: string[]`; several types run in parallel and merge by relevance. |
| `list_sources` | List the providers and source packs the server offers (newer servers). |

Search tools take `query` plus:

| Input | Default | Meaning |
|---|---|---|
| `max_results` | 50 | Up to 500. |
| `min_relevance` | 0.35 | Drop results below this 0..1 relevance; `0` keeps everything. |
| `mode` | `auto` | `auto` pages until `max_results` or results stop being relevant; `page` fetches one page (`page` / `cursor`). |
| `sources` | all | Restrict to providers, e.g. `["arxiv", "openalex"]`. |
| `detail` | `compact` | `full` returns complete records. |

The response is `{ query, total_returned, stopped_because, results, next_cursor }`,
each result carrying `id`, `type`, `title`, `url`, `year`, `source`,
`relevance`, a short `description` and the first three `authors`.

Works with older Open Idea servers too: without a server `relevance`, it is
derived from `score`; `sources` and `min_relevance` are applied on this side;
`list_sources` says when the server does not support it. Full schemas and
response shapes are in [docs/api-reference.md](docs/api-reference.md).

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
| `429 rate_limited` | Throughput limit on this key (retried once). Lower `max_results`, wait, or use a second key. |
| Empty results | Upstream provider down, or `type` filter excludes all results. Try `search_all`. |
| `connection refused` | `OPENIDEA_API_URL` doesn't point to a running Open Idea instance. |

Full guide: [docs/troubleshooting.md](docs/troubleshooting.md).

## License

MIT.
