"""Tests for ontology parser."""

from pathlib import Path
from xml.sax import SAXParseException

import pytest
from defusedxml.common import ExternalReferenceForbidden
from rdflib import OWL, RDF, URIRef

from askwol import pipeline
from askwol.parser import parse_ontology
from askwol.pipeline import run_full_validation

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "html" / "ontologies"


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ont.ttl"
    p.write_text(content)
    return p


def _write_rdfxml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ont.rdf"
    p.write_text(content)
    return p


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


def test_relative_self_reference_resolves_against_base_uri(tmp_path):
    """A ``<#>``/``<>`` self-declaration must resolve against the ontology's
    real published URL, not the local temp file it happens to be read from.

    This is exactly what happens when askwol fetches an ontology by URL: the
    content is downloaded to a temp file first, then parsed. Real-world
    ontologies (e.g. the W3C PROV family bundle) use relative self-references
    like this, relying on the caller to supply the correct base."""
    path = _write(tmp_path, """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<#> a owl:Ontology .
<#Term> a owl:Class ; rdfs:label "Term" .
""")
    parsed = parse_ontology(path, base_uri="https://example.org/ns/thing#")
    ontology_iris = {
        str(s) for s in parsed.graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(s, URIRef)
    }
    assert ontology_iris == {"https://example.org/ns/thing#"}
    assert not any(uri.startswith("file://") for uri in ontology_iris)


def test_without_base_uri_relative_self_reference_falls_back_to_file_uri(tmp_path):
    """Without an explicit base_uri (the file-upload case), relative IRIs
    fall back to rdflib's default: the temp file's own file:// path. There is
    no better option here since an uploaded file has no published URL."""
    path = _write(tmp_path, """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .

<#> a owl:Ontology .
""")
    parsed = parse_ontology(path)
    ontology_iris = {
        str(s) for s in parsed.graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(s, URIRef)
    }
    assert len(ontology_iris) == 1
    assert next(iter(ontology_iris)).startswith("file://")


def test_dcterms_replaces_does_not_create_phantom_namespace(tmp_path):
    """Real-world case: GeoSPARQL 1.1's header has
    ``dcterms:replaces <http://www.opengis.net/ont/geosparql/1.0>``, pointing
    at its own prior version. Without exempting dcterms:replaces, rdflib
    would split that IRI into namespace .../geosparql/ plus phantom local
    name "1.0", surfacing a bogus namespace and term in the report."""
    path = _write(tmp_path, """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

<http://example.org/ont> a owl:Ontology ;
    dcterms:replaces <http://example.org/ont/1.0> .
<http://example.org/ont#Term> a owl:Class .
""")
    parsed = parse_ontology(path)
    assert not any(uri == "http://example.org/ont/" for uri in parsed.namespaces.values())
    assert "1.0" not in {t for terms in parsed.terms_by_namespace.values() for t in terms}


def test_rdfxml_internal_entities_are_allowed(tmp_path):
    """Real-world RDF/XML ontologies (e.g. the W3C Wine ontology) commonly
    declare simple internal DTD entities as string macros for namespace
    URIs. These must parse successfully - forbidding all entities as a side
    effect of blocking the "billion laughs" DoS would break a large class of
    otherwise perfectly valid ontology files."""
    path = _write_rdfxml(tmp_path, """\
<?xml version="1.0"?>
<!DOCTYPE rdf:RDF [
   <!ENTITY ex "http://example.org/ont#">
]>
<rdf:RDF
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:owl="http://www.w3.org/2002/07/owl#">
  <owl:Ontology rdf:about="&ex;"/>
  <owl:Class rdf:about="&ex;Thing"/>
</rdf:RDF>
""")
    parsed = parse_ontology(path)
    classes = {str(s) for s in parsed.graph.subjects(RDF.type, OWL.Class)}
    assert "http://example.org/ont#Thing" in classes


def test_rdfxml_billion_laughs_is_still_blocked(tmp_path):
    """Entity *expansion* bombs must still be rejected even though simple
    internal entities are now allowed - expat's own amplification-factor
    limit (independent of defusedxml's forbid_entities flag) catches this."""
    path = _write_rdfxml(tmp_path, """\
<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
 <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
 <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
 <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
 <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
 <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<lolz>&lol9;</lolz>
""")
    with pytest.raises(SAXParseException, match="amplification"):
        parse_ontology(path)


def test_rdfxml_external_entity_is_still_blocked(tmp_path):
    """XXE (reading external/local resources via a SYSTEM entity) must still
    be rejected - only internal entity *declarations* were relaxed."""
    path = _write_rdfxml(tmp_path, """\
<?xml version="1.0"?>
<!DOCTYPE rdf:RDF [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
  <rdf:Description rdf:about="http://example.org/foo">
    <rdfs:comment>&xxe;</rdfs:comment>
  </rdf:Description>
</rdf:RDF>
""")
    with pytest.raises(ExternalReferenceForbidden):
        parse_ontology(path)


def test_undeclared_namespace_is_registered_once(tmp_path):
    path = _write(tmp_path, """
<https://example.org/unknown#One> a <http://www.w3.org/2002/07/owl#Class> .
<https://example.org/unknown#Two> a <http://www.w3.org/2002/07/owl#Class> .
<https://example.org/unknown#Three> a <http://www.w3.org/2002/07/owl#Class> .
""")
    parsed = parse_ontology(path)
    prefixes = [pfx for pfx, uri in parsed.namespaces.items() if uri == "https://example.org/unknown#"]
    assert len(prefixes) == 1
    assert parsed.terms_by_namespace[prefixes[0]] == {"One", "Two", "Three"}


def test_explicit_format_reads_turtle_in_an_owl_file(tmp_path):
    path = tmp_path / "ontology.owl"
    path.write_text('<https://example.org/Thing> a <http://www.w3.org/2002/07/owl#Class> .')
    parsed = parse_ontology(path, format="turtle")
    assert len(parsed.graph) == 1


@pytest.mark.parametrize("term", [
    '<file:///example/Thing> <https://example.org/property> "value" .',
    '<https://example.org/Thing> <file:///example/property> "value" .',
    '<https://example.org/Thing> <https://example.org/property> <file:///example/value> .',
    '<https://example.org/Thing> <https://example.org/property> "value"^^<file:///example/datatype> .',
])
async def test_local_identifiers_are_explained_without_adding_findings(tmp_path, term):
    path = _write(tmp_path, term)
    report, _ = await run_full_validation(path, skip_resolution=True, include_mermaid=False)
    assert report.input_error is None
    assert report.parse_errors == []
    assert len(report.input_warnings) == 1
    assert "file://" in report.input_warnings[0]
    assert "base_uri" in report.input_warnings[0]
    assert not any(f.message == report.input_warnings[0] for f in report.findings())


async def test_explicit_base_removes_temporary_identifiers_without_changing_absolute_iris(tmp_path):
    path = _write(tmp_path, '''@prefix owl: <http://www.w3.org/2002/07/owl#> .
<> a owl:Ontology . <#Thing> a owl:Class .
<https://other.example/Term> a owl:Class .''')
    report, _ = await run_full_validation(
        path, base_uri="https://example.org/ontology", skip_resolution=True, include_mermaid=False,
    )
    assert report.input_warnings == []
    parsed = parse_ontology(path, base_uri="https://example.org/ontology")
    assert URIRef("https://other.example/Term") in set(parsed.graph.subjects())


async def test_pipeline_missing_file_is_an_io_error(tmp_path):
    report, _ = await run_full_validation(tmp_path / "missing.ttl", skip_resolution=True)
    assert report.input_error.code == "io_error"
    assert report.parse_errors == [report.input_error.message]
    assert report.has_errors


async def test_pipeline_normalizes_empty_timeout_and_propagates_timeout(monkeypatch):
    import httpx

    def timeout(source, **kwargs):
        assert kwargs["timeout"] == 1.25
        assert kwargs["format"] == "turtle"
        raise httpx.ReadTimeout("")

    monkeypatch.setattr(pipeline, "parse_ontology", timeout)
    report, _ = await run_full_validation("ontology.unknown", timeout=1.25, format="turtle")
    assert report.input_error.code == "fetch_timeout"
    assert "timed out" in report.input_error.message
    assert report.parse_errors == [report.input_error.message]
    assert report.ontology_metadata is None


async def test_pipeline_preserves_syntax_failure_with_actionable_format_hint(tmp_path):
    path = _write(tmp_path, "this is not RDF <<<")
    report, _ = await run_full_validation(path, skip_resolution=True)
    assert report.input_error.code == "invalid_rdf"
    assert "input format" in report.input_error.guidance
    assert report.parse_errors == [report.input_error.message]


async def test_pipeline_graph_limit_has_distinct_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_TRIPLES", 1)
    path = _write(tmp_path, '<https://example.org/a> <https://example.org/p> "one", "two" .')
    report, _ = await run_full_validation(path, skip_resolution=True)
    assert report.input_error.code == "resource_limit"
    assert report.parse_errors == [report.input_error.message]
    assert report.ontology_metadata is None


