"""Tests for the owl:imports resolution check."""

import httpx
import pytest
import respx
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF

from askwol.cache import OntologyCache
from askwol.imports_check import check_imports
from askwol.models import Status

ONT = URIRef("https://example.org/ont")

SAMPLE_TURTLE = b"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<http://example.org/imported#Thing> a owl:Class .
"""


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
