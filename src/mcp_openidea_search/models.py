"""Pydantic models mirroring the Open Idea Resource API contract.

Defined from scratch from the public API docs — no import from the Ecosyz-search
repo so this package stays independently deployable.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResourceType(str, Enum):
    paper = "paper"
    dataset = "dataset"
    code = "code"
    model = "model"
    hardware = "hardware"
    video = "video"


class ResourceProvider(str, Enum):
    """Providers known when this package was released.

    Documentation only: `Resource.source` is a plain string because Open Idea
    adds providers server-side, and a strict enum would reject every result
    from a provider this package has not heard of yet. `GET /api/v1/sources`
    (see `OpenIdeaClient.list_sources`) is the live list.
    """

    openalex = "openalex"
    arxiv = "arxiv"
    zenodo = "zenodo"
    swh = "swh"
    ckan = "ckan"
    huggingface = "huggingface"
    youtube = "youtube"
    github = "github"
    gitlab = "gitlab"
    figshare = "figshare"
    kaggle = "kaggle"
    custom = "custom"


class Resource(BaseModel):
    """A single normalized search result."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: ResourceType
    title: str
    # Any provider name; see ResourceProvider for why this is not the enum.
    source: str
    url: str
    authors: list[str] | None = None
    year: int | None = None
    license: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None
    score: float | None = None
    # Normalized 0..1 relevance. Newer servers send it; older ones only send
    # `score`, whose scale varies by provider (the tools derive a fallback).
    relevance: float | None = None


class SearchCoverage(BaseModel):
    model_config = ConfigDict(extra="allow")

    requestedProviders: list[str] = Field(default_factory=list)
    receivedCounts: dict[str, int] = Field(default_factory=dict)
    uniqueBefore: int = 0
    uniqueAfter: int = 0
    merged: int = 0


class SearchResponse(BaseModel):
    """Shape returned by GET /api/v1/search."""

    model_config = ConfigDict(extra="allow")

    results: list[Resource] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coalesce_items(cls, data: Any) -> Any:
        """The live API returns hits under `items` (and an empty `results`).
        Fold `items` into `results` and drop it, so callers always read a
        populated `results` and nothing leaks back out under `items`."""
        if isinstance(data, dict) and data.get("items") is not None:
            data = {**data, "results": data["items"]}
            data.pop("items", None)
        return data
    total: int = 0
    page: int | None = None
    limit: int | None = None
    hasMore: bool | None = None
    nextCursor: str | None = None
    coverage: SearchCoverage | None = None
    ranking: Any | None = None


class Source(BaseModel):
    """One entry of GET /api/v1/sources."""

    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    pillar: str | None = None
    types: list[str] = Field(default_factory=list)
    tier: str | None = None
    unlocked: bool | None = None
    configured: bool | None = None


class SourcePack(BaseModel):
    """A named bundle of sources, e.g. "life sciences"."""

    model_config = ConfigDict(extra="allow")

    id: str
    label: str | None = None
    description: str | None = None
    sources: list[str] = Field(default_factory=list)


class SourcesResponse(BaseModel):
    """Shape returned by GET /api/v1/sources (newer servers only)."""

    model_config = ConfigDict(extra="allow")

    sources: list[Source] = Field(default_factory=list)
    packs: list[SourcePack] = Field(default_factory=list)
