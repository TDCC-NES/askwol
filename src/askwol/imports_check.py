"""Check that external vocabularies are declared with `owl:imports`.

For every namespace that the ontology actually uses (has at least one
subject-position term), verify that the ontology header declares it with
`owl:imports`. Core RDF/OWL vocabularies and the ontology's own namespace
are skipped.
"""

from __future__ import annotations

from rdflib import OWL, RDF, Graph, URIRef

from askwol.models import ImportsCheck, ImportsReport, Status

# Core W3C vocabularies that are part of the RDF/OWL substrate. Nobody
# imports these explicitly, so missing imports for them are not flagged.
_CORE_NS = {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/2001/XMLSchema#",
    "http://www.w3.org/XML/1998/namespace",
}


def _strip(uri: str) -> str:
    """Normalise a namespace/import IRI for comparison (drop trailing # or /)."""
    return uri.rstrip("#/")


def check_imports(
    graph: Graph,
    namespaces: dict[str, str],
    terms_by_namespace: dict[str, set[str]],
) -> ImportsReport:
    ontology_iris = sorted(
        str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)
    )

    declared: set[str] = set()
    for ont in ontology_iris:
        for o in graph.objects(URIRef(ont), OWL.imports):
            if isinstance(o, URIRef):
                val = str(o).strip()
                if val:
                    declared.add(val)
    declared_stripped = {_strip(d) for d in declared}

    # Namespaces considered "own" to the ontology: anything sharing a
    # stem with one of the ontology IRIs.
    own_prefixes: set[str] = set()
    ont_stems = {_strip(ont) for ont in ontology_iris}
    for pfx, ns_uri in namespaces.items():
        ns_stem = _strip(ns_uri)
        if any(ns_stem == s or ns_stem.startswith(s + "/") or ns_stem.startswith(s + "#")
               or s.startswith(ns_stem + "/") or s.startswith(ns_stem + "#") or s == ns_stem
               for s in ont_stems):
            own_prefixes.add(pfx)

    checks: list[ImportsCheck] = []
    for pfx, ns_uri in sorted(namespaces.items(), key=lambda kv: kv[0].lower()):
        if ns_uri in _CORE_NS:
            continue
        if pfx in own_prefixes:
            continue
        if not terms_by_namespace.get(pfx):
            continue
        ns_stem = _strip(ns_uri)
        if ns_stem in declared_stripped:
            checks.append(ImportsCheck(
                prefix=pfx, namespace=ns_uri, status=Status.OK,
                message="declared in owl:imports",
            ))
        else:
            checks.append(ImportsCheck(
                prefix=pfx, namespace=ns_uri, status=Status.WARN,
                message="used in the ontology but not declared in owl:imports",
            ))

    if not ontology_iris:
        # No owl:Ontology declaration -> the metadata check already flags
        # this; we mark the imports check as skipped to avoid double noise.
        return ImportsReport(
            ontology_iri=None,
            declared=sorted(declared),
            checks=[],
            status=Status.SKIP,
        )

    status = Status.OK
    if any(c.status == Status.WARN for c in checks):
        status = Status.WARN

    return ImportsReport(
        ontology_iri=ontology_iris[0],
        declared=sorted(declared),
        checks=checks,
        status=status,
    )
