"""Tests for the non-ontology-terms check (flags skos:Concept only)."""

from rdflib import Graph

from askwol.models import Status
from askwol.non_ontology_terms import check_non_ontology_terms

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
    report = check_non_ontology_terms(g)
    assert report.status == Status.WARN
    assert report.total_flagged == 1
    issue = report.terms[0]
    assert issue.display_name == "biology"
    assert issue.type_label == "SKOS concept"


def test_named_individual_is_not_flagged():
    g = _graph(BASE + "ex:Person a owl:Class .\nex:alice a ex:Person .\n")
    report = check_non_ontology_terms(g)
    assert report.status == Status.OK
    assert report.terms == []


def test_controlled_vocabulary_individuals_are_not_flagged():
    """Regression test: OWL-Time-style enumerations (days of week, time
    units) defined as named individuals alongside their schema should not be
    flagged, even though there are several of them under the same class."""
    ttl = (
        BASE
        + "ex:DayOfWeek a owl:Class .\n"
        + "ex:Monday a ex:DayOfWeek .\n"
        + "ex:Tuesday a ex:DayOfWeek .\n"
        + "ex:Wednesday a ex:DayOfWeek .\n"
    )
    report = check_non_ontology_terms(_graph(ttl))
    assert report.status == Status.OK
    assert report.terms == []


def test_classes_and_properties_are_not_flagged():
    g = _graph(
        BASE
        + "ex:Person a owl:Class .\n"
        + "ex:knows a owl:ObjectProperty .\n"
        + "ex:age a owl:DatatypeProperty .\n"
        + "ex:personAge a rdfs:Datatype .\n"
    )
    report = check_non_ontology_terms(g)
    assert report.status == Status.OK
    assert report.terms == []


def test_punned_class_and_individual_is_not_flagged():
    g = _graph(
        BASE
        + "ex:SocialRole a owl:Class .\n"
        + "ex:Father a owl:Class ;\n    a ex:SocialRole .\n"
    )
    report = check_non_ontology_terms(g)
    # Father is also an individual of SocialRole, but it carries owl:Class, so
    # it is a legitimate schema term.
    assert all(t.display_name != "Father" for t in report.terms)


def test_external_skos_concept_is_not_flagged():
    ttl = BASE + (
        "@prefix other: <https://vocab.example.com/scheme#> .\n"
        "ex:Dataset a owl:Class ;\n"
        "    rdfs:label \"Dataset\"@en .\n"
        "ex:Dataset skos:related other:biology .\n"
        "other:biology a skos:Concept .\n"
    )
    report = check_non_ontology_terms(_graph(ttl))
    assert report.status == Status.OK
    assert report.terms == []


def test_multiple_non_ontology_terms_are_all_flagged():
    g = _graph(BASE + "ex:biology a skos:Concept .\nex:chemistry a skos:Concept .\n")
    report = check_non_ontology_terms(g)
    assert report.status == Status.WARN
    assert {t.display_name for t in report.terms} == {"biology", "chemistry"}


def test_no_ontology_declaration_skips():
    g = _graph(
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
        "@prefix ex: <https://example.org/ont#> .\n"
        "ex:biology a skos:Concept .\n"
    )
    report = check_non_ontology_terms(g)
    assert report.status == Status.SKIP
