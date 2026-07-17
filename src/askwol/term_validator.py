"""Validate that terms used from external namespaces actually exist in those vocabularies."""

from __future__ import annotations

from rdflib import URIRef

from askwol.cache import OntologyCache
from askwol.deprecation import deprecation_marker
from askwol.models import Status, TermCheck

# ---------------------------------------------------------------------------
# Built-in allowlists for vocabularies that don't serve RDF
# ---------------------------------------------------------------------------

# XSD 1.1 built-in datatypes and special type names
# https://www.w3.org/TR/xmlschema11-2/#built-in-datatypes
XSD_BUILTIN_TYPES: frozenset[str] = frozenset({
    # Special types
    "anyType", "anySimpleType", "anyAtomicType",
    # Primitive datatypes
    "string", "boolean", "decimal", "float", "double",
    "duration", "dateTime", "time", "date",
    "gYearMonth", "gYear", "gMonthDay", "gDay", "gMonth",
    "hexBinary", "base64Binary", "anyURI", "QName", "NOTATION",
    # Derived datatypes
    "normalizedString", "token", "language",
    "NMTOKEN", "NMTOKENS", "Name", "NCName",
    "ID", "IDREF", "IDREFS", "ENTITY", "ENTITIES",
    "integer", "nonPositiveInteger", "negativeInteger",
    "long", "int", "short", "byte",
    "nonNegativeInteger", "unsignedLong", "unsignedInt",
    "unsignedShort", "unsignedByte", "positiveInteger",
    # XSD 1.1 additions
    "dateTimeStamp", "dayTimeDuration", "yearMonthDuration",
    # Facets (used as properties in OWL restrictions)
    "minInclusive", "maxInclusive", "minExclusive", "maxExclusive",
    "minLength", "maxLength", "length", "totalDigits", "fractionDigits",
    "pattern", "whiteSpace", "enumeration",
})

# Map namespace URI -> known local names
KNOWN_TERMS: dict[str, frozenset[str]] = {
    "http://www.w3.org/2001/XMLSchema#": XSD_BUILTIN_TYPES,
}


def validate_terms(
    prefix: str,
    namespace_uri: str,
    local_names: set[str],
    cache: OntologyCache,
) -> list[TermCheck]:
    """Check whether each local name exists in the cached remote vocabulary.

    A term is considered to exist if its full URI appears in ANY triple position
    (subject, predicate, or object) in the remote ontology graph.

    For vocabularies that don't serve RDF (e.g. XSD), a built-in allowlist
    is used instead.
    """
    results: list[TermCheck] = []

    # Check built-in allowlist first (for non-RDF vocabularies like XSD)
    known = KNOWN_TERMS.get(namespace_uri)
    if known is not None:
        for local in sorted(local_names):
            if local in known:
                results.append(
                    TermCheck(
                        term_uri=namespace_uri + local,
                        prefix=prefix,
                        local_name=local,
                        status=Status.OK,
                    )
                )
            else:
                results.append(
                    TermCheck(
                        term_uri=namespace_uri + local,
                        prefix=prefix,
                        local_name=local,
                        status=Status.FAIL,
                        error="Not a recognised XSD built-in type",
                    )
                )
        return results

    remote_graph = cache.get(namespace_uri)

    if remote_graph is None:
        cached_err = cache.get_error(namespace_uri)
        reason = cached_err or "Namespace could not be loaded as RDF"
        for local in sorted(local_names):
            results.append(
                TermCheck(
                    term_uri=namespace_uri + local,
                    prefix=prefix,
                    local_name=local,
                    status=Status.SKIP,
                    error=reason,
                )
            )
        return results

    # Build a set of all URIs present in the remote graph for fast lookup
    remote_uris: set[str] = set()
    for s, p, o in remote_graph:
        if isinstance(s, URIRef):
            remote_uris.add(str(s))
        if isinstance(p, URIRef):
            remote_uris.add(str(p))
        if isinstance(o, URIRef):
            remote_uris.add(str(o))

    for local in sorted(local_names):
        full_uri = namespace_uri + local
        if full_uri in remote_uris:
            marker = deprecation_marker(remote_graph, URIRef(full_uri))
            results.append(
                TermCheck(
                    term_uri=full_uri,
                    prefix=prefix,
                    local_name=local,
                    status=Status.WARN if marker else Status.OK,
                    deprecated=marker,
                )
            )
        else:
            results.append(
                TermCheck(
                    term_uri=full_uri,
                    prefix=prefix,
                    local_name=local,
                    status=Status.FAIL,
                    error=f"Term not found in remote vocabulary at {namespace_uri}",
                )
            )

    return results
