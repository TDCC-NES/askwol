from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS

from askwol.models import Status, ValidationReport
from askwol.reasoner_checks import run_reasoner_checks
from askwol.report import report_as_markdown

EX = Namespace("https://example.org/ont#")


def test_consistent_ontology_reports_ok():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Person, RDF.type, OWL.Class))
    g.add((EX.Person, RDFS.label, Literal("Person", lang="en")))

    report = run_reasoner_checks(g)

    assert report.consistent is True
    assert report.unsatisfiable_classes == []
    assert any(c.key == "ontology_consistency" and c.status == Status.OK for c in report.checks)


def test_all_three_facets_always_present_when_ok():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Person, RDF.type, OWL.Class))

    report = run_reasoner_checks(g)

    keys = [c.key for c in report.checks]
    assert keys == ["ontology_consistency", "inconsistent_individuals", "unsatisfiable_classes"]
    assert all(c.status == Status.OK for c in report.checks)


def test_all_three_facets_always_present_when_unsatisfiable_class_only():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Cat, RDF.type, OWL.Class))
    g.add((EX.Dog, RDF.type, OWL.Class))
    g.add((EX.Cat, OWL.disjointWith, EX.Dog))
    g.add((EX.ImpossiblePet, RDF.type, OWL.Class))
    g.add((EX.ImpossiblePet, RDFS.subClassOf, EX.Cat))
    g.add((EX.ImpossiblePet, RDFS.subClassOf, EX.Dog))

    report = run_reasoner_checks(g)

    keys = {c.key: c.status for c in report.checks}
    assert {"ontology_consistency", "inconsistent_individuals", "unsatisfiable_classes"} <= set(keys)
    assert keys["inconsistent_individuals"] == Status.OK
    assert keys["unsatisfiable_classes"] == Status.WARN
    assert keys["ontology_consistency"] == Status.WARN


def test_disjoint_types_make_individual_inconsistent():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Cat, RDF.type, OWL.Class))
    g.add((EX.Dog, RDF.type, OWL.Class))
    g.add((EX.Cat, OWL.disjointWith, EX.Dog))
    g.add((EX.Fido, RDF.type, EX.Cat))
    g.add((EX.Fido, RDF.type, EX.Dog))

    report = run_reasoner_checks(g)

    assert report.consistent is False
    assert any("Fido" in item for item in report.inconsistent_individuals)
    assert any(c.key.startswith("inconsistent_individual") and c.status == Status.FAIL for c in report.checks)


def test_unsatisfiable_class_is_reported_without_dummy_instances():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Cat, RDF.type, OWL.Class))
    g.add((EX.Dog, RDF.type, OWL.Class))
    g.add((EX.Cat, OWL.disjointWith, EX.Dog))
    g.add((EX.ImpossiblePet, RDF.type, OWL.Class))
    g.add((EX.ImpossiblePet, RDFS.subClassOf, EX.Cat))
    g.add((EX.ImpossiblePet, RDFS.subClassOf, EX.Dog))

    report = run_reasoner_checks(g)

    assert "https://example.org/ont#ImpossiblePet" in report.unsatisfiable_classes
    assert any(c.key.startswith("unsatisfiable_class") and c.status == Status.WARN for c in report.checks)


def test_markdown_report_includes_reasoner_section():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Cat, RDF.type, OWL.Class))
    g.add((EX.Dog, RDF.type, OWL.Class))
    g.add((EX.Cat, OWL.disjointWith, EX.Dog))
    g.add((EX.Fido, RDF.type, EX.Cat))
    g.add((EX.Fido, RDF.type, EX.Dog))

    full = ValidationReport(file="example.ttl")
    full.reasoner = run_reasoner_checks(g)

    md = report_as_markdown(full)
    assert "## Reasoner checks" in md
    assert "Ontology consistency" in md
