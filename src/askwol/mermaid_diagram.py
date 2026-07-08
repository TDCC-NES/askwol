"""Render a parsed ontology as a Mermaid class diagram."""

from __future__ import annotations

import re

from rdflib import RDF, RDFS, OWL, Graph, URIRef


def _shorten(uri: str, namespaces: dict[str, str]) -> str:
    """Shorten a URI to prefix:local using the ontology's own prefixes."""
    uri_str = str(uri)
    # Prefer the most specific (longest) matching namespace so overlapping
    # namespaces (e.g. .../food/ vs .../food#) don't leave a '#' in the local
    # part.
    best: tuple[str, str] | None = None  # (prefix, local)
    for pfx, ns_uri in namespaces.items():
        if uri_str.startswith(ns_uri):
            local = uri_str[len(ns_uri):]
            if local and (best is None or len(ns_uri) > len(namespaces[best[0]])):
                best = (pfx, local)
    if best is not None:
        pfx, local = best
        return f"{pfx}:{local}" if pfx else local
    # Fallback: use fragment or last path segment
    if "#" in uri_str:
        return uri_str.rsplit("#", 1)[-1]
    if "/" in uri_str:
        return uri_str.rsplit("/", 1)[-1]
    return uri_str


def _mermaid_id(label: str) -> str:
    """Make a label safe for use as a Mermaid node ID."""
    return re.sub(r"[^0-9A-Za-z_]", "_", label)


# U+2236 RATIO looks identical to a colon but doesn't trigger Mermaid's parser
_RATIO = "\u2236"


def _mermaid_text(label: str) -> str:
    """Make label safe for Mermaid edge/attribute text (replace : with RATIO)."""
    return label.replace(":", _RATIO)


def build_mermaid(graph: Graph, namespaces: dict[str, str]) -> str:
    """Extract classes, properties, and relationships from the graph into a Mermaid class diagram."""
    lines = ["classDiagram"]

    # Collect classes
    classes: set[str] = set()
    for s, _, _ in graph.triples((None, RDF.type, OWL.Class)):
        if isinstance(s, URIRef):
            classes.add(str(s))
    for s, _, _ in graph.triples((None, RDF.type, RDFS.Class)):
        if isinstance(s, URIRef):
            classes.add(str(s))

    # Collect properties with domain/range
    properties: list[tuple[str, str | None, str | None, str]] = []  # (name, domain, range, kind)
    seen_props: set[str] = set()
    for pred_type, kind in [(OWL.ObjectProperty, "obj"), (OWL.DatatypeProperty, "data")]:
        for s, _, _ in graph.triples((None, RDF.type, pred_type)):
            if not isinstance(s, URIRef):
                continue
            prop_name = _shorten(str(s), namespaces)
            domains = [str(o) for _, _, o in graph.triples((s, RDFS.domain, None)) if isinstance(o, URIRef)]
            ranges = [str(o) for _, _, o in graph.triples((s, RDFS.range, None)) if isinstance(o, URIRef)]
            domain = domains[0] if domains else None
            rng = ranges[0] if ranges else None
            properties.append((prop_name, domain, rng, kind))
            seen_props.add(str(s))
            # Ensure domain/range classes appear even if not explicitly typed
            if domain:
                classes.add(domain)
            if rng and kind == "obj":
                classes.add(rng)

    # Also pick up plain rdf:Property (used by Dublin Core, schema.org, etc.)
    # — infer kind from the range URI (xsd:* or rdfs:Literal => data, else obj).
    xsd_ns = "http://www.w3.org/2001/XMLSchema#"
    rdfs_literal = "http://www.w3.org/2000/01/rdf-schema#Literal"
    for s, _, _ in graph.triples((None, RDF.type, RDF.Property)):
        if not isinstance(s, URIRef) or str(s) in seen_props:
            continue
        prop_name = _shorten(str(s), namespaces)
        domains = [str(o) for _, _, o in graph.triples((s, RDFS.domain, None)) if isinstance(o, URIRef)]
        ranges = [str(o) for _, _, o in graph.triples((s, RDFS.range, None)) if isinstance(o, URIRef)]
        domain = domains[0] if domains else None
        rng = ranges[0] if ranges else None
        if rng and (rng.startswith(xsd_ns) or rng == rdfs_literal):
            kind = "data"
        elif rng:
            kind = "obj"
        else:
            kind = "data"  # no range => assume literal/annotation
        properties.append((prop_name, domain, rng, kind))
        if domain:
            classes.add(domain)
        if rng and kind == "obj":
            classes.add(rng)

    # Collect subClassOf
    subclass_rels: list[tuple[str, str]] = []
    for s, _, o in graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            classes.add(str(s))
            classes.add(str(o))
            subclass_rels.append((str(s), str(o)))

    if not classes:
        return ""

    # Filter out well-known vocabulary classes (owl:, rdf:, rdfs:, xsd:)
    skip_ns = {
        "http://www.w3.org/2002/07/owl#",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://www.w3.org/2000/01/rdf-schema#",
        "http://www.w3.org/2001/XMLSchema#",
    }
    classes = {c for c in classes if not any(c.startswith(ns) for ns in skip_ns)}

    if not classes:
        return ""

    # Emit class nodes  -  quoted labels handle real colons fine
    for cls_uri in sorted(classes):
        label = _shorten(cls_uri, namespaces)
        mid = _mermaid_id(label)
        lines.append(f'    class {mid}["{label}"]')

    # Emit subClassOf (inheritance)
    for child, parent in subclass_rels:
        c_label = _shorten(child, namespaces)
        p_label = _shorten(parent, namespaces)
        if any(str(child).startswith(ns) for ns in skip_ns) or any(str(parent).startswith(ns) for ns in skip_ns):
            continue
        lines.append(f"    {_mermaid_id(p_label)} <|-- {_mermaid_id(c_label)}")

    # Emit object properties as associations
    for prop_name, domain, rng, kind in properties:
        if kind == "obj" and domain and rng:
            if any(domain.startswith(ns) for ns in skip_ns) or any(rng.startswith(ns) for ns in skip_ns):
                continue
            d_label = _shorten(domain, namespaces)
            r_label = _shorten(rng, namespaces)
            lines.append(f'    {_mermaid_id(d_label)} --> {_mermaid_id(r_label)} : {_mermaid_text(prop_name)}')
        elif kind == "data" and domain:
            if any(domain.startswith(ns) for ns in skip_ns):
                continue
            d_label = _shorten(domain, namespaces)
            rng_label = _mermaid_text(_shorten(rng, namespaces)) if rng else "Literal"
            d_mid = _mermaid_id(d_label)
            lines.append(f"    {d_mid} : {_mermaid_text(prop_name)} {rng_label}")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)

