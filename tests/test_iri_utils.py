"""Tests for shared IRI helpers in iri_utils.py."""

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, SH, SKOS

from askwol.iri_utils import EXTERNAL_NAMESPACES, ontology_namespaces
from askwol.shacl_runner import SHAPES_DIR


def test_ontology_namespaces_matches_exact_subject_as_namespace():
    """Some ontologies use their own IRI directly as the namespace (no separator added)."""
    g = Graph()
    g.add((URIRef("https://example.org/onto#"), RDF.type, OWL.Ontology))
    ns = ontology_namespaces(g)
    assert "https://example.org/onto#" in ns


def test_ontology_namespaces_empty_without_owl_ontology_declaration():
    g = Graph()
    assert ontology_namespaces(g) == set()


def test_ontology_namespaces_excludes_parent_paths_and_bare_prefixes():
    g = Graph()
    g.add((URIRef("https://example.org/dataset"), RDF.type, OWL.Ontology))
    assert ontology_namespaces(g) == {
        "https://example.org/dataset#", "https://example.org/dataset/",
    }


def test_ontology_namespaces_keeps_existing_fragment_namespace():
    g = Graph()
    g.add((URIRef("https://example.org/onto#thisOntology"), RDF.type, OWL.Ontology))
    assert ontology_namespaces(g) == {"https://example.org/onto#"}


@pytest.mark.parametrize("ontology_iri, own_terms", [
    ("https://example.org/onto", {"https://example.org/onto#Term", "https://example.org/onto/Term"}),
    ("https://example.org/onto#", {"https://example.org/onto#Term"}),
    ("https://example.org/onto#header", {"https://example.org/onto#Term"}),
    ("https://example.org/onto/", {"https://example.org/onto/Term"}),
])
def test_standalone_shape_targets_use_the_same_bounded_scope(ontology_iri, own_terms):
    graph = Graph()
    graph.add((URIRef(ontology_iri), RDF.type, OWL.Ontology))
    terms = own_terms | {
        "https://example.org/onto#Term", "https://example.org/onto/Term",
        "https://example.org/onto2#Neighbour", "https://example.org/other/Neighbour",
    }
    # Every term qualifies for each target's role filter; only scope differs.
    for term in terms:
        for role in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, SKOS.Concept):
            graph.add((URIRef(term), RDF.type, role))

    assert {term for term in terms if any(term.startswith(ns) for ns in ontology_namespaces(graph))} == own_terms
    for filename in ("term_inventory.ttl", "definition_documentation.ttl", "non_ontology_terms.ttl"):
        shapes = Graph().parse(SHAPES_DIR / filename, format="turtle")
        for query in shapes.objects(None, SH.select):
            # Constraint queries use $this; only the custom targets select ?this.
            if "SELECT DISTINCT ?this" in str(query):
                assert {str(row[0]) for row in graph.query(str(query))} == own_terms


def test_documentation_fallback_matches_the_shared_external_vocabulary_list():
    from askwol.definition_docs import check_definition_documentation

    graph = Graph()
    for namespace in EXTERNAL_NAMESPACES:
        graph.add((URIRef(namespace + "ExternalTerm"), RDF.type, OWL.Class))
    internal = "https://example.org/own#Term"
    graph.add((URIRef(internal), RDF.type, OWL.Class))

    report = check_definition_documentation(graph)

    assert [check.term for check in report.checks] == [internal]
    assert report.checks[0].has_label is False
    assert report.checks[0].has_comment is False
