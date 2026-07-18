from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

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


def test_prior_version_is_not_flagged():
    # Real-world case: OWL-Time's header has
    # `owl:priorVersion <http://www.w3.org/2006/time#2006>`, a symbolic
    # marker for "the 2006 edition" of the ontology, not a term - it must
    # not be reported as "referenced but never defined".
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["ontology"], OWL.priorVersion, EX["2006"]))

    report = check_internal_terms(g)

    assert all("2006" not in i.term for i in report.undefined)
    assert report.status == Status.OK


def test_backward_compatible_with_and_incompatible_with_are_not_flagged():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["ontology"], OWL.backwardCompatibleWith, EX["v1"]))
    g.add((EX["ontology"], OWL.incompatibleWith, EX["v0"]))

    report = check_internal_terms(g)

    undefined_names = {i.display_name for i in report.undefined}
    assert "v1" not in undefined_names
    assert "v0" not in undefined_names
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


def test_dcterms_replaces_is_not_flagged():
    # Real-world case: GeoSPARQL 1.1's header has
    # `dcterms:replaces <http://www.opengis.net/ont/geosparql/1.0>`, pointing
    # at its own prior version - a symbolic marker, not a term, and must not
    # be reported as "referenced but never defined".
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["ontology"], DCTERMS.replaces, EX["1.0"]))

    report = check_internal_terms(g)

    assert all("1.0" not in i.term for i in report.undefined)
    assert report.status == Status.OK


def test_own_namespace_self_reference_is_not_flagged():
    # Real-world pattern (GeoSPARQL and many other vocabularies): a term
    # points back at its own bare vocabulary namespace via rdfs:isDefinedBy,
    # e.g. `:gmlLiteral rdfs:isDefinedBy :`. The bare namespace IRI (empty
    # local name) is the vocabulary itself, not a term in it, and is a
    # different string from the owl:Ontology subject IRI - it must not be
    # reported as "referenced but never defined".
    g = _base_graph()
    ns = URIRef("https://example.org/ont#")
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["Person"], RDFS.isDefinedBy, ns))

    report = check_internal_terms(g)

    assert all(i.term != str(ns) for i in report.undefined)
    assert report.status == Status.OK


def test_redeclaring_a_reused_term_does_not_claim_its_whole_namespace():
    # Real-world pattern (PROV-O, FOAF, and many other ontologies): re-declare
    # a reused RDFS/OWL term as an owl:AnnotationProperty for OWL-DL
    # compliance. That single triple must not make askwol treat the ENTIRE
    # RDFS/OWL namespace as "this ontology's own", flagging every other
    # rdfs:/owl: term used elsewhere (only ever as predicate/object, never as
    # a subject) as "referenced but never defined".
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["Person"], RDFS.label, Literal("Person")))
    g.add((EX["Person"], RDFS.subClassOf, EX["Agent"]))
    g.add((EX["Agent"], RDF.type, OWL.Class))
    # Common boilerplate: re-typing a reused annotation property.
    g.add((RDFS.label, RDF.type, OWL.AnnotationProperty))
    g.add((RDFS.comment, RDF.type, OWL.AnnotationProperty))

    report = check_internal_terms(g)

    undefined_terms = {i.term for i in report.undefined}
    assert str(RDFS.subClassOf) not in undefined_terms
    assert str(RDFS.label) not in undefined_terms
    assert str(RDFS.comment) not in undefined_terms
    assert report.status == Status.OK
