"""Tests for HTML report rendering.

These tests build synthetic `ValidationReport` objects and assert that
`render_report` produces well-formed HTML containing the expected anchors,
status markers, and per-check sections. They also guard the alignment
between `CHECKS` and `GUIDE_SECTIONS` by importing the module - the
import-time assert in `report_html.py` will fail loudly otherwise.
"""

from askwol.models import (
    DatatypeReport,
    DatatypeUsage,
    DefinitionDocumentationCheck,
    DefinitionDocumentationReport,
    DomainRangeCheck,
    DomainRangeReport,
    ImportsReport,
    InternalTermEntry,
    InternalTermIssue,
    InternalTermsReport,
    IRISchemeConflict,
    IRISchemeReport,
    IRIStrategyReport,
    LangTagReport,
    LicenseCheck,
    LicenseReport,
    MetadataCheck,
    MetadataReport,
    NamespaceCheck,
    NamespaceReport,
    NonOntologyTermsReport,
    ReasonerCheck,
    ReasonerReport,
    Status,
    TermCheck,
    TermInventoryReport,
    UnusedPrefix,
    ValidationReport,
)
from askwol.report_html import CHECKS, render_report
from askwol.templates import GUIDE_SECTIONS


def test_checks_align_with_guide_sections():
    """Guard the architectural assert in report_html.py."""
    guide_check_anchors = [s["anchor"] for s in GUIDE_SECTIONS if s["group"] == "check"]
    assert [c["guide_anchor"] for c in CHECKS] == guide_check_anchors


def test_render_minimal_report_contains_all_section_anchors():
    report = ValidationReport(file="empty.ttl")
    report.ontology_metadata = MetadataReport(
        checks=[MetadataCheck(
            key="title",
            label="Title",
            property="http://purl.org/dc/terms/title",
            severity="required",
            status=Status.OK,
        )],
    )
    report.definition_docs = DefinitionDocumentationReport(
        total_definitions=1,
        documented_definitions=1,
        checks=[DefinitionDocumentationCheck(
            term="http://example.org/A",
            display_name="ex:A",
            term_type="Class",
            has_label=True,
            has_comment=True,
            status=Status.OK,
        )],
    )
    report.imports = ImportsReport(status=Status.OK, message="ok")
    report.iri_strategy = IRIStrategyReport(status=Status.OK, strategy="hash", hash_count=3)
    report.iri_scheme = IRISchemeReport(status=Status.OK, total_hosts=1, http_only_hosts=0, https_only_hosts=1)
    report.license = LicenseReport(
        checks=[LicenseCheck(
            iri="https://creativecommons.org/licenses/by/4.0/",
            name="Creative Commons Attribution 4.0 International",
            is_open=True,
            is_recommended=True,
            status=Status.OK,
        )],
    )
    report.internal_terms = InternalTermsReport(
        status=Status.FAIL,
        total_referenced=2,
        defined=1,
        undefined=[InternalTermIssue(term="https://example.org/ont#Persom", display_name="Persom")],
    )
    report.term_inventory = TermInventoryReport(
        status=Status.OK,
        total_terms=1,
        category_counts={"Class": 1},
        entries=[InternalTermEntry(
            term="https://example.org/ont#Person",
            display_name="Person",
            category="Class",
            naming_ok=True,
        )],
    )
    report.domains_ranges = DomainRangeReport(
        status=Status.OK,
        total_properties=1,
        object_properties=1,
        checks=[DomainRangeCheck(
            term="https://example.org/ont#hasParent",
            display_name="hasParent",
            category="Object property",
            has_domain=True,
            has_range=True,
            status=Status.OK,
        )],
    )
    report.datatypes = DatatypeReport(
        status=Status.OK,
        total_datatypes=1,
        usages=[DatatypeUsage(
            datatype="http://www.w3.org/2001/XMLSchema#integer",
            display_name="integer",
            count=1,
            sources=["literal"],
            recognized=True,
        )],
    )
    report.lang_tags = LangTagReport()
    report.non_ontology_terms = NonOntologyTermsReport(status=Status.OK)
    report.reasoner = ReasonerReport(
        consistent=True,
        checks=[ReasonerCheck(key="consistency", label="Consistency", status=Status.OK)],
    )

    html = render_report(report)

    # All check anchors are present in the rendered HTML.
    for check in CHECKS:
        assert f'id="{check["report_anchor"]}"' in html, f"missing section anchor: {check['report_anchor']}"
    # Every "Learn more" link points at the matching guide anchor.
    for check in CHECKS:
        assert f'guide#{check["guide_anchor"]}' in html


def test_render_parse_error_short_circuits():
    report = ValidationReport(file="broken.ttl")
    report.parse_errors.append("syntax error at line 3")
    html = render_report(report)

    assert "Parse error" in html
    assert "syntax error at line 3" in html
    # When there is a parse error none of the check sections render.
    assert 'id="ontology-metadata"' not in html


def test_render_iri_scheme_warn_shows_conflicts():
    report = ValidationReport(file="mixed.ttl")
    report.iri_scheme = IRISchemeReport(
        status=Status.WARN,
        total_hosts=1,
        conflicts=[
            IRISchemeConflict(
                host="example.org",
                http_count=2,
                https_count=3,
                http_examples=["http://example.org/A"],
                https_examples=["https://example.org/B"],
            )
        ],
    )
    html = render_report(report)

    assert 'id="iri-scheme"' in html
    assert "example.org" in html
    assert "http://example.org/A" in html
    assert "https://example.org/B" in html
    # WARN status mark is present.
    assert "&#x26A0;" in html


def test_render_namespaces_section_shows_failures():
    failing_ns = NamespaceReport(
        prefix="bad",
        uri="http://bad.example/",
        resolution=NamespaceCheck(
            prefix="bad",
            uri="http://bad.example/",
            status=Status.FAIL,
            http_status=404,
            error="not found",
        ),
        terms=[],
    )
    ok_ns = NamespaceReport(
        prefix="good",
        uri="http://good.example/",
        resolution=NamespaceCheck(
            prefix="good",
            uri="http://good.example/",
            status=Status.OK,
            http_status=200,
            is_valid_rdf=True,
        ),
        terms=[
            TermCheck(
                term_uri="http://good.example/X",
                prefix="good",
                local_name="X",
                status=Status.OK,
            ),
        ],
    )
    report = ValidationReport(file="ns.ttl", namespaces=[failing_ns, ok_ns])
    html = render_report(report)

    assert 'id="namespaces"' in html
    assert "http://bad.example/" in html
    assert "http://good.example/" in html
    # Summary should mention 1/2 resolved.
    assert "1/2" in html


def test_render_unused_prefixes_section():
    report = ValidationReport(
        file="u.ttl",
        unused_prefixes=[UnusedPrefix(prefix="foaf", uri="http://xmlns.com/foaf/0.1/")],
    )
    html = render_report(report)

    assert 'id="unused-prefixes"' in html
    assert "foaf" in html
