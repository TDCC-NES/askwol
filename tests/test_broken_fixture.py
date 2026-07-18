"""Pin the broken example: every check should fire on html/ontologies/broken.ttl.

This is a smoke test on top of the per-module unit tests. If any single check
ever silently stops detecting issues, this file will fail loudly because the
example is hand-crafted to trip *every* check at once.
"""

from pathlib import Path

import pytest
from rdflib import Graph

from askwol.cache import OntologyCache
from askwol.definition_docs import check_definition_documentation
from askwol.imports_check import check_imports
from askwol.internal_terms import check_internal_terms
from askwol.iri_scheme import check_iri_scheme
from askwol.iri_strategy import check_iri_strategy
from askwol.lang_tags import check_lang_tags
from askwol.metadata_validator import validate_ontology_metadata
from askwol.models import Status
from askwol.parser import parse_ontology
from askwol.reasoner_checks import run_reasoner_checks
from askwol.non_ontology_terms import check_non_ontology_terms
from askwol.term_inventory import (
    check_datatypes,
    check_domains_ranges,
    check_term_inventory,
)
from askwol.term_validator import validate_terms

BROKEN = Path(__file__).resolve().parent.parent / "html" / "ontologies" / "broken.ttl"


@pytest.fixture(scope="module")
def parsed():
    return parse_ontology(BROKEN)


@pytest.fixture
def foaf_stub():
    """A small stand-in FOAF graph (real terms, no MadeUpConcept).

    Lets tests validate against a namespace with the same shape as the real
    FOAF vocabulary without depending on it being reachable over the network.
    """
    g = Graph()
    g.parse(
        data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <http://xmlns.com/foaf/0.1/Agent> a owl:Class .
        <http://xmlns.com/foaf/0.1/Person> a owl:Class .
        """,
        format="turtle",
    )
    return g


def test_parses_cleanly(parsed):
    assert parsed.graph is not None


def test_unused_prefix_detected(parsed):
    unused = set(parsed.declared_prefixes) - set(parsed.namespaces)
    assert "neverused" in unused


def test_metadata_has_failures_and_warnings(parsed):
    meta = validate_ontology_metadata(parsed.graph)
    assert meta.failed_checks >= 1
    assert meta.warning_checks >= 1


def test_definition_docs_has_issues(parsed):
    docs = check_definition_documentation(parsed.graph)
    assert docs.issues, "expected at least one undocumented internal definition"


@pytest.mark.asyncio
async def test_imports_check_fails_on_broken_import(parsed):
    # The declared owl:imports target is on the reserved nonexistent.invalid
    # host (RFC 2606), so it can never resolve.
    imp = await check_imports(parsed.graph, OntologyCache())
    assert imp.status == Status.FAIL
    assert len(imp.broken) == 1
    assert imp.broken[0].iri == "http://nonexistent.invalid/broken-import/"


def test_internal_terms_flags_undefined_predicate(parsed):
    it = check_internal_terms(parsed.graph)
    assert it.status == Status.FAIL
    undefined = {i.display_name for i in it.undefined}
    assert "hasNickname" in undefined


def test_external_terms_flags_hijacked_foaf_term(parsed, foaf_stub):
    # foaf:MadeUpConcept is asserted as a class in broken.ttl but is not a
    # real FOAF term. Seed the cache with a stand-in FOAF graph so this stays
    # network-free and deterministic.
    assert "foaf" in parsed.terms_by_namespace
    assert "MadeUpConcept" in parsed.terms_by_namespace["foaf"]

    cache = OntologyCache()
    cache.put("http://xmlns.com/foaf/0.1/", foaf_stub)

    results = validate_terms(
        "foaf", "http://xmlns.com/foaf/0.1/", parsed.terms_by_namespace["foaf"], cache,
    )
    by_name = {r.local_name: r for r in results}
    assert by_name["MadeUpConcept"].status == Status.FAIL


def test_iri_strategy_warns_on_mixed(parsed):
    iri = check_iri_strategy(parsed.graph)
    assert iri.status == Status.WARN
    assert iri.strategy == "mixed"


def test_iri_scheme_warns_on_mixed_host(parsed):
    sch = check_iri_scheme(parsed.graph, parsed.namespaces)
    assert sch.status == Status.WARN
    hosts = {c.host for c in sch.conflicts}
    assert "w3id.org" in hosts


def test_lang_tags_has_issue(parsed):
    lt = check_lang_tags(parsed.graph, parsed.namespaces)
    assert lt.issues, "expected a missing-tag issue on Person"


def test_reasoner_detects_inconsistency(parsed):
    r = run_reasoner_checks(parsed.graph)
    assert r.consistent is False
    assert r.inconsistent_individuals, "expected Alice to be flagged"
    assert any(cls.endswith("ImpossiblePerson") for cls in r.unsatisfiable_classes), (
        "expected ImpossiblePerson to be flagged as unsatisfiable"
    )


def test_non_ontology_terms_warns(parsed):
    report = check_non_ontology_terms(parsed.graph)
    assert report.status == Status.WARN
    flagged = {t.display_name for t in report.terms}
    # A SKOS concept and named individuals defined in the ontology's own namespace.
    assert "Biology" in flagged
    assert "alice" in flagged
    assert "bob" in flagged


def test_term_inventory_flags_naming(parsed):
    inv = check_term_inventory(parsed.graph)
    assert inv.status == Status.FAIL
    flagged = {e.display_name for e in inv.naming_issues}
    assert "badFormat" in flagged
    assert "HasOwner" in flagged


def test_domains_ranges_has_problems(parsed):
    dr = check_domains_ranges(parsed.graph)
    assert dr.status == Status.FAIL
    flagged = {c.display_name for c in dr.issues}
    assert "worksFor" in flagged
    assert "hasLabelText" in flagged
    assert "relatedTo" in flagged


def test_datatypes_flags_unrecognized(parsed):
    dt = check_datatypes(parsed.graph)
    assert dt.status == Status.FAIL
    flagged = {u.display_name for u in dt.unrecognized}
    assert "flaot" in flagged
    assert "stirng" in flagged


@pytest.mark.asyncio
async def test_cli_pipeline_populates_every_check(monkeypatch, foaf_stub):
    """Regression guard: the CLI must actually run all 16 checks.

    cli.py's _run_check() used to never call check_iri_strategy,
    check_iri_scheme, or check_non_ontology_terms, so those three checks
    silently never ran from the CLI even though web.py wired them up
    correctly and the report renderer had a row ready for them. This pins
    the full pipeline, not just the individual modules.

    The ontology's own w3id.org namespaces and the real foaf: vocabulary are
    pre-seeded into the cache so this stays network-free, matching the
    fixture's other tests. The nonexistent.invalid host (RFC 2606) is left
    to resolve for real, since it fails via DNS instantly and needs no
    external service to be up.
    """
    cache = OntologyCache()
    cache.put("http://xmlns.com/foaf/0.1/", foaf_stub)
    cache.put("http://w3id.org/askwol/broken/", None, error="404 - not found")
    cache.put("http://w3id.org/askwol/broken#", None, error="404 - not found")
    monkeypatch.setattr("askwol.cli.OntologyCache", lambda: cache)

    from askwol.cli import _run_check

    report = await _run_check(BROKEN, timeout=10.0, skip_resolution=False)

    assert report.ontology_metadata is not None and report.ontology_metadata.failed_checks
    assert report.imports is not None and report.imports.status == Status.FAIL
    assert report.iri_strategy is not None and report.iri_strategy.status == Status.WARN
    assert report.iri_scheme is not None and report.iri_scheme.status == Status.WARN
    assert report.unused_prefixes
    assert report.non_ontology_terms is not None and report.non_ontology_terms.status == Status.WARN
    assert report.internal_terms is not None and report.internal_terms.status == Status.FAIL
    assert report.term_inventory is not None and report.term_inventory.status == Status.FAIL
    assert report.domains_ranges is not None and report.domains_ranges.status == Status.FAIL
    assert report.datatypes is not None and report.datatypes.status == Status.FAIL
    assert report.definition_docs is not None and report.definition_docs.issues
    assert report.lang_tags is not None and report.lang_tags.issues
    assert report.reasoner is not None and report.reasoner.consistent is False
    assert report.reasoner.unsatisfiable_classes, "expected ImpossiblePerson to be flagged as unsatisfiable"
    assert report.namespaces
    foaf_ns = next(n for n in report.namespaces if n.prefix == "foaf")
    assert foaf_ns.resolution.status == Status.OK
    madeup = next(t for t in foaf_ns.terms if t.local_name == "MadeUpConcept")
    assert madeup.status == Status.FAIL
