"""Parse OWL/RDF ontology files and extract namespaces, terms, and imports."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, URIRef, OWL, RDF
from rdflib.namespace import DCTERMS


@dataclass
class ParsedOntology:
    """Structured extraction from a parsed ontology file."""

    graph: Graph
    namespaces: dict[str, str] = field(default_factory=dict)
    # prefix -> set of local names used from that namespace
    terms_by_namespace: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    imports: list[str] = field(default_factory=list)
    # All prefixes declared in the file (including unused ones)
    declared_prefixes: dict[str, str] = field(default_factory=dict)


def parse_ontology(source: str | Path, base_uri: str | None = None) -> ParsedOntology:
    """Parse an ontology file and extract its structure.

    Args:
        source: File path or URL to the ontology.
        base_uri: The ontology's real, published URI, used to resolve any
            relative IRIs it contains (e.g. ``<>`` or ``<#Term>``). Pass this
            whenever ``source`` is a local temp file holding content that was
            downloaded from a URL: without it, rdflib falls back to the temp
            file's own ``file://`` path as the base, so relative IRIs resolve
            to a bogus location instead of the ontology's real namespace.
            Leave unset when ``source`` is a genuine local file with no
            corresponding published URL (e.g. a user-uploaded file).

    Returns:
        ParsedOntology with extracted namespaces, terms, and imports.
    """
    g = Graph()

    # Capture rdflib's built-in prefixes before parsing
    builtin_prefixes = {str(pfx) for pfx, _ in g.namespaces()}

    g.parse(str(source), publicID=base_uri)

    # Build a lookup of ALL registered prefixes (including rdflib built-ins)
    all_prefixes: dict[str, str] = {
        str(prefix): str(ns_uri) for prefix, ns_uri in g.namespaces()
    }

    result = ParsedOntology(graph=g)
    # Only record prefixes that the file actually declared (not rdflib defaults)
    result.declared_prefixes = {
        pfx: uri for pfx, uri in all_prefixes.items()
        if pfx not in builtin_prefixes
    }

    # Collect owl:imports
    for _, _, imported in g.triples((None, OWL.imports, None)):
        result.imports.append(str(imported))

    # The ontology's own IRI, version markers, and import targets are not
    # vocabulary terms - without this exclusion, rdflib would split a slash
    # IRI like <http://ex.org/ont> into namespace <http://ex.org/> plus a
    # phantom local name "ont".
    header_iris: set[str] = {
        str(s) for s in g.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)
    }
    for pred in (OWL.versionIRI, OWL.priorVersion, OWL.imports,
                 OWL.backwardCompatibleWith, OWL.incompatibleWith,
                 DCTERMS.replaces, DCTERMS.isReplacedBy):
        for obj in g.objects(None, pred):
            if isinstance(obj, URIRef):
                header_iris.add(str(obj))

    # Walk every triple and bucket each URI by its namespace.
    # Only namespaces that are actually *used* in triples get included.
    # Terms are only collected from *subject* positions  -  these are the
    # concepts the ontology defines, not the vocabulary it references.
    seen_ns: set[str] = set()       # URIs already registered for namespace discovery
    seen_terms: set[str] = set()    # subject URIs already added to terms_by_namespace
    for s, p, o in g:
        # Register namespaces from all positions
        for node in (s, p, o):
            if isinstance(node, URIRef):
                uri = str(node)
                if uri in header_iris:
                    continue
                if uri not in seen_ns:
                    seen_ns.add(uri)
                    _bucket_uri(uri, result, all_prefixes)
        # Only collect subject URIs as terms to validate
        if isinstance(s, URIRef):
            s_uri = str(s)
            if s_uri not in header_iris and s_uri not in seen_terms:
                seen_terms.add(s_uri)
                _add_term(s_uri, result, all_prefixes)

    return result


def _bucket_uri(uri: str, result: ParsedOntology, all_prefixes: dict[str, str]) -> None:
    """Register a URI's namespace."""
    # Try splitting on # first, then last /
    if "#" in uri:
        ns, local = uri.rsplit("#", 1)
        ns += "#"
    elif "/" in uri:
        ns, local = uri.rsplit("/", 1)
        ns += "/"
    else:
        return  # Can't determine namespace

    if not local:
        return  # The URI *is* the namespace itself

    # Find the prefix for this namespace (from all registered prefixes)
    prefix = None
    for pfx, ns_uri in all_prefixes.items():
        if ns_uri == ns:
            prefix = pfx
            break

    if prefix is None:
        # Unknown namespace  -  register it with an auto-generated prefix
        prefix = f"_ns{len(result.namespaces)}"

    # Only add namespace to result when we actually see a term from it
    if prefix not in result.namespaces:
        result.namespaces[prefix] = ns



def _add_term(uri: str, result: ParsedOntology, all_prefixes: dict[str, str]) -> None:
    """Add a subject URI's local name to terms_by_namespace."""
    if "#" in uri:
        ns, local = uri.rsplit("#", 1)
        ns += "#"
    elif "/" in uri:
        ns, local = uri.rsplit("/", 1)
        ns += "/"
    else:
        return
    if not local:
        return
    for pfx, ns_uri in all_prefixes.items():
        if ns_uri == ns:
            result.terms_by_namespace[pfx].add(local)
            return
    # Check auto-generated prefixes already in result
    for pfx, ns_uri in result.namespaces.items():
        if ns_uri == ns:
            result.terms_by_namespace[pfx].add(local)
            return
