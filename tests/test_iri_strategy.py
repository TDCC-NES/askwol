"""Tests for the hash-vs-slash IRI strategy check."""

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from askwol.iri_strategy import check_iri_strategy
from askwol.models import Status


def _ont(graph: Graph, iri: str) -> URIRef:
    ref = URIRef(iri)
    graph.add((ref, RDF.type, OWL.Ontology))
    return ref


def test_skipped_without_owl_ontology():
    g = Graph()
    g.add((URIRef("http://example.org/ont/X"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.SKIP
    assert r.ontology_iri is None


def test_skipped_when_no_terms_in_own_namespace():
    g = Graph()
    _ont(g, "http://example.org/ont")
    # Only an external term defined here
    g.add((URIRef("http://other.org/Foo"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.SKIP


def test_hash_strategy_ok():
    g = Graph()
    _ont(g, "http://example.org/ont")
    for name in ("Person", "knows", "Place"):
        g.add((URIRef(f"http://example.org/ont#{name}"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.OK
    assert r.strategy == "hash"
    assert r.hash_count == 3
    assert r.slash_count == 0


def test_slash_strategy_ok():
    g = Graph()
    _ont(g, "http://example.org/ont")
    for name in ("Person", "Organization"):
        g.add((URIRef(f"http://example.org/ont/{name}"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.OK
    assert r.strategy == "slash"
    assert r.slash_count == 2
    assert r.hash_count == 0


def test_mixed_strategy_warns():
    g = Graph()
    _ont(g, "http://example.org/ont")
    g.add((URIRef("http://example.org/ont#Person"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/ont/Organization"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.WARN
    assert r.strategy == "mixed"
    assert r.hash_count == 1
    assert r.slash_count == 1
    assert r.hash_examples and r.slash_examples


def test_bundle_with_multiple_ontology_subjects_is_not_hidden_by_alphabetical_order():
    """A file can self-declare more than one owl:Ontology (e.g. the W3C PROV
    family bundles prov, prov-o, prov-dc, ... into one document). The terms
    of a later-sorting namespace must still be found, not hidden behind an
    alphabetically-earlier sibling that happens to define nothing."""
    g = Graph()
    _ont(g, "http://example.org/aux")  # sorts first alphabetically, defines nothing
    _ont(g, "http://example.org/main")  # sorts second, defines everything below
    for name in ("Person", "Organization"):
        g.add((URIRef(f"http://example.org/main#{name}"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.OK
    assert r.strategy == "hash"
    assert r.hash_count == 2


def test_host_root_is_not_treated_as_own_namespace():
    """A slash ontology IRI with no "#" must not swallow the entire host."""
    g = Graph()
    _ont(g, "http://example.org/dataset")
    g.add((URIRef("http://example.org/unrelated/Thing"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.SKIP
