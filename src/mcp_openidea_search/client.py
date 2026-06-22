"""Async HTTPX client for the Open Idea public API."""
from __future__ import annotations

import asyncio
import os

import httpx

from .models import Resource, ResourceType, SearchResponse


class OpenIdeaAuthError(RuntimeError):
    """Raised when the API rejects the configured key."""


class OpenIdeaClient:
    """Thin async wrapper around /api/v1/* on Open Idea."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        url = (base_url or os.environ.get("OPENIDEA_API_URL", "")).strip()
        key = (api_key or os.environ.get("OPENIDEA_API_KEY", "")).strip()
        if not url:
            raise RuntimeError("OPENIDEA_API_URL is required (env var or constructor arg).")
        if not key:
            raise RuntimeError("OPENIDEA_API_KEY is required (env var or constructor arg).")
        self.base_url = url.rstrip("/")
        self.api_key = key
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {key}",
                "User-Agent": "mcp-openidea-search/0.1",
                "Accept": "application/json",
            },
        )

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        r = await self._http.request(method, f"{self.base_url}{path}", **kw)
        if r.status_code == 429:
            delay = float(r.headers.get("Retry-After", "1"))
            await asyncio.sleep(min(delay, 5.0))
            r = await self._http.request(method, f"{self.base_url}{path}", **kw)
        if r.status_code == 401:
            raise OpenIdeaAuthError("Open Idea rejected the API key (401).")
        return r

    async def search(
        self,
        query: str,
        type: ResourceType | None = None,
        limit: int = 20,
        page: int | None = None,
        cursor: str | None = None,
    ) -> SearchResponse:
        params: dict[str, str] = {"q": query, "limit": str(limit)}
        if type is not None:
            params["type"] = type.value
        if page is not None:
            params["page"] = str(page)
        if cursor is not None:
            params["cursor"] = cursor
        r = await self._request("GET", "/api/v1/search", params=params)
        r.raise_for_status()
        return SearchResponse.model_validate(r.json())

    async def get_resource(self, resource_id: str) -> Resource | None:
        r = await self._request("GET", f"/api/v1/resources/{resource_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return Resource.model_validate(r.json())

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "OpenIdeaClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
