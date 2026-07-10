"""Tests for the SKOS concepts check."""

from rdflib import Graph

from askwol.models import Status
from askwol.skos_concepts import check_skos_concepts

BASE = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <https://example.org/ont#> .

<https://example.org/ont> a owl:Ontology .
"""


def _graph(ttl: str) -> Graph:
    g = Graph()
    g.parse(data=ttl, format="turtle")
    return g


def test_internal_skos_concept_is_flagged():
    g = _graph(BASE + "ex:biology a skos:Concept .\n")
    report = check_skos_concepts(g)
    assert report.status == Status.WARN
    assert report.total_concepts == 1
    assert [c.display_name for c in report.internal_concepts] == ["biology"]


def test_external_skos_concept_is_not_flagged():
    ttl = BASE + (
        "@prefix other: <https://vocab.example.com/scheme#> .\n"
        "ex:Dataset a owl:Class ;\n"
        "    rdfs:label \"Dataset\"@en .\n"
        "ex:Dataset skos:related other:biology .\n"
        "other:biology a skos:Concept .\n"
    )
    report = check_skos_concepts(_graph(ttl))
    assert report.status == Status.OK
    assert report.internal_concepts == []


def test_multiple_internal_concepts_are_all_flagged():
    g = _graph(BASE + "ex:biology a skos:Concept .\nex:chemistry a skos:Concept .\n")
    report = check_skos_concepts(g)
    assert report.status == Status.WARN
    assert {c.display_name for c in report.internal_concepts} == {"biology", "chemistry"}


def test_no_ontology_declaration_skips():
    g = _graph(
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
        "@prefix ex: <https://example.org/ont#> .\n"
        "ex:biology a skos:Concept .\n"
    )
    report = check_skos_concepts(g)
    assert report.status == Status.SKIP
    assert report.internal_concepts == []
