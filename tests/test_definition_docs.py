from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS

from askwol.models import Status, ValidationReport
from askwol.report import report_as_markdown
from askwol.definition_docs import check_definition_documentation

EX = Namespace("https://example.org/ont#")
EXT = Namespace("http://xmlns.com/foaf/0.1/")


def test_internal_class_and_property_missing_docs_are_reported():
    g = Graph()
    g.add((EX["ontology"], RDF.type, OWL.Ontology))
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["knows"], RDF.type, OWL.ObjectProperty))
    g.add((EX["knows"], RDFS.label, Literal("knows", lang="en")))

    report = check_definition_documentation(g)

    assert report.total_definitions == 2
    assert len(report.issues) == 2
    assert any(i.term.endswith("Person") and "label" in i.missing and "comment" in i.missing for i in report.issues)
    assert any(i.term.endswith("knows") and i.missing == ["comment"] for i in report.issues)


def test_external_reused_terms_are_ignored():
    g = Graph()
    g.add((EX["ontology"], RDF.type, OWL.Ontology))
    g.add((EXT["Person"], RDF.type, OWL.Class))

    report = check_definition_documentation(g)

    assert report.total_definitions == 0
    assert report.issues == []


def test_markdown_report_includes_labels_and_comments_sections():
    g = Graph()
    g.add((EX["ontology"], RDF.type, OWL.Ontology))
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["Person"], RDFS.label, Literal("Person", lang="en")))

    full = ValidationReport(file="example.ttl")
    full.definition_docs = check_definition_documentation(g)

    md = report_as_markdown(full)
    assert "## Labels" in md
    assert "## Comments" in md
    assert "| Term | Type | Label |" in md
    assert "| Term | Type | Comment |" in md
    assert "| `Person` | Class | ok |" in md
    assert "| `Person` | Class | missing |" in md
