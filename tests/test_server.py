"""Tests for the MCP server module.

We can't easily round-trip through the MCP SDK's transport in unit tests without
a full client+server stdio pair, so these tests cover:
  1. build_server() returns a usable Server with the expected name.
  2. The SEARCH_PRESETS dict matches the documented tool surface.
  3. The URI prefix is what callers expect.
End-to-end transport behavior is verified via the MCP Inspector in the README.
"""
from __future__ import annotations

import pytest

from mcp_openidea_search.client import OpenIdeaClient
from mcp_openidea_search.models import Resource, ResourceType
from mcp_openidea_search.server import (
    SEARCH_PRESETS,
    SUGGESTED_MODEL,
    URI_PREFIX,
    build_handoff_markdown,
    build_server,
    candidate_ids_for_ref,
    clamp_limit,
    format_citation,
    lab_handoff_bundle,
    merge_resources,
    meta_link_ids,
    neighbourhood_for,
    normalize_paper_ref,
    parse_page,
    resolve_paper_ref,
    seed_search_queries,
    strip_resource_ref,
)


def test_search_presets_cover_all_resource_types_except_all():
    assert set(SEARCH_PRESETS.values()) == set(ResourceType)


def test_uri_prefix_is_openidea_scheme():
    assert URI_PREFIX == "openidea://"


@pytest.mark.asyncio
async def test_build_server_returns_named_server():
    async with OpenIdeaClient(base_url="https://example.test", api_key="oi_live_test") as client:
        server = build_server(client)
    assert server.name == "openidea-search"


def _paper(rid: str, source: str = "openalex") -> Resource:
    return Resource(
        id=rid,
        type=ResourceType.paper,
        title="Attention Is All You Need",
        source=source,  # type: ignore[arg-type]
        url=f"https://example.test/{rid}",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017,
    )


def test_clamp_limit_clamps_to_1_to_100():
    assert clamp_limit(20) == 20
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1
    assert clamp_limit(1000) == 100
    assert clamp_limit(None) == 20
    with pytest.raises(ValueError):
        clamp_limit("many")


def test_parse_page_none_when_omitted():
    assert parse_page(None) is None
    assert parse_page(2) == 2
    with pytest.raises(ValueError):
        parse_page(0)
    with pytest.raises(ValueError):
        parse_page("soon")


def test_strip_resource_ref_accepts_id_and_uri():
    assert strip_resource_ref("openalex:W42") == "openalex:W42"
    assert strip_resource_ref("openidea://openalex:W42") == "openalex:W42"
    with pytest.raises(ValueError):
        strip_resource_ref("")
    with pytest.raises(ValueError):
        strip_resource_ref("openidea://")


def test_format_citation_styles():
    r = _paper("openalex:W42")
    md = format_citation(r, "markdown")
    assert "Attention Is All You Need" in md and "openalex" in md
    apa = format_citation(r, "apa")
    assert apa.startswith("Ashish Vaswani, Noam Shazeer (2017).")
    bib = format_citation(r, "bibtex")
    assert bib.startswith("@misc{openalex_W42,")
    assert "year={2017}" in bib
    with pytest.raises(ValueError):
        format_citation(r, "chicago")


def test_format_citation_handles_missing_metadata():
    r = Resource(
        id="zenodo:456",
        type=ResourceType.dataset,
        title="Untitled dump",
        source="zenodo",  # type: ignore[arg-type]
        url="https://example.test/456",
    )
    assert "n.d." in format_citation(r, "apa")
    assert "n.a." in format_citation(r, "markdown")


def test_merge_resources_dedupes_and_covers():
    a = [_paper("openalex:W1"), _paper("openalex:W2")]
    b = [_paper("openalex:W2"), _paper("arxiv:1", source="arxiv")]
    merged, coverage = merge_resources([a, b])
    assert [r.id for r in merged] == ["openalex:W1", "openalex:W2", "arxiv:1"]
    assert coverage["uniqueBefore"] == 4
    assert coverage["uniqueAfter"] == 3
    assert coverage["merged"] == 1
    assert coverage["receivedCounts"] == {"openalex": 3, "arxiv": 1}


def test_normalize_paper_ref_strips_schemes():
    assert normalize_paper_ref("openidea://openalex:W42") == "openalex:W42"
    assert normalize_paper_ref("doi:10.1234/abc") == "10.1234/abc"
    assert normalize_paper_ref("https://doi.org/10.1234/abc") == "10.1234/abc"
    assert normalize_paper_ref("arxiv:1706.03762") == "1706.03762"


def test_candidate_ids_cover_doi_arxiv_openalex():
    assert "doi:10.1234/abc" in candidate_ids_for_ref("10.1234/abc")
    assert "arxiv:1706.03762" in candidate_ids_for_ref("1706.03762")
    assert "openalex:W42" in candidate_ids_for_ref("W42")
    assert candidate_ids_for_ref("openalex:W42") == ["openalex:W42"]


def test_seed_search_queries_title_first():
    r = _paper("openalex:W1")
    qs = seed_search_queries(r)
    assert qs[0].startswith("Attention Is All You Need")
    assert any("Vaswani" in q for q in qs)


def test_meta_link_ids_collect_and_exclude_seed():
    r = _paper("openalex:W1")
    r.meta = {"references": ["openalex:W2", {"id": "openalex:W3"}], "related": ["openalex:W1"]}
    assert meta_link_ids(r) == ["openalex:W2", "openalex:W3"]


def test_build_handoff_markdown_has_model_hint_and_notes():
    r = _paper("openalex:W42")
    md = build_handoff_markdown("Diffusion MRI", [(r, format_citation(r))], notes="focus on tractography")
    assert "Lab handoff: Diffusion MRI" in md
    assert SUGGESTED_MODEL in md
    assert "tractography" in md


class _FakeClient:
    def __init__(self, resources: dict, search_hits: list | None = None):
        self._resources = resources
        self._hits = search_hits or []

    async def get_resource(self, rid: str):
        return self._resources.get(rid)

    async def search(self, query, type=None, limit=20, page=None):
        from mcp_openidea_search.models import SearchResponse

        return SearchResponse(results=list(self._hits), total=len(self._hits))


@pytest.mark.asyncio
async def test_resolve_paper_direct_hit():
    seed = _paper("openalex:W42")
    out = await resolve_paper_ref(_FakeClient({"openalex:W42": seed}), "openidea://openalex:W42")
    assert out["method"] == "direct"
    assert out["resolved"]["id"] == "openalex:W42"


@pytest.mark.asyncio
async def test_resolve_paper_search_fallback():
    hits = [_paper("openalex:W9"), _paper("openalex:W10")]
    out = await resolve_paper_ref(_FakeClient({}, hits), "some novel title")
    assert out["method"] == "search"
    assert out["resolved"]["id"] == "openalex:W9"
    assert len(out["candidates"]) == 1


@pytest.mark.asyncio
async def test_neighbourhood_search_fallback_excludes_seed():
    seed = _paper("openalex:W1")
    hits = [seed, _paper("openalex:W2")]
    out = await neighbourhood_for(_FakeClient({"openalex:W1": seed}, hits), "openalex:W1", limit=5)
    assert out["strategy"] == "search"
    assert [n["id"] for n in out["neighbours"]] == ["openalex:W2"]


@pytest.mark.asyncio
async def test_neighbourhood_meta_strategy():
    seed = _paper("openalex:W1")
    n2 = _paper("openalex:W2")
    seed.meta = {"references": ["openalex:W2"]}
    out = await neighbourhood_for(
        _FakeClient({"openalex:W1": seed, "openalex:W2": n2}), "openalex:W1"
    )
    assert out["strategy"] == "meta"
    assert [n["id"] for n in out["neighbours"]] == ["openalex:W2"]


@pytest.mark.asyncio
async def test_lab_handoff_bundle_marks_missing():
    seed = _paper("openalex:W42")
    out = await lab_handoff_bundle(
        _FakeClient({"openalex:W42": seed}),
        topic="Tractography",
        refs=["openalex:W42", "openalex:MISSING"],
        notes="n",
    )
    assert out["suggestedModel"] == SUGGESTED_MODEL
    assert out["missing"] == ["openalex:MISSING"]
    assert len(out["citations"]) == 1
    assert "Tractography" in out["markdown"]
