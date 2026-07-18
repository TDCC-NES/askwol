"""Tests for term validator."""

from rdflib import Graph

from askwol.cache import OntologyCache
from askwol.models import Status
from askwol.term_validator import validate_terms

REMOTE_TURTLE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/vocab#RealClass> a owl:Class ;
    rdfs:label "Real Class" .

<http://example.org/vocab#realProp> a owl:ObjectProperty .
"""


def test_term_exists():
    cache = OntologyCache()
    g = Graph()
    g.parse(data=REMOTE_TURTLE, format="turtle")
    cache.put("http://example.org/vocab#", g)

    results = validate_terms("v", "http://example.org/vocab#", {"RealClass", "realProp"}, cache)
    assert all(r.status == Status.OK for r in results)


def test_term_not_found():
    cache = OntologyCache()
    g = Graph()
    g.parse(data=REMOTE_TURTLE, format="turtle")
    cache.put("http://example.org/vocab#", g)

    results = validate_terms("v", "http://example.org/vocab#", {"MadeUpClass"}, cache)
    assert len(results) == 1
    assert results[0].status == Status.FAIL
    assert "not found" in results[0].error.lower()


def test_mixed_terms():
    cache = OntologyCache()
    g = Graph()
    g.parse(data=REMOTE_TURTLE, format="turtle")
    cache.put("http://example.org/vocab#", g)

    results = validate_terms("v", "http://example.org/vocab#", {"RealClass", "FakeClass"}, cache)
    by_name = {r.local_name: r for r in results}
    assert by_name["RealClass"].status == Status.OK
    assert by_name["FakeClass"].status == Status.FAIL


def test_deprecated_upstream_term_is_warned():
    cache = OntologyCache()
    g = Graph()
    g.parse(
        data=REMOTE_TURTLE + "\n<http://example.org/vocab#OldClass> a owl:DeprecatedClass .\n",
        format="turtle",
    )
    cache.put("http://example.org/vocab#", g)

    results = validate_terms("v", "http://example.org/vocab#", {"RealClass", "OldClass"}, cache)
    by_name = {r.local_name: r for r in results}
    assert by_name["RealClass"].status == Status.OK
    assert by_name["RealClass"].deprecated is None
    assert by_name["OldClass"].status == Status.WARN
    assert by_name["OldClass"].deprecated == "owl:DeprecatedClass"


def test_namespace_not_cached():
    cache = OntologyCache()
    results = validate_terms("missing", "http://example.org/nope/", {"SomeTerm"}, cache)
    assert len(results) == 1
    assert results[0].status == Status.SKIP


def test_namespace_cached_with_error():
    cache = OntologyCache()
    cache.put("http://example.org/err/", graph=None, error="HTTP 500")
    results = validate_terms("e", "http://example.org/err/", {"X"}, cache)
    assert len(results) == 1
    assert results[0].status == Status.SKIP
    assert "500" in results[0].error


# --- XSD built-in allowlist tests ---

XSD_NS = "http://www.w3.org/2001/XMLSchema#"


def test_xsd_valid_types():
    cache = OntologyCache()
    results = validate_terms("xsd", XSD_NS, {"string", "integer", "dateTime", "boolean"}, cache)
    assert all(r.status == Status.OK for r in results), [r.error for r in results]


def test_xsd_invalid_type():
    cache = OntologyCache()
    results = validate_terms("xsd", XSD_NS, {"madeUpType"}, cache)
    assert len(results) == 1
    assert results[0].status == Status.FAIL
    assert "XSD" in results[0].error


def test_xsd_mixed():
    cache = OntologyCache()
    results = validate_terms("xsd", XSD_NS, {"string", "madeUpType"}, cache)
    by_name = {r.local_name: r for r in results}
    assert by_name["string"].status == Status.OK
    assert by_name["madeUpType"].status == Status.FAIL
