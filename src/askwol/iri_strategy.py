"""Detect the IRI strategy (hash vs slash) used by an ontology's own terms.

For every term defined inside the ontology's own namespace, determine
whether it follows the hash pattern (`http://example.org/ont#Term`) or
the slash pattern (`http://example.org/ont/Term`). Consistency is judged
per declared owl:Ontology base IRI: a file that bundles more than one base
IRI (e.g. the W3C PROV family's prov/prov-o) may use a different, but
internally consistent, style per base IRI without being flagged. Mixing
hash and slash within ONE base IRI's own terms is what triggers a warning.
"""

from __future__ import annotations

from rdflib import OWL, RDF, RDFS, Graph, URIRef

from askwol.iri_utils import ontology_stems
from askwol.models import IRINamespaceStrategy, IRIStrategyReport, Status

# RDF types that mark a node as something *defined* by the ontology.
_DEFINING_TYPES = (
    OWL.Class,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    OWL.NamedIndividual,
    RDFS.Class,
    RDF.Property,
)


def _classify_stem(stem: str, defined: set[str]) -> IRINamespaceStrategy | None:
    """Classify the subset of `defined` terms under one ontology stem's own
    hash ("stem#") or slash ("stem/") namespace. Returns None when the stem
    defines no terms of its own."""
    hash_ns, slash_ns = stem + "#", stem + "/"
    hash_terms = sorted(u for u in defined if u.startswith(hash_ns) and len(u) > len(hash_ns))
    slash_terms = sorted(u for u in defined if u.startswith(slash_ns) and len(u) > len(slash_ns))
    if not hash_terms and not slash_terms:
        return None
    strategy = "mixed" if hash_terms and slash_terms else ("hash" if hash_terms else "slash")
    return IRINamespaceStrategy(
        namespace=stem,
        strategy=strategy,
        hash_count=len(hash_terms),
        slash_count=len(slash_terms),
        hash_examples=hash_terms[:5],
        slash_examples=slash_terms[:5],
    )


def check_iri_strategy(graph: Graph) -> IRIStrategyReport:
    stems = ontology_stems(graph)
    if not stems:
        return IRIStrategyReport(status=Status.SKIP, message="no owl:Ontology declaration found")

    ontology_iri = sorted(stems)[0]

    # Collect every URI that is declared as a class/property/individual.
    defined: set[str] = set()
    for t in _DEFINING_TYPES:
        for s in graph.subjects(RDF.type, t):
            if isinstance(s, URIRef):
                defined.add(str(s))

    # A file can declare more than one owl:Ontology subject (e.g. the W3C PROV
    # family bundles prov, prov-o, prov-dc, ... into one document). Classify
    # each stem's OWN terms separately so one base IRI's style never
    # contaminates another's verdict.
    namespaces: list[IRINamespaceStrategy] = []
    for stem in sorted(stems):
        classified = _classify_stem(stem, defined)
        if classified is not None:
            namespaces.append(classified)

    if not namespaces:
        return IRIStrategyReport(
            ontology_iri=ontology_iri,
            status=Status.SKIP,
            message="no internally defined terms found in the ontology's own namespace",
        )

    mixed = [ns for ns in namespaces if ns.strategy == "mixed"]
    if mixed:
        hash_n = sum(ns.hash_count for ns in mixed)
        slash_n = sum(ns.slash_count for ns in mixed)
        offenders = ", ".join(f"<code>{ns.namespace}</code>" for ns in mixed)
        message = (
            f"{hash_n} hash-style and {slash_n} slash-style terms are mixed within "
            f"{offenders}; pick one style per base IRI and stick to it"
        )
        return IRIStrategyReport(
            ontology_iri=ontology_iri, namespaces=namespaces, status=Status.WARN, message=message,
        )

    styles = {ns.strategy for ns in namespaces}
    total = sum(ns.hash_count + ns.slash_count for ns in namespaces)
    if len(namespaces) == 1:
        strategy = namespaces[0].strategy
        pattern = "#Term" if strategy == "hash" else "/Term"
        message = f"all {total} defined terms use the {strategy} pattern (<code>{pattern}</code>)"
    elif len(styles) == 1:
        strategy = styles.pop()
        pattern = "#Term" if strategy == "hash" else "/Term"
        message = (
            f"all {total} defined terms across {len(namespaces)} declared base IRIs "
            f"use the {strategy} pattern (<code>{pattern}</code>)"
        )
    else:
        message = (
            f"{len(namespaces)} declared base IRIs are each internally consistent "
            f"({total} defined terms overall) but differ from each other; see the breakdown"
        )

    return IRIStrategyReport(
        ontology_iri=ontology_iri, namespaces=namespaces, status=Status.OK, message=message,
    )

