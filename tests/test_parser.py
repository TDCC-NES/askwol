"""Tests for ontology parser."""

from pathlib import Path

from askwol.parser import parse_ontology

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "examples"


def test_parse_sample_ttl():
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    assert "owl" in parsed.namespaces
    assert "rdf" in parsed.namespaces
    assert parsed.namespaces["owl"] == "http://www.w3.org/2002/07/owl#"


def test_extracts_terms_by_namespace():
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    # The default namespace holds the ontology's own defined terms.
    # Find the prefix that maps to the ontology's own namespace
    test_prefix = None
    for pfx, uri in parsed.namespaces.items():
        if uri == "https://lod-4tu.tudelft.nl/dataset#":
            test_prefix = pfx
            break
    assert test_prefix is not None
    terms = parsed.terms_by_namespace[test_prefix]
    assert "Dataset" in terms
    assert "supersedes" in terms
    assert "sizeInBytes" in terms


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


def test_imports_in_sample():
    parsed = parse_ontology(FIXTURE_DIR / "sample.ttl")
    assert parsed.imports == ["http://www.w3.org/ns/dcat"]
