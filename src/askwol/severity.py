"""Severity levels, finding rules, and the presentation shared by all reports.

A ``Status`` says what a single check did (ok, warn, fail, skip). A
``Severity`` says how much a *finding* matters:

- ``error``: a formal logic or OWL 2 DL problem.
- ``warning``: a likely mistake or a serious interoperability problem.
- ``recommendation``: ontology publishing best practice.

Every finding is created from a ``Rule``. ``RULE_SEVERITY`` is the single place
that says how severe each rule is (the same idea as ROBOT's report profile).
This module deliberately imports nothing from ``askwol.models`` so that the
models can build findings without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    RECOMMENDATION = "recommendation"


# Display order, most severe first.
SEVERITY_ORDER: tuple[Severity, ...] = (Severity.ERROR, Severity.WARNING, Severity.RECOMMENDATION)


class Rule(str, Enum):
    """One kind of finding. The part before the dot is the check's report anchor."""

    PARSE_ERROR = "parse.error"
    METADATA_MISSING = "ontology-metadata.missing"
    IMPORT_UNRESOLVED = "imports.unresolved"
    IRI_STRATEGY_MIXED = "iri-strategy.mixed"
    IRI_SCHEME_MIXED = "iri-scheme.mixed"
    LICENSE_MISSING = "license.missing"
    LICENSE_NOT_OPEN = "license.not-open"
    LICENSE_NOT_RECOMMENDED = "license.not-recommended"
    LICENSE_MULTIPLE = "license.multiple"
    NAMESPACE_UNRESOLVED = "namespaces.unresolved"
    UNUSED_PREFIX = "unused-prefixes.unused"
    EXTERNAL_TERM_NOT_FOUND = "external-terms.not-found"
    EXTERNAL_TERM_DEPRECATED = "external-terms.deprecated"
    INTERNAL_TERM_UNDEFINED = "internal-terms.undefined"
    NAMING_CONVENTION = "term-inventory.naming"
    DOMAIN_RANGE_MISSING = "domains-ranges.missing"
    DOMAIN_RANGE_MISMATCH = "domains-ranges.mismatch"
    DATATYPE_UNRECOGNISED = "datatypes.unrecognised"
    NON_ONTOLOGY_TERM = "non-ontology-terms.concept"
    LABEL_MISSING = "labels.missing"
    COMMENT_MISSING = "comments.missing"
    LANG_TAG_INCONSISTENT = "language-tags.inconsistent"
    LANG_TAG_MISSING = "language-tags.missing"
    INCONSISTENT_INDIVIDUAL = "reasoner.inconsistent-individual"
    UNSATISFIABLE_CLASS = "reasoner.unsatisfiable-class"

    @property
    def check(self) -> str:
        return self.value.split(".", 1)[0]


_E, _W, _R = Severity.ERROR, Severity.WARNING, Severity.RECOMMENDATION

# The classification. Keep the SHACL shapes in askwol/shapes in step with the
# rules they implement (tests/test_severity.py fails if they drift apart).
RULE_SEVERITY: dict[Rule, Severity] = {
    Rule.PARSE_ERROR: _E,
    Rule.METADATA_MISSING: _R,
    Rule.IMPORT_UNRESOLVED: _W,
    Rule.IRI_STRATEGY_MIXED: _W,
    Rule.IRI_SCHEME_MIXED: _W,
    Rule.LICENSE_MISSING: _R,
    Rule.LICENSE_NOT_OPEN: _R,
    Rule.LICENSE_NOT_RECOMMENDED: _R,
    Rule.LICENSE_MULTIPLE: _R,
    Rule.NAMESPACE_UNRESOLVED: _W,
    Rule.UNUSED_PREFIX: _R,
    Rule.EXTERNAL_TERM_NOT_FOUND: _W,
    Rule.EXTERNAL_TERM_DEPRECATED: _W,
    Rule.INTERNAL_TERM_UNDEFINED: _W,
    Rule.NAMING_CONVENTION: _R,
    Rule.DOMAIN_RANGE_MISSING: _R,
    Rule.DOMAIN_RANGE_MISMATCH: _E,
    Rule.DATATYPE_UNRECOGNISED: _E,
    Rule.NON_ONTOLOGY_TERM: _R,
    Rule.LABEL_MISSING: _R,
    Rule.COMMENT_MISSING: _R,
    Rule.LANG_TAG_INCONSISTENT: _R,
    Rule.LANG_TAG_MISSING: _R,
    Rule.INCONSISTENT_INDIVIDUAL: _E,
    Rule.UNSATISFIABLE_CLASS: _E,
}


class Finding(BaseModel):
    """One thing a check found, with the severity its rule assigns."""

    rule: Rule
    check: str
    severity: Severity
    subject: str | None = None
    message: str | None = None

    @classmethod
    def of(cls, rule: Rule, subject: str | None = None, message: str | None = None) -> Finding:
        return cls(
            rule=rule,
            check=rule.check,
            severity=RULE_SEVERITY[rule],
            subject=subject,
            message=message,
        )


def worst_severity(findings: list[Finding]) -> Severity | None:
    """The most severe level among ``findings``, or None when there are none."""
    present = {f.severity for f in findings}
    return next((sev for sev in SEVERITY_ORDER if sev in present), None)


class SeveritySummary(BaseModel):
    """Counts of individual findings per severity, plus the findings themselves."""

    has_errors: bool = False
    errors: int = 0
    warnings: int = 0
    recommendations: int = 0
    findings: list[Finding] = Field(default_factory=list)

    def count(self, severity: Severity) -> int:
        return {
            Severity.ERROR: self.errors,
            Severity.WARNING: self.warnings,
            Severity.RECOMMENDATION: self.recommendations,
        }[severity]

    def for_check(self, check: str) -> list[Finding]:
        return [f for f in self.findings if f.check == check]


def summarise(findings: list[Finding]) -> SeveritySummary:
    """Roll findings up by severity, most severe first (stable within a level)."""
    ordered = sorted(findings, key=lambda f: SEVERITY_ORDER.index(f.severity))
    counts = {sev: sum(1 for f in ordered if f.severity == sev) for sev in SEVERITY_ORDER}
    return SeveritySummary(
        has_errors=counts[Severity.ERROR] > 0,
        errors=counts[Severity.ERROR],
        warnings=counts[Severity.WARNING],
        recommendations=counts[Severity.RECOMMENDATION],
        findings=ordered,
    )


@dataclass(frozen=True)
class SeverityStyle:
    """How a severity is named and drawn, shared by the HTML, CLI and Markdown reports."""

    label: str
    singular: str
    plural: str
    glyph: str
    color: str  # hex, used by the HTML report
    rich: str  # style name, used by the terminal report
    description: str

    @property
    def html_glyph(self) -> str:
        return f"&#x{ord(self.glyph):X};"


SEVERITY_STYLES: dict[Severity, SeverityStyle] = {
    Severity.ERROR: SeverityStyle(
        label="Error",
        singular="error",
        plural="errors",
        glyph="\u2717",
        color="#c62828",
        rich="red",
        description="a formal logic or OWL 2 DL problem.",
    ),
    Severity.WARNING: SeverityStyle(
        label="Warning",
        singular="warning",
        plural="warnings",
        glyph="\u26A0",
        color="#e6a700",
        rich="yellow",
        description="a likely mistake or a serious interoperability problem.",
    ),
    Severity.RECOMMENDATION: SeverityStyle(
        label="Recommendation",
        singular="recommendation",
        plural="recommendations",
        glyph="\U0001F4A1",
        color="#1e6fb5",
        rich="blue",
        description="ontology publishing best practice.",
    ),
}


def count_label(severity: Severity, n: int) -> str:
    """``"1 error"``, ``"3 warnings"``."""
    style = SEVERITY_STYLES[severity]
    return f"{n} {style.singular if n == 1 else style.plural}"
