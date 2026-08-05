"""Tests for the open licence check."""

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, SDO

from askwol.license_check import check_license
from askwol.models import Status

ONT = URIRef("https://example.org/ont")


def test_no_license_declared_fails():
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    report = check_license(g)
    assert report.status == Status.FAIL
    assert report.checks == []


@pytest.mark.parametrize("license_iri", [
    "https://creativecommons.org/publicdomain/zero/1.0/",
    "https://creativecommons.org/licenses/by/4.0/",
])
def test_recommended_license_is_ok(license_iri):
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef(license_iri)))
    report = check_license(g)
    assert report.status == Status.OK
    assert len(report.checks) == 1
    check = report.checks[0]
    assert check.is_recommended is True
    assert check.is_open is True
    assert check.status == Status.OK


def test_open_but_not_recommended_license_warns():
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by-sa/4.0/")))
    report = check_license(g)
    assert report.status == Status.WARN
    check = report.checks[0]
    assert check.is_open is True
    assert check.is_recommended is False
    assert check.status == Status.WARN


@pytest.mark.parametrize("license_iri", [
    "https://creativecommons.org/licenses/by/4.0/legalcode",
    "https://creativecommons.org/licenses/by/4.0/legalcode.en",
    "https://creativecommons.org/licenses/by/4.0/deed.en",
    "https://creativecommons.org/licenses/by/3.0/",
    "https://creativecommons.org/licenses/by/3.0/legalcode",
    "https://creativecommons.org/licenses/by/2.5/",
    "https://creativecommons.org/publicdomain/zero/1.0/legalcode",
])
def test_cc_url_variants_and_older_versions_are_recommended(license_iri):
    """Creative Commons licences are versioned and each version has more than
    one equivalent URL (short deed link, full /legalcode text, translated
    /legalcode.xx or /deed.xx). Found via the real CiTO ontology, which cites
    the /legalcode URL directly - that was not recognised at all before."""
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef(license_iri)))
    report = check_license(g)
    assert report.status == Status.OK, license_iri
    check = report.checks[0]
    assert check.is_recommended is True
    assert check.is_open is True


@pytest.mark.parametrize("license_iri", [
    "https://creativecommons.org/licenses/by-sa/3.0/legalcode",
    "https://creativecommons.org/licenses/by-sa/2.0/deed.en",
])
def test_cc_url_variants_of_a_non_recommended_family_still_only_warn(license_iri):
    """Normalising away the version and /legalcode or /deed suffix must not
    blur different CC licence families together - only CC-BY and CC0 are
    recommended, CC-BY-SA (any version or URL form) stays open-but-warn."""
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef(license_iri)))
    report = check_license(g)
    assert report.status == Status.WARN, license_iri
    check = report.checks[0]
    assert check.is_open is True
    assert check.is_recommended is False


def test_rejected_license_fails():
    """CC-BY-NC-4.0 is explicitly rejected by the Open Definition and must not
    be treated as open just because it appears in the license register."""
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by-nc/4.0/")))
    report = check_license(g)
    assert report.status == Status.FAIL
    check = report.checks[0]
    assert check.is_open is False
    assert check.is_recommended is False
    assert check.status == Status.FAIL


@pytest.mark.parametrize("license_iri", [
    "http://opendatacommons.org/licenses/pddl/1.0/",
    "http://opendatacommons.org/licenses/by/1.0/",
    "http://opendatacommons.org/licenses/odbl/1.0/",
])
def test_odc_real_world_url_recognized_as_open(license_iri):
    """licenses.json points PDDL/ODC-By/ODbL's `url` at an opendefinition.org
    registry page, but ontologies (and Open Data Commons' own instructions)
    cite the opendatacommons.org form. That real-world form must still be
    recognised as open."""
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef(license_iri)))
    report = check_license(g)
    assert report.status == Status.WARN
    assert report.checks[0].is_open is True


def test_multiple_recommended_licenses_warn():
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef("https://creativecommons.org/publicdomain/zero/1.0/")))
    g.add((ONT, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by/4.0/")))
    report = check_license(g)
    assert report.status == Status.WARN
    assert len(report.checks) == 2
    assert all(c.is_recommended for c in report.checks)


def test_rdflicense_prefix_is_known_open():
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, URIRef("http://purl.org/NET/rdflicense/cc-by3.0")))
    report = check_license(g)
    assert report.status == Status.WARN
    check = report.checks[0]
    assert check.is_open is True
    assert check.is_recommended is False
    assert check.name == "Known open licence"


def test_schema_license_predicate_is_checked():
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, SDO.license, URIRef("https://creativecommons.org/licenses/by/4.0/")))
    report = check_license(g)
    assert report.status == Status.OK
    assert len(report.checks) == 1


@pytest.mark.parametrize("license_value", [
    Literal("All rights reserved"),
    URIRef("https://example.org/my-custom-license"),
])
def test_unknown_license_fails(license_value):
    g = Graph()
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, DCTERMS.license, license_value))
    report = check_license(g)
    assert report.status == Status.FAIL
    check = report.checks[0]
    assert check.is_open is False
    assert check.is_recommended is False
    assert check.name == "Unknown non-open licence"
