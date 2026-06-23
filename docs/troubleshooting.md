# Troubleshooting

## Overview

A catalogue of issues encountered while developing and operating
`mcp-openidea-search`, each mapped to its root cause (traced to specific code in
this repo) and a concrete fix.

## Purpose

Get a stuck developer or operator unblocked quickly, and document the
real-world failure modes the codebase was hardened against (notably the
API-key-whitespace `.strip()` fix).

## Prerequisites

- Familiarity with [setup.md](setup.md) and your client guide
  ([Claude Desktop](claude-desktop.md), [Claude Code](claude-code.md), or
  [MCP Inspector](mcp-inspector.md)).

## Quick reference

| Symptom | Likely cause | Section |
|---|---|---|
| `Open Idea rejected the API key (401).` | Bad/expired/whitespace key | [401 Unauthorized](#401-unauthorized) |
| Tools 401 only sometimes | Key has a trailing newline | [API key newline issues](#api-key-newline-issues) |
| `error: OPENIDEA_API_…is required` | Missing env var | [MCP startup failures](#mcp-startup-failures) |
| `command not found` | Executable not on PATH | [Missing executable path](#missing-executable-path) |
| Server absent in Claude Desktop | Bad config / path | [Claude Desktop not detecting MCP](#claude-desktop-not-detecting-the-mcp) |
| `claude mcp list` shows failed | Registration/command issue | [Claude Code registration failures](#claude-code-registration-failures) |
| `No resource found for …` | Upstream 404 / wrong id | [Resource not found](#resource-not-found) |
| 5xx from upstream | Open Idea internal error | [OpenIdea API 500 errors](#openidea-api-500-errors) |
| `429` / rate limited | >throughput limit on the key | [Rate limiting (429)](#rate-limiting-429) |

---

## 401 Unauthorized

**Error:** `OpenIdeaAuthError: Open Idea rejected the API key (401).`

Raised in [client.py](../src/mcp_openidea_search/client.py) `_request` whenever
Open Idea returns HTTP `401`.

**Causes & fixes:**

1. **Key missing or empty** — confirm `OPENIDEA_API_KEY` is set in the client's
   `env` block (not just your shell). The process exits with code 2 before any
   request if it is empty.
2. **Key revoked or expired** — mint a fresh key at
   `https://openidea.world/developer/api-keys`. The plaintext is shown only
   once at creation.
3. **Wrong key prefix/format** — production keys look like `oi_live_…`. Make
   sure you did not paste a placeholder.
4. **Wrong base URL** — if `OPENIDEA_API_URL` points at the wrong host, the key
   is valid but rejected there. Confirm it is `https://www.openidea.world`.

## Invalid API Key

**Symptom:** Every tool call fails with a 401, immediately, with a key you
believe is correct.

**Fixes:**

- Re-copy the key from the developer console; partial copies are common.
- Verify there are no surrounding quotes inside the JSON value (the value should
  be `"oi_live_…"`, not `"\"oi_live_…\""`).
- Test the key directly, bypassing MCP entirely:

  ```bash
  curl -sS -H "Authorization: Bearer oi_live_xxx" \
    "https://www.openidea.world/api/v1/search?q=test&limit=1"
  ```

  A `200` confirms the key; a `401` confirms the key/host is the problem, not
  the MCP server.

## API key newline issues

**Symptom:** The key works in `curl` but 401s through an MCP client, or vice
versa — often when the key was stored in a file or pasted from a terminal that
appended a newline.

**Root cause / fix:** This was a real bug. The constructor now `.strip()`s both
env vars:

```python
url = (base_url or os.environ.get("OPENIDEA_API_URL", "")).strip()
key = (api_key or os.environ.get("OPENIDEA_API_KEY", "")).strip()
```

(See the diff against the initial commit in
[client.py](../src/mcp_openidea_search/client.py).) Leading/trailing whitespace
and a single trailing newline are therefore tolerated. **But:**

- A newline *in the middle* of the key still breaks it — re-paste it as a single
  unbroken line.
- In JSON config files, the value must be one line: `"OPENIDEA_API_KEY": "oi_live_…"`.
  JSON cannot contain a raw newline inside a string.
- If you source the key from a file, strip it yourself: `tr -d '\n' < key.txt`.

## MCP startup failures

**Errors:**

```
error: OPENIDEA_API_URL is required (env var or constructor arg).
error: OPENIDEA_API_KEY is required (env var or constructor arg).
```

The CLI ([cli.py](../src/mcp_openidea_search/cli.py)) constructs the client
before starting any transport. If either variable is missing, it prints the
error to stderr and **exits with code 2**. To a client this looks like "the
server started and immediately died."

**Fix:** Ensure both `OPENIDEA_API_URL` and `OPENIDEA_API_KEY` are present in
the launch environment — the `env` block for Claude Desktop, the `-e` flags for
`claude mcp add`, or inline before `npx` for the Inspector.

## Missing executable path

**Symptom:** `command not found: mcp-openidea-search`, or the client reports it
cannot spawn the server.

**Cause:** The console script (registered by `[project.scripts]` in
[pyproject.toml](../pyproject.toml)) is not on the `PATH` seen by the client.
GUI apps frequently do not inherit your shell `PATH`.

**Fixes:**

- Find the absolute path and use it as `command`:

  ```bash
  which mcp-openidea-search                 # macOS / Linux
  (Get-Command mcp-openidea-search).Source  # Windows PowerShell
  ```

- Or invoke through the venv interpreter:

  ```json
  { "command": "/abs/path/.venv/bin/python", "args": ["-m", "mcp_openidea_search.cli", "stdio"] }
  ```

- Re-install if the script is genuinely absent: `pip install -e .`.

## Claude Desktop not detecting the MCP

**Symptom:** After editing the config and restarting, `openidea` does not appear.

**Checklist:**

1. **Correct file path for your OS** (see [claude-desktop.md](claude-desktop.md)).
2. **Valid JSON** — a trailing comma or unescaped backslash invalidates the whole
   file. On Windows, paths need doubled backslashes (`C:\\Users\\…`).
3. **Fully restart** Claude Desktop (quit, not just close the window).
4. **Absolute `command` path** — resolves PATH-inheritance issues.
5. Test the exact command in a terminal first; if it 401s or exits there, it will
   fail in Claude Desktop too.

## Claude Code registration failures

**Symptom:** `claude mcp list` shows `openidea` as failed/disconnected, or tools
never appear.

**Fixes:**

- Inspect the resolved config: `claude mcp get openidea`. Confirm `command`,
  `args: ["stdio"]`, and both env vars.
- If the command is wrong, remove and re-add:

  ```bash
  claude mcp remove openidea
  claude mcp add openidea \
    -e OPENIDEA_API_URL=https://www.openidea.world \
    -e OPENIDEA_API_KEY=oi_live_xxx \
    -- mcp-openidea-search stdio
  ```

- If PATH is the issue, register with an absolute command path or the
  `python -m mcp_openidea_search.cli stdio` form.
- Validate the server independently with the [MCP Inspector](mcp-inspector.md)
  to isolate Claude Code from the server.

## Resource not found

**Error:** `ValueError: No resource found for openidea://<id>`

Raised by `_read_resource` when `client.get_resource` returns `None` (upstream
HTTP `404`).

**Causes & fixes:**

- **Wrong id** — ids come from search results and look like `openalex:W42` or
  `github:vercel/next.js`. Run a search first and copy the exact `id`.
- **Missing scheme** — the URI must start with `openidea://`. Without it you get
  `ValueError: URI must start with 'openidea://' …` instead.
- **Resource genuinely absent upstream** — the provider record may have been
  removed.

## OpenIdea API 500 errors

**Symptom:** A tool call surfaces an `httpx.HTTPStatusError` with a `5xx` status.

**Cause:** `client.search` / `client.get_resource` call `raise_for_status()`,
which raises on any non-2xx not specifically handled (401, 404, 429). A `500`
indicates an upstream/server-side failure at Open Idea.

**Fixes:**

- Retry — 500s are frequently transient (one provider timing out during
  federation).
- Narrow the query or use a preset tool instead of `search_all` to reduce the
  number of providers fanned out.
- If it persists for a specific query, capture the request and report it to the
  Open Idea API team. The MCP server cannot fix an upstream 500.

## Rate limiting (429)

**Symptom:** Slow responses, or eventually an error after a retry.

**Behavior:** `_request` retries **once** on a `429`, sleeping
`min(Retry-After, 5.0)` seconds first. If the second attempt also fails, the
status propagates.

**Fixes:**

- Reduce request volume — note `search_all` with a `types` filter issues **one
  request per type**, multiplying your call count.
- Stagger calls, or use a second API key for high-throughput workloads.

## Empty results (not an error)

If a tool returns `{"results": [], "total": 0}`:

- The query may genuinely have no matches for that `type`. Try `search_all`.
- An upstream provider may be temporarily down — check the `coverage` object
  (present on unfiltered searches) for `receivedCounts` per provider.

## Still stuck?

1. Reproduce in the [MCP Inspector](mcp-inspector.md) to remove the AI client
   as a variable.
2. Hit the API directly with `curl` to separate MCP-layer from API-layer issues.
3. Re-read [architecture.md](architecture.md) for the exact error/retry
   semantics of each layer.
