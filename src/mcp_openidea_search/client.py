"""Async HTTPX client for the Open Idea public API."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable

import httpx

from . import __version__
from .models import Resource, ResourceType, SearchResponse, SourcesResponse

# Federated search waits on the slowest upstream provider; 10s cut off
# legitimate multi-provider queries, so the default is 30s.
DEFAULT_TIMEOUT = 30.0
RETRY_AFTER_CAP = 5.0


class OpenIdeaAuthError(RuntimeError):
    """Raised when the API rejects the configured key."""


def _timeout_from_env() -> float:
    raw = os.environ.get("OPENIDEA_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(f"OPENIDEA_TIMEOUT must be a number of seconds; got {raw!r}.") from None
    if value <= 0:
        raise RuntimeError(f"OPENIDEA_TIMEOUT must be positive; got {raw!r}.")
    return value


def _retry_after_seconds(response: httpx.Response) -> float:
    """Seconds to wait from a Retry-After header, capped. HTTP-date values and
    garbage fall back to 1s rather than failing the request."""
    try:
        delay = float(response.headers.get("Retry-After", "1"))
    except ValueError:
        delay = 1.0
    return max(0.0, min(delay, RETRY_AFTER_CAP))


class OpenIdeaClient:
    """Thin async wrapper around /api/v1/* on Open Idea."""

    # Pause before retrying a 5xx or connect error. Class attribute so tests
    # can zero it.
    retry_backoff: float = 0.5

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        url = (base_url or os.environ.get("OPENIDEA_API_URL", "")).strip()
        key = (api_key or os.environ.get("OPENIDEA_API_KEY", "")).strip()
        if not url:
            raise RuntimeError("OPENIDEA_API_URL is required (env var or constructor arg).")
        if not key:
            raise RuntimeError("OPENIDEA_API_KEY is required (env var or constructor arg).")
        self.base_url = url.rstrip("/")
        self.api_key = key
        self.timeout = timeout if timeout is not None else _timeout_from_env()
        self._http = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {key}",
                "User-Agent": f"mcp-openidea-search/{__version__}",
                "Accept": "application/json",
            },
        )

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        """Send one request with at most one retry.

        Retries once on 429 (waiting Retry-After, capped at 5s), on 5xx, and on
        connection failures. Read timeouts are not retried: the server is
        working, and a second attempt would double the wait.
        """
        url = f"{self.base_url}{path}"
        try:
            r = await self._http.request(method, url, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            await asyncio.sleep(self.retry_backoff)
            r = await self._http.request(method, url, **kw)
        else:
            if r.status_code == 429:
                await asyncio.sleep(_retry_after_seconds(r))
                r = await self._http.request(method, url, **kw)
            elif r.status_code >= 500:
                await asyncio.sleep(self.retry_backoff)
                r = await self._http.request(method, url, **kw)
        if r.status_code == 401:
            raise OpenIdeaAuthError("Open Idea rejected the API key (401).")
        return r

    async def search(
        self,
        query: str,
        type: ResourceType | str | None = None,
        limit: int = 20,
        page: int | None = None,
        cursor: str | None = None,
        min_relevance: float | None = None,
        sources: Iterable[str] | None = None,
    ) -> SearchResponse:
        params: dict[str, str] = {"q": query, "limit": str(limit)}
        if type is not None:
            params["type"] = type.value if isinstance(type, ResourceType) else str(type)
        if page is not None:
            params["page"] = str(page)
        if cursor is not None:
            params["cursor"] = cursor
        if min_relevance is not None:
            params["minRelevance"] = f"{min_relevance:g}"
        if sources:
            joined = ",".join(s.strip() for s in sources if s and s.strip())
            if joined:
                params["sources"] = joined
        r = await self._request("GET", "/api/v1/search", params=params)
        r.raise_for_status()
        return SearchResponse.model_validate(r.json())

    async def get_resource(self, resource_id: str) -> Resource | None:
        r = await self._request("GET", f"/api/v1/resources/{resource_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return Resource.model_validate(r.json())

    async def list_sources(self) -> SourcesResponse | None:
        """GET /api/v1/sources. Returns None when the server predates the
        endpoint (404), so callers can degrade instead of failing."""
        r = await self._request("GET", "/api/v1/sources")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return SourcesResponse.model_validate(r.json())

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "OpenIdeaClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
