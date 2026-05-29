"""Detect the IRI strategy (hash vs slash) used by an ontology's own terms.

For every term defined inside the ontology's own namespace, determine
whether it follows the hash pattern (`http://example.org/ont#Term`) or
the slash pattern (`http://example.org/ont/Term`). Mixing both within a
single ontology is flagged as a consistency warning.
"""

from __future__ import annotations

from rdflib import OWL, RDF, RDFS, Graph, URIRef

from askwol.models import IRIStrategyReport, Status

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


def _strip(uri: str) -> str:
    return uri.rstrip("#/")


def check_iri_strategy(graph: Graph) -> IRIStrategyReport:
    ontology_iris = sorted(
        str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)
    )
    if not ontology_iris:
        return IRIStrategyReport(status=Status.SKIP, message="no owl:Ontology declaration found")

    ontology_iri = ontology_iris[0]
    stem = _strip(ontology_iri)

    # Collect every URI that is declared as a class/property/individual.
    defined: set[str] = set()
    for t in _DEFINING_TYPES:
        for s in graph.subjects(RDF.type, t):
            if isinstance(s, URIRef):
                defined.add(str(s))

    hash_terms: list[str] = []
    slash_terms: list[str] = []
    for uri in defined:
        if not (uri.startswith(stem + "#") or uri.startswith(stem + "/")):
            continue
        suffix = uri[len(stem):]
        # suffix starts with '#' or '/'. Only count when there is a non-empty
        # local name after the separator.
        sep, local = suffix[0], suffix[1:]
        if not local:
            continue
        # If the local name itself contains another '/', the term is nested
        # one level deeper - still classify by the separator immediately
        # following the ontology stem.
        if sep == "#":
            hash_terms.append(uri)
        elif sep == "/":
            slash_terms.append(uri)

    total = len(hash_terms) + len(slash_terms)
    if total == 0:
        return IRIStrategyReport(
            ontology_iri=ontology_iri,
            status=Status.SKIP,
            message="no internally defined terms found in the ontology's own namespace",
        )

    hash_terms.sort()
    slash_terms.sort()

    if hash_terms and slash_terms:
        strategy = "mixed"
        status = Status.WARN
        message = (
            f"{len(hash_terms)} hash-style and {len(slash_terms)} slash-style terms "
            "are defined in the same namespace - pick one and stick to it"
        )
    elif hash_terms:
        strategy = "hash"
        status = Status.OK
        message = f"all {len(hash_terms)} defined terms use the hash pattern (<code>#Term</code>)"
    else:
        strategy = "slash"
        status = Status.OK
        message = f"all {len(slash_terms)} defined terms use the slash pattern (<code>/Term</code>)"

    return IRIStrategyReport(
        ontology_iri=ontology_iri,
        strategy=strategy,
        hash_count=len(hash_terms),
        slash_count=len(slash_terms),
        hash_examples=hash_terms[:5],
        slash_examples=slash_terms[:5],
        status=status,
        message=message,
    )
