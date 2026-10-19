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


def test_mixed_terms():
    cache = OntologyCache()
    g = Graph()
    g.parse(data=REMOTE_TURTLE, format="turtle")
    cache.put("http://example.org/vocab#", g)

    results = validate_terms("v", "http://example.org/vocab#", {"RealClass", "realProp", "FakeClass"}, cache)
    assert len(results) == 3
    by_name = {r.local_name: r for r in results}
    assert set(by_name) == {"RealClass", "realProp", "FakeClass"}
    assert by_name["RealClass"].status == Status.OK
    assert by_name["realProp"].status == Status.OK
    assert by_name["FakeClass"].status == Status.FAIL
    assert "not found" in by_name["FakeClass"].error.lower()


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


def test_xsd_non_datatype_names_remain_recognised_vocabulary_terms():
    results = validate_terms("xsd", XSD_NS, {"minInclusive", "pattern", "length", "anyType"}, OntologyCache())
    assert all(result.status == Status.OK for result in results)


def test_xsd_mixed():
    cache = OntologyCache()
    valid_types = {"string", "integer", "dateTime", "boolean"}
    results = validate_terms("xsd", XSD_NS, valid_types | {"madeUpType"}, cache)
    assert len(results) == 5
    by_name = {r.local_name: r for r in results}
    assert set(by_name) == valid_types | {"madeUpType"}
    assert all(by_name[name].status == Status.OK for name in valid_types)
    assert by_name["madeUpType"].status == Status.FAIL
    assert "XSD" in by_name["madeUpType"].error
