"""Check that the ontology does not define SKOS concepts in its own namespace."""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, SKOS

from askwol.models import SkosConceptIssue, SkosConceptsReport, Status


def _namespace_of(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[0] + "#"
    if "/" in uri:
        return uri.rsplit("/", 1)[0] + "/"
    return uri


def _local_name(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[1]
    if "/" in uri:
        return uri.rstrip("/").rsplit("/", 1)[1]
    return uri


def check_skos_concepts(graph: Graph) -> SkosConceptsReport:
    """Flag ``skos:Concept`` instances defined in the ontology's own namespace.

    An OWL ontology is the schema: it defines classes and properties. Individual
    subject-matter concepts belong in a separate SKOS concept scheme, not mixed
    into the ontology. Only concepts in the ontology's own namespace are flagged;
    concepts referenced from an external scheme (as objects) are fine.
    """
    ontology_iris = {
        str(subject)
        for subject in graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    }
    ontology_namespaces = {_namespace_of(iri) for iri in ontology_iris}

    if not ontology_namespaces:
        return SkosConceptsReport(
            status=Status.SKIP,
            message="no owl:Ontology declaration found",
        )

    def _in_own_namespace(uri: str) -> bool:
        return any(uri.startswith(ns) for ns in ontology_namespaces)

    concepts = {
        str(subject)
        for subject in graph.subjects(RDF.type, SKOS.Concept)
        if isinstance(subject, URIRef)
    }
    internal_uris = sorted(uri for uri in concepts if _in_own_namespace(uri))
    internal = [
        SkosConceptIssue(term=uri, display_name=_local_name(uri))
        for uri in internal_uris
    ]

    return SkosConceptsReport(
        total_concepts=len(concepts),
        internal_concepts=internal,
        status=Status.OK if not internal else Status.WARN,
    )
