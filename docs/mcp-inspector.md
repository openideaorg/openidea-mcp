# MCP Inspector Guide

## Overview

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) is the
reference tool for exercising an MCP server in isolation — listing tools,
calling them with arbitrary arguments, and reading resources — without any AI
client in the loop. It is the fastest way to confirm `mcp-openidea-search`
works before wiring it into Claude Desktop or Claude Code.

## Purpose

Walk through installing and running the Inspector against both the stdio and
HTTP/SSE transports, and through testing every tool and the resource reader.

## Prerequisites

- Node.js (for `npx`).
- `mcp-openidea-search` installed (see [setup.md](setup.md)).
- A valid `OPENIDEA_API_KEY`.

## Installation

The Inspector is run on demand with `npx`; no global install is required:

```bash
npx @modelcontextprotocol/inspector --help
```

To pin a global copy:

```bash
npm install -g @modelcontextprotocol/inspector
```

## Running the Inspector

### Connecting via stdio

The Inspector launches the server as a subprocess and speaks MCP over its pipes.
Provide the env vars inline so the spawned process inherits them:

```bash
OPENIDEA_API_URL=https://www.openidea.world \
OPENIDEA_API_KEY=oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx \
npx @modelcontextprotocol/inspector mcp-openidea-search stdio
```

On Windows (PowerShell), set the variables first, then run:

```powershell
$env:OPENIDEA_API_URL = "https://www.openidea.world"
$env:OPENIDEA_API_KEY = "oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
npx @modelcontextprotocol/inspector mcp-openidea-search stdio
```

The Inspector opens a local web UI (it prints the URL, typically
`http://localhost:6274`). The transport will already be set to **STDIO** with
the command/args you provided.

### Connecting via HTTP/SSE

First start the server in HTTP mode:

```bash
OPENIDEA_API_URL=https://www.openidea.world \
OPENIDEA_API_KEY=oi_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx \
mcp-openidea-search http --host 127.0.0.1 --port 8000
```

Then point the Inspector at the SSE endpoint:

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/sse
```

(The server exposes `GET /sse` for the event stream and `POST /messages/` for
client→server messages — see [architecture.md](architecture.md).)

## Configuration / Environment Variables

| Variable | Required | Where |
|---|---|---|
| `OPENIDEA_API_URL` | yes | Inline before `npx` (stdio) or in the server's environment (HTTP). |
| `OPENIDEA_API_KEY` | yes | Same as above. |

## Testing Tools

In the Inspector UI:

1. Open the **Tools** tab and click **List Tools**. You should see all seven:
   `search_papers`, `search_code`, `search_datasets`, `search_models`,
   `search_hardware`, `search_videos`, `search_all`, `list_sources`.
2. Select `search_papers` and enter arguments:

   ```json
   { "query": "transformer architectures", "max_results": 5 }
   ```

3. Click **Run Tool**. The result is one text content block containing JSON:

   ```json
   { "query": "transformer architectures", "total_returned": 5, "stopped_because": "max_results",
     "results": [ { "id": "openalex:W…", "type": "paper", "title": "…", "url": "https://…", "source": "openalex", "relevance": 0.97 } ],
     "next_cursor": "…" }
   ```

4. Test `search_all` with a `types` filter:

   ```json
   { "query": "protein folding", "max_results": 10, "types": ["paper", "dataset"] }
   ```

   Both types run in parallel; the response is merged, de-duplicated and sorted
   by relevance, with per-type status under `by_type`.

5. Run `list_sources` (no arguments). Servers without `/api/v1/sources` return
   `{"supported": false, "message": "…"}`.

## Testing Resources

1. Open the **Resources** tab and click **List Resources**. The list is
   **empty by design** — resources are addressable but not enumerable.
2. Use **Read Resource** with a URI discovered from a search result, e.g.:

   ```
   openidea://openalex:W2741809807
   ```

3. The reader returns the resource JSON, or an error if the URI does not start
   with `openidea://` or the resource is not found.

## Expected Outputs

- **List Tools** → 7 tools with their input schemas.
- **Run Tool** → a JSON text block matching the shapes in
  [api-reference.md](api-reference.md).
- **List Resources** → `[]`.
- **Read Resource** (valid URI) → a single `Resource` JSON object.

## Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| Inspector "connection error" (stdio) | `mcp-openidea-search` not found | Use an absolute path or `python -m mcp_openidea_search.cli stdio`. |
| Server exits immediately | Env vars not passed to the subprocess | Set `OPENIDEA_API_URL` / `OPENIDEA_API_KEY` inline before `npx`. |
| Tool call returns a 401 error | Invalid/whitespace key | Re-paste the key on one line; mint a fresh one. |
| HTTP connect fails | Server not running, or wrong port | Confirm the `http` process is up and the `/sse` URL/port match. |
| `Read Resource` raises "must start with 'openidea://'" | Wrong URI scheme | Prefix the id with `openidea://`. |

## Troubleshooting

See [troubleshooting.md](troubleshooting.md). The Inspector is itself the best
first step when diagnosing client-side issues, since it removes the AI client
from the equation.
