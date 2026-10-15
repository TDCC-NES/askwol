"""Unused namespace bindings, independent of vocabulary-term extraction."""

from pathlib import Path

import pytest

from askwol.parser import parse_ontology
from askwol.pipeline import run_full_validation


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ont.ttl"
    p.write_text(content)
    return p


def _unused(parsed) -> set[str]:
    return set(parsed.declared_prefixes) - parsed.used_prefixes


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


@pytest.mark.parametrize('triples', [
    'used:ontology a owl:Ontology .',
    '<urn:ontology> owl:imports used:ontology .',
    '<urn:term> <urn:value> "value"^^used:datatype .',
    '<https://example.org/used/Term> a owl:Class .',
])
@pytest.mark.asyncio
async def test_namespace_usage_includes_headers_datatypes_and_aliases(tmp_path, triples):
    path = _write(tmp_path, '''
@prefix used: <https://example.org/used/> .
@prefix alias: <https://example.org/used/> .
@prefix unused: <https://example.org/unused/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
''' + triples)
    report, _ = await run_full_validation(path, skip_resolution=True, include_mermaid=False)
    assert {item.prefix for item in report.unused_prefixes} == {'unused'}
