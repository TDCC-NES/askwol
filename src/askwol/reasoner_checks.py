"""Lightweight OWL reasoner checks for the current ontology graph only."""

from __future__ import annotations

from itertools import combinations

from rdflib import Graph, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS
from owlrl import DeductiveClosure, OWLRL_Semantics

from askwol.models import ReasonerCheck, ReasonerReport, Status

CLASS_TYPES = {OWL.Class, RDFS.Class}
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


def _is_internal(uri: str, ontology_namespaces: set[str]) -> bool:
    if ontology_namespaces:
        # Own namespace wins even when it is a well-known vocabulary.
        return any(uri.startswith(ns) for ns in ontology_namespaces)
    return not any(uri.startswith(ns) for ns in EXTERNAL_NAMESPACES)


def _ontology_namespaces(graph: Graph) -> set[str]:
    return {
        _namespace_of(str(subject))
        for subject in graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    }


def _disjoint_pairs(graph: Graph) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()

    for left, right in graph.subject_objects(OWL.disjointWith):
        if isinstance(left, URIRef) and isinstance(right, URIRef):
            pairs.add((str(left), str(right)))
            pairs.add((str(right), str(left)))

    for node in graph.subjects(RDF.type, OWL.AllDisjointClasses):
        members = graph.value(node, OWL.members)
        if members is None:
            continue
        uris = [item for item in Collection(graph, members) if isinstance(item, URIRef)]
        for left, right in combinations(uris, 2):
            pairs.add((str(left), str(right)))
            pairs.add((str(right), str(left)))

    return pairs


def run_reasoner_checks(graph: Graph) -> ReasonerReport:
    """Run lightweight consistency checks on the current ontology graph only.

    This intentionally does not follow owl:imports. It reasons only over the
    triples present in the uploaded ontology.
    """
    closure = Graph()
    for triple in graph:
        closure.add(triple)
    DeductiveClosure(OWLRL_Semantics).expand(closure)

    ontology_namespaces = _ontology_namespaces(closure)
    disjoint = _disjoint_pairs(closure)

    schema_nodes = {
        subject
        for subject, rdf_type in closure.subject_objects(RDF.type)
        if isinstance(subject, URIRef) and (rdf_type in CLASS_TYPES or rdf_type in PROPERTY_TYPES or rdf_type == OWL.Ontology)
    }

    inconsistent_individuals: list[str] = []
    seen_individuals = sorted(
        {
            subject
            for subject, rdf_type in closure.subject_objects(RDF.type)
            if isinstance(subject, URIRef) and subject not in schema_nodes and _is_internal(str(subject), ontology_namespaces)
        },
        key=str,
    )
    for individual in seen_individuals:
        types = {str(obj) for obj in closure.objects(individual, RDF.type) if isinstance(obj, URIRef)}
        for left, right in combinations(sorted(types), 2):
            if (left, right) in disjoint:
                inconsistent_individuals.append(str(individual))
                break

    unsatisfiable_classes: list[str] = []
    named_classes = sorted(
        {
            subject
            for subject, rdf_type in closure.subject_objects(RDF.type)
            if isinstance(subject, URIRef) and rdf_type in CLASS_TYPES and _is_internal(str(subject), ontology_namespaces)
        },
        key=str,
    )
    for cls in named_classes:
        superclasses = {str(cls)}
        superclasses.update(str(obj) for obj in closure.objects(cls, RDFS.subClassOf) if isinstance(obj, URIRef))
        if str(OWL.Nothing) in superclasses:
            unsatisfiable_classes.append(str(cls))
            continue
        contradiction_found = False
        for left, right in combinations(sorted(superclasses), 2):
            if (left, right) in disjoint:
                contradiction_found = True
                break
        if contradiction_found:
            unsatisfiable_classes.append(str(cls))

    # "Reasoning scope" is metadata about how the check is run (already shown
    # in the section subtitle), not a check result. Don't list it as a check.
    checks: list[ReasonerCheck] = []

    if inconsistent_individuals:
        checks.append(
            ReasonerCheck(
                key="ontology_consistency",
                label="Ontology consistency",
                status=Status.FAIL,
                message=f"Found inconsistent named individual(s): {', '.join(inconsistent_individuals)}.",
            )
        )
        for individual in inconsistent_individuals:
            checks.append(
                ReasonerCheck(
                    key=f"inconsistent_individual:{individual}",
                    label="Inconsistent individual",
                    status=Status.FAIL,
                    message=f"{individual} is typed in a contradictory way in the current ontology.",
                )
            )
    else:
        checks.append(
            ReasonerCheck(
                key="ontology_consistency",
                label="Ontology consistency",
                status=Status.OK,
                message="No logical contradictions found among named individuals in the current ontology.",
            )
        )

    if unsatisfiable_classes:
        for cls in unsatisfiable_classes:
            checks.append(
                ReasonerCheck(
                    key=f"unsatisfiable_class:{cls}",
                    label="Unsatisfiable class",
                    status=Status.WARN,
                    message=f"{cls} cannot consistently have instances in the current ontology.",
                )
            )
    else:
        checks.append(
            ReasonerCheck(
                key="unsatisfiable_classes",
                label="Unsatisfiable classes",
                status=Status.OK,
                message="No unsatisfiable named classes detected in the current ontology.",
            )
        )

    return ReasonerReport(
        scoped_to_current_ontology=True,
        imports_followed=False,
        consistent=not inconsistent_individuals,
        inconsistent_individuals=inconsistent_individuals,
        unsatisfiable_classes=unsatisfiable_classes,
        checks=checks,
    )
