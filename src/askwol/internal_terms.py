"""Check that terms in the ontology's own namespace are actually defined."""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from askwol.models import InternalTermIssue, InternalTermsReport, Status

# rdf:type values that mark a subject as a term the ontology defines itself.
# The namespaces of such subjects make up the ontology's "own namespace(s)".
_DEFINITIONAL_TYPES = {
    RDFS.Class,
    OWL.Class,
    RDF.Property,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
    RDFS.Datatype,
    OWL.NamedIndividual,
}


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


def check_internal_terms(graph: Graph) -> InternalTermsReport:
    """Flag terms in the ontology's own namespace that are used but never defined.

    A term is *defined* when it appears as the subject of at least one triple.
    It is *referenced* when it appears as a predicate or object. A term that is
    referenced from the ontology's own namespace but never defined is usually a
    typo or a forgotten declaration.
    """
    ontology_iris = {
        str(subject)
        for subject in graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    }

    if not ontology_iris:
        return InternalTermsReport(
            status=Status.SKIP,
            message="no owl:Ontology declaration found",
        )

    # The ontology's own namespace(s) are inferred from where it actually
    # declares terms (subjects carrying a definitional rdf:type), not from the
    # ontology IRI's parent path. A slash ontology IRI like
    # https://host/dataset would otherwise claim the entire host as its
    # namespace and flag unrelated IRIs such as owl:versionIRI documents.
    ontology_namespaces = {
        _namespace_of(str(subject))
        for subject, _, type_ in graph.triples((None, RDF.type, None))
        if isinstance(subject, URIRef)
        and type_ in _DEFINITIONAL_TYPES
        and str(subject) not in ontology_iris
    }

    if not ontology_namespaces:
        return InternalTermsReport(
            status=Status.SKIP,
            message="no terms are defined in the ontology's own namespace",
        )

    def _in_own_namespace(uri: str) -> bool:
        return any(uri.startswith(ns) for ns in ontology_namespaces)

    defined: set[str] = {
        str(subject)
        for subject in graph.subjects()
        if isinstance(subject, URIRef) and _in_own_namespace(str(subject))
    }

    # owl:versionIRI targets identify the ontology document, not a term that
    # needs its own definition, so they are excluded from the reference scan.
    version_iris = {
        str(obj)
        for obj in graph.objects(predicate=OWL.versionIRI)
        if isinstance(obj, URIRef)
    }

    referenced: set[str] = set()
    for _, predicate, obj in graph:
        for term in (predicate, obj):
            if isinstance(term, URIRef):
                uri = str(term)
                # The ontology IRI itself is not a defined term.
                if uri in ontology_iris:
                    continue
                if uri in version_iris:
                    continue
                if _in_own_namespace(uri):
                    referenced.add(uri)

    undefined_uris = sorted(uri for uri in referenced if uri not in defined)
    undefined = [
        InternalTermIssue(term=uri, display_name=_local_name(uri))
        for uri in undefined_uris
    ]

    return InternalTermsReport(
        total_referenced=len(referenced),
        defined=len(referenced) - len(undefined),
        undefined=undefined,
        status=Status.OK if not undefined else Status.FAIL,
    )
