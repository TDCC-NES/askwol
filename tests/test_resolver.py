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
    route = respx.get("http://example.org/onto#").mock(
        return_value=httpx.Response(
            200,
            content=SAMPLE_TURTLE,
            headers={"content-type": "text/turtle"},
        )
    )

    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("ex", "http://example.org/onto#", client, cache)
        cached = await resolve_namespace("alias", "http://example.org/onto#", client, cache)

    assert result.status == Status.OK
    assert result.http_status == 200
    assert result.is_valid_rdf is True
    assert result.retrieved_url == "http://example.org/onto#"
    assert result.discovery_note is None
    assert cached.model_dump() == {**result.model_dump(), "prefix": "alias"}
    assert route.call_count == 1
    # Should be cached now
    assert cache.has("http://example.org/onto#")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_namespace_404():
    route = respx.get("http://example.org/missing/").mock(
        return_value=httpx.Response(404, headers={"content-type": "text/html"})
    )

    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("miss", "http://example.org/missing/", client, cache)
        cached = await resolve_namespace("miss", "http://example.org/missing/", client, cache)

    assert result.status == Status.FAIL
    assert result.http_status == 404
    assert result.content_type == "text/html"
    assert cached == result
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_resolve_namespace_http_error():
    respx.get("http://example.org/timeout/").mock(side_effect=httpx.ConnectTimeout(""))

    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("to", "http://example.org/timeout/", client, cache)

    assert result.status == Status.FAIL
    assert "timed out" in result.error.lower()


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
        cached = await resolve_namespace("ex", original, client, cache)
    assert result.is_valid_rdf
    assert result.uri == original
    assert result.retrieved_url == "https://example.org/rdf/vocab.ttl"
    assert result.content_type == "text/html"
    assert result.discovery_note and "HTML" in result.discovery_note
    assert cached == result
    assert str(next(cache.get(original).subjects())) == "https://example.org/rdf/vocab.ttl#Term"


@pytest.mark.asyncio
@respx.mock
async def test_configured_alternative_is_disclosed_and_cached(monkeypatch):
    original = "https://example.org/vocabulary#"
    alternative = "https://example.org/ontology.ttl"
    monkeypatch.setattr("askwol.resolver.NAMESPACE_REDIRECTS", {original: alternative})
    route = respx.get(alternative).mock(return_value=httpx.Response(
        200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"},
    ))
    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        first = await resolve_namespace("ex", original, client, cache)
        second = await resolve_namespace("ex", original, client, cache)
    assert first.status == Status.OK
    assert first.retrieved_url == alternative
    assert "configured alternative" in first.discovery_note
    assert first == second
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_resolver_jsonld_context_obeys_client_timeout(monkeypatch):
    from askwol import rdf_io

    observed_timeouts = []

    def context_document(url, **kwargs):
        observed_timeouts.append(kwargs["timeout"])
        return b'{"@context": {}}', url, "application/ld+json"

    monkeypatch.setattr(rdf_io, "fetch_document", context_document)
    iri = "https://example.org/ontology.jsonld"
    respx.get(iri).mock(return_value=httpx.Response(
        200, json={
            "@context": "https://example.org/context",
            "@id": "https://example.org/Thing",
            "@type": "http://www.w3.org/2002/07/owl#Class",
        }, headers={"content-type": "application/ld+json"},
    ))
    async with httpx.AsyncClient(timeout=0.25) as client:
        result = await resolve_namespace("ex", iri, client, OntologyCache())
    assert result.is_valid_rdf is True
    assert observed_timeouts == [0.25]


@pytest.mark.parametrize("uri", ["https://example.org/\x00", "https://example.org:bad/vocabulary"])
@pytest.mark.asyncio
@respx.mock
async def test_malformed_namespace_url_produces_informative_cached_failure(uri):
    cache = OntologyCache()
    async with httpx.AsyncClient() as client:
        first = await resolve_namespace("ex", uri, client, cache)
        second = await resolve_namespace("ex", uri, client, cache)
    assert first.status == Status.FAIL
    assert "Invalid document URL" in first.error
    assert "namespace or import URL" in first.error
    assert first == second


@pytest.mark.parametrize("invalid_link", [
    "https://example.org:bad/broken.ttl", "https://[bad]/broken.ttl",
])
@pytest.mark.asyncio
@respx.mock
async def test_invalid_discovered_document_url_does_not_hide_later_valid_link(invalid_link):
    iri = "https://example.org/vocabulary"
    respx.get(iri).mock(return_value=httpx.Response(
        200, text=(
            f'<html><a href="{invalid_link}">Broken</a>'
            '<a href="valid.ttl">RDF</a></html>'
        ), headers={"content-type": "text/html"},
    ))
    respx.get("https://example.org/valid.ttl").mock(return_value=httpx.Response(
        200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"},
    ))
    async with httpx.AsyncClient() as client:
        result = await resolve_namespace("ex", iri, client, OntologyCache())
    assert result.status == Status.OK
    assert result.is_valid_rdf is True
    assert result.retrieved_url == "https://example.org/valid.ttl"
