"""Categorize the ontology's own terms and check their structure.

This module runs a single classification pass over every term defined in the
ontology's own namespace and drives three checks:

* ``check_term_inventory`` - what category each term falls into (class, object
  property, datatype property, ...) plus the capitalization convention
  (classes start uppercase, properties start lowercase).
* ``check_domains_ranges`` - whether object and datatype properties declare a
  domain and range, and whether the range is the right kind of thing (a class
  for object properties, a datatype for datatype properties).
* ``check_datatypes`` - an inventory of the datatypes used (as property ranges
  and as literal datatypes), flagging any that are not recognized.
"""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from askwol.deprecation import deprecation_marker
from askwol.models import (
    DatatypeReport,
    DatatypeUsage,
    DomainRangeCheck,
    DomainRangeReport,
    InternalTermEntry,
    Status,
    TermInventoryReport,
)
from askwol.shacl_runner import run_shapes
from askwol.term_validator import XSD_BUILTIN_TYPES

_SHAPES_FILE = "term_inventory.ttl"

RDF_LANG_STRING = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#langString")

# Category labels (also used as display strings in the report).
CLASS = "Class"
OBJECT_PROPERTY = "Object property"
DATATYPE_PROPERTY = "Datatype property"
ANNOTATION_PROPERTY = "Annotation property"
PROPERTY = "Property"
DATATYPE = "Datatype"
NAMED_INDIVIDUAL = "Named individual"
UNTYPED = "Untyped"

# The order categories appear in the inventory table and counts.
CATEGORY_ORDER = [
    CLASS,
    OBJECT_PROPERTY,
    DATATYPE_PROPERTY,
    ANNOTATION_PROPERTY,
    PROPERTY,
    DATATYPE,
    NAMED_INDIVIDUAL,
    UNTYPED,
]

# Categories the capitalization convention applies to.
_PROPERTY_CATEGORIES = {OBJECT_PROPERTY, DATATYPE_PROPERTY, ANNOTATION_PROPERTY, PROPERTY}

_CLASS_TYPES = {OWL.Class, RDFS.Class}
_GENERIC_PROPERTY_TYPES = {
    RDF.Property,
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
}

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

# Datatypes recognized in addition to the XSD built-ins.
_OTHER_DATATYPES = {
    str(RDFS.Literal),
    str(RDF_LANG_STRING),
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#XMLLiteral",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#HTML",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#PlainLiteral",
    "http://www.w3.org/2002/07/owl#real",
    "http://www.w3.org/2002/07/owl#rational",
}


def _namespace_of(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[0] + "#"
    if "/" in uri:
        return uri.rsplit("/", 1)[0] + "/"
    return uri


def _local_name(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[1]
    if "/" in uri:
        return uri.rstrip("/").rsplit("/", 1)[1]
    return uri


def _is_external(uri: str) -> bool:
    return any(uri.startswith(ns) for ns in EXTERNAL_NAMESPACES)


def _ontology_namespaces(graph: Graph) -> set[str]:
    return {
        _namespace_of(str(subject))
        for subject in graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    }


def _primary_category(types: set[URIRef]) -> str:
    """Reduce a term's declared rdf:type values to a single primary category.

    Punning (e.g. a term that is both a class and an individual) is resolved by
    priority: the more specific schema role wins.
    """
    if types & _CLASS_TYPES:
        return CLASS
    if OWL.ObjectProperty in types:
        return OBJECT_PROPERTY
    if OWL.DatatypeProperty in types:
        return DATATYPE_PROPERTY
    if OWL.AnnotationProperty in types:
        return ANNOTATION_PROPERTY
    if RDFS.Datatype in types:
        return DATATYPE
    if types & _GENERIC_PROPERTY_TYPES:
        return PROPERTY
    if OWL.NamedIndividual in types:
        return NAMED_INDIVIDUAL
    if types:
        # Typed as an instance of some (non-meta) class.
        return NAMED_INDIVIDUAL
    return UNTYPED


def _classify_internal_terms(graph: Graph) -> dict[str, str]:
    """Map each internal term URI to its primary category.

    An internal term is any URIRef in the ontology's own namespace that is a
    subject of at least one triple (i.e. it is defined here). The ontology IRI
    itself is excluded.
    """
    ontology_iris = {
        str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)
    }
    ontology_namespaces = _ontology_namespaces(graph)

    def _is_internal(uri: str) -> bool:
        if uri in ontology_iris:
            return False
        if ontology_namespaces:
            # The ontology's own namespace wins, even when it is a well-known
            # vocabulary (e.g. validating FOAF itself). The external allowlist
            # only matters as a fallback when there is no owl:Ontology.
            return any(uri.startswith(ns) for ns in ontology_namespaces)
        return not _is_external(uri)

    result: dict[str, str] = {}
    for subject in set(graph.subjects()):
        if not isinstance(subject, URIRef):
            continue
        uri = str(subject)
        if not _is_internal(uri):
            continue
        types = set(graph.objects(subject, RDF.type))
        result[uri] = _primary_category(types)
    return result


def check_term_inventory(graph: Graph) -> TermInventoryReport:
    """Categorize the ontology's own terms and check naming conventions."""
    if not _ontology_namespaces(graph):
        return TermInventoryReport(status=Status.SKIP, message="no owl:Ontology declaration found")

    classified = _classify_internal_terms(graph)
    if not classified:
        return TermInventoryReport(
            status=Status.SKIP,
            message="no terms are defined in the ontology's own namespace",
        )

    naming_violations: dict[str, str] = {
        result.focus_node: result.message
        for result in run_shapes(graph, _SHAPES_FILE)
        if result.name in ("ClassNaming", "PropertyNaming")
    }

    entries: list[InternalTermEntry] = []
    counts: dict[str, int] = {}
    for uri, category in sorted(classified.items()):
        local = _local_name(uri)
        marker = deprecation_marker(graph, URIRef(uri))
        naming_message = None if marker else naming_violations.get(uri)
        entries.append(
            InternalTermEntry(
                term=uri,
                display_name=local,
                category=category,
                naming_ok=naming_message is None,
                naming_message=naming_message,
                deprecated=marker,
            )
        )
        counts[category] = counts.get(category, 0) + 1

    ordered_counts = {c: counts[c] for c in CATEGORY_ORDER if c in counts}
    naming_issues = [e for e in entries if not e.naming_ok]

    return TermInventoryReport(
        total_terms=len(entries),
        category_counts=ordered_counts,
        entries=entries,
        status=Status.FAIL if naming_issues else Status.OK,
    )


def _is_class_value(graph: Graph, value: URIRef) -> bool:
    if value in (OWL.Thing, OWL.Nothing):
        return True
    types = set(graph.objects(value, RDF.type))
    return bool(types & _CLASS_TYPES)


def check_domains_ranges(graph: Graph) -> DomainRangeReport:
    """Check that object and datatype properties have sound domains and ranges.

    Only direct ``rdfs:domain`` / ``rdfs:range`` triples are considered;
    domains and ranges inherited via super-properties or inference are not
    followed, consistent with the rest of askwol.
    """
    if not _ontology_namespaces(graph):
        return DomainRangeReport(status=Status.SKIP, message="no owl:Ontology declaration found")

    classified = _classify_internal_terms(graph)
    properties = {
        uri: cat
        for uri, cat in classified.items()
        if cat in (OBJECT_PROPERTY, DATATYPE_PROPERTY)
    }
    if not properties:
        return DomainRangeReport(
            status=Status.SKIP,
            message="no object or datatype properties are defined in the ontology's own namespace",
        )

    violations: dict[str, dict[str, str]] = {}
    for result in run_shapes(graph, _SHAPES_FILE):
        if result.name in (
            "DomainMissing", "RangeMissing", "DomainIsDatatype",
            "ObjectPropertyRangeIsDatatype", "DatatypePropertyRangeIsClass",
        ):
            violations.setdefault(result.focus_node, {})[result.name] = result.message

    checks: list[DomainRangeCheck] = []
    object_count = 0
    datatype_count = 0

    for uri, category in sorted(properties.items()):
        subject = URIRef(uri)
        has_domain = any(True for _ in graph.objects(subject, RDFS.domain))
        has_range = any(True for _ in graph.objects(subject, RDFS.range))

        if category == OBJECT_PROPERTY:
            object_count += 1
        else:
            datatype_count += 1

        node_violations = violations.get(uri, {})
        marker = deprecation_marker(graph, subject)
        problems = [
            node_violations[name]
            for name in ("DomainIsDatatype", "ObjectPropertyRangeIsDatatype", "DatatypePropertyRangeIsClass")
            if name in node_violations
        ]
        missing = [node_violations[name] for name in ("DomainMissing", "RangeMissing") if name in node_violations]

        if marker:
            status = Status.OK
            message = "Deprecated; domain and range are not checked."
        elif problems:
            status = Status.FAIL
            message = " ".join(problems)
        elif missing:
            status = Status.WARN
            message = " ".join(missing)
        else:
            status = Status.OK
            message = "Domain and range declared."

        checks.append(
            DomainRangeCheck(
                term=uri,
                display_name=_local_name(uri),
                category=category,
                has_domain=has_domain,
                has_range=has_range,
                status=status,
                message=message,
                deprecated=marker,
            )
        )

    if any(c.status == Status.FAIL for c in checks):
        overall = Status.FAIL
    elif any(c.status == Status.WARN for c in checks):
        overall = Status.WARN
    else:
        overall = Status.OK

    return DomainRangeReport(
        total_properties=len(checks),
        object_properties=object_count,
        datatype_properties=datatype_count,
        checks=checks,
        status=overall,
    )


def _datatype_recognized(graph: Graph, uri: str) -> bool:
    if uri.startswith(str(XSD)):
        return _local_name(uri) in XSD_BUILTIN_TYPES
    if uri in _OTHER_DATATYPES:
        return True
    if (URIRef(uri), RDF.type, RDFS.Datatype) in graph:
        return True
    return False


def check_datatypes(graph: Graph) -> DatatypeReport:
    """Inventory the datatypes used and flag any that are not recognized.

    Datatypes are gathered from the ranges of datatype properties, from the
    datatypes of typed literals, and from local ``rdfs:Datatype`` declarations.
    """
    if not _ontology_namespaces(graph):
        return DatatypeReport(status=Status.SKIP, message="no owl:Ontology declaration found")

    # datatype uri -> (count, set of sources)
    usage: dict[str, tuple[int, set[str]]] = {}

    def _record(uri: str, source: str) -> None:
        count, sources = usage.get(uri, (0, set()))
        usage[uri] = (count + 1, sources | {source})

    classified = _classify_internal_terms(graph)
    datatype_props = {
        URIRef(uri)
        for uri, cat in classified.items()
        if cat == DATATYPE_PROPERTY
    }

    # 1. Ranges of datatype properties. A range that is actually a class is a
    #    domain/range problem, not a datatype; leave it to that check.
    for prop in datatype_props:
        for rng in graph.objects(prop, RDFS.range):
            if isinstance(rng, URIRef) and not _is_class_value(graph, rng):
                _record(str(rng), "range")

    # 2. Datatypes of typed literals.
    for _s, _p, obj in graph:
        if isinstance(obj, Literal) and obj.datatype is not None:
            _record(str(obj.datatype), "literal")

    # 3. Locally declared custom datatypes.
    for subject in graph.subjects(RDF.type, RDFS.Datatype):
        if isinstance(subject, URIRef):
            _record(str(subject), "declared")

    if not usage:
        return DatatypeReport(
            status=Status.SKIP,
            message="no datatypes are used in the ontology",
        )

    usages: list[DatatypeUsage] = []
    for uri in sorted(usage):
        count, sources = usage[uri]
        recognized = _datatype_recognized(graph, uri)
        usages.append(
            DatatypeUsage(
                datatype=uri,
                display_name=_local_name(uri),
                count=count,
                sources=sorted(sources),
                recognized=recognized,
                status=Status.OK if recognized else Status.FAIL,
                message=None if recognized else "Not a recognized datatype (possible typo).",
            )
        )

    unrecognized = [u for u in usages if not u.recognized]
    return DatatypeReport(
        total_datatypes=len(usages),
        usages=usages,
        status=Status.FAIL if unrecognized else Status.OK,
    )
