from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from askwol.internal_terms import check_internal_terms
from askwol.models import Status

EX = Namespace("https://example.org/ont#")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")


def _base_graph() -> Graph:
    g = Graph()
    g.add((EX["ontology"], RDF.type, OWL.Ontology))
    return g


def test_referenced_but_undefined_internal_term_is_flagged():
    g = _base_graph()
    # Person is defined (appears as subject); hasMother is used as a predicate
    # but never defined.
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["Person"], EX["hasMother"], EX["Anna"]))

    report = check_internal_terms(g)

    assert report.status == Status.FAIL
    undefined_names = {i.display_name for i in report.undefined}
    # hasMother (predicate) and Anna (object) are referenced but not defined.
    assert "hasMother" in undefined_names
    assert "Anna" in undefined_names
    # Person is defined, so it must not be flagged.
    assert "Person" not in undefined_names


def test_all_internal_terms_defined_passes():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["hasMother"], RDF.type, OWL.ObjectProperty))
    g.add((EX["Person"], EX["hasMother"], EX["Person"]))

    report = check_internal_terms(g)

    assert report.status == Status.OK
    assert report.undefined == []
    assert report.defined == report.total_referenced


def test_external_terms_are_not_flagged():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["Person"], RDFS.subClassOf, FOAF["Person"]))

    report = check_internal_terms(g)

    # foaf:Person is external and must be ignored here.
    assert all("foaf" not in i.term for i in report.undefined)
    assert report.status == Status.OK


def test_version_iri_is_not_flagged():
    # The ontology IRI is a slash IRI, so its parent path is the host root.
    # The own namespace must instead come from where terms are declared
    # (dataset#), so the versionIRI document under /ontologies/ is not flagged.
    g = Graph()
    onto = URIRef("https://lod-4tu.tudelft.nl/dataset")
    dataset = URIRef("https://lod-4tu.tudelft.nl/dataset#Dataset")
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((onto, OWL.versionIRI, URIRef("https://lod-4tu.tudelft.nl/ontologies/sample.ttl")))
    g.add((dataset, RDF.type, OWL.Class))

    report = check_internal_terms(g)

    assert all("sample.ttl" not in i.term for i in report.undefined)
    assert report.status == Status.OK


def test_host_root_is_not_treated_as_own_namespace():
    # A sibling slash IRI under the same host (but a different path) must not be
    # flagged just because it shares the host with the ontology IRI.
    g = Graph()
    onto = URIRef("https://lod-4tu.tudelft.nl/dataset")
    dataset = URIRef("https://lod-4tu.tudelft.nl/dataset#Dataset")
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((dataset, RDF.type, OWL.Class))
    g.add((dataset, RDFS.seeAlso, URIRef("https://lod-4tu.tudelft.nl/other/Thing")))

    report = check_internal_terms(g)

    assert all("other/Thing" not in i.term for i in report.undefined)
    assert report.status == Status.OK


def test_skips_without_ontology_declaration():
    g = Graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["Person"], EX["hasMother"], EX["Anna"]))

    report = check_internal_terms(g)

    assert report.status == Status.SKIP
    assert report.undefined == []
