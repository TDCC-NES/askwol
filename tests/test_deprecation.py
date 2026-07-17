"""Tests for the shared deprecation-marker detection helper."""

from rdflib import Graph, URIRef

from askwol.deprecation import deprecation_marker, is_deprecated

EX = "https://example.org/ont#"


def _graph(ttl: str) -> Graph:
    g = Graph()
    g.parse(
        data=(
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
            "@prefix vs: <http://www.w3.org/2003/06/sw-vocab-status/ns#> .\n"
            "@prefix ex: <https://example.org/ont#> .\n" + ttl
        ),
        format="turtle",
    )
    return g


def test_no_marker_returns_none():
    g = _graph("ex:Current a owl:Class .\n")
    assert deprecation_marker(g, URIRef(EX + "Current")) is None
    assert is_deprecated(g, URIRef(EX + "Current")) is False


def test_owl_deprecated_true_is_detected():
    g = _graph('ex:OldClass owl:deprecated "true"^^xsd:boolean .\n')
    term = URIRef(EX + "OldClass")
    assert deprecation_marker(g, term) == "owl:deprecated"
    assert is_deprecated(g, term) is True


def test_owl_deprecated_false_is_not_detected():
    g = _graph('ex:Current owl:deprecated "false"^^xsd:boolean .\n')
    assert deprecation_marker(g, URIRef(EX + "Current")) is None


def test_owl_deprecated_class_type_is_detected():
    g = _graph("ex:OldClass a owl:DeprecatedClass .\n")
    assert deprecation_marker(g, URIRef(EX + "OldClass")) == "owl:DeprecatedClass"


def test_owl_deprecated_property_type_is_detected():
    g = _graph("ex:oldProp a owl:DeprecatedProperty .\n")
    assert deprecation_marker(g, URIRef(EX + "oldProp")) == "owl:DeprecatedProperty"


def test_vs_term_status_deprecated_is_detected():
    g = _graph('ex:legacyName vs:term_status "deprecated" .\n')
    assert deprecation_marker(g, URIRef(EX + "legacyName")) == 'vs:term_status "deprecated"'


def test_vs_term_status_archaic_is_detected():
    g = _graph('ex:geekcode vs:term_status "archaic" .\n')
    assert deprecation_marker(g, URIRef(EX + "geekcode")) == 'vs:term_status "archaic"'


def test_vs_term_status_stable_is_not_flagged():
    g = _graph('ex:currentName vs:term_status "stable" .\n')
    assert deprecation_marker(g, URIRef(EX + "currentName")) is None
    assert is_deprecated(g, URIRef(EX + "currentName")) is False


def test_term_not_in_graph_is_not_flagged():
    g = _graph("ex:Something a owl:Class .\n")
    assert deprecation_marker(g, URIRef(EX + "NotPresent")) is None
