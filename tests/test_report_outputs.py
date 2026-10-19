"""The report formats retain complete pipeline results and reuse findings."""

from enum import Enum
from io import StringIO
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDFS, SKOS
from rich.console import Console

from askwol.checks import CHECKS, DATATYPE_SCOPE, REASONER_SCOPE
from askwol.agent_api import compact_report
from askwol.lang_tags import check_lang_tags
from askwol.models import (
    ImportsCheck,
    ImportsReport,
    InputDiagnostic,
    NamespaceCheck,
    NamespaceReport,
    Status,
    TermCheck,
    ValidationReport,
)
from askwol.pipeline import run_full_validation
from askwol.report import print_report, report_as_json, report_as_markdown
from askwol.report_html import render_report


def _human_outputs(report):
    terminal = StringIO()
    print_report(report, Console(file=terminal, width=220, color_system=None))
    return render_report(report), report_as_markdown(report), terminal.getvalue()


async def test_failed_parsing_does_not_report_unrun_checks_as_passed(tmp_path):
    source = tmp_path / "invalid.ttl"
    source.write_text("this is not valid Turtle !!")
    report, _ = await run_full_validation(source, skip_resolution=True, include_mermaid=False)

    assert report.parse_errors
    for output in _human_outputs(report):
        assert "Ontology checks were not run" in output
        assert "Unused prefixes" not in output
        assert "no external terms to check" not in output
        assert "Namespaces checked" not in output
    assert all(check.status == "skipped" for check in compact_report(report).checks)


def test_input_diagnostic_is_actionable_without_duplicate_parse_message():
    diagnostic = InputDiagnostic(
        code="html_instead_of_rdf", message="This is an HTML file viewer.",
        suggested_url="https://github.com/example/ontology/raw/main/ontology.ttl",
        guide_url="https://lod-4tu.tudelft.nl/askwol/guide#server-config",
    )
    report = ValidationReport(file="ontology.ttl", input_error=diagnostic, parse_errors=[diagnostic.message])

    for output in _human_outputs(report):
        assert "Input error" in output
        assert "Parse error" not in output and "Parse Errors" not in output
        assert output.count(diagnostic.message) == 1
        assert diagnostic.suggested_url in output
        assert diagnostic.guide_url in output
        assert "Ontology checks were not run" in output


@pytest.mark.parametrize(("line", "column", "detail", "expected"), [
    (3, 8, "Expected a full stop.", "Parser stopped at line 3, column 8: Expected a full stop."),
    (3, None, "Invalid line.", "Parser stopped at line 3: Invalid line."),
    (None, None, "Unexpected end of input.", "Unexpected end of input."),
    (3, 8, None, "Parser stopped at line 3, column 8."),
    (None, None, None, None),
])
def test_syntax_diagnostic_shows_only_available_parser_information(line, column, detail, expected):
    diagnostic = InputDiagnostic(
        code="invalid_rdf", message="Could not parse the input as Turtle.", format="turtle",
        detail=detail, line=line, column=column,
        guidance="Fix the reported error and try again. Further syntax errors may appear.",
        guide_url="https://lod-4tu.tudelft.nl/askwol/guide#rdf-syntax",
    )
    report = ValidationReport(file="ontology.ttl", input_error=diagnostic, parse_errors=[diagnostic.message])

    for output in _human_outputs(report):
        assert output.count(diagnostic.message) == 1
        assert output.count(diagnostic.guidance) == 1
        assert "Help with RDF syntax" in output
        if expected:
            assert output.count(expected) == 1
        else:
            assert "Parser stopped" not in output


def test_syntax_diagnostic_is_preserved_in_full_and_compact_json():
    diagnostic = InputDiagnostic(
        code="invalid_rdf", message="Could not parse the input as JSON-LD.", format="json-ld",
        detail="Expected a property name.", line=2, column=4,
        source="https://example.org/context.jsonld", guidance="Fix the context and try again.",
        guide_url="https://lod-4tu.tudelft.nl/askwol/guide#rdf-syntax",
    )
    report = ValidationReport(file="ontology.jsonld", input_error=diagnostic, parse_errors=[diagnostic.message])

    restored = ValidationReport.model_validate_json(report_as_json(report))
    assert restored.input_error == diagnostic
    assert compact_report(report).model_dump(mode="json")["input_error"] == diagnostic.model_dump(mode="json")
    for output in _human_outputs(report):
        assert "Context:" in output
        assert diagnostic.source in output
        assert output.index("Context:") < output.index("Parser stopped")


def test_parser_metadata_is_literal_markdown_and_terminal_text():
    payload = '<img src=x onerror=alert(1)> [bold]parser[/bold]'
    source = "javascript:alert(1)"
    report = ValidationReport(file="ontology.ttl", input_error=InputDiagnostic(
        code="invalid_rdf", message="Could not parse the input as Turtle.",
        detail=payload, source=source, guidance=payload,
    ))

    _, markdown, terminal = _human_outputs(report)

    assert markdown.count('&lt;img src=x onerror=alert(1)&gt; \\[bold\\]parser\\[/bold\\]') == 2
    assert f"Context: {source}" in markdown
    assert f"](<{source}>)" not in markdown
    assert terminal.count(payload) == 2


@pytest.mark.parametrize("coordinate", ["line", "column"])
def test_parser_coordinates_are_one_based(coordinate):
    with pytest.raises(ValidationError):
        InputDiagnostic(code="invalid_rdf", message="Invalid RDF.", **{coordinate: 0})


def test_source_guidance_is_literal_and_does_not_add_findings():
    warning = '<img src=x onerror=alert(1)> uses file:///tmp/local#Term [bold]'
    report = ValidationReport(file="ontology.ttl", input_warnings=[warning])
    html, markdown, text = _human_outputs(report)

    assert "Source guidance" in html and "Source guidance" in markdown and "Source guidance" in text
    assert "<img src=x" not in html and "&lt;img" in html
    assert "<img src=x" not in markdown and "&lt;img" in markdown
    assert warning in text
    assert report.findings() == []
    assert compact_report(report).input_warnings == [warning]
    assert compact_report(report).severity_summary == report.severity_summary


async def test_default_text_identifies_missing_documentation_and_links_its_guides(tmp_path):
    source = tmp_path / "undocumented.ttl"
    source.write_text('''@prefix : <https://example.org/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://example.org/ontology> a owl:Ontology .
:UndocumentedCanary a owl:Class .
''')
    report, _ = await run_full_validation(source, skip_resolution=True, include_mermaid=False)
    _, markdown, text = _human_outputs(report)

    assert "https://example.org/ontology#UndocumentedCanary" in text
    assert "rdfs:label" in text and "rdfs:comment" in text
    for check in ("labels", "comments"):
        finding = next(finding for finding in report.findings() if finding.check == check)
        assert text.count(finding.guide_url) == 1
        assert markdown.count(f"](<{finding.guide_url}>)") == 1


def test_discovered_import_retains_warning_and_both_sources_in_every_report():
    original = "https://example.org/ontology"
    retrieved = "https://example.org/releases/ontology.ttl"
    note = "RDF found through an HTML link. Other tools may need a direct RDF address."
    resolution = NamespaceCheck(
        prefix="import", uri=original, status=Status.WARN, http_status=200,
        content_type="text/html", is_valid_rdf=True,
        retrieved_url=retrieved, discovery_note=note,
    )
    report = ValidationReport(file="ontology.ttl", imports=ImportsReport(
        status=Status.WARN, checks=[ImportsCheck(iri=original, resolution=resolution)],
    ), namespaces=[NamespaceReport(prefix="ex", uri=original, resolution=resolution.model_copy(update={"status": Status.OK}))])

    for output in _human_outputs(report):
        assert original in output and retrieved in output and note in output
        assert "declared import(s), all resolve" not in output
        assert "declared, all resolve" not in output
        assert 'title="all resolve"' not in output
    compact = compact_report(report)
    finding = compact.severity_summary.findings[0]
    assert finding.rule == "imports.discovered" and finding.severity == "warning"
    assert finding.subject == original and retrieved in finding.message
    assert compact.severity_summary == report.severity_summary
    assert compact.severity_summary.warnings == 1


@pytest.mark.parametrize(("values", "issue_type", "wording"), [
    ((Literal("First"), Literal("Second")), "missing_tag", "1 issue with untagged values"),
    ((Literal("B", lang="en"),), "missing_language", "1 issue with missing languages"),
])
def test_language_report_counts_subject_property_issues(values, issue_type, wording):
    ex = Namespace("https://example.org/ontology#")
    graph = Graph()
    for language in ("de", "en", "nl"):
        graph.add((ex.A, RDFS.label, Literal(f"A-{language}", lang=language)))
    for value in values:
        graph.add((ex.B, RDFS.label, value))
    report = ValidationReport(file="ontology.ttl", lang_tags=check_lang_tags(
        graph, {"ex": str(ex), "rdfs": str(RDFS)},
    ))
    original = report_as_json(report)

    html, markdown, terminal = _human_outputs(report)
    restored = ValidationReport.model_validate_json(original)

    assert len(restored.lang_tags.issues) == 1
    issue = restored.lang_tags.issues[0]
    assert issue.subject_uri == str(ex.B) and issue.property == "rdfs:label"
    assert issue.issue_type == issue_type
    assert issue.languages_expected == ["de", "en", "nl"]
    assert len(restored.severity_summary.for_check("language-tags")) == 1
    assert wording in html and wording in markdown
    assert "1 consistency issue" in terminal
    assert report_as_json(report) == original


def test_language_expectations_remain_specific_to_each_property():
    ex = Namespace("https://example.org/ontology#")
    graph = Graph()
    for prop, languages in ((RDFS.label, ("en", "nl")), (SKOS.definition, ("de", "fr"))):
        for language in languages:
            graph.add((ex.A, prop, Literal(f"A-{language}", lang=language)))
    graph.add((ex.B, RDFS.label, Literal("B")))
    graph.add((ex.B, SKOS.definition, Literal("B-de", lang="de")))
    report = ValidationReport(file="ontology.ttl", lang_tags=check_lang_tags(
        graph, {"ex": str(ex), "rdfs": str(RDFS), "skos": str(SKOS)},
    ))

    html, markdown, _ = _human_outputs(report)
    section = html.split('id="language-tags"', 1)[1].split("</section>", 1)[0]
    headline, table = section.split("<table>", 1)

    assert "expected " not in headline.lower()
    for prop, expected, other in (("rdfs:label", ("en", "nl"), ("de", "fr")),
                                  ("skos:definition", ("de", "fr"), ("en", "nl"))):
        html_row = next(row for row in table.split("</tr>") if f"<code>{prop}</code>" in row)
        markdown_row = next(row for row in markdown.splitlines() if f"`{prop}`" in row)
        assert all(f"<code>{language}</code>" in html_row for language in expected)
        assert all(f"<code>{language}</code>" not in html_row for language in other)
        assert markdown_row.endswith(f"| {', '.join(expected)} |")
    assert len(report.lang_tags.issues) == 2


@pytest.mark.parametrize(("status", "http_status", "content_type", "heading"), [
    (Status.OK, 200, "application/pdf", "Namespaces without retrieved RDF"),
    (Status.OK, None, None, "Namespaces without retrieved RDF"),
    (Status.FAIL, 403, "text/html", "Namespace retrieval failures"),
])
def test_namespace_wording_does_not_assume_html_or_network_failure(status, http_status, content_type, heading):
    uri = "https://example.org/vocab#"
    report = ValidationReport(file="ontology.ttl", namespaces=[NamespaceReport(
        prefix="ex", uri=uri,
        resolution=NamespaceCheck(
            prefix="ex", uri=uri, status=status, http_status=http_status,
            content_type=content_type, is_valid_rdf=False,
            error="HTTP 403" if status == Status.FAIL else None,
        ),
        terms=[TermCheck(term_uri=uri + "A", prefix="ex", local_name="A", status=Status.OK)],
    )])

    markdown = report_as_markdown(report)

    assert f"## {heading}" in markdown
    for claim in ("returning HTML", "HTTP 200", "could **not** be verified", "could not be reached", "unreachable"):
        assert claim not in markdown
    assert report.namespaces[0].valid_terms == 1
    assert len(report.severity_summary.for_check("namespaces")) == int(status == Status.FAIL)
    assert ValidationReport.model_validate_json(report_as_json(report)).namespaces == report.namespaces


async def test_pipeline_findings_survive_each_output_format(monkeypatch):
    source = Path(__file__).resolve().parent.parent / "html" / "ontologies" / "broken.ttl"
    report, _ = await run_full_validation(source, skip_resolution=True, include_mermaid=False)
    original_findings = ValidationReport.findings
    calls = []

    def findings(self):
        calls.append(self)
        return original_findings(self)

    monkeypatch.setattr(ValidationReport, "findings", findings)
    terminal = StringIO()
    outputs = []
    for render in (
        render_report,
        report_as_markdown,
        lambda result: print_report(result, Console(file=terminal, width=140, color_system=None)),
    ):
        calls.clear()
        output = render(report)
        outputs.append(output if output is not None else terminal.getvalue())
        # Building the complete finding list is expensive for large ontologies.
        # Every check in an output must share the same computed summary.
        assert len(calls) == 1

    html, markdown, text = outputs
    for check in CHECKS:
        assert f'id="{check["report_anchor"]}"' in html
    for output in outputs:
        for finding in ("hasNickname", "badFormat", "HasOwner", "worksFor", "Biology", "neverused"):
            assert finding in output
    for heading in (
        "## Imports", "## Open licence", "## IRI strategy", "## IRI scheme",
        "## External term definitions", "## Ontology metadata", "## Internal term definitions",
        "## Term inventory", "## Domains", "## Datatypes", "## Labels", "## Comments",
        "## Reasoner checks", "## Language tag consistency", "## Non-ontology terms",
    ):
        assert heading in markdown
    assert "Checks overview" in text
    assert "Reasoner checks" in text


@pytest.mark.parametrize("filename", ["input[bold].ttl", "folder[/red]/ontology.ttl"])
def test_terminal_filename_and_parse_error_are_literal(filename):
    output = StringIO()
    error = "Unexpected [/blue] token [bold]"
    report = ValidationReport(file=filename, parse_errors=[error])

    print_report(report, Console(file=output, width=140, color_system=None))

    assert filename in output.getvalue()
    assert error in output.getvalue()


async def test_terminal_rdf_values_cannot_become_rich_markup():
    source = Path(__file__).resolve().parent.parent / "html" / "ontologies" / "broken.ttl"
    report, _ = await run_full_validation(source, skip_resolution=True, include_mermaid=False)
    payload = "literal[/red] [bold]"

    def replace_display_values(value):
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                child = getattr(value, name)
                if isinstance(child, str) and not isinstance(child, Enum):
                    # Preserve the identifiers used to select check algorithms.
                    if name not in {"key", "strategy", "issue_type", "tier", "category"}:
                        setattr(value, name, payload)
                else:
                    replace_display_values(child)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                if isinstance(child, str) and not isinstance(child, Enum):
                    value[i] = payload
                else:
                    replace_display_values(child)

    replace_display_values(report)
    output = StringIO()
    print_report(report, Console(file=output, width=180, color_system=None))

    assert payload in output.getvalue()
    # Table cells as well as inline titles and warnings retain literal values.
    assert output.getvalue().count(payload) > 15


async def test_corrected_unknown_results_and_exemptions_across_formats(tmp_path):
    source = tmp_path / 'ontology.ttl'
    source.write_text('''
@prefix : <https://example.org/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dct: <http://purl.org/dc/terms/> .
<https://example.org/ontology> a owl:Ontology ; dct:license <https://example.org/licence> .
:Old a owl:Class ; owl:deprecated true .
:p a owl:DatatypeProperty ; rdfs:domain :Old ; rdfs:range <https://example.org/unknown#Datatype> ;
   rdfs:label "p" ; rdfs:comment "A property." .
''')
    report, _ = await run_full_validation(source, skip_resolution=True, include_mermaid=False)
    restored = ValidationReport.model_validate_json(report_as_json(report))
    assert restored.reasoner.consistent is None
    assert restored.license.checks[0].is_open is None
    assert restored.license.checks[0].category == 'unrecognised'
    assert restored.definition_docs.with_label == 1
    assert restored.definition_docs.with_comment == 1
    assert restored.definition_docs.deprecated_count == 1
    assert not restored.definition_docs.missing_label
    assert not restored.definition_docs.missing_comment
    assert restored.severity_summary.errors == 0
    assert any(f.rule == 'datatypes.unrecognised' and f.severity == 'warning'
               for f in restored.findings())

    terminal = StringIO()
    print_report(restored, Console(file=terminal, width=220, color_system=None))
    outputs = [render_report(restored), report_as_markdown(restored), terminal.getvalue()]
    for output in outputs:
        assert 'unrecognised' in output
        assert REASONER_SCOPE in ' '.join(output.split())
    for output in outputs[1:]:
        assert 'non-open' not in output.lower()
    assert DATATYPE_SCOPE in outputs[0] and DATATYPE_SCOPE in outputs[1]
    assert '1 deprecated term(s) exempt' in outputs[0]
    assert 'exempt (deprecated)' in outputs[1]
