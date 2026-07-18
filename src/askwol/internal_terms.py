"""Check that terms in the ontology's own namespace are actually defined.

Scoping (which namespace is "the ontology's own") and the actual
defined-vs-referenced check both live in shapes/internal_terms.ttl, run
through pyshacl. This module only guards the two SKIP conditions, which have
no focus node for a SHACL shape to report against.
"""

from __future__ import annotations

from rdflib import Graph
from rdflib.namespace import OWL, RDF, RDFS

from askwol.iri_utils import local_name as _local_name
from askwol.models import InternalTermIssue, InternalTermReference, InternalTermsReport, Status
from askwol.shacl_runner import run_shapes, run_target

_SHAPES_FILE = "internal_terms.ttl"

# rdf:type values that mark a subject as a term the ontology defines itself;
# used only to decide whether *any* term is defined at all (see
# shapes/internal_terms.ttl for the identical list used in the real check).
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



def check_internal_terms(graph: Graph) -> InternalTermsReport:
    """Flag terms in the ontology's own namespace that are used but never defined.

    A term is *defined* when it appears as the subject of at least one triple.
    It is *referenced* when it appears as a predicate or object. A term that is
    referenced from the ontology's own namespace but never defined is usually a
    typo or a forgotten declaration.
    """
    if not any(True for _ in graph.subjects(RDF.type, OWL.Ontology)):
        return InternalTermsReport(
            status=Status.SKIP,
            message="no owl:Ontology declaration found",
        )

    if not any(t in _DEFINITIONAL_TYPES for _, _, t in graph.triples((None, RDF.type, None))):
        return InternalTermsReport(
            status=Status.SKIP,
            message="no terms are defined in the ontology's own namespace",
        )

    referenced = run_target(graph, _SHAPES_FILE)
    undefined_uris = sorted(
        result.focus_node
        for result in run_shapes(graph, _SHAPES_FILE)
        if result.name == "InternalTermDefined"
    )
    undefined_set = set(undefined_uris)
    undefined = [
        InternalTermIssue(term=uri, display_name=_local_name(uri))
        for uri in undefined_uris
    ]
    all_referenced = [
        InternalTermReference(term=uri, display_name=_local_name(uri), defined=uri not in undefined_set)
        for uri in sorted(referenced)
    ]

    return InternalTermsReport(
        total_referenced=len(referenced),
        defined=len(referenced) - len(undefined),
        undefined=undefined,
        referenced=all_referenced,
        status=Status.OK if not undefined else Status.FAIL,
    )
