"""The report formats retain complete pipeline results and reuse findings."""

from enum import Enum
from io import StringIO
from pathlib import Path

import pytest
from pydantic import BaseModel
from rich.console import Console

from askwol.checks import CHECKS, DATATYPE_SCOPE, REASONER_SCOPE
from askwol.models import ValidationReport
from askwol.pipeline import run_full_validation
from askwol.report import print_report, report_as_json, report_as_markdown
from askwol.report_html import render_report


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
