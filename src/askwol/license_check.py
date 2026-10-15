"""Check ontology-header licences against the bundled licence register."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from rdflib import Graph
from rdflib.namespace import DCTERMS, OWL, RDF, SDO

from askwol.models import LicenseCheck, LicenseReport, Status

LICENSE_FILE = "licenses.json"
JSON_DIR = Path(__file__).resolve().parent / "json"

_CC_VERSIONS = ("1.0", "2.0", "2.5", "3.0", "4.0")
_CC_FAMILIES = {
    "licenses/by": ("CC-BY-4.0", _CC_VERSIONS),
    "licenses/by-sa": ("CC-BY-SA-4.0", _CC_VERSIONS),
    "licenses/by-nc": ("CC-BY-NC-4.0", _CC_VERSIONS),
    "licenses/by-nd": ("CC-BY-ND-4.0", _CC_VERSIONS),
    "licenses/by-nc-sa": ("CC-BY-NC-SA-4.0", _CC_VERSIONS),
    "licenses/by-nc-nd": ("CC-BY-NC-ND-4.0", _CC_VERSIONS[1:]),
    "publicdomain/zero": ("CC0-1.0", ("1.0",)),
}
_CC_LICENSE_RE = re.compile(
    r"^creativecommons\.org/(?P<family>licenses/[a-z-]+|publicdomain/zero)/(?P<version>[0-9.]+)"
    r"(?:/(?:legalcode|deed)(?:\.[a-z]{2,3}(?:[-_][a-z0-9]+)*)?)?$"
)

# Equivalent URLs used by ontology authors rather than the register's URLs.
KNOWN_URL_ALIASES: dict[str, tuple[str, ...]] = {
    "PDDL-1.0": ("https://opendatacommons.org/licenses/pddl/1.0",),
    "ODC-BY-1.0": ("https://opendatacommons.org/licenses/by/1.0",),
    "ODbL-1.0": ("https://opendatacommons.org/licenses/odbl/1.0",),
}
_RDFLICENSE_ALIASES = {
    "purl.org/NET/rdflicense/cc-by3.0": "creativecommons.org/licenses/by/3.0",
    "purl.org/NET/rdflicense/cc-by4.0": "creativecommons.org/licenses/by/4.0",
    "purl.org/NET/rdflicense/cc-by-nc4.0": "creativecommons.org/licenses/by-nc/4.0",
    "purl.org/NET/rdflicense/cc-by-nc-nd4.0": "creativecommons.org/licenses/by-nc-nd/4.0",
}


def _normalise_iri(value: str) -> str:
    """Identify known HTTP(S) aliases without merging different versions."""
    if any(ord(char) < 33 for char in value):
        return value
    try:
        url = urlsplit(value)
        if (url.scheme not in ("http", "https") or not url.netloc
                or url.username or url.password or url.port or url.query or url.fragment):
            return value
    except ValueError:
        return value
    key = f"{url.hostname}{url.path.rstrip('/')}"
    key = _RDFLICENSE_ALIASES.get(key, key)
    match = _CC_LICENSE_RE.fullmatch(key)
    if match:
        family, version = match.group("family", "version")
        spec = _CC_FAMILIES.get(family)
        if spec and version in spec[1]:
            key = f"creativecommons.org/{family}/{version}"
    return "https://" + key


def _recognised_licences() -> dict[str, tuple[str, bool | None]]:
    with (JSON_DIR / LICENSE_FILE).open(encoding="utf-8") as source:
        registry = json.load(source)

    recognised: dict[str, tuple[str, bool | None]] = {}
    for license_id, entry in registry.items():
        conformance = {entry["od_conformance"], entry["osd_conformance"]}
        is_open = True if "approved" in conformance else False if "rejected" in conformance else None
        urls = (entry["url"], *KNOWN_URL_ALIASES.get(license_id, ()))
        for url in urls:
            if url:
                recognised[_normalise_iri(url)] = (entry["title"], is_open)

    # The register lists the current CC versions; preserve the already
    # supported historical versions and give them their actual version name.
    for family, (license_id, versions) in _CC_FAMILIES.items():
        entry = registry[license_id]
        is_open = entry["od_conformance"] == "approved"
        for version in versions:
            name = entry["title"].replace(license_id.rsplit("-", 1)[-1], version)
            recognised[f"https://creativecommons.org/{family}/{version}"] = (name, is_open)
    return recognised


def check_license(graph: Graph) -> LicenseReport:
    """Check distinct licences declared on owl:Ontology header subjects."""
    recognised = _recognised_licences()
    values = {
        str(value)
        for ontology in graph.subjects(RDF.type, OWL.Ontology)
        for predicate in (DCTERMS.license, SDO.license)
        for value in graph.objects(ontology, predicate)
    }
    checks: list[LicenseCheck] = []
    seen: set[str] = set()
    for value in sorted(values):
        key = _normalise_iri(value)
        if key in seen:
            continue
        seen.add(key)
        name, is_open = recognised.get(key, ("Unrecognised licence", None))
        is_recommended = is_open is True and (
            key.startswith("https://creativecommons.org/licenses/by/")
            or key == "https://creativecommons.org/publicdomain/zero/1.0"
        )
        checks.append(LicenseCheck(
            iri=value,
            name=name,
            is_open=is_open,
            is_recommended=is_recommended,
            status=Status.OK if is_recommended else Status.FAIL if is_open is False else Status.WARN,
        ))
    return LicenseReport(checks=checks)
