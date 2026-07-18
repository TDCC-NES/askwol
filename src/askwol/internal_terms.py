"""Check that terms in the ontology's own namespace are actually defined.

"The ontology's own namespace" is derived from the subject(s) of
owl:Ontology (iri_utils.ontology_namespaces), the same single source of
truth used by term_inventory.py, definition_docs.py, non_ontology_terms.py,
and reasoner_checks.py - not from wherever a definitional rdf:type happens
to appear. An ontology that re-declares a reused term as, say,
``rdfs:label a owl:AnnotationProperty`` (common boilerplate; PROV-O, FOAF,
and many others do this) does not thereby "own" the whole RDFS/OWL
namespace, so referencing other RDFS/OWL terms elsewhere must not be
flagged as "undefined internal terms".
"""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

from askwol.iri_utils import local_name as _local_name, ontology_namespaces as _ontology_namespaces
from askwol.models import InternalTermIssue, InternalTermReference, InternalTermsReport, Status

# rdf:type values that mark a subject as a term the ontology defines itself;
# used only to decide whether *any* term is defined at all (i.e. whether this
# check is worth running).
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

# owl:Ontology header properties whose IRI-valued objects are opaque
# version identifiers, not terms - they are never expected to appear as
# rdf:type subjects, so referencing one must not be flagged as "undefined".
# E.g. OWL-Time's own header has both
# owl:priorVersion <http://www.w3.org/2006/time#2006> and
# owl:versionIRI <http://www.w3.org/2006/time#2016>: "2006"/"2016" are
# symbolic version markers, not classes/properties/individuals. GeoSPARQL's
# header similarly has dcterms:replaces <.../geosparql/1.0>, pointing at its
# own prior version.
_VERSION_PROPERTIES = (
    OWL.versionIRI,
    OWL.priorVersion,
    OWL.backwardCompatibleWith,
    OWL.incompatibleWith,
    DCTERMS.replaces,
    DCTERMS.isReplacedBy,
)


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

    # Parent-path fallback deliberately excluded (see ontology_namespaces'
    # docstring): a slash ontology IRI like https://host/dataset would
    # otherwise claim the entire host, misclassifying unrelated IRIs such as
    # an owl:versionIRI document or a sibling resource under the same host.
    own_ns = _ontology_namespaces(graph, include_parent_path=False)
    ontology_iris = {str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)}
    version_iris = {
        str(o)
        for prop in _VERSION_PROPERTIES
        for o in graph.objects(None, prop)
        if isinstance(o, URIRef)
    }

    referenced: set[str] = set()
    for _s, p, o in graph:
        for node in (p, o):
            if not isinstance(node, URIRef):
                continue
            uri = str(node)
            if uri in ontology_iris or uri in version_iris:
                continue
            # A bare namespace IRI (empty local name) is the vocabulary
            # itself, not a term in it - e.g. `:someTerm rdfs:isDefinedBy :`
            # is a common RDFS idiom pointing back at the ontology's own
            # namespace, and must not be flagged as an undefined term.
            if not _local_name(uri):
                continue
            if any(uri.startswith(ns) for ns in own_ns):
                referenced.add(uri)

    undefined_uris = sorted(
        uri for uri in referenced
        if next(graph.triples((URIRef(uri), None, None)), None) is None
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
