"""Validate ontology license by loading `json/licenses.json`
and checking if the license is open or recommended."""

from __future__ import annotations

from rdflib import Graph
from rdflib.namespace import OWL, RDF, DCTERMS, SDO

from askwol.models import LicenseCheck, LicenseReport, Status

from pathlib import Path

import json

LICENSE_FILE = "licenses.json"

RECOMMENDED_IRIS = set([
    "creativecommons.org/publicdomain/zero/1.0",
    "creativecommons.org/licenses/by/4.0",
])

JSON_DIR = Path(__file__).resolve().parent / "json"

def check_license(graph: Graph) -> LicenseReport:
    """Evaluate whether an ontology is released under an open license."""

    open_iris = {}

    with open(str(JSON_DIR / LICENSE_FILE), "r", encoding="utf-8") as f:
        open_licenses = json.load(f)
        for l in open_licenses.values():
            if l["url"]:
                open_iris[(l["url"].split("://")[1].strip("/"))] = {"name": l["title"]}

    ontology = any(True for _ in graph.triples((None, RDF.type, OWL.Ontology)))

    licenses = []
    licenses += list(graph.triples((None, DCTERMS.license, None)))
    licenses += list(graph.triples((None, SDO.license, None)))
    license_count = len(licenses)

    checks: list[LicenseCheck] = []

    for license in licenses:
        try:
            license_iri_cut = license[2].split("://")[1].strip("/")
        except IndexError:
            license_iri_cut = license[2]
        is_recommended = license_iri_cut in RECOMMENDED_IRIS
        is_open = license_iri_cut in open_iris
        license_name = open_iris[license_iri_cut]["name"] if is_open else "Unknown non-open license"
        if license_iri_cut.startswith('purl.org/NET/rdflicense/'):
            is_open = True
            license_name = "Known open license"
        checks.append(
            LicenseCheck(
                iri=license[2],
                name=license_name,
                is_open=is_open,
                is_recommended=is_recommended,
                status=Status.OK if is_recommended else Status.WARN if is_open else Status.FAIL,
            )
        )

    return LicenseReport(checks=checks)
