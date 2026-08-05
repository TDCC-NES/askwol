"""CLI entry point for the ontology checker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console

from askwol.pipeline import run_full_validation
from askwol.report import print_report, report_as_json, report_as_markdown


@click.group()
def main() -> None:
    """OWL Ontology Checker  -  validate namespace resolution and term existence."""


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    help="Output format.",
)
@click.option(
    "-o", "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Write report to file instead of stdout.",
)
@click.option("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
@click.option(
    "--skip-resolution",
    is_flag=True,
    default=False,
    help="Skip HTTP resolution (offline mode).",
)
def check(file: Path, output_format: str, output: Path | None, timeout: float, skip_resolution: bool) -> None:
    """Check an ontology file for namespace resolution and term validity."""
    console = Console(stderr=True)
    console.print(f"Checking [bold]{file}[/bold] …")

    report, _mermaid = asyncio.run(
        run_full_validation(
            file, include_mermaid=False, skip_resolution=skip_resolution, timeout=timeout,
        )
    )

    if output_format == "json":
        result = report_as_json(report)
    elif output_format == "markdown":
        result = report_as_markdown(report)
    else:
        result = None

    if result is not None:
        if output:
            output.write_text(result, encoding="utf-8")
            console.print(f"Report written to [bold]{output}[/bold]")
        else:
            click.echo(result)
    else:
        print_report(report)

    sys.exit(1 if report.has_issues else 0)


if __name__ == "__main__":
    main()
