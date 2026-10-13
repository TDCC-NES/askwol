"""Severity levels: errors, warnings and recommendations (issue #17)."""

from pathlib import Path

import pytest

from askwol.models import (
    DefinitionDocumentationCheck,
    DefinitionDocumentationReport,
    LicenseReport,
    MetadataCheck,
    MetadataReport,
    ReasonerCheck,
    ReasonerReport,
    Severity,
    Status,
    UnusedPrefix,
    ValidationReport,
)
from askwol.pipeline import run_full_validation
from askwol.report import report_as_json, report_as_markdown
from askwol.report_html import CHECKS, render_report
from askwol.severity import CHECK_SEVERITY, check_status, severity_of, summarise

ROOT = Path(__file__).resolve().parent.parent
BROKEN = ROOT / "html" / "ontologies" / "broken.ttl"
SAMPLE = ROOT / "html" / "ontologies" / "sample.ttl"


def test_every_check_has_a_severity_mapping():
    assert {c["report_anchor"] for c in CHECKS} == set(CHECK_SEVERITY)


def test_severity_of_ok_and_skip_is_none():
    assert severity_of("labels", Status.OK) is None
    assert severity_of("labels", Status.SKIP) is None


def test_documentation_and_metadata_are_recommendations_not_errors():
    assert severity_of("labels", Status.FAIL) is Severity.RECOMMENDATION
    assert severity_of("comments", Status.FAIL) is Severity.RECOMMENDATION
    assert severity_of("ontology-metadata", Status.FAIL) is Severity.RECOMMENDATION
    assert severity_of("license", Status.FAIL) is Severity.RECOMMENDATION


def test_logic_problems_are_errors():
    assert severity_of("reasoner", Status.FAIL) is Severity.ERROR
    assert severity_of("reasoner", Status.WARN) is Severity.ERROR
    assert severity_of("datatypes", Status.FAIL) is Severity.ERROR
    assert severity_of("external-terms", Status.FAIL) is Severity.ERROR


def test_interoperability_problems_are_warnings():
    assert severity_of("namespaces", Status.FAIL) is Severity.WARNING
    assert severity_of("imports", Status.FAIL) is Severity.WARNING
    assert severity_of("iri-scheme", Status.WARN) is Severity.WARNING
    assert severity_of("external-terms", Status.WARN) is Severity.WARNING


def test_domains_ranges_split_by_status():
    assert severity_of("domains-ranges", Status.FAIL) is Severity.ERROR
    assert severity_of("domains-ranges", Status.WARN) is Severity.RECOMMENDATION


def _report_with_missing_label_and_metadata() -> ValidationReport:
    report = ValidationReport(file="docs.ttl")
    report.ontology_metadata = MetadataReport(checks=[
        MetadataCheck(key="title", label="Title", property="dcterms:title",
                      severity="required", status=Status.FAIL),
        MetadataCheck(key="created", label="Created", property="dcterms:created",
                      severity="recommended", status=Status.WARN),
    ])
    report.definition_docs = DefinitionDocumentationReport(
        total_definitions=1,
        documented_definitions=0,
        checks=[DefinitionDocumentationCheck(
            term="http://example.org/A", display_name="A", term_type="class",
            has_label=False, has_comment=True, status=Status.FAIL,
        )],
    )
    report.unused_prefixes = [UnusedPrefix(prefix="x", uri="http://x.example/")]
    return report


def test_only_recommendations_keeps_ontology_valid():
    report = _report_with_missing_label_and_metadata()
    summary = report.severity_summary

    assert summary.valid and report.is_valid
    assert (summary.errors, summary.warnings) == (0, 0)
    assert summary.recommendations == 3
    # Legacy flag still sees "something to look at".
    assert report.has_issues


def test_reasoner_problem_makes_ontology_invalid():
    report = ValidationReport(file="bad.ttl")
    report.reasoner = ReasonerReport(
        consistent=False,
        inconsistent_individuals=["http://example.org/x"],
        checks=[ReasonerCheck(key="ontology_consistency", label="Ontology consistency",
                              status=Status.FAIL, message="bad")],
    )
    summary = summarise(report)

    assert not summary.valid
    assert summary.errors == 1
    assert [f.check for f in summary.findings] == ["reasoner"]


def test_parse_errors_count_as_errors():
    report = ValidationReport(file="x.ttl", parse_errors=["boom"])
    assert not report.is_valid
    assert report.severity_summary.errors == 1


def test_license_status_roundtrips_through_check_status():
    report = ValidationReport(file="x.ttl", license=LicenseReport())
    assert check_status(report, "license") is Status.FAIL


def test_findings_sorted_most_severe_first():
    report = _report_with_missing_label_and_metadata()
    report.reasoner = ReasonerReport(
        consistent=False,
        checks=[ReasonerCheck(key="k", label="l", status=Status.FAIL)],
    )
    severities = [f.severity for f in report.severity_summary.findings]
    assert severities[0] is Severity.ERROR
    assert severities == sorted(severities, key=["error", "warning", "recommendation"].index)


def test_html_report_labels_recommendations_and_does_not_call_them_errors():
    html = render_report(_report_with_missing_label_and_metadata())

    assert "No errors found." in html
    assert "nmet recommendations do not make an ontology invalid." in html
    assert "&#x1F4A1;" in html  # light bulb
    assert 'class="sev sev-recommendation"' in html
    summary_table = html.split('<div class="summary">')[1].split("</table>")[0]
    assert "sev-error" not in summary_table
    assert "sev-warning" not in summary_table


def test_html_report_shows_errors_with_cross_mark():
    report = ValidationReport(file="bad.ttl")
    report.reasoner = ReasonerReport(
        consistent=False,
        inconsistent_individuals=["http://example.org/x"],
        checks=[ReasonerCheck(key="ontology_consistency", label="Ontology consistency",
                              status=Status.FAIL, message="bad")],
    )
    html = render_report(report)

    assert "Errors found." in html
    assert 'title="Error"' in html
    assert "&#x2717;" in html


def test_markdown_report_summarises_by_severity():
    md = report_as_markdown(_report_with_missing_label_and_metadata())

    assert "No errors found." in md
    assert "3 recommendations" in md
    assert "Unmet recommendations do not make an ontology invalid." in md
    assert "| \U0001F4A1 Recommendation | Labels |" in md


def test_json_report_includes_severity_summary():
    import json

    data = json.loads(report_as_json(_report_with_missing_label_and_metadata()))
    summary = data["severity_summary"]

    assert summary["valid"] is True
    assert summary["recommendations"] == 3
    assert {f["severity"] for f in summary["findings"]} == {"recommendation"}
    # Existing per-check statuses are unchanged.
    assert data["definition_docs"]["checks"][0]["status"] == "fail"


@pytest.mark.parametrize("path, valid", [(BROKEN, False), (SAMPLE, True)])
async def test_fixtures(path, valid):
    report, _ = await run_full_validation(path, include_mermaid=False, skip_resolution=True)
    assert report.is_valid is valid
    if valid:
        assert report.severity_summary.findings == []
    else:
        summary = report.severity_summary
        assert summary.errors and summary.warnings and summary.recommendations
