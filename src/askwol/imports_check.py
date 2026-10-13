"""Check that declared owl:imports targets actually resolve.

Whether you *should* import a given vocabulary is a modelling judgement
call this tool does not second-guess. What is objectively checkable is
whether the imports you already declared are live: each declared IRI is
fetched over HTTP and parsed as RDF, exactly like the namespace check.
"""

from __future__ import annotations

from rdflib import OWL, Graph, URIRef

from askwol.cache import OntologyCache
from askwol.models import ImportsCheck, ImportsReport, NamespaceCheck, Status
from askwol.resolver import DEFAULT_TIMEOUT, resolve_all_namespaces


def declared_imports(graph: Graph) -> list[str]:
    """Distinct owl:imports target IRIs, in the order they appear."""
    declared: list[str] = []
    seen: set[str] = set()
    for o in graph.objects(None, OWL.imports):
        if isinstance(o, URIRef):
            val = str(o).strip()
            if val and val not in seen:
                seen.add(val)
                declared.append(val)
    return declared


def skipped_imports(graph: Graph) -> ImportsReport:
    """The imports report for an offline run: every declared import, unresolved."""
    checks = [
        ImportsCheck(
            iri=iri,
            resolution=NamespaceCheck(prefix=iri, uri=iri, status=Status.SKIP, error="Resolution skipped"),
        )
        for iri in declared_imports(graph)
    ]
    return ImportsReport(status=Status.SKIP if checks else Status.OK, checks=checks)


async def check_imports(
    graph: Graph,
    cache: OntologyCache,
    timeout: float = DEFAULT_TIMEOUT,
) -> ImportsReport:
    """Resolve every declared owl:imports target and report broken ones."""
    declared = declared_imports(graph)

    if not declared:
        return ImportsReport(status=Status.OK, checks=[])

    resolutions = await resolve_all_namespaces(
        {iri: iri for iri in declared}, cache, timeout=timeout,
    )
    checks = [ImportsCheck(iri=r.uri, resolution=r) for r in resolutions]
    status = Status.FAIL if any(c.resolution.status == Status.FAIL for c in checks) else Status.OK
    return ImportsReport(status=status, checks=checks)
