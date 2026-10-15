"""The broken example must exercise every check through the shared pipeline."""

from pathlib import Path

import pytest
from rdflib import Graph

from askwol.cache import OntologyCache
from askwol.models import Status
from askwol.pipeline import run_full_validation

BROKEN = Path(__file__).resolve().parent.parent / "html" / "ontologies" / "broken.ttl"


@pytest.fixture
def cache():
    """Resolve the fixture's vocabularies without network access."""
    foaf = Graph().parse(data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <http://xmlns.com/foaf/0.1/Agent> a owl:Class .
        <http://xmlns.com/foaf/0.1/Person> a owl:Class .
    """, format="turtle")
    cache = OntologyCache()
    cache.put("http://xmlns.com/foaf/0.1/", foaf)
    for uri in (
        "http://w3id.org/askwol/broken/",
        "http://w3id.org/askwol/broken#",
        "http://nonexistent.invalid/broken-import/",
    ):
        cache.put(uri, None, error="404 - not found")
    return cache


@pytest.mark.parametrize("skip_resolution", [False, True])
async def test_broken_example_populates_every_check(cache, skip_resolution):
    report, _ = await run_full_validation(
        BROKEN, include_mermaid=False, skip_resolution=skip_resolution, cache=cache,
    )

    assert report.ontology_metadata is not None
    assert {c.tier for c in report.ontology_metadata.missing} == {"core", "additional"}
    assert report.license is not None and report.license.status == Status.FAIL
    assert "neverused" in {p.prefix for p in report.unused_prefixes}

    assert report.iri_strategy is not None and report.iri_strategy.status == Status.WARN
    assert any(ns.strategy == "mixed" for ns in report.iri_strategy.namespaces)
    assert report.iri_scheme is not None and report.iri_scheme.status == Status.WARN
    assert "w3id.org/askwol/broken/" in {c.host for c in report.iri_scheme.conflicts}

    assert report.internal_terms is not None and report.internal_terms.status == Status.FAIL
    assert "hasNickname" in {i.display_name for i in report.internal_terms.undefined}
    assert report.term_inventory is not None and report.term_inventory.status == Status.WARN
    assert {"badFormat", "HasOwner"} <= {i.display_name for i in report.term_inventory.naming_issues}
    assert report.domains_ranges is not None and report.domains_ranges.status == Status.FAIL
    assert {"worksFor", "hasLabelText", "relatedTo"} <= {i.display_name for i in report.domains_ranges.issues}
    assert report.datatypes is not None and report.datatypes.status == Status.FAIL
    assert {"flaot", "stirng"} <= {i.display_name for i in report.datatypes.unrecognised}
    assert report.definition_docs is not None and report.definition_docs.issues
    assert report.lang_tags is not None and report.lang_tags.issues

    assert report.non_ontology_terms is not None and report.non_ontology_terms.status == Status.WARN
    flagged = {t.display_name for t in report.non_ontology_terms.terms}
    assert "Biology" in flagged
    assert not {"alice", "bob"} & flagged

    assert report.reasoner is not None and report.reasoner.consistent is False
    assert report.reasoner.inconsistent_individuals
    assert any(cls.endswith("ImpossiblePerson") for cls in report.reasoner.unsatisfiable_classes)

    assert report.imports is not None
    assert report.namespaces
    if skip_resolution:
        assert report.imports.skipped
        assert report.imports.broken == []
        assert all(ns.resolution.status == Status.SKIP for ns in report.namespaces)
        assert all(ns.terms == [] for ns in report.namespaces)
    else:
        assert report.imports.status == Status.FAIL
        assert [c.iri for c in report.imports.broken] == ["http://nonexistent.invalid/broken-import/"]
        foaf = next(ns for ns in report.namespaces if ns.prefix == "foaf")
        assert foaf.resolution.status == Status.OK
        madeup = next(t for t in foaf.terms if t.local_name == "MadeUpConcept")
        assert madeup.status == Status.FAIL
