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
    assert len(r.namespaces) == 1
    ns = r.namespaces[0]
    assert ns.strategy == "hash"
    assert ns.hash_count == 3
    assert ns.slash_count == 0


def test_slash_strategy_ok():
    g = Graph()
    _ont(g, "http://example.org/ont")
    for name in ("Person", "Organization"):
        g.add((URIRef(f"http://example.org/ont/{name}"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.OK
    assert len(r.namespaces) == 1
    ns = r.namespaces[0]
    assert ns.strategy == "slash"
    assert ns.slash_count == 2
    assert ns.hash_count == 0


def test_mixed_strategy_warns():
    g = Graph()
    _ont(g, "http://example.org/ont")
    g.add((URIRef("http://example.org/ont#Person"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/ont/Organization"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.WARN
    assert len(r.namespaces) == 1
    ns = r.namespaces[0]
    assert ns.strategy == "mixed"
    assert ns.hash_count == 1
    assert ns.slash_count == 1
    assert ns.hash_examples and ns.slash_examples


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
    assert len(r.namespaces) == 1
    assert r.namespaces[0].strategy == "hash"
    assert r.namespaces[0].hash_count == 2


def test_different_styles_across_base_iris_does_not_warn():
    """Two declared base IRIs, each internally consistent but using a
    DIFFERENT style from each other, must not be flagged as mixed: style
    consistency is judged per base IRI, not pooled across all of them."""
    g = Graph()
    _ont(g, "http://example.org/hash-ont")
    _ont(g, "http://example.org/slash-ont")
    g.add((URIRef("http://example.org/hash-ont#Person"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/hash-ont#Organization"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/slash-ont/Person"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.OK
    assert len(r.namespaces) == 2
    by_ns = {ns.namespace: ns.strategy for ns in r.namespaces}
    assert by_ns["http://example.org/hash-ont"] == "hash"
    assert by_ns["http://example.org/slash-ont"] == "slash"


def test_mixed_within_one_base_iri_warns_even_with_other_consistent_base_iris():
    """A single base IRI that internally mixes hash and slash must still
    warn, even when other declared base IRIs are each perfectly consistent."""
    g = Graph()
    _ont(g, "http://example.org/clean-ont")
    _ont(g, "http://example.org/messy-ont")
    g.add((URIRef("http://example.org/clean-ont#Widget"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/messy-ont#Person"), RDF.type, OWL.Class))
    g.add((URIRef("http://example.org/messy-ont/Organization"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.WARN
    mixed = [ns for ns in r.namespaces if ns.strategy == "mixed"]
    assert len(mixed) == 1
    assert mixed[0].namespace == "http://example.org/messy-ont"


def test_host_root_is_not_treated_as_own_namespace():
    """A slash ontology IRI with no "#" must not swallow the entire host."""
    g = Graph()
    _ont(g, "http://example.org/dataset")
    g.add((URIRef("http://example.org/unrelated/Thing"), RDF.type, OWL.Class))
    r = check_iri_strategy(g)
    assert r.status == Status.SKIP
