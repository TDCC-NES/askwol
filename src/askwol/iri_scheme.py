"""Check that each namespace is referenced with a single URI scheme (http vs https).

`http://example.org/X` and `https://example.org/X` are different IRIs as far
as RDF is concerned. Within a single ontology, every namespace (the base IRI
up to and including the last `/` or `#`) should appear under exactly one
scheme.

This check groups every IRI in the graph (plus bound namespaces) by scheme-
independent namespace - host plus path, not just the host - and flags any
namespace that is referenced under both `http://` and `https://`. Two
unrelated vocabularies that merely share a host (e.g. `purl.org/dc/terms/`
and `purl.org/ontology/bibo/`) are never compared to each other; only the
same namespace path under both schemes counts as a conflict.
"""

from __future__ import annotations

import re
from collections import defaultdict

from rdflib import Graph, URIRef

from askwol.models import IRISchemeConflict, IRISchemeHost, IRISchemeReport, Status

_HOST_RE = re.compile(r"^([^/#?]+)")


def _split(uri: str) -> tuple[str, str] | None:
    """Return (scheme, namespace) for an http(s) URI, else None.

    `namespace` is the host (lowercased, since DNS names are
    case-insensitive) plus everything up to and including the last `/` or
    `#` in the path (case-sensitive, since URI paths are) - i.e. the same
    base IRI `iri_utils.namespace_of` would compute, with the scheme
    stripped so http:// and https:// variants of the SAME namespace compare
    equal.
    """
    if uri.startswith("http://"):
        rest = uri[len("http://"):]
        scheme = "http"
    elif uri.startswith("https://"):
        rest = uri[len("https://"):]
        scheme = "https"
    else:
        return None
    m = _HOST_RE.match(rest)
    if not m:
        return None
    host = m.group(1).lower()
    path = rest[len(m.group(1)):]
    if "#" in path:
        path = path.rsplit("#", 1)[0] + "#"
    elif "/" in path:
        path = path.rsplit("/", 1)[0] + "/"
    else:
        path = ""
    return scheme, host + path


def check_iri_scheme(graph: Graph, namespaces: dict[str, str]) -> IRISchemeReport:
    # namespace -> scheme -> set of example IRIs (cap collection per scheme to keep memory bounded)
    by_namespace: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    # namespace -> scheme -> total count
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add(uri: str) -> None:
        sp = _split(uri)
        if sp is None:
            return
        scheme, namespace = sp
        counts[namespace][scheme] += 1
        bucket = by_namespace[namespace][scheme]
        if len(bucket) < 5:
            bucket.add(uri)

    seen: set[str] = set()
    for s, p, o in graph:
        for node in (s, p, o):
            if isinstance(node, URIRef):
                u = str(node)
                if u in seen:
                    continue
                seen.add(u)
                add(u)

    for ns_uri in namespaces.values():
        add(ns_uri)

    if not by_namespace:
        return IRISchemeReport(status=Status.SKIP, message="no http(s) IRIs found in the ontology")

    conflicts: list[IRISchemeConflict] = []
    for namespace in sorted(by_namespace):
        schemes = by_namespace[namespace]
        if "http" in schemes and "https" in schemes:
            conflicts.append(IRISchemeConflict(
                host=namespace,
                http_count=counts[namespace]["http"],
                https_count=counts[namespace]["https"],
                http_examples=sorted(schemes["http"])[:5],
                https_examples=sorted(schemes["https"])[:5],
            ))

    # Single-scheme namespaces, listed so the report can show what was
    # checked, not just a count.
    hosts: list[IRISchemeHost] = []
    for namespace in sorted(by_namespace):
        schemes = by_namespace[namespace]
        if "http" in schemes and "https" in schemes:
            continue
        scheme = "http" if "http" in schemes else "https"
        hosts.append(IRISchemeHost(
            host=namespace,
            scheme=scheme,
            count=counts[namespace][scheme],
            examples=sorted(schemes[scheme])[:5],
        ))

    # Headline scheme breakdown for the OK case
    http_hosts = sum(1 for ns, sc in by_namespace.items() if "http" in sc and "https" not in sc)
    https_hosts = sum(1 for ns, sc in by_namespace.items() if "https" in sc and "http" not in sc)

    if conflicts:
        return IRISchemeReport(
            status=Status.WARN,
            total_hosts=len(by_namespace),
            http_only_hosts=http_hosts,
            https_only_hosts=https_hosts,
            hosts=hosts,
            conflicts=conflicts,
            message=f"{len(conflicts)} namespace(s) referenced under both http:// and https://",
        )

    return IRISchemeReport(
        status=Status.OK,
        total_hosts=len(by_namespace),
        http_only_hosts=http_hosts,
        https_only_hosts=https_hosts,
        hosts=hosts,
        conflicts=[],
        message=f"{len(by_namespace)} namespace(s), each referenced under a single scheme",
    )

