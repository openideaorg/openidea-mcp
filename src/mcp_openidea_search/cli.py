"""CLI entrypoint — `mcp-openidea-search stdio` or `mcp-openidea-search http`."""
from __future__ import annotations

import argparse
import asyncio
import sys

from .client import OpenIdeaClient
from .server import build_server


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcp-openidea-search",
        description="MCP server for Open Idea federated search.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stdio", help="Run over stdio (default for Claude Desktop / Claude Code).")
    http = sub.add_parser("http", help="Run over HTTP+SSE (for remote clients).")
    http.add_argument("--host", default="127.0.0.1")
    http.add_argument("--port", type=int, default=8000)
    return p


async def _run_stdio(client: OpenIdeaClient) -> None:
    from mcp.server.stdio import stdio_server

    server = build_server(client)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def _run_http(client: OpenIdeaClient, host: str, port: int) -> None:
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    server = build_server(client)
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (read, write):
            await server.run(read, write, server.create_initialization_options())

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )
    uvicorn.run(app, host=host, port=port)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        client = OpenIdeaClient()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.cmd == "stdio":
        try:
            asyncio.run(_run_stdio(client))
        finally:
            asyncio.run(client.aclose())
        return 0

    if args.cmd == "http":
        try:
            _run_http(client, args.host, args.port)
        finally:
            asyncio.run(client.aclose())
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
