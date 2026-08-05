"""Shared ontology validation pipeline.

The single place that parses a file and runs every check. Used by the
isolated worker process (``validate_worker.py``, spawned per request by the
web app) and directly by the CLI, so ``/validate``, ``/api/validate``, and
``askwol check`` can never drift into separate copies of the same logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from askwol.cache import OntologyCache
from askwol.definition_docs import check_definition_documentation
from askwol.imports_check import check_imports
from askwol.internal_terms import check_internal_terms
from askwol.iri_scheme import check_iri_scheme
from askwol.iri_strategy import check_iri_strategy
from askwol.iri_utils import ontology_namespaces
from askwol.lang_tags import check_lang_tags
from askwol.license_check import check_license
from askwol.mermaid_diagram import build_mermaid
from askwol.metadata_validator import validate_ontology_metadata
from askwol.models import NamespaceCheck, NamespaceReport, Status, UnusedPrefix, ValidationReport
from askwol.non_ontology_terms import check_non_ontology_terms
from askwol.parser import parse_ontology
from askwol.reasoner_checks import run_reasoner_checks
from askwol.resolver import DEFAULT_TIMEOUT, resolve_all_namespaces
from askwol.term_inventory import check_datatypes, check_domains_ranges, check_term_inventory
from askwol.term_validator import validate_terms

# Generous caps against pathological or oversized ontologies. Checked right
# after parsing, before any expensive check runs, so an oversized file fails
# fast instead of occupying a validation slot for the full job timeout.
MAX_TRIPLES = int(os.environ.get("ASKWOL_MAX_TRIPLES", "500000"))
MAX_NAMESPACES = int(os.environ.get("ASKWOL_MAX_NAMESPACES", "500"))
MAX_IMPORTS = int(os.environ.get("ASKWOL_MAX_IMPORTS", "200"))

PhaseCallback = Callable[[str], None]


class OntologyTooLargeError(Exception):
    """Raised when a parsed ontology exceeds a configured size cap."""


def _noop_phase(_phase: str) -> None:
    pass


def _check_size_limits(parsed) -> None:
    if len(parsed.graph) > MAX_TRIPLES:
        raise OntologyTooLargeError(
            f"This ontology has {len(parsed.graph):,} triples, over the "
            f"{MAX_TRIPLES:,} limit. Try a smaller file."
        )
    if len(parsed.declared_prefixes) > MAX_NAMESPACES:
        raise OntologyTooLargeError(
            f"This ontology declares {len(parsed.declared_prefixes)} namespaces, "
            f"over the {MAX_NAMESPACES} limit."
        )
    if len(parsed.imports) > MAX_IMPORTS:
        raise OntologyTooLargeError(
            f"This ontology declares {len(parsed.imports)} owl:imports, "
            f"over the {MAX_IMPORTS} limit."
        )


def _skip_check(prefix: str, uri: str) -> NamespaceCheck:
    return NamespaceCheck(prefix=prefix, uri=uri, status=Status.SKIP, error="Resolution skipped")


async def run_full_validation(
    source: str | Path,
    *,
    display_name: str | None = None,
    base_uri: str | None = None,
    include_mermaid: bool = True,
    skip_resolution: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    cache: OntologyCache | None = None,
    phase: PhaseCallback = _noop_phase,
) -> tuple[ValidationReport, str]:
    """Parse and fully validate one ontology file.

    Args:
        source: Path to the ontology file to validate.
        display_name: Name shown in the report (e.g. the original URL or
            upload filename). Defaults to ``str(source)``.
        base_uri: The ontology's real published URI, for relative IRIs.
        include_mermaid: Whether to also build the class diagram.
        skip_resolution: Skip namespace/import HTTP resolution (offline mode).
        timeout: Per-HTTP-call timeout for namespace/import resolution.
        cache: Ontology cache to reuse; a fresh one is created if omitted.
        phase: Called with a short phase name as the pipeline progresses,
            so a caller (e.g. the isolated worker) can report progress.

    Returns:
        The validation report and, if requested, a Mermaid diagram source.
    """
    cache = cache if cache is not None else OntologyCache()
    report = ValidationReport(file=display_name or str(source))

    phase("parsing")
    try:
        parsed = parse_ontology(source, base_uri=base_uri)
    except Exception as exc:
        report.parse_errors.append(str(exc))
        return report, ""

    try:
        _check_size_limits(parsed)
    except OntologyTooLargeError as exc:
        report.parse_errors.append(str(exc))
        return report, ""

    mermaid = build_mermaid(parsed.graph, parsed.namespaces) if include_mermaid else ""

    used_prefixes = set(parsed.namespaces.keys())
    for pfx, uri in parsed.declared_prefixes.items():
        if pfx not in used_prefixes:
            report.unused_prefixes.append(UnusedPrefix(prefix=pfx, uri=uri))

    phase("checks")
    report.lang_tags = check_lang_tags(parsed.graph, parsed.namespaces)
    report.ontology_metadata = validate_ontology_metadata(parsed.graph)
    report.license = check_license(parsed.graph)
    report.definition_docs = check_definition_documentation(parsed.graph)
    report.internal_terms = check_internal_terms(parsed.graph)
    report.term_inventory = check_term_inventory(parsed.graph)
    report.domains_ranges = check_domains_ranges(parsed.graph)
    report.datatypes = check_datatypes(parsed.graph)
    report.iri_strategy = check_iri_strategy(parsed.graph)
    report.iri_scheme = check_iri_scheme(parsed.graph, parsed.namespaces)
    report.non_ontology_terms = check_non_ontology_terms(parsed.graph)

    phase("reasoner")
    report.reasoner = run_reasoner_checks(parsed.graph)

    if skip_resolution:
        for prefix, uri in parsed.namespaces.items():
            report.namespaces.append(
                NamespaceReport(prefix=prefix, uri=uri, resolution=_skip_check(prefix, uri))
            )
        phase("done")
        return report, mermaid

    phase("namespaces")
    report.imports = await check_imports(parsed.graph, cache, timeout=timeout)

    # Only resolve and report namespaces that have subject-position terms
    active_ns = {pfx: uri for pfx, uri in parsed.namespaces.items()
                 if parsed.terms_by_namespace.get(pfx)}
    own_ns = ontology_namespaces(parsed.graph)

    ns_checks = await resolve_all_namespaces(active_ns, cache, timeout=timeout)
    ns_check_map = {c.uri: c for c in ns_checks}

    # Skip the ontology's own namespace: its terms are already covered by the
    # internal-terms and term-inventory checks, not "externally reused" terms.
    for prefix, uri in active_ns.items():
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())
        term_checks = [] if uri in own_ns else validate_terms(prefix, uri, local_names, cache)
        report.namespaces.append(
            NamespaceReport(prefix=prefix, uri=uri, resolution=ns_check, terms=term_checks)
        )

    phase("done")
    return report, mermaid
