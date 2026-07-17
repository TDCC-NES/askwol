"""CLI entry point for the ontology checker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console

from askwol.cache import OntologyCache
from askwol.definition_docs import check_definition_documentation
from askwol.imports_check import check_imports
from askwol.internal_terms import check_internal_terms
from askwol.lang_tags import check_lang_tags
from askwol.metadata_validator import validate_ontology_metadata
from askwol.reasoner_checks import run_reasoner_checks
from askwol.models import NamespaceCheck, NamespaceReport, Status, UnusedPrefix, ValidationReport
from askwol.parser import parse_ontology
from askwol.report import print_report, report_as_json, report_as_markdown
from askwol.resolver import resolve_all_namespaces
from askwol.term_inventory import check_datatypes, check_domains_ranges, check_term_inventory
from askwol.term_validator import validate_terms


async def _run_check(
    file: Path,
    timeout: float,
    skip_resolution: bool,
) -> ValidationReport:
    report = ValidationReport(file=str(file))
    cache = OntologyCache()

    # 1. Parse
    try:
        parsed = parse_ontology(file)
    except Exception as exc:
        report.parse_errors.append(str(exc))
        return report

    if skip_resolution:
        for prefix, uri in parsed.namespaces.items():
            report.namespaces.append(
                NamespaceReport(
                    prefix=prefix,
                    uri=uri,
                    resolution=_skip_check(prefix, uri),
                )
            )
        return report

    # Detect unused prefixes (declared but never used in any triple)
    used_prefixes = set(parsed.namespaces.keys())
    for pfx, uri in parsed.declared_prefixes.items():
        if pfx not in used_prefixes:
            report.unused_prefixes.append(UnusedPrefix(prefix=pfx, uri=uri))

    # Language tag consistency
    report.lang_tags = check_lang_tags(parsed.graph, parsed.namespaces)

    # Ontology-level metadata
    report.ontology_metadata = validate_ontology_metadata(parsed.graph)

    # Label and comment documentation
    report.definition_docs = check_definition_documentation(parsed.graph)

    # Internal terms referenced in the ontology's own namespace must be defined
    report.internal_terms = check_internal_terms(parsed.graph)

    # Categorize the ontology's own terms and check naming conventions
    report.term_inventory = check_term_inventory(parsed.graph)

    # Domains and ranges of object and datatype properties
    report.domains_ranges = check_domains_ranges(parsed.graph)

    # Datatypes used across the ontology
    report.datatypes = check_datatypes(parsed.graph)

    # Reasoner checks (current ontology only; imports are not followed)
    report.reasoner = run_reasoner_checks(parsed.graph)

    # Declared owl:imports targets must actually resolve
    report.imports = await check_imports(parsed.graph, cache, timeout=timeout)

    # Only resolve and report namespaces that have subject-position terms
    active_ns = {pfx: uri for pfx, uri in parsed.namespaces.items()
                 if parsed.terms_by_namespace.get(pfx)}

    # 2. Resolve namespaces
    ns_checks = await resolve_all_namespaces(active_ns, cache, timeout=timeout)
    ns_check_map = {c.uri: c for c in ns_checks}

    # 3. Validate terms per namespace
    for prefix, uri in active_ns.items():
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())

        term_checks = validate_terms(prefix, uri, local_names, cache)

        report.namespaces.append(
            NamespaceReport(
                prefix=prefix,
                uri=uri,
                resolution=ns_check,
                terms=term_checks,
            )
        )

    return report


def _skip_check(prefix: str, uri: str):
    return NamespaceCheck(prefix=prefix, uri=uri, status=Status.SKIP, error="Resolution skipped")


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

    report = asyncio.run(_run_check(file, timeout, skip_resolution))

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
