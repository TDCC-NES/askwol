"""SHACL optimizations stay local and do not retain stale graph results."""

from rdflib import Graph, Literal, Namespace, RDF, RDFS
from rdflib.query import Processor

from askwol.definition_docs import check_definition_documentation
from askwol.shacl_runner import _CachedQueryGraph

EX = Namespace("https://example.org/ont#")


def test_graph_bound_prefixes_work_after_importing_askwol_checkers():
    graph = Graph()
    graph.bind("example", EX)
    graph.add((EX.Term, RDF.type, EX.Class))
    assert list(graph.query("SELECT ?s WHERE { ?s a example:Class }")) == [(EX.Term,)]


def test_owned_query_cache_uses_bound_namespaces_and_honours_custom_processor():
    graph = _CachedQueryGraph()
    graph.bind("example", EX)
    graph.add((EX.Term, RDF.type, EX.Class))
    query = "SELECT ?s WHERE { ?s a example:Class }"
    assert list(graph.query(query)) == [(EX.Term,)]

    class CustomProcessor(Processor):
        def query(self, query_object, *_args, **_kwargs):
            assert query_object == query
            return {"type_": "ASK", "askAnswer": True}

    assert bool(graph.query(query, processor=CustomProcessor(graph)))


def test_rechecking_mutated_graph_refreshes_shacl_results():
    graph = Graph().parse(data="""
        @prefix ex: <https://example.org/ont#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        ex: a owl:Ontology .
        ex:Term a owl:Class .
    """, format="turtle")
    first = check_definition_documentation(graph)
    assert first.issues
    graph.add((EX.Term, RDFS.label, Literal("Term")))
    graph.add((EX.Term, RDFS.comment, Literal("A term.")))
    second = check_definition_documentation(graph)
    assert second.issues == []
