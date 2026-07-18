"""Tests for language tag consistency checking."""

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from askwol.lang_tags import check_lang_tags
from askwol.models import Status

EX = Namespace("http://example.org/")


def _make_ns_map():
    return {"ex": str(EX), "rdfs": str(RDFS), "skos": str(SKOS)}


def test_consistent_tags_no_issues():
    """All subjects use the same language set — no issues, status OK."""
    g = Graph()
    g.add((EX.A, RDF.type, OWL.Class))
    g.add((EX.A, RDFS.label, Literal("A", lang="en")))
    g.add((EX.A, RDFS.label, Literal("A-nl", lang="nl")))
    g.add((EX.B, RDF.type, OWL.Class))
    g.add((EX.B, RDFS.label, Literal("B", lang="en")))
    g.add((EX.B, RDFS.label, Literal("B-nl", lang="nl")))

    report = check_lang_tags(g, _make_ns_map())
    assert report.languages_used == ["en", "nl"]
    assert report.issues == []
    assert report.status == Status.OK


def test_missing_tag_detected():
    """One subject has an untagged label when others use tags."""
    g = Graph()
    g.add((EX.A, RDFS.label, Literal("A", lang="en")))
    g.add((EX.B, RDFS.label, Literal("B")))  # no tag

    report = check_lang_tags(g, _make_ns_map())
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.issue_type == "missing_tag"
    assert "ex:B" == issue.subject
    assert report.status == Status.WARN


def test_missing_language_detected():
    """Subject has @en but missing @nl when other subjects have both."""
    g = Graph()
    g.add((EX.A, RDFS.label, Literal("A-en", lang="en")))
    g.add((EX.A, RDFS.label, Literal("A-nl", lang="nl")))
    g.add((EX.B, RDFS.label, Literal("B-en", lang="en")))
    # B is missing @nl

    report = check_lang_tags(g, _make_ns_map())
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.issue_type == "missing_language"
    assert "nl" in issue.detail


def test_no_tags_at_all_is_warn():
    """Labels are present but none carry a language tag: no itemized
    per-subject issues (nothing inconsistent to point at), but the overall
    status is WARN since language tags are recommended whenever labels are
    used at all."""
    g = Graph()
    g.add((EX.A, RDFS.label, Literal("A")))
    g.add((EX.B, RDFS.label, Literal("B")))

    report = check_lang_tags(g, _make_ns_map())
    assert report.issues == []
    assert report.languages_used == []
    assert report.status == Status.WARN


def test_no_labels_at_all_is_skip():
    """No labels/comments/etc. anywhere: nothing to check, status stays SKIP."""
    g = Graph()
    g.add((EX.A, RDF.type, OWL.Class))

    report = check_lang_tags(g, _make_ns_map())
    assert report.properties_checked == 0
    assert report.issues == []
    assert report.status == Status.SKIP


def test_deprecated_subject_is_exempt():
    """A deprecated subject's untagged or inconsistent labels are ignored,
    and don't affect what's expected of the still-active subjects."""
    g = Graph()
    g.add((EX.A, RDFS.label, Literal("A", lang="en")))
    g.add((EX.A, RDFS.label, Literal("A-nl", lang="nl")))
    g.add((EX.Old, RDF.type, OWL.Class))
    g.add((EX.Old, OWL.deprecated, Literal(True)))
    g.add((EX.Old, RDFS.label, Literal("old label")))  # untagged; would normally fail

    report = check_lang_tags(g, _make_ns_map())
    assert report.issues == []


def test_skos_definition_checked():
    """skos:definition is among the checked properties."""
    g = Graph()
    g.add((EX.A, SKOS.definition, Literal("Def A", lang="en")))
    g.add((EX.B, SKOS.definition, Literal("Def B")))  # no tag

    report = check_lang_tags(g, _make_ns_map())
    assert len(report.issues) == 1
    assert report.issues[0].property == "skos:definition"


def test_non_label_properties_ignored():
    """Properties not in the checked set are ignored."""
    g = Graph()
    custom = URIRef("http://example.org/customProp")
    g.add((EX.A, custom, Literal("value", lang="en")))
    g.add((EX.B, custom, Literal("value")))  # no tag

    report = check_lang_tags(g, _make_ns_map())
    assert report.issues == []


def test_multiple_properties_independent():
    """Each property is checked independently."""
    g = Graph()
    # rdfs:label — consistent
    g.add((EX.A, RDFS.label, Literal("A", lang="en")))
    g.add((EX.B, RDFS.label, Literal("B", lang="en")))
    # skos:definition — inconsistent
    g.add((EX.A, SKOS.definition, Literal("Def A", lang="en")))
    g.add((EX.B, SKOS.definition, Literal("Def B")))

    report = check_lang_tags(g, _make_ns_map())
    assert len(report.issues) == 1
    assert report.issues[0].property == "skos:definition"
