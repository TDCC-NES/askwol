"""Tests for namespace resolver."""

import httpx
import pytest
import respx
from rdflib import Graph

from askwol.cache import OntologyCache
from askwol.models import Status
from askwol import network
from askwol.resolver import resolve_all_namespaces, resolve_namespace

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
async def test_resolve_all_namespaces(monkeypatch):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *_args: [(2, 1, 6, "", ("93.184.216.34", 0))])
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


@pytest.mark.asyncio
@respx.mock
async def test_cached_non_rdf_response_stays_non_rdf():
    route = respx.get("https://example.org/plain").mock(
        return_value=httpx.Response(200, text="This is not RDF.", headers={"content-type": "text/plain"})
    )
    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        first = await resolve_namespace("ex", "https://example.org/plain", client, cache)
        second = await resolve_namespace("ex", "https://example.org/plain", client, cache)
    assert first.is_valid_rdf is False
    assert second.is_valid_rdf is False
    assert cache.get("https://example.org/plain") is None
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_redirected_rdf_and_discovered_links_use_final_document_base():
    original = "https://example.org/vocabulary"
    respx.get(original).mock(return_value=httpx.Response(302, headers={"location": "/docs/index.html"}))
    respx.get("https://example.org/docs/index.html").mock(return_value=httpx.Response(
        200, text='<html><link rel="alternate" type="text/turtle" href="vocab.ttl"></html>',
        headers={"content-type": "text/html"},
    ))
    respx.get("https://example.org/docs/vocab.ttl").mock(return_value=httpx.Response(
        302, headers={"location": "/rdf/vocab.ttl"},
    ))
    respx.get("https://example.org/rdf/vocab.ttl").mock(return_value=httpx.Response(
        200, content=b'<#Term> a <http://www.w3.org/2002/07/owl#Class> .',
        headers={"content-type": "text/turtle"},
    ))
    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("ex", original, client, cache)
    assert result.is_valid_rdf
    assert str(next(cache.get(original).subjects())) == "https://example.org/rdf/vocab.ttl#Term"
