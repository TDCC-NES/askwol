"""Severity levels: errors, warnings and recommendations (issue #17)."""

import json
from io import StringIO
from pathlib import Path

import pytest
from click.testing import CliRunner
from rdflib import Graph
from rdflib.namespace import Namespace
from rich.console import Console

from askwol.cli import main
from askwol.models import (
    DatatypeReport,
    DatatypeUsage,
    DefinitionDocumentationCheck,
    DefinitionDocumentationReport,
    DomainRangeCheck,
    DomainRangeReport,
    LangTagReport,
    LicenseCheck,
    LicenseReport,
    MetadataCheck,
    MetadataReport,
    NamespaceCheck,
    NamespaceReport,
    ReasonerCheck,
    ReasonerReport,
    Status,
    TermCheck,
    UnusedPrefix,
    ValidationReport,
)
from askwol.pipeline import run_full_validation
from askwol.report import print_report, report_as_json, report_as_markdown
from askwol.report_html import CHECKS, render_report
from askwol.severity import RULE_SEVERITY, SEVERITY_STYLES, Rule, Severity, count_label
from askwol.term_inventory import check_domains_ranges

ROOT = Path(__file__).resolve().parent.parent
BROKEN = ROOT / "html" / "ontologies" / "broken.ttl"
SAMPLE = ROOT / "html" / "ontologies" / "sample.ttl"
SHAPES_DIR = ROOT / "src" / "askwol" / "shapes"
SH = Namespace("http://www.w3.org/ns/shacl#")


# --- the rule table ---------------------------------------------------------


def test_every_rule_has_a_severity():
    assert set(RULE_SEVERITY) == set(Rule)


def test_every_check_has_rules_and_every_rule_belongs_to_a_check():
    anchors = {c["report_anchor"] for c in CHECKS}
    assert {r.check for r in Rule if r != Rule.PARSE_ERROR} == anchors


@pytest.mark.parametrize("rule, severity", [
    (Rule.UNSATISFIABLE_CLASS, Severity.ERROR),
    (Rule.INCONSISTENT_INDIVIDUAL, Severity.ERROR),
    (Rule.DATATYPE_UNRECOGNISED, Severity.WARNING),
    (Rule.DOMAIN_RANGE_MISMATCH, Severity.ERROR),
    (Rule.EXTERNAL_TERM_NOT_FOUND, Severity.WARNING),
    (Rule.IMPORT_UNRESOLVED, Severity.WARNING),
    (Rule.NAMESPACE_UNRESOLVED, Severity.WARNING),
    (Rule.IRI_SCHEME_MIXED, Severity.WARNING),
    (Rule.DOMAIN_RANGE_MISSING, Severity.RECOMMENDATION),
    (Rule.LABEL_MISSING, Severity.RECOMMENDATION),
    (Rule.COMMENT_MISSING, Severity.RECOMMENDATION),
    (Rule.METADATA_MISSING, Severity.RECOMMENDATION),
    (Rule.LICENSE_MISSING, Severity.RECOMMENDATION),
])
def test_classification(rule, severity):
    assert RULE_SEVERITY[rule] is severity


# --- the SHACL shapes agree with the table ---------------------------------

SHAPE_RULES = {
    ("ontology_metadata.ttl", "Title"): Rule.METADATA_MISSING,
    ("ontology_metadata.ttl", "Description"): Rule.METADATA_MISSING,
    ("ontology_metadata.ttl", "Creator"): Rule.METADATA_MISSING,
    ("ontology_metadata.ttl", "Version"): Rule.METADATA_MISSING,
    ("ontology_metadata.ttl", "Created date"): Rule.METADATA_MISSING,
    ("ontology_metadata.ttl", "Modified date"): Rule.METADATA_MISSING,
    ("ontology_metadata.ttl", "Publisher"): Rule.METADATA_MISSING,
    ("definition_documentation.ttl", "Label"): Rule.LABEL_MISSING,
    ("definition_documentation.ttl", "Comment"): Rule.COMMENT_MISSING,
    ("term_inventory.ttl", "ClassNaming"): Rule.NAMING_CONVENTION,
    ("term_inventory.ttl", "PropertyNaming"): Rule.NAMING_CONVENTION,
    ("term_inventory.ttl", "DomainMissing"): Rule.DOMAIN_RANGE_MISSING,
    ("term_inventory.ttl", "RangeMissing"): Rule.DOMAIN_RANGE_MISSING,
    ("term_inventory.ttl", "DomainIsDatatype"): Rule.DOMAIN_RANGE_MISMATCH,
    ("term_inventory.ttl", "ObjectPropertyRangeIsDatatype"): Rule.DOMAIN_RANGE_MISMATCH,
    ("term_inventory.ttl", "DatatypePropertyRangeIsClass"): Rule.DOMAIN_RANGE_MISMATCH,
    ("non_ontology_terms.ttl", "ConceptInSchema"): Rule.NON_ONTOLOGY_TERM,
}
SHACL_LEVELS = {SH.Info: Severity.RECOMMENDATION, SH.Warning: Severity.WARNING, SH.Violation: Severity.ERROR}


def test_shapes_match_rule_table():
    found = {}
    for path in SHAPES_DIR.glob("*.ttl"):
        graph = Graph().parse(path, format="turtle")
        for node, name in graph.subject_objects(SH.name):
            level = graph.value(node, SH.severity) or SH.Violation  # SHACL's default
            found[(path.name, str(name))] = SHACL_LEVELS[level]
    assert found == {key: RULE_SEVERITY[rule] for key, rule in SHAPE_RULES.items()}


# --- one finding per affected element --------------------------------------


def _doc_check(name: str, *, label: bool, comment: bool) -> DefinitionDocumentationCheck:
    return DefinitionDocumentationCheck(
        term=f"http://example.org/{name}", display_name=name, term_type="class",
        has_label=label, has_comment=comment, status=Status.OK if label and comment else Status.WARN,
    )


def _rules(report: ValidationReport) -> list[Rule]:
    return [f.rule for f in report.findings()]


def test_missing_labels_and_comments_are_counted_per_term():
    report = ValidationReport(file="docs.ttl", definition_docs=DefinitionDocumentationReport(
        total_definitions=4,
        checks=[
            _doc_check("A", label=False, comment=False),
            _doc_check("B", label=False, comment=True),
            _doc_check("C", label=True, comment=False),
            _doc_check("D", label=True, comment=True),
        ],
    ))
    rules = _rules(report)
    assert rules.count(Rule.LABEL_MISSING) == 2
    assert rules.count(Rule.COMMENT_MISSING) == 2
    assert report.severity_summary.recommendations == 4
    assert not report.has_errors


def test_domain_range_findings_are_counted_per_problem():
    report = ValidationReport(file="dr.ttl", domains_ranges=DomainRangeReport(
        total_properties=2,
        status=Status.FAIL,
        checks=[
            DomainRangeCheck(
                term="http://example.org/p", display_name="p", category="Object property",
                status=Status.FAIL, mismatches=["Range is a datatype."], omissions=["No rdfs:domain declared."],
            ),
            DomainRangeCheck(
                term="http://example.org/q", display_name="q", category="Datatype property",
                status=Status.WARN, omissions=["No rdfs:domain declared.", "No rdfs:range declared."],
            ),
        ],
    ))
    summary = report.severity_summary
    assert (summary.errors, summary.warnings, summary.recommendations) == (1, 0, 3)
    assert report.has_errors


def test_licence_findings():
    def lic(status, name):
        return LicenseCheck(iri=f"http://l/{name}", name=name, is_open=status != Status.FAIL,
                            is_recommended=status == Status.OK, status=status)

    assert _rules(ValidationReport(file="x", license=LicenseReport())) == [Rule.LICENSE_MISSING]
    assert _rules(ValidationReport(file="x", license=LicenseReport(checks=[lic(Status.OK, "CC0")]))) == []
    two = LicenseReport(checks=[lic(Status.OK, "CC0"), lic(Status.FAIL, "NC")])
    assert sorted(_rules(ValidationReport(file="x", license=two))) == sorted(
        [Rule.LICENSE_NOT_OPEN, Rule.LICENSE_MULTIPLE]
    )


def _namespace(uri: str, status: Status, terms: list[TermCheck]) -> NamespaceReport:
    return NamespaceReport(
        prefix="p", uri=uri,
        resolution=NamespaceCheck(prefix="p", uri=uri, status=status),
        terms=terms,
    )


def _term(uri: str, status: Status, **kw) -> TermCheck:
    return TermCheck(term_uri=uri, prefix="p", local_name=uri.rsplit("/", 1)[-1], status=status, **kw)


def test_unresolved_namespace_and_term_findings_skip_uncheckable_terms():
    report = ValidationReport(file="ns.ttl", namespaces=[
        _namespace("http://dead.example/", Status.FAIL, [_term("http://dead.example/A", Status.SKIP)]),
        _namespace("http://ok.example/", Status.OK, [
            _term("http://ok.example/missing", Status.FAIL),
            _term("http://ok.example/old", Status.WARN, deprecated="owl:deprecated"),
            _term("http://ok.example/fine", Status.OK),
        ]),
    ])
    assert sorted(_rules(report)) == sorted([
        Rule.NAMESPACE_UNRESOLVED, Rule.EXTERNAL_TERM_NOT_FOUND, Rule.EXTERNAL_TERM_DEPRECATED,
    ])


def test_reasoner_findings_are_counted_per_individual_and_class():
    report = ValidationReport(file="r.ttl", reasoner=ReasonerReport(
        consistent=False,
        inconsistent_individuals=["http://e/x", "http://e/y"],
        unsatisfiable_classes=["http://e/C"],
        checks=[ReasonerCheck(key="ontology_consistency", label="Logical findings", status=Status.FAIL)],
    ))
    assert report.severity_summary.errors == 3


def test_parse_errors_are_errors():
    report = ValidationReport(file="x.ttl", parse_errors=["boom"])
    assert report.has_errors
    assert _rules(report) == [Rule.PARSE_ERROR]


def test_metadata_gaps_are_recommendations_in_both_tiers():
    report = ValidationReport(file="m.ttl", ontology_metadata=MetadataReport(checks=[
        MetadataCheck(key="title", label="Title", property="dcterms:title", tier="core", status=Status.WARN),
        MetadataCheck(key="created", label="Created", property="dcterms:created", tier="additional", status=Status.WARN),
        MetadataCheck(key="creator", label="Creator", property="dcterms:creator", tier="core", status=Status.OK),
    ]))
    assert report.severity_summary.recommendations == 2
    assert not report.has_errors


def test_findings_are_sorted_most_severe_first():
    report = ValidationReport(
        file="x.ttl",
        unused_prefixes=[UnusedPrefix(prefix="x", uri="http://x/")],
        parse_errors=["boom"],
    )
    assert [f.severity for f in report.severity_summary.findings] == [Severity.ERROR, Severity.RECOMMENDATION]


def test_wording():
    assert count_label(Severity.ERROR, 1) == "1 error"
    assert count_label(Severity.RECOMMENDATION, 2) == "2 recommendations"


# --- the reports -----------------------------------------------------------


def _recommendations_only() -> ValidationReport:
    return ValidationReport(
        file="docs.ttl",
        unused_prefixes=[UnusedPrefix(prefix="x", uri="http://x/")],
        definition_docs=DefinitionDocumentationReport(
            total_definitions=2,
            checks=[_doc_check("A", label=False, comment=True), _doc_check("B", label=False, comment=True)],
        ),
        license=LicenseReport(),
    )


def test_html_headline_counts_and_marks():
    html = render_report(_recommendations_only())

    headline = html.split('<div class="severity-summary">')[1].split("</div>")[0]
    assert "<strong>0</strong> errors" in headline
    assert "<strong>4</strong> recommendations" in headline
    assert 'title="Recommendation: ' in headline  # tooltip instead of a legend
    assert "&#x1F4A1;" in html
    assert "(2 recommendations)" in html  # the Labels row: two terms without a label
    assert "legend" not in html


def test_html_shows_errors_with_a_cross():
    report = ValidationReport(file="bad.ttl", reasoner=ReasonerReport(
        consistent=False,
        inconsistent_individuals=["http://example.org/x"],
        checks=[ReasonerCheck(key="ontology_consistency", label="Logical findings", status=Status.FAIL, message="bad")],
    ))
    html = render_report(report)

    assert "<strong>1</strong> error" in html
    assert 'title="Error"' in html
    assert "(1 error)" in html


def test_markdown_summarises_by_severity():
    md = report_as_markdown(_recommendations_only())

    assert "> ✗ 0 errors" in md
    assert "4 recommendations" in md
    assert "| \U0001F4A1 Recommendation | Labels | 2 |" in md


def test_json_includes_findings_and_keeps_item_statuses():
    data = json.loads(report_as_json(_recommendations_only()))
    summary = data["severity_summary"]

    assert summary["has_errors"] is False
    assert summary["recommendations"] == 4
    assert {f["severity"] for f in summary["findings"]} == {"recommendation"}
    assert {"rule", "check", "severity", "subject", "message"} <= set(summary["findings"][0])
    assert data["definition_docs"]["checks"][0]["status"] == "warn"


# --- the fixtures and the CLI ----------------------------------------------


@pytest.mark.parametrize("path, has_errors", [(BROKEN, True), (SAMPLE, False)])
async def test_fixtures(path, has_errors):
    report, _ = await run_full_validation(path, include_mermaid=False, skip_resolution=True)

    assert report.has_errors is has_errors
    summary = report.severity_summary
    if has_errors:
        assert summary.errors and summary.warnings and summary.recommendations
    else:
        assert summary.findings == []


def _cli(path: Path):
    return CliRunner().invoke(main, ["check", str(path), "--skip-resolution"])


def test_cli_exit_code_is_one_with_errors():
    assert _cli(BROKEN).exit_code == 1


def test_cli_exit_code_is_zero_without_findings():
    assert _cli(SAMPLE).exit_code == 0


def test_cli_exit_code_is_zero_with_recommendations_only(tmp_path):
    ontology = tmp_path / "plain.ttl"
    ontology.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<http://example.org/o> a owl:Ontology .\n"
        "<http://example.org/o#Thing> a owl:Class .\n"
    )
    result = _cli(ontology)

    assert result.exit_code == 0
    assert "0 errors" in result.output
    assert "recommendation" in result.output


def test_cli_exit_code_is_zero_with_warnings_only(tmp_path):
    ontology = tmp_path / "mixed.ttl"
    ontology.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "<http://example.org/o> a owl:Ontology .\n"
        "<http://example.org/o#A> a owl:Class ; rdfs:label \"A\"@en ; rdfs:comment \"a\"@en .\n"
        "<https://example.org/o#B> a owl:Class ; rdfs:label \"B\"@en ; rdfs:comment \"b\"@en .\n"
    )
    result = _cli(ontology)

    assert result.exit_code == 0
    assert "0 errors" in result.output
    assert "1 warning" in result.output


def _terminal(report: ValidationReport) -> str:
    output = StringIO()
    print_report(report, Console(file=output, width=180, color_system=None))
    return output.getvalue()


def _html_section(report: ValidationReport, anchor: str) -> str:
    return render_report(report).split(f'id="{anchor}"')[1].split("</section>")[0]


@pytest.mark.parametrize("severity", list(Severity))
@pytest.mark.parametrize("rule,anchor", [
    (Rule.LABEL_MISSING, "labels"),
    (Rule.COMMENT_MISSING, "comments"),
])
def test_documentation_rules_are_independently_configurable(monkeypatch, rule, anchor, severity):
    monkeypatch.setitem(RULE_SEVERITY, rule, severity)
    report = ValidationReport(file="docs.ttl", definition_docs=DefinitionDocumentationReport(
        total_definitions=1,
        checks=[_doc_check("A", label=anchor != "labels", comment=anchor != "comments")],
    ))
    assert report.severity_summary.count(severity) == 1
    assert report.has_errors is (severity == Severity.ERROR)
    section = _html_section(report, anchor)
    assert f'title="{severity.value.title()}"' in section
    md = report_as_markdown(report).split(f"## {anchor.title()}")[1].split("## ")[0]
    assert f"{severity.value}: missing" in md
    assert severity.value.upper() in _terminal(report)


@pytest.mark.parametrize("rule,key", [
    (Rule.INCONSISTENT_INDIVIDUAL, "inconsistent_individuals"),
    (Rule.UNSATISFIABLE_CLASS, "unsatisfiable_classes"),
])
@pytest.mark.parametrize("severity", list(Severity))
def test_reasoner_rules_are_independently_configurable(monkeypatch, rule, key, severity):
    monkeypatch.setitem(RULE_SEVERITY, rule, severity)
    reasoner = ReasonerReport(
        inconsistent_individuals=["http://example.org/a"] if key == "inconsistent_individuals" else [],
        unsatisfiable_classes=["http://example.org/C"] if key == "unsatisfiable_classes" else [],
        checks=[
            ReasonerCheck(key="ontology_consistency", label="Logical findings", status=Status.FAIL),
            ReasonerCheck(key=key, label="Affected terms", status=Status.FAIL),
        ],
    )
    report = ValidationReport(file="logic.ttl", reasoner=reasoner)
    assert report.severity_summary.count(severity) == 1
    assert reasoner.findings_for_check(key)[0].severity == severity
    assert f'title="{severity.value.title()}"' in _html_section(report, "reasoner")
    assert f"| Affected terms | {severity.value} |" in report_as_markdown(report)
    row = next(line for line in _terminal(report).splitlines() if "Affected terms" in line)
    assert severity.value.upper() in row


@pytest.mark.parametrize("mismatch,omission", [
    (Severity.ERROR, Severity.RECOMMENDATION),
    (Severity.WARNING, Severity.ERROR),
])
def test_mixed_domain_range_findings_keep_both_levels(monkeypatch, mismatch, omission):
    monkeypatch.setitem(RULE_SEVERITY, Rule.DOMAIN_RANGE_MISMATCH, mismatch)
    monkeypatch.setitem(RULE_SEVERITY, Rule.DOMAIN_RANGE_MISSING, omission)
    graph = Graph().parse(data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        <http://example.org/o> a owl:Ontology .
        <http://example.org/o#p> a owl:ObjectProperty ; rdfs:range xsd:string .
    """, format="turtle")
    report = ValidationReport(file="mixed.ttl", domains_ranges=check_domains_ranges(graph))
    assert len(report.findings()) == 2
    assert report.severity_summary.count(mismatch) == 1
    assert report.severity_summary.count(omission) == 1
    html = _html_section(report, "domains-ranges")
    md = report_as_markdown(report)
    cli = _terminal(report)
    for severity in (mismatch, omission):
        assert f'title="{severity.value.title()}"' in html
        assert f"| {SEVERITY_STYLES[severity].glyph} {severity.value.title()} | Domains & ranges | 1 |" in md
        assert severity.value.upper() in cli
    for finding in report.findings():
        assert finding.message in html
        assert finding.message in md
        assert finding.message in cli
    assert "| Domains & ranges | 2 |" not in md


def test_datatype_deduplication_matches_all_reports():
    iri = "http://www.w3.org/2001/XMLSchema#stirng"
    ns = NamespaceReport(
        prefix="xsd", uri="http://www.w3.org/2001/XMLSchema#",
        resolution=NamespaceCheck(prefix="xsd", uri="http://www.w3.org/2001/XMLSchema#", status=Status.OK),
        terms=[TermCheck(term_uri=iri, prefix="xsd", local_name="stirng", status=Status.FAIL)],
    )
    report = ValidationReport(
        file="datatype.ttl", namespaces=[ns],
        datatypes=DatatypeReport(total_datatypes=1, status=Status.FAIL, usages=[
            DatatypeUsage(datatype=iri, display_name="stirng", recognised=False, status=Status.FAIL),
        ]),
    )
    assert _rules(report) == [Rule.DATATYPE_UNRECOGNISED]
    assert report.external_term_checks == []
    assert report.external_terms_unchecked is False
    for text in (_html_section(report, "external-terms"),
                 report_as_markdown(report).split("## External term definitions")[1].split("## ")[0]):
        assert "stirng" not in text
        assert "Terms not found in their vocabulary" not in text
        assert "1 not found" not in text
        assert "no external terms to check" in text.lower()
    assert "Terms not found in remote vocabulary" not in _terminal(report)


async def test_offline_skips_are_consistent_in_all_outputs():
    report, _ = await run_full_validation(BROKEN, include_mermaid=False, skip_resolution=True)
    assert report.imports is not None and report.imports.skipped
    assert report.namespace_resolution_skipped
    assert report.external_terms_unchecked
    assert report.severity_summary.for_check("imports") == []
    html = render_report(report)
    assert html.count("resolution skipped") >= 2  # imports and namespaces rows
    assert "not checked (namespaces not resolved)" in html
    md = report_as_markdown(report)
    imports = md.split("## Imports")[1].split("## ")[0]
    assert "| not checked |" in imports
    assert "| warning |" not in imports
    assert "Not checked (namespaces not resolved)" in md
    cli = _terminal(report)
    assert "resolution skipped" in cli
    assert "not checked (namespaces not resolved)" in cli
    assert "All checks passed" not in cli


def test_unavailable_terms_are_not_successful():
    ns = NamespaceReport(
        prefix="ex", uri="http://example.org/",
        resolution=NamespaceCheck(prefix="ex", uri="http://example.org/", status=Status.FAIL),
        terms=[TermCheck(term_uri="http://example.org/C", prefix="ex", local_name="C", status=Status.SKIP)],
    )
    report = ValidationReport(file="unavailable.ttl", namespaces=[ns])
    assert report.external_terms_unchecked
    assert report.severity_summary.for_check("external-terms") == []
    html = _html_section(report, "external-terms")
    assert "not checked" in html
    assert 'title="Warning"' not in html
    assert "Not checked (namespaces not resolved)" in report_as_markdown(report)
    assert "not checked (namespaces not resolved)" in _terminal(report)


@pytest.mark.parametrize("severity", list(Severity))
def test_language_tag_wording_uses_its_rule(monkeypatch, severity):
    monkeypatch.setitem(RULE_SEVERITY, Rule.LANG_TAG_MISSING, severity)
    report = ValidationReport(file="language.ttl", lang_tags=LangTagReport(status=Status.WARN))
    assert report.severity_summary.count(severity) == 1
    assert f"> **{severity.value.title()}:** labels" in report_as_markdown(report)
    assert f'title="{severity.value.title()}"' in _html_section(report, "language-tags")
    assert severity.value.upper() in _terminal(report)


def test_partial_external_checks_keep_checked_findings():
    report = ValidationReport(file="partial.ttl", namespaces=[
        _namespace("http://dead.example/", Status.FAIL, [_term("http://dead.example/C", Status.SKIP)]),
        _namespace("http://ok.example/", Status.OK, [_term("http://ok.example/missing", Status.FAIL)]),
    ])
    assert not report.external_terms_unchecked
    assert len(report.severity_summary.for_check("external-terms")) == 1
    html = _html_section(report, "external-terms")
    assert 'title="Warning"' in html
    assert "<strong>1</strong> not found" in html
    assert "<strong>1</strong> skipped" in html
    assert "not checked (namespaces not resolved)" not in report_as_markdown(report).lower()
    assert "not checked (namespaces not resolved)" not in _terminal(report)


def test_reasoner_rollup_uses_worst_of_independent_rules(monkeypatch):
    monkeypatch.setitem(RULE_SEVERITY, Rule.INCONSISTENT_INDIVIDUAL, Severity.WARNING)
    monkeypatch.setitem(RULE_SEVERITY, Rule.UNSATISFIABLE_CLASS, Severity.RECOMMENDATION)
    reasoner = ReasonerReport(
        inconsistent_individuals=["http://example.org/a"],
        unsatisfiable_classes=["http://example.org/C"],
        checks=[
            ReasonerCheck(key="ontology_consistency", label="Logical findings", status=Status.FAIL),
            ReasonerCheck(key="inconsistent_individuals", label="Inconsistent individuals", status=Status.FAIL),
            ReasonerCheck(key="unsatisfiable_classes", label="Unsatisfiable classes", status=Status.WARN),
        ],
    )
    report = ValidationReport(file="logic.ttl", reasoner=reasoner)
    assert not report.has_errors
    assert report.severity_summary.warnings == 1
    assert report.severity_summary.recommendations == 1
    assert 'title="Error"' not in _html_section(report, "reasoner")
    md = report_as_markdown(report)
    assert "| Logical findings | warning |" in md
    assert "| Inconsistent individuals | warning |" in md
    assert "| Unsatisfiable classes | recommendation |" in md
    row = next(line for line in _terminal(report).splitlines() if "Logical findings" in line)
    assert "WARNING" in row
