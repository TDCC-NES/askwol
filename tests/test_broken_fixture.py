"""Pin the broken example: every check should fire on html/ontologies/broken.ttl.

This is a smoke test on top of the per-module unit tests. If any single check
ever silently stops detecting issues, this file will fail loudly because the
example is hand-crafted to trip *every* check at once.
"""

from pathlib import Path

import pytest

from askwol.cache import OntologyCache
from askwol.definition_docs import check_definition_documentation
from askwol.imports_check import check_imports
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

BROKEN = Path(__file__).resolve().parent.parent / "html" / "ontologies" / "broken.ttl"


@pytest.fixture(scope="module")
def parsed():
    return parse_ontology(BROKEN)


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
async def test_imports_check_runs(parsed):
    imp = await check_imports(parsed.graph, OntologyCache())
    assert imp.status in (Status.OK, Status.FAIL)


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
