"""Tests for ontology parser."""

from pathlib import Path

from askwol.parser import parse_ontology

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_sample_ttl():
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    assert "owl" in parsed.namespaces
    assert "rdf" in parsed.namespaces
    assert parsed.namespaces["owl"] == "http://www.w3.org/2002/07/owl#"


def test_extracts_terms_by_namespace():
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    # The default namespace has our custom terms
    # Find the prefix that maps to https://w3id.org/test/
    test_prefix = None
    for pfx, uri in parsed.namespaces.items():
        if uri == "https://w3id.org/test/":
            test_prefix = pfx
            break
    assert test_prefix is not None
    terms = parsed.terms_by_namespace[test_prefix]
    assert "MyClass" in terms
    assert "myProperty" in terms
    assert "myInstance" in terms


def test_extracts_owl_terms():
    """owl:Class etc. are only in object position, not subjects — should not appear as terms."""
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    owl_terms = parsed.terms_by_namespace.get("owl", set())
    # owl: terms are used as types/objects, not defined as subjects
    assert "Class" not in owl_terms
    assert "ObjectProperty" not in owl_terms
    assert "Ontology" not in owl_terms


def test_extracts_rdf_terms():
    """rdf:type is a predicate, not a subject — should not appear as a term."""
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    rdf_terms = parsed.terms_by_namespace.get("rdf", set())
    assert "type" not in rdf_terms


def test_no_imports_in_sample():
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    assert parsed.imports == []
