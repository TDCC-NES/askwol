"""Flag skos:Concept instances defined in the ontology's own namespace.

An OWL ontology should define *schema*: classes, properties, and datatypes.
A SKOS concept scheme is subject-matter data, not schema, so it belongs in a
separate resource, not mixed into the ontology itself.

Named individuals (owl:NamedIndividual) are deliberately not flagged: many
ontologies define a small, fixed set of individuals alongside their schema
(for example OWL-Time's days of week and time units), which is a common,
legitimate modeling pattern rather than accidental instance data.

The check itself runs through pyshacl against shapes/non_ontology_terms.ttl;
this module only computes the display label for whatever it flags.
"""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from askwol.iri_utils import local_name as _local_name, namespace_of as _namespace_of
from askwol.models import NonOntologyTermIssue, NonOntologyTermsReport, Status
from askwol.shacl_runner import run_shapes

_SHAPES_FILE = "non_ontology_terms.ttl"


def check_non_ontology_terms(graph: Graph) -> NonOntologyTermsReport:
    """Flag own-namespace skos:Concept instances mixed into the schema."""
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
        if result.name != "ConceptInSchema":
            continue
        flagged.append(
            NonOntologyTermIssue(
                term=result.focus_node,
                display_name=_local_name(result.focus_node),
                type_label="SKOS concept",
            )
        )

    flagged.sort(key=lambda issue: issue.term)

    return NonOntologyTermsReport(
        total_flagged=len(flagged),
        terms=flagged,
        status=Status.OK if not flagged else Status.WARN,
    )
