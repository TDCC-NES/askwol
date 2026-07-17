"""Check that internal class and property definitions have labels and comments.

Label and comment presence (including the owl:inverseOf comment exemption) is
checked by running the ontology through pyshacl against
shapes/definition_documentation.ttl; this module gathers the candidate terms
(for the total/type-per-term summary) and folds the SHACL results in.
"""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from askwol.deprecation import deprecation_marker
from askwol.models import DefinitionDocumentationCheck, DefinitionDocumentationIssue, DefinitionDocumentationReport, Status
from askwol.shacl_runner import run_shapes

_SHAPES_FILE = "definition_documentation.ttl"

CLASS_TYPES = {
    OWL.Class,
    RDFS.Class,
}

PROPERTY_TYPES = {
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
}

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


def check_definition_documentation(graph: Graph) -> DefinitionDocumentationReport:
    """Check internal class and property definitions for labels and comments."""

    candidates: dict[URIRef, str] = {}
    for subject, rdf_type in graph.subject_objects(RDF.type):
        if not isinstance(subject, URIRef):
            continue
        if rdf_type in CLASS_TYPES:
            candidates[subject] = "Class"
        elif rdf_type in PROPERTY_TYPES:
            candidates[subject] = "Property"

    ontology_namespaces = {
        _namespace_of(str(subject))
        for subject in graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    }

    # Index SHACL violations by focus node and shape name ("Label"/"Comment").
    # A term absent from this map for a given name satisfied that shape.
    violations: dict[str, dict[str, str]] = {}
    for result in run_shapes(graph, _SHAPES_FILE):
        if result.name in ("Label", "Comment"):
            violations.setdefault(result.focus_node, {})[result.name] = result.message

    checks: list[DefinitionDocumentationCheck] = []
    issues: list[DefinitionDocumentationIssue] = []
    total = 0
    documented = 0

    for subject, term_type in sorted(candidates.items(), key=lambda item: str(item[0])):
        uri = str(subject)
        if ontology_namespaces:
            # The ontology's own namespace wins, even when it is a well-known
            # vocabulary (e.g. validating FOAF itself). Only terms outside the
            # own namespace are treated as reused/external.
            if not any(uri.startswith(ns) for ns in ontology_namespaces):
                continue
        elif _is_external(uri):
            # No owl:Ontology declaration: fall back to excluding well-known vocabularies.
            continue

        total += 1
        marker = deprecation_marker(graph, subject)
        if marker:
            documented += 1
            checks.append(
                DefinitionDocumentationCheck(
                    term=uri,
                    display_name=_local_name(uri),
                    term_type=term_type,
                    has_label=True,
                    has_comment=True,
                    status=Status.OK,
                    message="Deprecated; documentation not checked.",
                    deprecated=marker,
                )
            )
            continue

        node_violations = violations.get(uri, {})
        has_label = "Label" not in node_violations
        has_comment = "Comment" not in node_violations
        missing: list[str] = []
        if not has_label:
            missing.append("label")
        if not has_comment:
            missing.append("comment")

        if missing:
            message = f"Missing rdfs:{' and rdfs:'.join(missing)}."
            issues.append(
                DefinitionDocumentationIssue(
                    term=uri,
                    display_name=_local_name(uri),
                    term_type=term_type,
                    missing=missing,
                    message=message,
                )
            )
            checks.append(
                DefinitionDocumentationCheck(
                    term=uri,
                    display_name=_local_name(uri),
                    term_type=term_type,
                    has_label=has_label,
                    has_comment=has_comment,
                    status=Status.FAIL,
                    message=message,
                )
            )
        else:
            documented += 1
            checks.append(
                DefinitionDocumentationCheck(
                    term=uri,
                    display_name=_local_name(uri),
                    term_type=term_type,
                    has_label=True,
                    has_comment=True,
                    status=Status.OK,
                    message="Complete.",
                )
            )

    return DefinitionDocumentationReport(
        total_definitions=total,
        documented_definitions=documented,
        checks=checks,
        issues=issues,
    )
