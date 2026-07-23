"""Validate ontology-level metadata by running it through pyshacl against
`shapes/ontology_metadata.ttl`, folded into a normalized summary."""

from __future__ import annotations

from rdflib import Graph
from rdflib.namespace import OWL, RDF

from askwol.models import MetadataCheck, MetadataReport, Status
from askwol.shacl_runner import load_shape_messages, run_shapes

_SHAPES_FILE = "ontology_metadata.ttl"

# key, sh:name (as used in the shape file), label, property, severity.
# "key" is the stable identifier consumers rely on; sh:name is how the shape
# file's own violations correlate back to it.
_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    ("ontology_declaration", "", "Ontology declaration", "rdf:type owl:Ontology", "required"),
    ("title", "Title", "Title", "dcterms:title or rdfs:label", "required"),
    ("description", "Description", "Description", "dcterms:description or rdfs:comment", "required"),
    ("creator", "Creator", "Creator", "dcterms:creator", "required"),
    ("version", "Version", "Version", "owl:versionInfo or owl:versionIRI", "required"),
    ("created", "Created date", "Created date", "dcterms:created or dcterms:issued", "recommended"),
    ("modified", "Modified date", "Modified date", "dcterms:modified", "recommended"),
    ("publisher", "Publisher", "Publisher", "dcterms:publisher", "recommended"),
)


def validate_ontology_metadata(graph: Graph) -> MetadataReport:
    """Evaluate whether an ontology has the key metadata properties it should have."""

    # A missing rdf:type owl:Ontology declaration leaves the shape below with
    # no focus node to attach a result to, so it is checked directly rather
    # than through the shape.
    has_ontology_decl = any(True for _ in graph.triples((None, RDF.type, OWL.Ontology)))

    results_by_name = {}
    if has_ontology_decl:
        for result in run_shapes(graph, _SHAPES_FILE):
            if result.name:
                results_by_name.setdefault(result.name, result)

    # Fallback text for when there is no owl:Ontology node at all: nothing
    # ran, but the report should still explain what each check wants.
    fallback_messages = load_shape_messages(_SHAPES_FILE)

    checks: list[MetadataCheck] = []
    for key, shape_name, label, prop, severity in _SPECS:
        if key == "ontology_declaration":
            checks.append(
                MetadataCheck(
                    key=key,
                    label=label,
                    property=prop,
                    severity=severity,
                    status=Status.OK if has_ontology_decl else Status.FAIL,
                    message=None if has_ontology_decl else "Declare the ontology itself with rdf:type owl:Ontology.",
                )
            )
            continue

        if not has_ontology_decl:
            status = Status.FAIL if severity == "required" else Status.WARN
            message = fallback_messages.get(shape_name)
        else:
            result = results_by_name.get(shape_name)
            status = result.status if result else Status.OK
            message = result.message if result else None

        checks.append(
            MetadataCheck(
                key=key,
                label=label,
                property=prop,
                severity=severity,
                status=status,
                message=message,
            )
        )

    return MetadataReport(checks=checks)
