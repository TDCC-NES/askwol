"""Tests for the owl:imports resolution check."""

import httpx
import pytest
import respx
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF

from askwol import network
from askwol.cache import OntologyCache
from askwol.imports_check import check_imports
from askwol.models import Status

ONT = URIRef("https://example.org/ont")

SAMPLE_TURTLE = b"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<http://example.org/imported#Thing> a owl:Class .
"""


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *_args: [(2, 1, 6, "", ("93.184.216.34", 0))])


@pytest.mark.asyncio
async def test_imports_ok_when_none_declared():
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    report = await check_imports(g, OntologyCache())
    assert report.status == Status.OK
    assert report.checks == []


@pytest.mark.asyncio
@respx.mock
async def test_imports_ok_when_declared_import_resolves():
    respx.get("http://example.org/imported#").mock(
        return_value=httpx.Response(
            200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"},
        )
    )
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, OWL.imports, URIRef("http://example.org/imported#")))

    report = await check_imports(g, OntologyCache())

    assert report.status == Status.OK
    assert len(report.checks) == 1
    assert report.checks[0].iri == "http://example.org/imported#"
    assert report.checks[0].resolution.status == Status.OK
    assert not report.broken


@pytest.mark.asyncio
@respx.mock
async def test_imports_fail_when_declared_import_is_broken():
    respx.get("http://example.org/missing#").mock(return_value=httpx.Response(404))
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, OWL.imports, URIRef("http://example.org/missing#")))

    report = await check_imports(g, OntologyCache())

    assert report.status == Status.FAIL
    assert len(report.broken) == 1
    assert report.broken[0].iri == "http://example.org/missing#"
    assert report.broken[0].resolution.http_status == 404


@pytest.mark.asyncio
@respx.mock
async def test_imports_dedupes_repeated_declarations():
    respx.get("http://example.org/imported#").mock(
        return_value=httpx.Response(
            200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"},
        )
    )
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, OWL.imports, URIRef("http://example.org/imported#")))
    other = URIRef("https://example.org/other")
    g.add((other, RDF.type, OWL.Ontology))
    g.add((other, OWL.imports, URIRef("http://example.org/imported#")))

    report = await check_imports(g, OntologyCache())

    assert len(report.checks) == 1


@pytest.mark.asyncio
async def test_imports_ignores_non_uri_objects():
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, OWL.imports, Literal("not a uri")))

    report = await check_imports(g, OntologyCache())

    assert report.status == Status.OK
    assert report.checks == []


@pytest.mark.parametrize('cached', [False, True])
@pytest.mark.asyncio
@respx.mock
async def test_reachable_non_rdf_import_fails(cached):
    iri = 'https://example.org/not-rdf'
    route = respx.get(iri).mock(return_value=httpx.Response(
        200, text='<html><body>No RDF here.</body></html>',
        headers={'content-type': 'text/html'},
    ))
    graph = Graph()
    graph.add((ONT, OWL.imports, URIRef(iri)))
    cache = OntologyCache()
    if cached:
        cache.put(iri, None)
    report = await check_imports(graph, cache)
    assert report.status == Status.FAIL
    assert len(report.findings()) == 1
    assert report.broken[0].resolution.error == 'Import did not provide parseable RDF.'
    assert route.call_count == (0 if cached else 1)


@pytest.mark.parametrize('body, content_type', [
    (SAMPLE_TURTLE, 'text/turtle'),
    (b'@prefix ex: <https://example.org/> .', 'text/turtle'),
    (SAMPLE_TURTLE, 'text/html'),
])
@pytest.mark.asyncio
@respx.mock
async def test_known_namespace_import_still_requires_rdf_retrieval(body, content_type):
    iri = 'http://www.w3.org/2001/XMLSchema#'
    route = respx.get(iri).mock(return_value=httpx.Response(
        200, content=body, headers={'content-type': content_type},
    ))
    graph = Graph()
    graph.add((ONT, OWL.imports, URIRef(iri)))
    report = await check_imports(graph, OntologyCache())
    assert route.call_count == 1
    assert report.status == Status.OK
    assert report.checks[0].resolution.is_valid_rdf is True


@pytest.mark.asyncio
@respx.mock
async def test_imports_remain_direct_only():
    iri = 'https://example.org/direct'
    respx.get(iri).mock(return_value=httpx.Response(
        200, content=b'<urn:ontology> <http://www.w3.org/2002/07/owl#imports> <https://example.org/nested> .',
        headers={'content-type': 'text/turtle'},
    ))
    graph = Graph()
    graph.add((ONT, OWL.imports, URIRef(iri)))
    report = await check_imports(graph, OntologyCache())
    assert report.status == Status.OK
    assert [check.iri for check in report.checks] == [iri]
