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
from askwol.resolver import resolve_namespace
from askwol.severity import Rule

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


@pytest.mark.asyncio
@respx.mock
async def test_import_html_discovery_warns_without_changing_cached_namespace_result():
    iri = "https://example.org/imported"
    raw_url = "https://example.org/imported.ttl"
    html_route = respx.get(iri).mock(return_value=httpx.Response(
        200, text='<html><link type="text/turtle" href="imported.ttl"></html>',
        headers={"content-type": "text/html"},
    ))
    rdf_route = respx.get(raw_url).mock(return_value=httpx.Response(
        200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"},
    ))
    graph = Graph()
    graph.add((ONT, OWL.imports, URIRef(iri)))
    cache = OntologyCache()
    first = await check_imports(graph, cache)
    second = await check_imports(graph, cache)
    async with httpx.AsyncClient() as client:
        namespace = await resolve_namespace("ex", iri, client, cache)

    assert first.status == Status.WARN
    assert first == second
    resolution = first.checks[0].resolution
    assert resolution.status == Status.WARN
    assert resolution.is_valid_rdf is True
    assert resolution.error is None
    assert resolution.uri == iri
    assert resolution.content_type == "text/html"
    assert resolution.retrieved_url == raw_url
    assert "owl:imports" in resolution.discovery_note
    assert first.findings()[0].rule == Rule.IMPORT_DISCOVERED
    assert namespace.status == Status.OK
    assert namespace.discovery_note and "owl:imports" not in namespace.discovery_note
    assert html_route.call_count == rdf_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_import_configured_alternative_warns(monkeypatch):
    iri = "https://example.org/imported#"
    alternative = "https://example.org/imported.ttl"
    monkeypatch.setattr("askwol.resolver.NAMESPACE_REDIRECTS", {iri: alternative})
    respx.get(alternative).mock(return_value=httpx.Response(
        200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"},
    ))
    graph = Graph()
    graph.add((ONT, OWL.imports, URIRef(iri)))
    report = await check_imports(graph, OntologyCache())
    assert report.status == Status.WARN
    assert report.checks[0].resolution.retrieved_url == alternative
    assert report.findings()[0].rule == Rule.IMPORT_DISCOVERED


@pytest.mark.asyncio
@respx.mock
async def test_import_http_redirect_is_direct_resolution():
    iri = "https://example.org/imported"
    raw_url = "https://example.org/imported.ttl"
    respx.get(iri).mock(return_value=httpx.Response(302, headers={"location": raw_url}))
    respx.get(raw_url).mock(return_value=httpx.Response(
        200, content=SAMPLE_TURTLE, headers={"content-type": "text/turtle"},
    ))
    graph = Graph()
    graph.add((ONT, OWL.imports, URIRef(iri)))
    report = await check_imports(graph, OntologyCache())
    assert report.status == Status.OK
    assert report.checks[0].resolution.retrieved_url == raw_url
    assert report.checks[0].resolution.discovery_note is None
    assert report.findings() == []


@pytest.mark.parametrize("malformed_redirect", [False, True])
@pytest.mark.asyncio
@respx.mock
async def test_import_with_malformed_url_reports_failure(malformed_redirect):
    malformed_url = "https://example.org:bad/imported.ttl"
    iri = "https://example.org/imported" if malformed_redirect else malformed_url
    if malformed_redirect:
        respx.get(iri).mock(return_value=httpx.Response(
            302, headers={"location": malformed_url},
        ))
    graph = Graph()
    graph.add((ONT, OWL.imports, URIRef(iri)))
    report = await check_imports(graph, OntologyCache())
    assert report.status == Status.FAIL
    assert report.broken[0].resolution.error.startswith("Invalid document URL")
    assert report.findings()[0].rule == Rule.IMPORT_UNRESOLVED
