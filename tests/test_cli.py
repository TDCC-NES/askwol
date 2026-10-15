"""CLI output destinations, stream separation, and exit status."""

import json

import pytest
from click.testing import CliRunner

from askwol import cli
from askwol.models import ValidationReport


@pytest.fixture
def ontology(tmp_path, monkeypatch):
    path = tmp_path / "input[bold].ttl"
    path.write_text("")

    async def validate(source, **kwargs):
        return ValidationReport(file=str(source)), ""

    monkeypatch.setattr(cli, "run_full_validation", validate)
    return path


@pytest.mark.parametrize("output_format", ["text", "json", "markdown"])
@pytest.mark.parametrize("has_errors", [False, True])
def test_output_file_contains_report_and_preserves_exit_code(ontology, tmp_path, monkeypatch, output_format, has_errors):
    async def validate(source, **kwargs):
        return ValidationReport(file=str(source), parse_errors=["invalid syntax"] if has_errors else []), ""

    monkeypatch.setattr(cli, "run_full_validation", validate)
    output = tmp_path / "report[bold].txt"
    args = ["check", str(ontology), "-o", str(output)]
    if output_format != "text":
        args += ["--format", output_format]

    result = CliRunner().invoke(cli.main, args)

    assert result.exit_code == int(has_errors), result.output
    assert result.stdout == ""
    assert ontology.name in result.stderr
    assert output.name in result.stderr
    text = output.read_text()
    assert "\x1b" not in text
    if output_format == "json":
        data = json.loads(text)
        assert data["file"] == str(ontology)
        assert data["severity_summary"]["has_errors"] is has_errors
    elif output_format == "markdown":
        assert text.startswith("# Ontology Check Report")
    else:
        assert "Ontology Check:" in text
    assert ("invalid syntax" in text) is has_errors


@pytest.mark.parametrize("output_format", ["text", "json", "markdown"])
def test_report_defaults_to_stdout_and_progress_to_stderr(ontology, output_format):
    result = CliRunner().invoke(cli.main, ["check", str(ontology), "--format", output_format])

    assert result.exit_code == 0, result.output
    assert result.stdout
    assert "Checking" not in result.stdout
    assert ontology.name in result.stderr
    if output_format == "json":
        assert json.loads(result.stdout)["file"] == str(ontology)
