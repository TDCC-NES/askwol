"""Tests for the per-host http vs https IRI scheme check."""

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from askwol.iri_scheme import check_iri_scheme
from askwol.models import Status


def test_skipped_with_no_http_iris():
    g = Graph()
    r = check_iri_scheme(g, {})
    assert r.status == Status.SKIP


def test_ok_when_each_host_uses_one_scheme():
    g = Graph()
    g.add((URIRef("https://example.org/A"), RDF.type, OWL.Class))
    g.add((URIRef("http://other.org/B"), RDF.type, OWL.Class))
    r = check_iri_scheme(g, {"ex": "https://example.org/", "ot": "http://other.org/"})
    assert r.status == Status.OK
    # Two custom hosts plus www.w3.org from RDF.type / OWL.Class predicates.
    assert r.total_hosts >= 2
    assert r.conflicts == []


def test_warns_on_mixed_scheme_for_same_host():
    g = Graph()
    g.add((URIRef("https://example.org/A"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/B"), RDF.type, OWL.Class))
    r = check_iri_scheme(g, {})
    assert r.status == Status.WARN
    assert len(r.conflicts) == 1
    c = r.conflicts[0]
    assert c.host == "example.org"
    assert c.http_count >= 1 and c.https_count >= 1
    assert c.http_examples and c.https_examples


def test_namespace_contributes_to_host_grouping():
    g = Graph()
    g.add((URIRef("http://example.org/A"), RDF.type, OWL.Class))
    # The graph alone only sees http://example.org, but the bound namespace
    # introduces https://example.org which should trigger a conflict.
    r = check_iri_scheme(g, {"ex": "https://example.org/"})
    assert r.status == Status.WARN
    assert r.conflicts[0].host == "example.org"


def test_host_comparison_is_case_insensitive():
    g = Graph()
    g.add((URIRef("https://Example.ORG/A"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/B"), RDF.type, OWL.Class))
    r = check_iri_scheme(g, {})
    assert r.status == Status.WARN
    assert r.conflicts[0].host == "example.org"


def test_hosts_list_populated_for_non_conflicting_hosts():
    g = Graph()
    g.add((URIRef("https://example.org/A"), RDF.type, OWL.Class))
    g.add((URIRef("http://other.org/B"), RDF.type, OWL.Class))
    r = check_iri_scheme(g, {"ex": "https://example.org/", "ot": "http://other.org/"})
    assert r.status == Status.OK
    hosts = {h.host: h.scheme for h in r.hosts}
    assert hosts.get("example.org") == "https"
    assert hosts.get("other.org") == "http"


def test_hosts_list_excludes_conflicting_hosts():
    g = Graph()
    g.add((URIRef("https://example.org/A"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/B"), RDF.type, OWL.Class))
    r = check_iri_scheme(g, {})
    assert r.status == Status.WARN
    assert all(h.host != "example.org" for h in r.hosts)
