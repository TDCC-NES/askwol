"""Tests for ontology metadata validation using SHACL-inspired checks."""

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import DCTERMS, OWL, RDF, XSD

from askwol.metadata_validator import validate_ontology_metadata
from askwol.models import MetadataCheck, MetadataReport, Status, ValidationReport
from askwol.report import report_as_markdown

EX = Namespace("https://example.org/ont/")


def _base_graph() -> Graph:
    g = Graph()
    ont = EX[""]
    g.add((ont, RDF.type, OWL.Ontology))
    return g


def test_complete_ontology_metadata_passes_required_checks():
    g = _base_graph()
    ont = EX[""]
    g.add((ont, DCTERMS.title, Literal("Example Ontology", lang="en")))
    g.add((ont, DCTERMS.description, Literal("An example ontology", lang="en")))
    g.add((ont, DCTERMS.creator, Literal("Example Team")))
    g.add((ont, DCTERMS.license, EX["license"]))
    g.add((ont, OWL.versionInfo, Literal("1.0")))
    g.add((ont, DCTERMS.created, Literal("2026-04-20", datatype=XSD.date)))
    g.add((ont, DCTERMS.publisher, Literal("TDCC-NES")))

    report = validate_ontology_metadata(g)

    assert report is not None
    assert report.failed_checks == 0
    assert report.passed_checks >= 5
    assert any(c.key == "title" and c.status == Status.OK for c in report.checks)


def test_missing_required_metadata_fails():
    g = _base_graph()

    report = validate_ontology_metadata(g)

    assert report.failed_checks >= 4
    assert any(c.key == "title" and c.status == Status.FAIL for c in report.checks)
    assert any(c.key == "creator" and c.status == Status.FAIL for c in report.checks)
    assert any(c.key == "license" and c.status == Status.FAIL for c in report.checks)


def test_missing_recommended_metadata_warns_not_fails():
    g = _base_graph()
    ont = EX[""]
    g.add((ont, DCTERMS.title, Literal("Example Ontology", lang="en")))
    g.add((ont, DCTERMS.description, Literal("An example ontology", lang="en")))
    g.add((ont, DCTERMS.creator, Literal("Example Team")))
    g.add((ont, DCTERMS.license, EX["license"]))
    g.add((ont, OWL.versionInfo, Literal("1.0")))

    report = validate_ontology_metadata(g)

    assert any(c.key == "created" and c.status == Status.WARN for c in report.checks)
    assert any(c.key == "publisher" and c.status == Status.WARN for c in report.checks)


def test_missing_ontology_declaration_is_reported():
    g = Graph()
    report = validate_ontology_metadata(g)

    assert any(c.key == "ontology_declaration" and c.status == Status.FAIL for c in report.checks)


def test_markdown_report_includes_metadata_summary():
    report = ValidationReport(file="example.ttl")
    report.ontology_metadata = MetadataReport(
        checks=[
            MetadataCheck(
                key="title",
                label="Title",
                property="dcterms:title",
                severity="required",
                status=Status.FAIL,
                message="Add a title.",
            )
        ]
    )

    md = report_as_markdown(report)
    assert "## Ontology metadata" in md
    assert "dcterms:title" in md
