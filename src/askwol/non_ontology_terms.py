"""Flag terms in the ontology's own namespace that are not OWL schema.

An OWL ontology should define *schema*: classes, properties, and datatypes.
Individuals, SKOS concepts, and other instance data belong in a separate data
resource or concept scheme, not mixed into the ontology itself.

This check uses a *whitelist* of schema constructs. A term defined in the
ontology's own namespace is fine when it carries at least one schema type
(class, property, datatype, or the ontology header). A term that carries a type
but no schema type (a SKOS concept, a named individual, other instance data) is
flagged.
"""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from askwol.models import NonOntologyTermIssue, NonOntologyTermsReport, Status

# rdf:type values that mark a term as legitimate OWL/RDFS schema.
SCHEMA_TYPES: frozenset[URIRef] = frozenset({
    OWL.Class,
    RDFS.Class,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    RDF.Property,
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
    RDFS.Datatype,
    OWL.Ontology,
})

EXTERNAL_NAMESPACES = (
    "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2001/XMLSchema#",
    "http://www.w3.org/XML/1998/namespace",
    "http://www.w3.org/2004/02/skos/core#",
    "http://www.w3.org/ns/prov#",
    "http://purl.org/dc/terms/",
    "http://purl.org/dc/elements/1.1/",
    "http://xmlns.com/foaf/0.1/",
    "https://schema.org/",
    "http://schema.org/",
    "http://www.w3.org/ns/shacl#",
    "http://www.w3.org/2006/time#",
    "http://www.w3.org/ns/dcat#",
    "http://www.opengis.net/ont/geosparql#",
)


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


def _is_external(uri: str) -> bool:
    return any(uri.startswith(ns) for ns in EXTERNAL_NAMESPACES)


def _type_label(types: set[URIRef]) -> str:
    if SKOS.Concept in types:
        return "SKOS concept"
    domain_types = sorted(str(t) for t in types if t != OWL.NamedIndividual)
    if domain_types:
        return f"instance of {_local_name(domain_types[0])}"
    return "named individual"


def check_non_ontology_terms(graph: Graph) -> NonOntologyTermsReport:
    """Flag own-namespace terms that are not part of the OWL schema."""
    ontology_iris = {
        str(subject)
        for subject in graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    }
    ontology_namespaces = {_namespace_of(iri) for iri in ontology_iris}

    if not ontology_namespaces:
        return NonOntologyTermsReport(
            status=Status.SKIP,
            message="no owl:Ontology declaration found",
        )

    def _in_own_namespace(uri: str) -> bool:
        return any(uri.startswith(ns) for ns in ontology_namespaces)

    flagged: list[NonOntologyTermIssue] = []
    for subject in set(graph.subjects()):
        if not isinstance(subject, URIRef):
            continue
        uri = str(subject)
        # Only the ontology's own namespace is considered. The own namespace
        # wins even when it is a well-known vocabulary (e.g. validating FOAF).
        if uri in ontology_iris or not _in_own_namespace(uri):
            continue
        types = set(graph.objects(subject, RDF.type))
        if not types:
            # Untyped terms are covered by the internal-terms check.
            continue
        if any(t in SCHEMA_TYPES for t in types):
            # Carries at least one schema type: a legitimate ontology term.
            continue
        flagged.append(
            NonOntologyTermIssue(
                term=uri,
                display_name=_local_name(uri),
                type_label=_type_label(types),
            )
        )

    flagged.sort(key=lambda issue: issue.term)

    return NonOntologyTermsReport(
        total_flagged=len(flagged),
        terms=flagged,
        status=Status.OK if not flagged else Status.WARN,
    )
