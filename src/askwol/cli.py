"""CLI entry point for the ontology checker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

from askwol.input_utils import RDF_FORMAT_SUFFIXES, github_raw_url, validate_base_uri
from askwol.pipeline import run_full_validation
from askwol.report import print_report, report_as_json, report_as_markdown


class _OntologyFile(click.Path):
    def convert(self, value, param, ctx):
        if isinstance(value, str) and "://" in value:
            try:
                raw_url = github_raw_url(value)
            except ValueError:
                raw_url = None
            message = "This command accepts a local file, not a URL. Download the raw ontology file, then run askwol check FILE."
            if raw_url:
                message += f" GitHub's file viewer returns HTML; use this raw URL: {raw_url}"
            self.fail(message, param, ctx)
        return super().convert(value, param, ctx)


def _base_uri_option(ctx, param, value):
    if value is None:
        return None
    try:
        return validate_base_uri(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc), ctx=ctx, param=param) from exc


@click.group()
def main() -> None:
    """OWL Ontology Checker  -  validate namespace resolution and term existence."""


@main.command()
@click.argument("file", type=_OntologyFile(exists=True, dir_okay=False, readable=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    help="Report output format.",
)
@click.option("--input-format", type=click.Choice(list(RDF_FORMAT_SUFFIXES)), help="RDF syntax; otherwise inferred from the filename.")
@click.option("--base-uri", callback=_base_uri_option, help="Absolute base IRI for relative identifiers; does not download a URL.")
@click.option(
    "-o", "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Write report to file instead of stdout.",
)
@click.option("--timeout", type=click.FloatRange(min=0, min_open=True), default=30.0, help="HTTP timeout in seconds, including JSON-LD contexts.")
@click.option(
    "--skip-resolution",
    is_flag=True,
    default=False,
    help="Skip HTTP resolution (offline mode).",
)
def check(
    file: Path, output_format: str, output: Path | None, timeout: float,
    skip_resolution: bool, input_format: str | None, base_uri: str | None,
) -> None:
    """Check an ontology file for namespace resolution and term validity."""
    console = Console(stderr=True)
    console.print(f"Checking [bold]{escape(str(file))}[/bold] …")

    options = {}
    if input_format:
        options["format"] = input_format
    if base_uri:
        options["base_uri"] = base_uri
    try:
        report, _mermaid = asyncio.run(
            run_full_validation(
                file, include_mermaid=False, skip_resolution=skip_resolution, timeout=timeout,
                **options,
            )
        )
    except Exception as exc:
        raise click.ClickException("Validation could not complete. " + (str(exc).strip() or type(exc).__name__)) from exc

    if output_format == "json":
        result = report_as_json(report)
    elif output_format == "markdown":
        result = report_as_markdown(report)
    else:
        result = None

    if output:
        if result is None:
            with output.open("w", encoding="utf-8") as stream:
                print_report(report, Console(file=stream, color_system=None))
        else:
            output.write_text(result, encoding="utf-8")
        console.print(f"Report written to [bold]{escape(str(output))}[/bold]")
    elif result is not None:
        click.echo(result)
    else:
        print_report(report)

    sys.exit(1 if report.has_errors else 0)


if __name__ == "__main__":
    main()
