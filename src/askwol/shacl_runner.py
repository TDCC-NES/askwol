"""Shared helper for running askwol's SHACL shapes with pyshacl.

Centralizes the pyshacl invocation (``advanced=True`` is required because the
shapes use custom SPARQL targets and SPARQL-based constraints) and turns the
SHACL validation report graph into a small list of `ShaclResult` objects that
each check module folds into its own report model.

Also patches `rdflib.Graph.query` to cache prepared SPARQL queries (see
`_cached_query` below) - profiling showed pyshacl's SPARQL-based targets and
constraints spend ~90% of their time re-parsing the same static query text
from the shapes files on every focus node, not evaluating it.
"""

from __future__ import annotations

import functools
import weakref
from dataclasses import dataclass
from pathlib import Path

from pyshacl import validate
from rdflib import Graph
from rdflib.namespace import Namespace, RDF
from rdflib.plugins.sparql import prepareQuery

from askwol.models import Status

SH = Namespace("http://www.w3.org/ns/shacl#")

_orig_graph_query = Graph.query


@functools.lru_cache(maxsize=256)
def _prepare(query_text: str, init_ns_items: tuple | None, base: str | None):
    init_ns = dict(init_ns_items) if init_ns_items else None
    return prepareQuery(query_text, initNs=init_ns, base=base)


def _cached_query(
    self,
    query_object,
    processor="sparql",
    result="sparql",
    initNs=None,
    initBindings=None,
    use_store_provided=True,
    **kwargs,
):
    """Reuse a prepared SPARQL query instead of re-parsing it on every call.

    Mirrors ``rdflib.Graph.query``'s exact positional signature - pyshacl
    (0.40+) calls it positionally via its ``DataGraph`` wrapper, not just
    by keyword, so this must accept the same parameters in the same order
    or callers passing them positionally break.

    pyshacl calls ``graph.query(text, initBindings=...)`` once per focus
    node, with the same small set of query templates from the static shapes
    files each time - only the focus node changes, via initBindings. The
    query TEXT is a fixed, bounded set (it comes from our own shape files,
    never from ontology data), so caching prepared queries by
    (text, initNs, base) is safe and removes the repeat parse cost entirely;
    results are unaffected since initBindings/the data graph still flow
    through untouched.
    """
    if isinstance(query_object, str):
        base = kwargs.get("base")
        init_ns_items = tuple(sorted(initNs.items())) if initNs else None
        query_object = _prepare(query_object, init_ns_items, base)
        initNs = None
    return _orig_graph_query(
        self, query_object, processor=processor, result=result,
        initNs=initNs, initBindings=initBindings,
        use_store_provided=use_store_provided, **kwargs,
    )


Graph.query = _cached_query
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


_SEVERITY_STATUS = {
    str(SH.Violation): Status.FAIL,
    str(SH.Warning): Status.WARN,
    str(SH.Info): Status.OK,
}


@dataclass(frozen=True)
class ShaclResult:
    """One `sh:ValidationResult`, folded into askwol's own vocabulary."""

    focus_node: str
    name: str | None  # sh:name of the violated shape, when the shape sets one
    path: str | None  # sh:resultPath, when the violated constraint has one
    status: Status  # derived from sh:resultSeverity
    message: str


# Per-data-graph cache of run_shapes() results, keyed by shapes_file. Some
# check modules validate the same shapes file twice against the same graph
# for different shapes within it (e.g. term_inventory.ttl holds both naming
# and domain/range shapes, checked by two separate public functions) -
# without this, that reruns the full pyshacl.validate() pipeline twice.
# WeakKeyDictionary keys on the graph's identity and auto-evicts the entry
# once the graph is garbage collected (each validation request builds its
# own fresh graph), so there is no cross-request leakage or manual cache
# management needed.
_shapes_results_cache: "weakref.WeakKeyDictionary[Graph, dict[str, list[ShaclResult]]]" = weakref.WeakKeyDictionary()


def run_shapes(data_graph: Graph, shapes_file: str) -> list[ShaclResult]:
    """Validate `data_graph` against `askwol/shapes/{shapes_file}`.

    Returns every `sh:ValidationResult` (any severity); callers decide how to
    fold each one into their own report model.
    """
    cached_for_graph = _shapes_results_cache.get(data_graph)
    if cached_for_graph is not None and shapes_file in cached_for_graph:
        return list(cached_for_graph[shapes_file])

    shapes_graph = _load_shapes_graph(shapes_file)

    _conforms, results_graph, _text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        advanced=True,
        inference=None,
        allow_warnings=True,
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
                status=_SEVERITY_STATUS.get(str(severity), Status.FAIL),
                message=str(message) if message is not None else "",
            )
        )
    _shapes_results_cache.setdefault(data_graph, {})[shapes_file] = results
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
    return {str(row[0]) for row in data_graph.query(str(select)) if row[0] is not None}
