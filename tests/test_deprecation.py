"""Tests for the shared deprecation-marker detection helper."""

import pytest
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


@pytest.mark.parametrize(
    "ttl, term_name, expected_marker",
    [
        ('ex:OldClass owl:deprecated "true"^^xsd:boolean .\n', "OldClass", "owl:deprecated"),
        ("ex:OldClass a owl:DeprecatedClass .\n", "OldClass", "owl:DeprecatedClass"),
        ("ex:oldProp a owl:DeprecatedProperty .\n", "oldProp", "owl:DeprecatedProperty"),
        ('ex:legacyName vs:term_status "deprecated" .\n', "legacyName", 'vs:term_status "deprecated"'),
        ('ex:geekcode vs:term_status "archaic" .\n', "geekcode", 'vs:term_status "archaic"'),
    ],
)
def test_deprecation_marker_detected(ttl, term_name, expected_marker):
    g = _graph(ttl)
    term = URIRef(EX + term_name)
    assert deprecation_marker(g, term) == expected_marker
    assert is_deprecated(g, term) is True


@pytest.mark.parametrize(
    "ttl, term_name",
    [
        ("ex:Current a owl:Class .\n", "Current"),
        ('ex:Current owl:deprecated "false"^^xsd:boolean .\n', "Current"),
        ('ex:currentName vs:term_status "stable" .\n', "currentName"),
    ],
)
def test_deprecation_marker_not_detected(ttl, term_name):
    g = _graph(ttl)
    term = URIRef(EX + term_name)
    assert deprecation_marker(g, term) is None
    assert is_deprecated(g, term) is False


def test_term_not_in_graph_is_not_flagged():
    g = _graph("ex:Something a owl:Class .\n")
    assert deprecation_marker(g, URIRef(EX + "NotPresent")) is None
