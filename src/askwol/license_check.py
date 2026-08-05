"""Validate ontology licence by loading `json/licenses.json`
and checking if the licence is open or recommended."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rdflib import Graph
from rdflib.namespace import DCTERMS, SDO

from askwol.models import LicenseCheck, LicenseReport, Status

LICENSE_FILE = "licenses.json"

JSON_DIR = Path(__file__).resolve().parent / "json"

RECOMMENDED_IRIS = set([
    "creativecommons.org/publicdomain/zero",
    "creativecommons.org/licenses/by",
])

# Creative Commons licences are versioned (1.0-4.0) and each version has more
# than one equivalent URL: the short deed link, the full /legalcode text, and
# translated /legalcode.xx or /deed.xx variants - all refer to the same
# licence. Match any version and any trailing form, and collapse them down to
# "creativecommons.org/<family>" (dropping the version and anything after
# it), so every URL variant of every version is recognised, not just the
# exact current-version short link. Found via a real ontology (CiTO) that
# cites the /legalcode URL directly.
_CC_LICENSE_RE = re.compile(
    r"^creativecommons\.org/(?P<family>licenses/[a-z-]+|publicdomain/zero)/[0-9.]+(?:/.*)?$"
)


def _normalise_iri(iri_cut: str) -> str:
    """Collapse Creative Commons URL variants (any version, /legalcode,
    /deed.xx, ...) down to one canonical form; anything else is returned
    unchanged."""
    match = _CC_LICENSE_RE.match(iri_cut)
    return f"creativecommons.org/{match.group('family')}" if match else iri_cut

# licenses.json (the Open Definition licence register) sometimes points its
# own `url` field at a registry reference page rather than the URL ontology
# authors actually cite in dcterms:license. The Open Data Commons licences are
# one such case: the register points at opendefinition.org, while real
# ontologies (and Open Data Commons' own "how to apply" instructions) cite
# opendatacommons.org. Map those real-world IRIs back to the register entry.
KNOWN_URL_ALIASES: dict[str, tuple[str, ...]] = {
    "PDDL-1.0": ("opendatacommons.org/licenses/pddl/1.0",),
    "ODC-BY-1.0": ("opendatacommons.org/licenses/by/1.0",),
    "ODbL-1.0": ("opendatacommons.org/licenses/odbl/1.0",),
}

KNOWN_OPEN_PREFIX = "purl.org/NET/rdflicense/"


def check_license(graph: Graph) -> LicenseReport:
    """Evaluate whether an ontology is released under an open licence."""

    open_iris: dict[str, str] = {}

    with open(str(JSON_DIR / LICENSE_FILE), "r", encoding="utf-8") as f:
        license_registry = json.load(f)
        for license_id, entry in license_registry.items():
            is_recognized_open = entry["od_conformance"] == "approved" or entry["osd_conformance"] == "approved"
            if not is_recognized_open:
                continue
            if entry["url"]:
                open_iris[_normalise_iri(entry["url"].split("://")[1].strip("/"))] = entry["title"]
            for alias in KNOWN_URL_ALIASES.get(license_id, ()):
                open_iris[_normalise_iri(alias)] = entry["title"]

    licenses = []
    licenses += list(graph.triples((None, DCTERMS.license, None)))
    licenses += list(graph.triples((None, SDO.license, None)))

    checks: list[LicenseCheck] = []

    for _subject, _predicate, license_value in licenses:
        try:
            license_iri_cut = _normalise_iri(license_value.split("://")[1].strip("/"))
        except IndexError:
            license_iri_cut = _normalise_iri(license_value)

        is_recommended = license_iri_cut in RECOMMENDED_IRIS
        is_known_open_prefix = license_iri_cut.startswith(KNOWN_OPEN_PREFIX)
        is_open = is_recommended or license_iri_cut in open_iris or is_known_open_prefix

        if license_iri_cut in open_iris:
            license_name = open_iris[license_iri_cut]
        elif is_known_open_prefix:
            license_name = "Known open licence"
        else:
            license_name = "Unknown non-open licence"

        checks.append(
            LicenseCheck(
                iri=license_value,
                name=license_name,
                is_open=is_open,
                is_recommended=is_recommended,
                status=Status.OK if is_recommended else Status.WARN if is_open else Status.FAIL,
            )
        )

    return LicenseReport(checks=checks)
