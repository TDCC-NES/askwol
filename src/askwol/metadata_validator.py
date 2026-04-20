"""Validate ontology-level metadata using SHACL shapes and a normalized summary."""

from __future__ import annotations

from typing import Iterable

from rdflib import Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

from askwol.models import MetadataCheck, MetadataReport, Status


CHECK_SPECS = (
    {
        "key": "ontology_declaration",
        "label": "Ontology declaration",
        "property": "rdf:type owl:Ontology",
        "severity": "required",
        "message": "Declare the ontology itself with rdf:type owl:Ontology.",
    },
    {
        "key": "title",
        "label": "Title",
        "property": "dcterms:title or rdfs:label",
        "severity": "required",
        "predicates": (DCTERMS.title, RDFS.label),
        "message": "Add a title using dcterms:title or rdfs:label.",
    },
    {
        "key": "description",
        "label": "Description",
        "property": "dcterms:description or rdfs:comment",
        "severity": "required",
        "predicates": (DCTERMS.description, RDFS.comment),
        "message": "Add a description using dcterms:description or rdfs:comment.",
    },
    {
        "key": "creator",
        "label": "Creator",
        "property": "dcterms:creator",
        "severity": "required",
        "predicates": (DCTERMS.creator,),
        "message": "Add at least one creator using dcterms:creator.",
    },
    {
        "key": "license",
        "label": "License",
        "property": "dcterms:license",
        "severity": "required",
        "predicates": (DCTERMS.license,),
        "require_iri": True,
        "message": "Add a license IRI using dcterms:license.",
    },
    {
        "key": "version",
        "label": "Version",
        "property": "owl:versionInfo or owl:versionIRI",
        "severity": "required",
        "predicates": (OWL.versionInfo, OWL.versionIRI),
        "message": "Add version information using owl:versionInfo or owl:versionIRI.",
    },
    {
        "key": "created",
        "label": "Created date",
        "property": "dcterms:created or dcterms:issued",
        "severity": "recommended",
        "predicates": (DCTERMS.created, DCTERMS.issued),
        "message": "Consider adding a creation or issue date.",
    },
    {
        "key": "modified",
        "label": "Modified date",
        "property": "dcterms:modified",
        "severity": "recommended",
        "predicates": (DCTERMS.modified,),
        "message": "Consider adding a modification date.",
    },
    {
        "key": "publisher",
        "label": "Publisher",
        "property": "dcterms:publisher",
        "severity": "recommended",
        "predicates": (DCTERMS.publisher,),
        "message": "Consider adding a publisher.",
    },
)

METADATA_PREDICATES = tuple(
    pred for spec in CHECK_SPECS for pred in spec.get("predicates", ())
)


def _candidate_ontology_nodes(graph: Graph) -> list[URIRef]:
    """Find ontology resources to evaluate metadata on."""
    ontology_nodes = {s for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)}
    if ontology_nodes:
        return sorted(ontology_nodes, key=str)

    # Fallback: find subjects that already carry ontology-like metadata.
    candidates = set()
    for pred in METADATA_PREDICATES:
        candidates.update(s for s in graph.subjects(pred, None) if isinstance(s, URIRef))
    return sorted(candidates, key=str)


def _values_for_any_predicate(graph: Graph, subjects: Iterable[URIRef], predicates: tuple) -> list:
    values = []
    for subject in subjects:
        for pred in predicates:
            values.extend(graph.objects(subject, pred))
    return values


def validate_ontology_metadata(graph: Graph) -> MetadataReport:
    """Evaluate whether an ontology has the key metadata properties it should have."""

    subjects = _candidate_ontology_nodes(graph)
    checks: list[MetadataCheck] = []

    has_ontology_decl = any(True for _ in graph.triples((None, RDF.type, OWL.Ontology)))
    checks.append(
        MetadataCheck(
            key="ontology_declaration",
            label="Ontology declaration",
            property="rdf:type owl:Ontology",
            severity="required",
            status=Status.OK if has_ontology_decl else Status.FAIL,
            message=None if has_ontology_decl else "Declare the ontology itself with rdf:type owl:Ontology.",
        )
    )

    for spec in CHECK_SPECS[1:]:
        values = _values_for_any_predicate(graph, subjects, spec["predicates"])
        if values:
            if spec.get("require_iri") and not any(isinstance(v, URIRef) for v in values):
                status = Status.FAIL if spec["severity"] == "required" else Status.WARN
                message = "Use an IRI value here rather than plain text."
            else:
                status = Status.OK
                message = None
        else:
            status = Status.FAIL if spec["severity"] == "required" else Status.WARN
            message = spec["message"]

        checks.append(
            MetadataCheck(
                key=spec["key"],
                label=spec["label"],
                property=spec["property"],
                severity=spec["severity"],
                status=status,
                message=message,
            )
        )

    return MetadataReport(checks=checks)
