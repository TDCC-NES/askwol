"""Check that each host is referenced with a single URI scheme (http vs https).

`http://example.org/X` and `https://example.org/X` are different IRIs as far
as RDF is concerned. Within a single ontology, every host should appear under
exactly one scheme.

This check groups every IRI in the graph (plus bound namespaces) by host and
flags any host that is referenced under both `http://` and `https://`.
"""

from __future__ import annotations

import re
from collections import defaultdict

from rdflib import Graph, URIRef

from askwol.models import IRISchemeConflict, IRISchemeHost, IRISchemeReport, Status

_HOST_RE = re.compile(r"^([^/#?]+)")


def _split(uri: str) -> tuple[str, str] | None:
    """Return (scheme, host) for an http(s) URI, else None."""
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
    return scheme, m.group(1).lower()


def check_iri_scheme(graph: Graph, namespaces: dict[str, str]) -> IRISchemeReport:
    # host -> scheme -> set of example IRIs (cap collection per scheme to keep memory bounded)
    by_host: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    # host -> scheme -> total count
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add(uri: str) -> None:
        sp = _split(uri)
        if sp is None:
            return
        scheme, host = sp
        counts[host][scheme] += 1
        bucket = by_host[host][scheme]
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

    if not by_host:
        return IRISchemeReport(status=Status.SKIP, message="no http(s) IRIs found in the ontology")

    conflicts: list[IRISchemeConflict] = []
    for host in sorted(by_host):
        schemes = by_host[host]
        if "http" in schemes and "https" in schemes:
            conflicts.append(IRISchemeConflict(
                host=host,
                http_count=counts[host]["http"],
                https_count=counts[host]["https"],
                http_examples=sorted(schemes["http"])[:5],
                https_examples=sorted(schemes["https"])[:5],
            ))

    # Single-scheme hosts, listed so the report can show what was checked,
    # not just a count.
    hosts: list[IRISchemeHost] = []
    for host in sorted(by_host):
        schemes = by_host[host]
        if "http" in schemes and "https" in schemes:
            continue
        scheme = "http" if "http" in schemes else "https"
        hosts.append(IRISchemeHost(
            host=host,
            scheme=scheme,
            count=counts[host][scheme],
            examples=sorted(schemes[scheme])[:5],
        ))

    # Headline scheme breakdown for the OK case
    http_hosts = sum(1 for h, sc in by_host.items() if "http" in sc and "https" not in sc)
    https_hosts = sum(1 for h, sc in by_host.items() if "https" in sc and "http" not in sc)

    if conflicts:
        return IRISchemeReport(
            status=Status.WARN,
            total_hosts=len(by_host),
            http_only_hosts=http_hosts,
            https_only_hosts=https_hosts,
            hosts=hosts,
            conflicts=conflicts,
            message=f"{len(conflicts)} host(s) referenced under both http:// and https://",
        )

    return IRISchemeReport(
        status=Status.OK,
        total_hosts=len(by_host),
        http_only_hosts=http_hosts,
        https_only_hosts=https_hosts,
        hosts=hosts,
        conflicts=[],
        message=f"{len(by_host)} host(s), each referenced under a single scheme",
    )
