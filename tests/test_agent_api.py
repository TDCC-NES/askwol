"""Programmatic input formats and compact-report coverage semantics."""

import json

import pytest
from pydantic import ValidationError
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.util import guess_format

from askwol.agent_api import OntologyContent, compact_report
from askwol.checks import CHECKS, REASONER_SCOPE
from askwol.models import (
    ImportsCheck,
    ImportsReport,
    InternalTermsReport,
    NamespaceCheck,
    NamespaceReport,
    ReasonerReport,
    Status,
    TermCheck,
    ValidationReport,
)
from askwol.pipeline import run_full_validation
from askwol.rdf_io import parse_rdf_bytes


@pytest.mark.parametrize(("format", "content"), [
    ("json-ld", {"@id": "#Example", "@type": str(OWL.Class)}),
    ("json-ld", [{"@id": "#Example", "@type": str(OWL.Class)}]),
    ("json-ld", '{"@id":"#Example","@type":"http://www.w3.org/2002/07/owl#Class"}'),
    ("turtle", "<#Example> a <http://www.w3.org/2002/07/owl#Class> ."),
    ("xml", '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="#Example"><rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Class"/></rdf:Description></rdf:RDF>'),
    ("nt", "<https://example.org/ontology#Example> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2002/07/owl#Class> ."),
    ("n3", "<#Example> a <http://www.w3.org/2002/07/owl#Class> ."),
])
def test_content_uses_existing_parser_with_explicit_syntax_and_base(format, content):
    request = OntologyContent(format=format, content=content, base_uri="https://example.org/ontology")
    assert guess_format("ontology" + request.suffix) == format
    graph = parse_rdf_bytes(Graph(), request.as_bytes(), format=format, base_uri=request.base_uri, allow_network=False)
    assert (URIRef("https://example.org/ontology#Example"), RDF.type, OWL.Class) in graph


def test_structured_jsonld_preserves_unicode_and_does_not_modify_input():
    content = {"@id": "urn:example:Wollie", "https://example.org/name": "Käthe"}
    request = OntologyContent(format="json-ld", content=content)
    assert json.loads(request.as_bytes()) == content
    assert "Käthe".encode() in request.as_bytes()


@pytest.mark.parametrize("payload", [
    {"content": ""},
    {"format": "unknown", "content": ""},
    {"format": "turtle", "content": {}},
    {"format": "xml", "content": []},
    {"format": "json-ld", "content": True},
    {"format": "json-ld", "content": None},
    {"format": "json-ld", "content": {"value": float("nan")}},
    {"format": "turtle", "content": "\ud800"},
    {"format": "json-ld", "content": {}, "base_url": "https://example.org/"},
])
def test_invalid_request_shapes_fail_before_serialisation(payload):
    with pytest.raises(ValidationError):
        OntologyContent.model_validate(payload)


@pytest.mark.parametrize("base_uri", [
    "https://example.org/ontology", "http://localhost:8000/ontology", "urn:example:ontology",
])
def test_base_iri_accepts_absolute_iris_without_fetching(base_uri):
    assert OntologyContent(format="turtle", content="", base_uri=base_uri).base_uri == base_uri


@pytest.mark.parametrize("base_uri", [
    "relative/path", "//example.org/ontology", "https:///missing-host", "https://example.org:bad/",
    "https://example.org/a b", "https://example.org/\n", "urn:example:\x00ontology",
])
def test_invalid_base_iri_is_rejected(base_uri):
    with pytest.raises(ValidationError):
        OntologyContent(format="turtle", content="", base_uri=base_uri)


def _namespace(resolution: Status, term: Status) -> NamespaceReport:
    return NamespaceReport(
        prefix="external", uri="https://example.org/vocab#",
        resolution=NamespaceCheck(prefix="external", uri="https://example.org/vocab#", status=resolution),
        terms=[TermCheck(term_uri="https://example.org/vocab#Term", prefix="external", local_name="Term", status=term)],
    )


@pytest.mark.parametrize(("namespaces", "namespace_status", "term_status"), [
    ([], "completed", "completed"),
    ([_namespace(Status.OK, Status.FAIL)], "completed", "completed"),
    ([_namespace(Status.FAIL, Status.SKIP)], "completed", "unavailable"),
    ([_namespace(Status.SKIP, Status.SKIP)], "skipped", "skipped"),
    ([_namespace(Status.OK, Status.OK), _namespace(Status.FAIL, Status.SKIP)], "completed", "partial"),
    ([_namespace(Status.OK, Status.WARN), _namespace(Status.SKIP, Status.SKIP)], "partial", "partial"),
])
def test_coverage_distinguishes_findings_unchecked_targets_and_disabled_resolution(namespaces, namespace_status, term_status):
    report = ValidationReport(file="ontology.ttl", namespaces=namespaces)
    compact = compact_report(report)
    coverage = {item.check: item.status for item in compact.checks}
    assert coverage["namespaces"] == namespace_status
    assert coverage["external-terms"] == term_status
    assert compact.severity_summary == report.severity_summary


def test_parse_failure_retains_findings_and_marks_checks_not_run():
    report = ValidationReport(file="invalid.ttl", parse_errors=["Invalid Turtle"])
    compact = compact_report(report)
    assert [item.check for item in compact.checks] == [item["report_anchor"] for item in CHECKS]
    assert all(item.status == "skipped" for item in compact.checks)
    assert compact.severity_summary == report.severity_summary
    assert compact.severity_summary.errors == 1
    assert compact.reasoner is None
    assert "parse_errors" not in compact.model_dump()


def test_absent_sections_are_unavailable_and_findings_do_not_mark_checks_skipped():
    report = ValidationReport(
        file="ontology.ttl",
        internal_terms=InternalTermsReport(status=Status.WARN),
        imports=ImportsReport(status=Status.FAIL, checks=[ImportsCheck(
            iri="https://example.org/import",
            resolution=NamespaceCheck(prefix="import", uri="https://example.org/import", status=Status.FAIL),
        )]),
        reasoner=ReasonerReport(consistent=False, inconsistent_individuals=["urn:example:individual"]),
    )
    compact = compact_report(report)
    coverage = {item.check: item.status for item in compact.checks}
    assert coverage["ontology-metadata"] == "unavailable"
    assert coverage["internal-terms"] == coverage["imports"] == coverage["reasoner"] == "completed"
    assert compact.reasoner.consistent is False
    assert compact.reasoner.description == REASONER_SCOPE
    assert "inconsistent_individuals" not in compact.reasoner.model_dump()
    assert compact.severity_summary == report.severity_summary


async def test_compact_pipeline_result_preserves_all_findings_without_term_inventories(tmp_path):
    source = tmp_path / "ontology.ttl"
    source.write_text("""@prefix : <https://example.org/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://example.org/ontology> a owl:Ontology; owl:imports <https://example.org/import> .
:Example a owl:Class .
""")
    report, _ = await run_full_validation(source, skip_resolution=True, include_mermaid=False)
    compact = compact_report(report)
    payload = compact.model_dump(mode="json")
    coverage = {item.check: item.status for item in compact.checks}
    assert compact.severity_summary == report.severity_summary
    assert coverage["imports"] == coverage["namespaces"] == coverage["external-terms"] == "skipped"
    assert coverage["domains-ranges"] == "skipped"
    assert coverage["labels"] == coverage["comments"] == "completed"
    assert compact.reasoner.scoped_to_current_ontology is True
    assert compact.reasoner.imports_followed is False
    assert compact.reasoner.consistent is None
    assert set(payload) == {"file", "severity_summary", "checks", "reasoner"}
    assert "term_inventory" not in payload
