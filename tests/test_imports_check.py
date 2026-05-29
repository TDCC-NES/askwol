"""Tests for the owl:imports completeness check."""

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import FOAF, OWL, RDF, RDFS, SKOS

from askwol.imports_check import check_imports
from askwol.models import Status

EX = Namespace("https://example.org/ont/")
ONT = URIRef("https://example.org/ont")


def _bind_common(g: Graph) -> dict[str, str]:
    g.bind("ex", EX)
    g.bind("foaf", FOAF)
    g.bind("skos", SKOS)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    return {
        "ex": str(EX),
        "foaf": str(FOAF),
        "skos": str(SKOS),
        "owl": str(OWL),
        "rdf": str(RDF),
        "rdfs": str(RDFS),
    }


def test_imports_skipped_when_no_owl_ontology():
    g = Graph()
    ns = _bind_common(g)
    g.add((EX["X"], RDF.type, OWL.Class))
    report = check_imports(g, ns, {"ex": {"X"}})
    assert report.status == Status.SKIP
    assert report.ontology_iri is None


def test_imports_ok_when_all_used_vocabs_declared():
    g = Graph()
    ns = _bind_common(g)
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, OWL.imports, URIRef("http://xmlns.com/foaf/0.1/")))
    g.add((ONT, OWL.imports, URIRef("http://www.w3.org/2004/02/skos/core")))
    g.add((EX["A"], RDF.type, OWL.Class))
    g.add((FOAF.Person, RDFS.label, Literal("Person")))
    g.add((SKOS.Concept, RDFS.label, Literal("Concept")))
    terms = {"ex": {"A"}, "foaf": {"Person"}, "skos": {"Concept"}}
    report = check_imports(g, ns, terms)
    assert report.status == Status.OK
    assert not report.missing
    # ex is the ontology's own namespace and should be skipped
    prefixes = {c.prefix for c in report.checks}
    assert "ex" not in prefixes
    assert {"foaf", "skos"} <= prefixes


def test_imports_warns_on_missing_declaration():
    g = Graph()
    ns = _bind_common(g)
    g.add((ONT, RDF.type, OWL.Ontology))
    # foaf used but not imported
    g.add((FOAF.Person, RDFS.label, Literal("Person")))
    terms = {"foaf": {"Person"}}
    report = check_imports(g, ns, terms)
    assert report.status == Status.WARN
    assert len(report.missing) == 1
    assert report.missing[0].prefix == "foaf"


def test_imports_ignores_core_vocabularies():
    g = Graph()
    ns = _bind_common(g)
    g.add((ONT, RDF.type, OWL.Ontology))
    # only core vocab terms used as subjects -> nothing to import
    g.add((OWL.Class, RDFS.label, Literal("Class")))
    terms = {"owl": {"Class"}}
    report = check_imports(g, ns, terms)
    assert report.status == Status.OK
    assert report.checks == []


def test_imports_ignores_unused_external_namespaces():
    g = Graph()
    ns = _bind_common(g)
    g.add((ONT, RDF.type, OWL.Ontology))
    # foaf is bound as a prefix but no foaf terms appear as subjects
    g.add((EX["A"], RDF.type, OWL.Class))
    terms = {"ex": {"A"}}
    report = check_imports(g, ns, terms)
    assert report.status == Status.OK
    assert all(c.prefix != "foaf" for c in report.checks)
