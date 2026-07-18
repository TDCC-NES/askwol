"""Tests for shared IRI helpers in iri_utils.py."""

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from askwol.iri_utils import ontology_namespaces


def test_ontology_namespaces_matches_hash_and_slash_style_prefixes():
    """Ontology subject is the bare IRI; the declared namespace adds a separator."""
    g = Graph()
    g.add((URIRef("https://example.org/onto"), RDF.type, OWL.Ontology))
    ns = ontology_namespaces(g)
    assert "https://example.org/onto#" in ns
    assert "https://example.org/onto/" in ns


def test_ontology_namespaces_matches_exact_subject_as_namespace():
    """Some ontologies use their own IRI directly as the namespace (no separator added)."""
    g = Graph()
    g.add((URIRef("https://example.org/onto#"), RDF.type, OWL.Ontology))
    ns = ontology_namespaces(g)
    assert "https://example.org/onto#" in ns


def test_ontology_namespaces_empty_without_owl_ontology_declaration():
    g = Graph()
    assert ontology_namespaces(g) == set()


def test_include_parent_path_false_drops_broad_host_fallback_for_slash_iri():
    """A slash-style ontology IRI's parent path claims the whole host - opt-out."""
    g = Graph()
    g.add((URIRef("https://example.org/dataset"), RDF.type, OWL.Ontology))
    assert "https://example.org/" in ontology_namespaces(g)
    assert "https://example.org/" not in ontology_namespaces(g, include_parent_path=False)


def test_include_parent_path_false_keeps_narrow_hash_fallback():
    """Truncating back to an existing "#" only narrows, so it's kept either way."""
    g = Graph()
    g.add((URIRef("https://example.org/onto#thisOntology"), RDF.type, OWL.Ontology))
    narrow = ontology_namespaces(g, include_parent_path=False)
    assert "https://example.org/onto#" in narrow
