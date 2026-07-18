"""Lightweight OWL reasoner checks for the current ontology graph only."""

from __future__ import annotations

from itertools import combinations

from rdflib import Graph, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS
from owlrl import DeductiveClosure, OWLRL_Semantics

from askwol.iri_utils import EXTERNAL_NAMESPACES, ontology_namespaces as _ontology_namespaces
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


def _is_internal(uri: str, ontology_namespaces: set[str]) -> bool:
    if ontology_namespaces:
        # Own namespace wins even when it is a well-known vocabulary.
        return any(uri.startswith(ns) for ns in ontology_namespaces)
    return not any(uri.startswith(ns) for ns in EXTERNAL_NAMESPACES)


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

    # Facet 1: overall rollup verdict (the more severe of the two facets below).
    if inconsistent_individuals:
        overall_status = Status.FAIL
        overall_message = (
            "The current ontology has inconsistent named individual(s) - see "
            "'Inconsistent individuals' below."
        )
    elif unsatisfiable_classes:
        overall_status = Status.WARN
        overall_message = (
            "The current ontology has unsatisfiable named class(es) - see "
            "'Unsatisfiable classes' below."
        )
    else:
        overall_status = Status.OK
        overall_message = (
            "No logical contradictions or unsatisfiable classes found in the "
            "current ontology."
        )
    checks.append(
        ReasonerCheck(
            key="ontology_consistency",
            label="Ontology consistency",
            status=overall_status,
            message=overall_message,
        )
    )

    # Facet 2: inconsistent individuals, always its own row.
    if inconsistent_individuals:
        checks.append(
            ReasonerCheck(
                key="inconsistent_individuals",
                label="Inconsistent individuals",
                status=Status.FAIL,
                message=f"Found {len(inconsistent_individuals)} inconsistent named individual(s): {', '.join(inconsistent_individuals)}.",
            )
        )
    else:
        checks.append(
            ReasonerCheck(
                key="inconsistent_individuals",
                label="Inconsistent individuals",
                status=Status.OK,
                message="No logical contradictions found among named individuals in the current ontology.",
            )
        )

    # Facet 3: unsatisfiable classes, always its own row (with a summary row
    # even when unsatisfiable classes are found, for symmetry with facet 2).
    if unsatisfiable_classes:
        checks.append(
            ReasonerCheck(
                key="unsatisfiable_classes",
                label="Unsatisfiable classes",
                status=Status.WARN,
                message=f"Found {len(unsatisfiable_classes)} unsatisfiable named class(es): {', '.join(unsatisfiable_classes)}.",
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
