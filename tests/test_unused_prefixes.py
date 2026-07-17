"""Tests for the unused prefix detection logic.

The logic itself lives inline in `web.py`: a prefix is considered unused
when it appears in `parsed.declared_prefixes` (literally `@prefix` in the
file, excluding rdflib's built-in defaults) but not in `parsed.namespaces`
(which the parser populates only with namespaces that show up in a triple).

These tests exercise that contract end to end through the parser using
temporary Turtle files, so they catch regressions in either the parser or
the unused-prefix heuristic. Note: prefixes that rdflib registers by
default (`owl`, `rdfs`, `foaf`, `dcterms`, ...) are intentionally not
flagged because the parser cannot tell them apart from the user's `@prefix`
declarations once parsing is done.
"""

from pathlib import Path


from askwol.parser import parse_ontology


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ont.ttl"
    p.write_text(content)
    return p


def _unused(parsed) -> set[str]:
    return set(parsed.declared_prefixes) - set(parsed.namespaces)


def test_all_prefixes_used(tmp_path):
    parsed = parse_ontology(_write(tmp_path, """\
@prefix : <https://w3id.org/ex/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<https://w3id.org/ex/> a owl:Ontology .
:A a owl:Class ; rdfs:label "A" .
"""))
    assert _unused(parsed) == set()


def test_one_unused_prefix(tmp_path):
    parsed = parse_ontology(_write(tmp_path, """\
@prefix : <https://w3id.org/ex/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix myvocab: <http://example.org/myvocab#> .

<https://w3id.org/ex/> a owl:Ontology .
:A a owl:Class .
"""))
    unused = _unused(parsed)
    assert "myvocab" in unused
    assert "owl" not in unused


def test_multiple_unused_prefixes(tmp_path):
    parsed = parse_ontology(_write(tmp_path, """\
@prefix : <https://w3id.org/ex/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix myvocab: <http://example.org/myvocab#> .
@prefix yourvocab: <http://example.org/yourvocab#> .

<https://w3id.org/ex/> a owl:Ontology .
:A a owl:Class .
"""))
    assert _unused(parsed) >= {"myvocab", "yourvocab"}


def test_prefix_used_only_in_predicate_is_counted_as_used(tmp_path):
    parsed = parse_ontology(_write(tmp_path, """\
@prefix : <https://w3id.org/ex/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<https://w3id.org/ex/> a owl:Ontology .
:A a owl:Class ; rdfs:comment "rdfs is used as a predicate" .
"""))
    assert "rdfs" not in _unused(parsed)
