"""Shared helper for running askwol's SHACL shapes with pyshacl.

Centralizes the pyshacl invocation (``advanced=True`` is required because the
shapes use custom SPARQL targets and SPARQL-based constraints) and turns the
SHACL validation report graph into a small list of `ShaclResult` objects that
each check module folds into its own report model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyshacl import validate
from rdflib import Graph
from rdflib.namespace import Namespace, RDF

from askwol.models import Status

SH = Namespace("http://www.w3.org/ns/shacl#")
SHAPES_DIR = Path(__file__).resolve().parent / "shapes"

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


def run_shapes(data_graph: Graph, shapes_file: str) -> list[ShaclResult]:
    """Validate `data_graph` against `askwol/shapes/{shapes_file}`.

    Returns every `sh:ValidationResult` (any severity); callers decide how to
    fold each one into their own report model.
    """
    shapes_graph = Graph()
    shapes_graph.parse(str(SHAPES_DIR / shapes_file), format="turtle")

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
    return results


def load_shape_messages(shapes_file: str) -> dict[str, str]:
    """Return {sh:name: sh:message} for every named shape in a shapes file.

    Useful as fallback text when a shape's target selects no focus nodes at
    all (e.g. no owl:Ontology declaration exists), so pyshacl has nothing to
    attach a validation result to even though the check conceptually applies.
    """
    shapes_graph = Graph()
    shapes_graph.parse(str(SHAPES_DIR / shapes_file), format="turtle")
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
    shapes_graph = Graph()
    shapes_graph.parse(str(SHAPES_DIR / shapes_file), format="turtle")
    target = next(shapes_graph.subjects(RDF.type, SH.SPARQLTarget), None)
    if target is None:
        return set()
    select = shapes_graph.value(target, SH.select)
    if select is None:
        return set()
    return {str(row[0]) for row in data_graph.query(str(select)) if row[0] is not None}
