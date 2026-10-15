"""Tests for HTML report rendering.

These tests build synthetic `ValidationReport` objects and assert that
`render_report` produces well-formed HTML containing the expected anchors,
status markers, and per-check sections. The alignment between `CHECKS` and
`GUIDE_SECTIONS` (and the non-empty `description` requirement) is guarded by
import-time asserts in `templates.py`, which every test run already exercises
by importing the module - no dedicated test needed here.
"""

from html import escape
from html.parser import HTMLParser
import json

import pytest
from rdflib import Graph

from askwol.license_check import check_license
from askwol.models import (
    DatatypeReport,
    DatatypeUsage,
    DefinitionDocumentationCheck,
    DefinitionDocumentationReport,
    DomainRangeCheck,
    DomainRangeReport,
    ImportsCheck,
    ImportsReport,
    InternalTermEntry,
    InternalTermIssue,
    InternalTermReference,
    InternalTermsReport,
    IRINamespaceStrategy,
    IRISchemeConflict,
    IRISchemeReport,
    IRIStrategyReport,
    LangTagIssue,
    LangTagReport,
    LicenseCheck,
    LicenseReport,
    MetadataCheck,
    MetadataReport,
    NamespaceCheck,
    NamespaceReport,
    NonOntologyTermIssue,
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
from askwol.templates import CHECK_NUMBERS, GUIDE_HTML


def _complete_report():
    report = ValidationReport(file="empty.ttl")
    report.ontology_metadata = MetadataReport(
        checks=[MetadataCheck(
            key="title",
            label="Title",
            property="http://purl.org/dc/terms/title",
            tier="core",
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
    report.iri_strategy = IRIStrategyReport(
        status=Status.OK,
        namespaces=[IRINamespaceStrategy(namespace="http://example.org/", strategy="hash", hash_count=3)],
    )
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
            recognised=True,
        )],
    )
    report.lang_tags = LangTagReport()
    report.non_ontology_terms = NonOntologyTermsReport(status=Status.OK)
    report.reasoner = ReasonerReport(
        consistent=True,
        checks=[ReasonerCheck(key="ontology_consistency", label="Logical findings", status=Status.OK)],
    )

    return report


def test_render_minimal_report_contains_all_section_anchors():
    html = render_report(_complete_report())

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


def test_shared_check_numbers_match_guide_headings():
    for check in CHECKS:
        number = CHECK_NUMBERS[check["report_anchor"]]
        assert f'id="{check["guide_anchor"]}">{number} ' in GUIDE_HTML


class _ReportHTML(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.links = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.links.append(dict(attrs))

    def handle_data(self, data):
        self.text.append(data)


def test_valid_rdf_licence_literal_is_text_in_html():
    payload = '</code><script>alert(1)</script><img src=x onerror=alert(2)>'
    graph = Graph().parse(
        data=f'<urn:ontology> a <http://www.w3.org/2002/07/owl#Ontology> ; <http://purl.org/dc/terms/license> {json.dumps(payload)} .',
        format="turtle",
    )
    report = ValidationReport(file="licence.ttl", license=check_license(graph))

    html = render_report(report)
    parsed = _ReportHTML(html)

    assert escape(payload) in html
    assert payload in "".join(parsed.text)
    assert "img" not in parsed.tags
    assert parsed.tags.count("script") == 1  # The report's fixed navigation handler only.
    assert all(link.get("href") != payload for link in parsed.links)


@pytest.mark.parametrize("uri", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\tscript:alert(1)",
    "data:text/html,<script>alert(1)</script>", "file:///etc/passwd", "//example.org/term",
])
def test_unsafe_iri_schemes_remain_readable_without_active_links(uri):
    report = _complete_report()
    report.file = uri
    report.license.checks[0].iri = uri
    report.imports.checks = [ImportsCheck(
        iri=uri, resolution=NamespaceCheck(prefix="ex", uri=uri, status=Status.FAIL),
    )]
    report.internal_terms.undefined[0].term = uri
    report.internal_terms.referenced = [InternalTermReference(term=uri, display_name="ref", defined=True)]
    report.term_inventory.entries[0].term = uri
    report.domains_ranges.checks[0].term = uri
    report.datatypes.usages[0].datatype = uri
    report.definition_docs.checks[0].term = uri
    report.non_ontology_terms.terms = [NonOntologyTermIssue(term=uri, display_name="concept", type_label="SKOS concept")]
    report.lang_tags = LangTagReport(status=Status.WARN, issues=[LangTagIssue(
        subject="subject", subject_uri=uri, property="rdfs:label", issue_type="missing_tag", detail="missing tag",
    )])
    # Exercise every external-term status branch, including its links.
    report.namespaces = [NamespaceReport(
        prefix="ex", uri="https://example.org/", resolution=NamespaceCheck(
            prefix="ex", uri="https://example.org/", status=Status.OK,
        ), terms=[TermCheck(term_uri=uri, prefix="ex", local_name=status.value, status=status) for status in Status],
    )]

    html = render_report(report)
    parsed = _ReportHTML(html)

    assert uri in "".join(parsed.text)
    assert all(link.get("href") != uri for link in parsed.links)
    assert all(not link.get("href", "").lower().startswith(("javascript:", "data:", "file:")) for link in parsed.links)


def test_http_links_escape_attributes_and_preserve_the_original_iri():
    uri = 'https://example.org/term?first="quoted"&second=<value>'
    report = ValidationReport(file=uri, license=LicenseReport(checks=[LicenseCheck(
        iri=uri, name='<img src=x onerror=alert(1)>', is_open=False, is_recommended=False, status=Status.FAIL,
    )]))

    parsed = _ReportHTML(render_report(report))

    links = [link for link in parsed.links if link.get("href") == uri]
    assert len(links) == 2
    assert all(link == {"href": uri, "target": "_blank", "rel": "noopener"} for link in links)
    assert "img" not in parsed.tags


def test_mermaid_source_cannot_close_its_html_containers():
    source = 'classDiagram\n</pre></textarea><script>alert(1)</script><img src=x onerror=alert(2)>'
    html = render_report(ValidationReport(file="diagram.ttl"), source)
    parsed = _ReportHTML(html)

    assert escape(source) in html
    assert parsed.tags.count("pre") == 1
    assert parsed.tags.count("textarea") == 1
    assert parsed.tags.count("script") == 3  # Two diagram scripts plus navigation.
    assert "img" not in parsed.tags
    assert 'securityLevel:"strict"' in html
    assert "error.textContent = 'Diagram error: ' + msg" in html
    assert "vp.innerHTML" not in html


@pytest.mark.parametrize("section", ["iri_strategy", "iri_scheme", "internal_terms", "lang_tags"])
def test_report_messages_and_language_names_are_escaped(section):
    payload = '<img src=x onerror=alert(1)>'
    report = _complete_report()
    if section == "lang_tags":
        report.lang_tags = LangTagReport(status=Status.OK, languages_used=[payload])
    else:
        check = getattr(report, section)
        check.status = Status.SKIP
        check.message = payload

    html = render_report(report)

    assert escape(payload) in html
    assert "img" not in _ReportHTML(html).tags
