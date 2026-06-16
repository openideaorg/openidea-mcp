"""Pydantic models mirroring the Open Idea Resource API contract.

Defined from scratch from the public API docs — no import from the Ecosyz-search
repo so this package stays independently deployable.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResourceType(str, Enum):
    paper = "paper"
    dataset = "dataset"
    code = "code"
    model = "model"
    hardware = "hardware"
    video = "video"


class ResourceProvider(str, Enum):
    openalex = "openalex"
    arxiv = "arxiv"
    zenodo = "zenodo"
    swh = "swh"
    ckan = "ckan"
    huggingface = "huggingface"
    paperswithcode = "paperswithcode"
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
    source: ResourceProvider
    url: str
    authors: list[str] | None = None
    year: int | None = None
    license: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None
    score: float | None = None


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
    total: int = 0
    page: int | None = None
    limit: int | None = None
    hasMore: bool | None = None
    nextCursor: str | None = None
    coverage: SearchCoverage | None = None
