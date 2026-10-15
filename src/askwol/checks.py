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


REASONER_SCOPE = (
    "Selected OWL RL/RDF checks for contradictory class memberships of named "
    "individuals and unsatisfiable internal classes in the current document; imports excluded. "
    "Passing these checks does not establish consistency or OWL 2 DL conformance."
)
DATATYPE_SCOPE = (
    "Checks datatype IRIs against recognised built-ins and local declarations. "
    "Literal values and OWL profile conformance are not validated."
)


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
     "description": "fetches directly declared `owl:imports` targets and checks that they provide parseable RDF. Nested imports are not followed."},
    {"report_anchor": "iri-strategy", "title": "IRI strategy", "guide_anchor": "iri-strategy", "category": "basics",
     "description": "the ontology's own defined terms should consistently use either hash (`#Term`) or slash (`/Term`), not both."},
    {"report_anchor": "iri-scheme", "title": "IRI scheme", "guide_anchor": "https-http", "category": "basics",
     "description": "each namespace (the base IRI, not just the host) should be referenced under a single URI scheme. `http://example.org/X` and `https://example.org/X` are different IRIs."},
    {"report_anchor": "license", "title": "Open licence", "guide_anchor": "license", "category": "basics",
     "description": "checks ontology-header `dcterms:license` or `schema:license` values against known licences. Missing, unrecognised, non-open, non-preferred or multiple licences are recommendations; CC0 and CC BY are preferred."},
    {"report_anchor": "namespaces", "title": "Namespaces", "guide_anchor": "resolvable", "category": "reuse",
     "description": "fetches namespaces with subject-position terms, checks HTTP status, and tries to parse RDF (Turtle, RDF/XML, JSON-LD, N-Triples). Falls back to scanning HTML pages for RDF links."},
    {"report_anchor": "unused-prefixes", "title": "Unused prefixes", "guide_anchor": "prefixes", "category": "reuse",
     "description": "flags detected prefix bindings whose namespace has no matching IRI use, including header and literal datatype IRIs."},
    {"report_anchor": "external-terms", "title": "External term definitions", "guide_anchor": "external-terms", "category": "reuse",
     "description": "checks whether external subject IRIs occur in the retrieved vocabulary RDF. Terms not found there and upstream deprecation are warnings. Predicate-only and object-only references are excluded."},
    {"report_anchor": "internal-terms", "title": "Internal term definitions", "guide_anchor": "internal-terms", "category": "structure",
     "description": "flags terms in the ontology's own namespace that are referenced but never defined. Usually a typo or a forgotten declaration."},
    {"report_anchor": "term-inventory", "title": "Term inventory & naming", "guide_anchor": "term-inventory", "category": "structure",
     "description": "categorises every internal term (class, object property, datatype property, datatype, individual) and checks capitalisation: classes start uppercase, properties lowercase. Coded identifiers are exempt."},
    {"report_anchor": "domains-ranges", "title": "Domains & ranges", "guide_anchor": "domains-ranges", "category": "structure",
     "description": "checks directly declared domains and ranges of internal object and datatype properties. Missing declarations are recommendations; selected named class/datatype mismatches are errors. Anonymous expressions are not evaluated."},
    {"report_anchor": "datatypes", "title": "Datatypes", "guide_anchor": "datatypes", "category": "structure",
     "description": DATATYPE_SCOPE},
    {"report_anchor": "non-ontology-terms", "title": "Non-ontology terms", "guide_anchor": "non-ontology-terms", "category": "structure",
     "description": "lists internal `skos:Concept` instances with a TDCC recommendation to consider separate management of concept schemes. This is an organisation preference, not an OWL validity requirement."},
    {"report_anchor": "labels", "title": "Labels", "guide_anchor": "labels", "category": "docs",
     "description": "a SHACL check that every internally defined class and property carries an `rdfs:label`."},
    {"report_anchor": "comments", "title": "Comments", "guide_anchor": "comments", "category": "docs",
     "description": "a SHACL check that every internally defined class and property carries an `rdfs:comment`."},
    {"report_anchor": "language-tags", "title": "Language tag consistency", "guide_anchor": "lang-tags", "category": "docs",
     "description": "labels and definitions (`rdfs:label`, `rdfs:comment`, `skos:prefLabel`, `skos:definition`, ...) on internally defined terms should use language tags consistently."},
    {"report_anchor": "reasoner", "title": "Reasoner checks", "guide_anchor": "reasoner", "category": "logic",
     "description": REASONER_SCOPE},
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
CHECK_GUIDE_URLS: dict[str, str] = {
    check["report_anchor"]: f"https://lod-4tu.tudelft.nl/askwol/guide#{check['guide_anchor']}"
    for check in CHECKS
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
    intro = (
        "Submit an OWL ontology and get a validation report as JSON. "
        "Use `compact=true` to return findings, counts, check coverage and reasoning scope "
        "without detailed term inventories. HTTP 200 means validation completed, not that "
        "the ontology passed: inspect `severity_summary` and skipped or unavailable checks. "
        "HTTP 422 returns a parse-error report or request-validation errors in `detail`.\n\n"
        "The checks are:\n\n"
    )
    outro = (
        "\n\n`severity_summary` lists every individual finding with its severity and "
        "counts them per level; each finding links to the relevant guide section in `guide_url`. "
        "Levels are `error` (a parsing failure or a logical or structural problem; "
        "`has_errors` is true), `warning` (a likely mistake or serious "
        "interoperability problem) and `recommendation` (publishing best "
        "practice). The per-item `status` values "
        "(`ok`, `warn`, `fail`, `skip`) describe the outcome of one check, not how "
        "serious the finding is."
        "\n\nOnly terms that appear as subjects in triples are validated "
        "against remote vocabularies. Terms used only as predicates or "
        "objects are not checked against remote vocabularies."
    )
    return intro + _check_bullets_markdown() + outro
