"""Shared check catalogue, categories, and numbering for every report format."""

from __future__ import annotations

from html import unescape
from typing import TypedDict


class CheckCategory(TypedDict):
    key: str
    label: str


class CheckDefinition(TypedDict):
    report_anchor: str
    title: str
    guide_anchor: str
    category: str
    description: str


CHECK_CATEGORIES: list[CheckCategory] = [
    {"key": "basics", "label": "Ontology basics"},
    {"key": "reuse", "label": "Namespaces &amp; reuse"},
    {"key": "structure", "label": "Term structure"},
    {"key": "docs", "label": "Term documentation"},
    {"key": "logic", "label": "Logic"},
]


CHECKS: list[CheckDefinition] = [
    {"report_anchor": "ontology-metadata", "title": "Ontology metadata", "guide_anchor": "metadata", "category": "basics",
     "description": "SHACL validation of the ontology header against Ask Wol's built-in shapes: title, description, creator, and version are the core properties; created and modified dates and publisher are additional. Every missing property is reported as a recommendation."},
    {"report_anchor": "imports", "title": "Imports", "guide_anchor": "imports", "category": "basics",
     "description": "every `owl:imports` target declared in the ontology header is fetched over HTTP and parsed as RDF, the same way a reasoner would follow it."},
    {"report_anchor": "iri-strategy", "title": "IRI strategy", "guide_anchor": "iri-strategy", "category": "basics",
     "description": "the ontology's own defined terms should consistently use either hash (`#Term`) or slash (`/Term`), not both."},
    {"report_anchor": "iri-scheme", "title": "IRI scheme", "guide_anchor": "https-http", "category": "basics",
     "description": "each namespace (the base IRI, not just the host) should be referenced under a single URI scheme. `http://example.org/X` and `https://example.org/X` are different IRIs."},
    {"report_anchor": "license", "title": "Open licence", "guide_anchor": "license", "category": "basics",
     "description": "the declared `dcterms:license` (or `schema:license`) should be an open licence per the Open Definition; CC0 and CC BY are the recommended choices, and a missing, non-open or merely open-but-not-recommended licence is reported as a recommendation."},
    {"report_anchor": "namespaces", "title": "Namespaces", "guide_anchor": "resolvable", "category": "reuse",
     "description": "fetches each declared namespace URI, checks HTTP status, and tries to parse it as RDF (Turtle, RDF/XML, JSON-LD, N-Triples). Falls back to scanning HTML pages for RDF links."},
    {"report_anchor": "unused-prefixes", "title": "Unused prefixes", "guide_anchor": "prefixes", "category": "reuse",
     "description": "flags `@prefix` declarations that are never used in any triple."},
    {"report_anchor": "external-terms", "title": "External term definitions", "guide_anchor": "external-terms", "category": "reuse",
     "description": "verifies that terms reused from an external vocabulary actually exist there. Catches both typos (`foaf:nme`) and made-up terms (`owl:MadeUpClass`). A term that exists but is marked deprecated upstream is flagged as a warning."},
    {"report_anchor": "internal-terms", "title": "Internal term definitions", "guide_anchor": "internal-terms", "category": "structure",
     "description": "flags terms in the ontology's own namespace that are referenced but never defined. Usually a typo or a forgotten declaration."},
    {"report_anchor": "term-inventory", "title": "Term inventory & naming", "guide_anchor": "term-inventory", "category": "structure",
     "description": "categorises every internal term (class, object property, datatype property, datatype, individual) and checks capitalisation: classes start uppercase, properties lowercase. Coded identifiers are exempt."},
    {"report_anchor": "domains-ranges", "title": "Domains & ranges", "guide_anchor": "domains-ranges", "category": "structure",
     "description": "every internally defined object and datatype property should declare a domain and a range. Object properties range over classes; datatype properties over datatypes. A missing domain or range is a recommendation; a domain or range of the wrong kind is an error."},
    {"report_anchor": "datatypes", "title": "Datatypes", "guide_anchor": "datatypes", "category": "structure",
     "description": "datatypes used as property ranges and literal datatypes should be recognised XSD built-ins, `rdfs:Literal`, `rdf:langString`, or a locally declared `rdfs:Datatype`. Catches typos like `xsd:stirng`."},
    {"report_anchor": "non-ontology-terms", "title": "Non-ontology terms", "guide_anchor": "non-ontology-terms", "category": "structure",
     "description": "an OWL ontology defines schema (classes, properties, datatypes). A `skos:Concept` scheme is subject-matter data, not schema, and belongs in a separate resource. Named individuals are not flagged."},
    {"report_anchor": "labels", "title": "Labels", "guide_anchor": "labels", "category": "docs",
     "description": "a SHACL check that every internally defined class and property carries an `rdfs:label`."},
    {"report_anchor": "comments", "title": "Comments", "guide_anchor": "comments", "category": "docs",
     "description": "a SHACL check that every internally defined class and property carries an `rdfs:comment`."},
    {"report_anchor": "language-tags", "title": "Language tag consistency", "guide_anchor": "lang-tags", "category": "docs",
     "description": "labels and definitions (`rdfs:label`, `rdfs:comment`, `skos:prefLabel`, `skos:definition`, ...) on internally defined terms should use language tags consistently."},
    {"report_anchor": "reasoner", "title": "Reasoner checks", "guide_anchor": "reasoner", "category": "logic",
     "description": "limited OWL RL checks for inconsistent individuals and unsatisfiable classes in the current document; imports are excluded. Not a complete consistency or OWL 2 DL conformance check."},
]


CLUSTER_NUMBERS: dict[str, int] = {
    category["key"]: i + 1 for i, category in enumerate(CHECK_CATEGORIES)
}


def _compute_check_numbers() -> dict[str, str]:
    counters: dict[str, int] = {}
    numbers: dict[str, str] = {}
    for check in CHECKS:
        category = check["category"]
        counters[category] = counters.get(category, 0) + 1
        numbers[check["report_anchor"]] = f"{CLUSTER_NUMBERS[category]}.{counters[category]}"
    return numbers


CHECK_NUMBERS = _compute_check_numbers()
GUIDE_CHECK_NUMBERS: dict[str, str] = {
    check["guide_anchor"]: CHECK_NUMBERS[check["report_anchor"]] for check in CHECKS
}

# Categories must form contiguous blocks in their declared order.
_seen_categories: list[str] = []
for _check in CHECKS:
    if not _seen_categories or _seen_categories[-1] != _check["category"]:
        _seen_categories.append(_check["category"])
assert _seen_categories == [category["key"] for category in CHECK_CATEGORIES]
assert all(check["description"].strip() for check in CHECKS)


def _check_bullets_markdown() -> str:
    """Flat Markdown bullet list for every check, in CHECKS order (used for
    the /api/validate description)."""
    parts: list[str] = []
    for check in CHECKS:
        num = CHECK_NUMBERS[check["report_anchor"]]
        title = unescape(check["title"])
        parts.append(f"- **{num} {title}** - {check['description']}")
    return "\n".join(parts)


def render_checks_api_description() -> str:
    """Render the flat checks list as Markdown for the /api/validate route's
    OpenAPI description."""
    intro = "Upload an OWL ontology and get a full validation report as JSON.\n\nThe report includes:\n\n"
    outro = (
        "\n\n`severity_summary` lists every individual finding with its severity and "
        "counts them per level: `error` (a formal logic or OWL 2 DL problem; "
        "`has_errors` is true), `warning` (a likely mistake or serious "
        "interoperability problem) and `recommendation` (publishing best "
        "practice). The per-item `status` values "
        "(`ok`, `warn`, `fail`, `skip`) describe the outcome of one check, not how "
        "serious the finding is."
        "\n\nOnly terms that appear as subjects in triples are validated "
        "against remote vocabularies. Terms used only as predicates or "
        "objects are treated as well-known vocabulary."
    )
    return intro + _check_bullets_markdown() + outro
