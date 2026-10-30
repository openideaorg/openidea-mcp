"""Relevance-aware paging over GET /api/v1/search, and compact output.

Kept apart from server.py so the paging rules can be tested without the MCP
transport.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .client import OpenIdeaAuthError, OpenIdeaClient
from .models import Resource, ResourceType

MAX_RESULTS_CAP = 500
DEFAULT_MAX_RESULTS = 50
DEFAULT_MIN_RELEVANCE = 0.35
# Largest page we ask for. Plan limits cap it lower server-side (free 30,
# student 50, plus 100, enterprise 200); asking for more than 100 would only
# help enterprise keys and makes single responses large.
PAGE_LIMIT = 100
# Safety stop for auto mode. 500 results at the free-plan page size of 30 is
# 17 pages; 25 leaves room for pages thinned out by the `sources` filter.
MAX_PAGES = 25
DESCRIPTION_CHARS = 200
AUTHORS_SHOWN = 3

# stopped_because values
STOP_MAX_RESULTS = "max_results"
STOP_EXHAUSTED = "no_more_pages"
STOP_BELOW_THRESHOLD = "below_threshold"
STOP_PAGE_CAP = "page_cap"
STOP_SINGLE_PAGE = "single_page"


@dataclass
class Scored:
    resource: Resource
    relevance: float | None


@dataclass
class Collected:
    results: list[Scored] = field(default_factory=list)
    stopped_because: str = STOP_EXHAUSTED
    next_cursor: str | None = None
    total_available: int | None = None
    pages_fetched: int = 0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def top_score(results: Sequence[Resource]) -> float | None:
    scores = [r.score for r in results if r.score is not None]
    best = max(scores, default=None)
    return best if best is not None and best > 0 else None


def relevance_of(r: Resource, top: float | None) -> float | None:
    """Server `relevance` when present; otherwise `score` divided by the best
    score of the first page, so older servers still get a 0..1 scale. None
    when neither is available (such results are kept, not filtered)."""
    if r.relevance is not None:
        return _clamp01(r.relevance)
    if r.score is not None and top:
        return _clamp01(r.score / top)
    return None


def _source_ok(r: Resource, wanted: set[str] | None) -> bool:
    # Older servers ignore the `sources` param, so it is also applied here.
    return wanted is None or r.source.lower() in wanted


async def collect(
    client: OpenIdeaClient,
    query: str,
    *,
    type: ResourceType | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    min_relevance: float = DEFAULT_MIN_RELEVANCE,
    mode: str = "auto",
    sources: Sequence[str] | None = None,
    page: int | None = None,
    cursor: str | None = None,
) -> Collected:
    """Fetch results for one type (or all types when `type` is None).

    auto: request pages of min(remaining, 100) and follow nextCursor until
    max_results is reached, the server has no more pages, or a whole page is
    below min_relevance. Below-threshold results on a partly relevant page are
    dropped individually.

    page: one request at `page`/`cursor`. Fallback relevance is then relative
    to that page's best score.
    """
    wanted = {s.lower() for s in sources} if sources else None
    server_min = min_relevance if min_relevance > 0 else None
    out = Collected()
    seen: set[str] = set()
    top: float | None = None
    page_no = page

    while True:
        remaining = max_results - len(out.results)
        resp = await client.search(
            query,
            type=type,
            limit=min(remaining, PAGE_LIMIT),
            page=page_no,
            cursor=cursor,
            min_relevance=server_min,
            sources=sources,
        )
        out.pages_fetched += 1
        if out.total_available is None:
            out.total_available = resp.total
        if top is None:
            top = top_score(resp.results)

        new = [r for r in resp.results if r.id not in seen]
        seen.update(r.id for r in resp.results)
        scored = [Scored(r, relevance_of(r, top)) for r in new if _source_ok(r, wanted)]
        relevant = [
            s for s in scored
            if min_relevance <= 0 or s.relevance is None or s.relevance >= min_relevance
        ]
        out.results.extend(relevant)

        # Where the next page would start. If the server sends no cursor but
        # says there is more, step the page number (older servers).
        next_cursor = resp.nextCursor
        next_page: int | None = None
        if not next_cursor and resp.hasMore:
            next_page = (resp.page or page_no or 1) + 1
        out.next_cursor = next_cursor

        if mode == "page":
            out.stopped_because = STOP_SINGLE_PAGE
            break
        if len(out.results) >= max_results:
            out.stopped_because = STOP_MAX_RESULTS
            break
        # An empty page that still points onward means a newer server dropped
        # the whole page via minRelevance.
        server_filtered_all = (
            not resp.results and server_min is not None and (next_cursor or next_page)
        )
        if (scored and not relevant) or server_filtered_all:
            out.stopped_because = STOP_BELOW_THRESHOLD
            break
        if not new or (next_cursor is None and next_page is None):
            out.stopped_because = STOP_EXHAUSTED
            break
        if out.pages_fetched >= MAX_PAGES:
            out.stopped_because = STOP_PAGE_CAP
            break
        cursor, page_no = next_cursor, (None if next_cursor else next_page)

    del out.results[max_results:]
    return out


async def collect_many(
    client: OpenIdeaClient,
    query: str,
    types: Sequence[ResourceType],
    **kw: Any,
) -> tuple[list[Scored], dict[str, dict[str, Any]]]:
    """Run `collect` for each type concurrently, merge, dedupe by id and sort
    by relevance (unknown last). Returns (merged, per-type info). A failing
    type is reported in its info instead of failing the whole call, unless
    every type failed or the key was rejected."""
    outcomes = await asyncio.gather(
        *(collect(client, query, type=t, **kw) for t in types),
        return_exceptions=True,
    )
    merged: dict[str, Scored] = {}
    by_type: dict[str, dict[str, Any]] = {}
    errors: list[BaseException] = []
    for t, outcome in zip(types, outcomes):
        if isinstance(outcome, OpenIdeaAuthError):
            raise outcome
        if isinstance(outcome, BaseException):
            errors.append(outcome)
            by_type[t.value] = {"error": f"{type(outcome).__name__}: {outcome}"}
            continue
        by_type[t.value] = {
            "returned": len(outcome.results),
            "stopped_because": outcome.stopped_because,
            "next_cursor": outcome.next_cursor,
        }
        for s in outcome.results:
            kept = merged.get(s.resource.id)
            if kept is None or (s.relevance or 0) > (kept.relevance or 0):
                merged[s.resource.id] = s
    if errors and len(errors) == len(types):
        raise errors[0]
    ordered = sorted(
        merged.values(),
        key=lambda s: (s.relevance is not None, s.relevance or 0.0),
        reverse=True,
    )
    return ordered, by_type


def _truncate(text: str, limit: int = DESCRIPTION_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render(s: Scored, detail: str = "compact") -> dict[str, Any]:
    rel = round(s.relevance, 2) if s.relevance is not None else None
    r = s.resource
    if detail == "full":
        full = r.model_dump(mode="json", exclude_none=True)
        full["relevance"] = rel
        return full
    item: dict[str, Any] = {
        "id": r.id,
        "type": r.type.value,
        "title": r.title,
        "url": r.url,
        "year": r.year,
        "source": r.source,
        "relevance": rel,
        "description": _truncate(r.description) if r.description else None,
        "authors": r.authors[:AUTHORS_SHOWN] if r.authors else None,
    }
    return {k: v for k, v in item.items() if v is not None}
