"""Shared helper for running askwol's SHACL shapes with pyshacl.

Centralizes the pyshacl invocation (``advanced=True`` is required because the
shapes use custom SPARQL targets and SPARQL-based constraints) and turns the
SHACL validation report graph into a small list of `ShaclResult` objects that
each check module folds into its own report model.

An owned graph subclass caches prepared SPARQL queries during validation -
profiling showed pyshacl's SPARQL-based targets and
constraints spend ~90% of their time re-parsing the same static query text
from the shapes files on every focus node, not evaluating it.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from pyshacl import validate
from rdflib import Graph
from rdflib.namespace import Namespace, RDF
from rdflib.plugins.sparql import prepareQuery

from askwol.models import Status
from askwol.severity import Severity
SH = Namespace("http://www.w3.org/ns/shacl#")

@functools.lru_cache(maxsize=256)
def _prepare(query_text: str, init_ns_items: tuple | None, base: str | None):
    init_ns = dict(init_ns_items) if init_ns_items else None
    return prepareQuery(query_text, initNs=init_ns, base=base)


class _CachedQueryGraph(Graph):
    """Cache only queries on askwol's own in-memory validation copy."""

    def query(
        self, query_object, processor="sparql", result="sparql", initNs=None,
        initBindings=None, use_store_provided=True, **kwargs,
    ):
        if isinstance(query_object, str) and processor == "sparql":
            namespaces = initNs or dict(self.namespaces())
            query_object = _prepare(query_object, tuple(sorted(namespaces.items())), kwargs.get("base"))
        return super().query(
            query_object, processor, result, initNs, initBindings, use_store_provided, **kwargs,
        )


def _validation_graph(data_graph: Graph) -> _CachedQueryGraph:
    graph = _CachedQueryGraph()
    for prefix, namespace in data_graph.namespaces():
        graph.bind(prefix, namespace, override=True, replace=True)
    for triple in data_graph:
        graph.add(triple)
    return graph


SHAPES_DIR = Path(__file__).resolve().parent / "shapes"


@functools.lru_cache(maxsize=None)
def _load_shapes_graph(shapes_file: str) -> Graph:
    """Parse a shapes file once and reuse it for the process lifetime.

    Shape files are static, read-only content bundled with the package -
    they never change at runtime - and pyshacl only reads the shapes graph
    it's given, it never mutates it, so sharing one parsed Graph across
    calls is safe (verified against the full test suite before relying on
    it in production).
    """
    g = Graph()
    g.parse(str(SHAPES_DIR / shapes_file), format="turtle")
    return g


_SEVERITY_LEVELS = {
    str(SH.Violation): Severity.ERROR,
    str(SH.Warning): Severity.WARNING,
    str(SH.Info): Severity.RECOMMENDATION,
}

# What a result means for the legacy per-item ``Status``: only a violation is
# a FAIL; anything softer (warning or info) is a WARN.
_SEVERITY_STATUS = {
    Severity.ERROR: Status.FAIL,
    Severity.WARNING: Status.WARN,
    Severity.RECOMMENDATION: Status.WARN,
}


@dataclass(frozen=True)
class ShaclResult:
    """One `sh:ValidationResult`, folded into askwol's own vocabulary."""

    focus_node: str
    name: str | None  # sh:name of the violated shape, when the shape sets one
    path: str | None  # sh:resultPath, when the violated constraint has one
    severity: Severity  # derived from sh:resultSeverity
    message: str

    @property
    def status(self) -> Status:
        return _SEVERITY_STATUS[self.severity]


# The pipeline's graph is immutable during its local checks. Independent
# public checker calls may modify/reuse a graph, so they must not share results.
_shapes_results_cache: ContextVar[dict | None] = ContextVar("shapes_results_cache", default=None)


@contextmanager
def shape_result_cache():
    token = _shapes_results_cache.set({})
    try:
        yield
    finally:
        _shapes_results_cache.reset(token)


def run_shapes(data_graph: Graph, shapes_file: str) -> list[ShaclResult]:
    """Validate `data_graph` against `askwol/shapes/{shapes_file}`.

    Returns every `sh:ValidationResult` (any severity); callers decide how to
    fold each one into their own report model.
    """
    cache = _shapes_results_cache.get()
    cache_key = (data_graph, shapes_file)
    if cache is not None and cache_key in cache:
        return list(cache[cache_key])

    shapes_graph = _load_shapes_graph(shapes_file)

    _conforms, results_graph, _text = validate(
        _validation_graph(data_graph),
        shacl_graph=shapes_graph,
        advanced=True,
        inference=None,
        allow_warnings=True,
        inplace=True,
    )

    results: list[ShaclResult] = []
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        focus = results_graph.value(result, SH.focusNode)
        if focus is None:
            continue
        # sh:name is looked up from the shapes graph (results don't carry it
        # directly). For a SPARQL-based constraint (sh:sparql), sh:sourceShape
        # is the *enclosing* shape, and the constraint's own annotations (like
        # a custom sh:name) live on sh:sourceConstraint instead, so that is
        # tried first.
        source_constraint = results_graph.value(result, SH.sourceConstraint)
        name = shapes_graph.value(source_constraint, SH.name) if source_constraint is not None else None
        if name is None:
            source_shape = results_graph.value(result, SH.sourceShape)
            name = shapes_graph.value(source_shape, SH.name) if source_shape is not None else None
        path = results_graph.value(result, SH.resultPath)
        severity = results_graph.value(result, SH.resultSeverity)
        message = results_graph.value(result, SH.resultMessage)
        results.append(
            ShaclResult(
                focus_node=str(focus),
                name=str(name) if name is not None else None,
                path=str(path) if path is not None else None,
                severity=_SEVERITY_LEVELS.get(str(severity), Severity.ERROR),
                message=str(message) if message is not None else "",
            )
        )
    if cache is not None:
        cache[cache_key] = results
    return list(results)


def load_shape_messages(shapes_file: str) -> dict[str, str]:
    """Return {sh:name: sh:message} for every named shape in a shapes file.

    Useful as fallback text when a shape's target selects no focus nodes at
    all (e.g. no owl:Ontology declaration exists), so pyshacl has nothing to
    attach a validation result to even though the check conceptually applies.
    """
    shapes_graph = _load_shapes_graph(shapes_file)
    messages: dict[str, str] = {}
    for shape in shapes_graph.subjects(SH.name, None):
        name = shapes_graph.value(shape, SH.name)
        message = shapes_graph.value(shape, SH.message)
        if name is not None and message is not None:
            messages.setdefault(str(name), str(message))
    return messages


def run_target(data_graph: Graph, shapes_file: str) -> set[str]:
    """Execute a shapes file's `sh:SPARQLTarget` directly and return every
    matched focus node.

    Useful when a caller needs the *full* set of nodes a shape targets (for
    totals/counts), not just the ones that violate its constraints.
    """
    shapes_graph = _load_shapes_graph(shapes_file)
    target = next(shapes_graph.subjects(RDF.type, SH.SPARQLTarget), None)
    if target is None:
        return set()
    select = shapes_graph.value(target, SH.select)
    if select is None:
        return set()
    return {str(row[0]) for row in _validation_graph(data_graph).query(str(select)) if row[0] is not None}
