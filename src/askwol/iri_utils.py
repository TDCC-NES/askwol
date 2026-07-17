"""Shared IRI helpers used across the internal-term checks.

Splitting a URI into its namespace/local-name parts and recognizing
well-known external vocabularies are needed by several checks
(definitions, internal terms, non-ontology terms, term inventory, reasoner
checks). This module is the single source of truth for both, so the
external-vocabulary allowlist only has to be updated in one place.
"""

from __future__ import annotations

# Well-known vocabularies that are reused, not defined, by an ontology.
# Terms from these namespaces are excluded from "own namespace" checks
# (definition docs, internal terms, term inventory, ...) even when there
# is no owl:Ontology declaration to determine the ontology's own namespace.
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


def namespace_of(uri: str) -> str:
    """Return the namespace part of a URI (up to and including # or the last /)."""
    if "#" in uri:
        return uri.rsplit("#", 1)[0] + "#"
    if "/" in uri:
        return uri.rsplit("/", 1)[0] + "/"
    return uri


def local_name(uri: str) -> str:
    """Return the local-name part of a URI (after # or the last /)."""
    if "#" in uri:
        return uri.rsplit("#", 1)[1]
    if "/" in uri:
        return uri.rstrip("/").rsplit("/", 1)[1]
    return uri


def is_external(uri: str) -> bool:
    """True if a URI belongs to one of the well-known EXTERNAL_NAMESPACES."""
    return any(uri.startswith(ns) for ns in EXTERNAL_NAMESPACES)
