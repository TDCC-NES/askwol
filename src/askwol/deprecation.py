"""Detect whether a term is marked deprecated by the vocabulary that defines it.

Shared by the checks that should not flag issues about a term once it is
deprecated (naming conventions, domain and range, label and comment
documentation, language tag consistency), and by `term_validator` to note
when a reused external term is deprecated upstream. The OWL 2 standard
annotation and two legacy conventions are recognised:

* ``owl:deprecated "true"^^xsd:boolean`` - the OWL 2 standard annotation
  property (https://www.w3.org/TR/owl2-syntax/#Annotation_Properties).
* ``rdf:type owl:DeprecatedClass`` / ``owl:DeprecatedProperty`` - the older
  OWL 1-era convention of retyping the term itself; defined in the OWL 1
  Reference (https://www.w3.org/TR/owl-ref/#Deprecation) and still used by
  some vocabularies (e.g. VIVO).
* ``vs:term_status "deprecated"`` / ``"archaic"`` - the W3C Vocabulary Status
  ontology (https://www.w3.org/2003/06/sw-vocab-status/note), used by e.g.
  FOAF.
"""

from __future__ import annotations

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, XSD

VS = Namespace("http://www.w3.org/2003/06/sw-vocab-status/ns#")

_DEPRECATED_STATUS_VALUES = {"deprecated", "archaic"}


def deprecation_marker(graph: Graph, term: URIRef) -> str | None:
    """Return the convention that marks `term` deprecated in `graph`, or None."""
    if any(
        isinstance(value, Literal) and value.datatype == XSD.boolean
        and str(value).strip() in ("true", "1")
        for value in graph.objects(term, OWL.deprecated)
    ):
        return "owl:deprecated"

    types = set(graph.objects(term, RDF.type))
    if OWL.DeprecatedClass in types:
        return "owl:DeprecatedClass"
    if OWL.DeprecatedProperty in types:
        return "owl:DeprecatedProperty"

    statuses = sorted(
        str(value) for value in graph.objects(term, VS.term_status)
        if str(value).lower() in _DEPRECATED_STATUS_VALUES
    )
    if statuses:
        return f'vs:term_status "{statuses[0]}"'

    return None


def is_deprecated(graph: Graph, term: URIRef) -> bool:
    """Whether `term` is marked deprecated in `graph` by any known convention."""
    return deprecation_marker(graph, term) is not None
