"""Tests for term inventory, domains/ranges, and datatype checks."""

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS, XSD

from askwol.models import Status
from askwol.term_inventory import (
    check_datatypes,
    check_domains_ranges,
    check_term_inventory,
)

EX = Namespace("https://example.org/ont#")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")


def _base_graph() -> Graph:
    g = Graph()
    g.add((EX["ontology"], RDF.type, OWL.Ontology))
    return g


# ---------------------------------------------------------------------------
# Term inventory + naming
# ---------------------------------------------------------------------------

def test_inventory_categorizes_terms():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["hasParent"], RDF.type, OWL.ObjectProperty))
    g.add((EX["birthDate"], RDF.type, OWL.DatatypeProperty))
    g.add((EX["note"], RDF.type, OWL.AnnotationProperty))
    g.add((EX["alice"], RDF.type, EX["Person"]))

    report = check_term_inventory(g)

    assert report.status == Status.OK
    assert report.total_terms == 5
    cats = {e.display_name: e.category for e in report.entries}
    assert cats["Person"] == "Class"
    assert cats["hasParent"] == "Object property"
    assert cats["birthDate"] == "Datatype property"
    assert cats["note"] == "Annotation property"
    assert cats["alice"] == "Named individual"
    assert report.category_counts["Class"] == 1


def test_inventory_flags_lowercase_class():
    g = _base_graph()
    g.add((EX["person"], RDF.type, OWL.Class))

    report = check_term_inventory(g)

    assert report.status == Status.FAIL
    issues = report.naming_issues
    assert len(issues) == 1
    assert issues[0].display_name == "person"
    assert "uppercase" in issues[0].naming_message


def test_inventory_flags_uppercase_property():
    g = _base_graph()
    g.add((EX["HasName"], RDF.type, OWL.ObjectProperty))

    report = check_term_inventory(g)

    assert report.status == Status.FAIL
    assert report.naming_issues[0].display_name == "HasName"
    assert "lowercase" in report.naming_issues[0].naming_message


def test_inventory_exempts_coded_identifier_properties():
    """CIDOC CRM (P2_has_type) and Wikidata (P19) style numbered property
    identifiers are a deliberate, established convention, not a naming
    mistake, so an uppercase letter directly followed by a digit is exempt."""
    g = _base_graph()
    g.add((EX["P2_has_type"], RDF.type, OWL.ObjectProperty))
    g.add((EX["P19"], RDF.type, OWL.ObjectProperty))
    g.add((EX["P1i_identifies"], RDF.type, OWL.ObjectProperty))

    report = check_term_inventory(g)

    assert report.status == Status.OK
    assert report.naming_issues == []


def test_inventory_naming_ok_for_well_named_terms():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["hasName"], RDF.type, OWL.DatatypeProperty))

    report = check_term_inventory(g)

    assert report.status == Status.OK
    assert report.naming_issues == []


def test_inventory_ignores_external_terms():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["Person"], RDFS.subClassOf, FOAF["Agent"]))

    report = check_term_inventory(g)

    assert all("foaf" not in e.term for e in report.entries)


def test_inventory_skips_without_ontology():
    g = Graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    assert check_term_inventory(g).status == Status.SKIP


def test_own_namespace_that_is_a_wellknown_vocab_is_internal():
    # Validating a well-known vocabulary (here FOAF) must treat its own terms as
    # internal, even though FOAF is in askwol's external allowlist.
    FOAF = Namespace("http://xmlns.com/foaf/0.1/")
    g = Graph()
    g.add((FOAF[""], RDF.type, OWL.Ontology))
    g.add((FOAF["Person"], RDF.type, OWL.Class))
    g.add((FOAF["knows"], RDF.type, OWL.ObjectProperty))

    report = check_term_inventory(g)

    assert report.status == Status.OK
    assert report.total_terms == 2
    names = {e.display_name for e in report.entries}
    assert {"Person", "knows"} <= names


def test_inventory_handles_punning_class_and_individual():
    g = _base_graph()
    # Father is both a class and an individual (metaclass punning).
    g.add((EX["Father"], RDF.type, OWL.Class))
    g.add((EX["Father"], RDF.type, EX["SocialRole"]))
    g.add((EX["SocialRole"], RDF.type, OWL.Class))

    report = check_term_inventory(g)

    cats = {e.display_name: e.category for e in report.entries}
    # Class role wins over the individual role.
    assert cats["Father"] == "Class"


# ---------------------------------------------------------------------------
# Domains and ranges
# ---------------------------------------------------------------------------

def test_domain_range_ok():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["hasParent"], RDF.type, OWL.ObjectProperty))
    g.add((EX["hasParent"], RDFS.domain, EX["Person"]))
    g.add((EX["hasParent"], RDFS.range, EX["Person"]))
    g.add((EX["age"], RDF.type, OWL.DatatypeProperty))
    g.add((EX["age"], RDFS.domain, EX["Person"]))
    g.add((EX["age"], RDFS.range, XSD.integer))

    report = check_domains_ranges(g)

    assert report.status == Status.OK
    assert report.total_properties == 2
    assert report.object_properties == 1
    assert report.datatype_properties == 1
    assert report.issues == []


def test_object_property_ranging_over_datatype_fails():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["worksFor"], RDF.type, OWL.ObjectProperty))
    g.add((EX["worksFor"], RDFS.domain, EX["Person"]))
    g.add((EX["worksFor"], RDFS.range, XSD.string))

    report = check_domains_ranges(g)

    assert report.status == Status.FAIL
    issue = report.issues[0]
    assert issue.display_name == "worksFor"
    assert issue.status == Status.FAIL


def test_datatype_property_ranging_over_class_fails():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    g.add((EX["hasLabelText"], RDF.type, OWL.DatatypeProperty))
    g.add((EX["hasLabelText"], RDFS.domain, EX["Person"]))
    g.add((EX["hasLabelText"], RDFS.range, EX["Person"]))

    report = check_domains_ranges(g)

    assert report.status == Status.FAIL
    assert report.issues[0].display_name == "hasLabelText"


def test_missing_domain_and_range_warns():
    g = _base_graph()
    g.add((EX["relatedTo"], RDF.type, OWL.ObjectProperty))

    report = check_domains_ranges(g)

    assert report.status == Status.WARN
    check = report.checks[0]
    assert check.status == Status.WARN
    assert not check.has_domain
    assert not check.has_range


def test_domain_range_skips_without_properties():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    assert check_domains_ranges(g).status == Status.SKIP


# ---------------------------------------------------------------------------
# Datatypes
# ---------------------------------------------------------------------------

def test_datatypes_recognized():
    g = _base_graph()
    g.add((EX["age"], RDF.type, OWL.DatatypeProperty))
    g.add((EX["age"], RDFS.range, XSD.nonNegativeInteger))
    g.add((EX["alice"], EX["age"], Literal(30)))

    report = check_datatypes(g)

    assert report.status == Status.OK
    names = {u.display_name for u in report.usages}
    assert "nonNegativeInteger" in names or "integer" in names
    assert report.unrecognized == []


def test_datatypes_flags_misspelled_range():
    g = _base_graph()
    g.add((EX["age"], RDF.type, OWL.DatatypeProperty))
    g.add((EX["age"], RDFS.range, XSD["stirng"]))

    report = check_datatypes(g)

    assert report.status == Status.FAIL
    assert any(u.display_name == "stirng" for u in report.unrecognized)


def test_datatypes_flags_misspelled_literal_datatype():
    g = _base_graph()
    g.add((EX["born"], RDF.type, OWL.DatatypeProperty))
    g.add((EX["alice"], EX["born"], Literal("2000", datatype=XSD["dat"])))

    report = check_datatypes(g)

    assert report.status == Status.FAIL
    assert any(u.display_name == "dat" for u in report.unrecognized)


def test_datatypes_recognizes_custom_datatype():
    g = _base_graph()
    g.add((EX["personAge"], RDF.type, RDFS.Datatype))
    g.add((EX["age"], RDF.type, OWL.DatatypeProperty))
    g.add((EX["age"], RDFS.range, EX["personAge"]))

    report = check_datatypes(g)

    assert report.status == Status.OK
    assert any(u.display_name == "personAge" and u.recognized for u in report.usages)


def test_datatypes_skips_when_none_used():
    g = _base_graph()
    g.add((EX["Person"], RDF.type, OWL.Class))
    assert check_datatypes(g).status == Status.SKIP
