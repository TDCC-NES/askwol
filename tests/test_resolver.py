"""Tests for namespace resolver."""

import httpx
import pytest
import respx
from rdflib import Graph

from askwol.cache import OntologyCache
from askwol.models import Status
from askwol.resolver import resolve_namespace, resolve_all_namespaces

SAMPLE_TURTLE = b"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/onto#MyClass> a owl:Class ;
    rdfs:label "My Class" .
"""


@pytest.mark.asyncio
@respx.mock
async def test_resolve_namespace_success():
    respx.get("http://example.org/onto#").mock(
        return_value=httpx.Response(
            200,
            content=SAMPLE_TURTLE,
            headers={"content-type": "text/turtle"},
        )
    )

    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("ex", "http://example.org/onto#", client, cache)

    assert result.status == Status.OK
    assert result.http_status == 200
    assert result.is_valid_rdf is True
    # Should be cached now
    assert cache.has("http://example.org/onto#")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_namespace_404():
    respx.get("http://example.org/missing/").mock(
        return_value=httpx.Response(404)
    )

    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("miss", "http://example.org/missing/", client, cache)

    assert result.status == Status.FAIL
    assert result.http_status == 404


@pytest.mark.asyncio
@respx.mock
async def test_resolve_namespace_http_error():
    respx.get("http://example.org/timeout/").mock(side_effect=httpx.ConnectTimeout("timeout"))

    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("to", "http://example.org/timeout/", client, cache)

    assert result.status == Status.FAIL
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
@respx.mock
async def test_resolve_all_namespaces():
    respx.get("http://example.org/a#").mock(
        return_value=httpx.Response(200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"})
    )
    respx.get("http://example.org/b/").mock(
        return_value=httpx.Response(404)
    )

    cache = OntologyCache()
    results = await resolve_all_namespaces({"a": "http://example.org/a#", "b": "http://example.org/b/"}, cache)

    assert len(results) == 2
    by_prefix = {r.prefix: r for r in results}
    assert by_prefix["a"].status == Status.OK
    assert by_prefix["b"].status == Status.FAIL


@pytest.mark.asyncio
async def test_resolve_uses_cache():
    cache = OntologyCache()
    g = Graph()
    g.parse(data=SAMPLE_TURTLE.decode(), format="turtle")
    cache.put("http://example.org/cached#", g)

    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("c", "http://example.org/cached#", client, cache)

    assert result.status == Status.OK
