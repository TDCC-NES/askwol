"""Flag terms in the ontology's own namespace that are not OWL schema.

An OWL ontology should define *schema*: classes, properties, and datatypes.
Individuals, SKOS concepts, and other instance data belong in a separate data
resource or concept scheme, not mixed into the ontology itself.

The whitelist check itself (does a term carry at least one recognized schema
type?) runs through pyshacl against shapes/non_ontology_terms.ttl; this module
only computes the display label for whatever it flags.
"""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, SKOS

from askwol.iri_utils import local_name as _local_name, namespace_of as _namespace_of
from askwol.models import NonOntologyTermIssue, NonOntologyTermsReport, Status
from askwol.shacl_runner import run_shapes

_SHAPES_FILE = "non_ontology_terms.ttl"


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

    flagged: list[NonOntologyTermIssue] = []
    for result in run_shapes(graph, _SHAPES_FILE):
        if result.name != "SchemaWhitelist":
            continue
        subject = URIRef(result.focus_node)
        types = set(graph.objects(subject, RDF.type))
        flagged.append(
            NonOntologyTermIssue(
                term=result.focus_node,
                display_name=_local_name(result.focus_node),
                type_label=_type_label(types),
            )
        )

    flagged.sort(key=lambda issue: issue.term)

    return NonOntologyTermsReport(
        total_flagged=len(flagged),
        terms=flagged,
        status=Status.OK if not flagged else Status.WARN,
    )
