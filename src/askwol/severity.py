"""Severity levels for askwol findings.

A check's ``Status`` says *what happened* (ok, fail, warn, skip); a ``Severity``
says *how much it matters*:

- ``error``: a formal logic or modelling problem. The ontology is invalid.
- ``warning``: a likely mistake or a serious interoperability problem.
- ``recommendation``: ontology publishing best practice. Unmet recommendations
  never make an ontology invalid.

``Status`` is kept as-is so the JSON API stays compatible; this module is the one
place that decides which severity a non-OK status carries for each check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from askwol.models import CheckFinding, Severity, SeveritySummary, Status

if TYPE_CHECKING:
    from askwol.models import ValidationReport


# Display order, most severe first.
SEVERITY_ORDER: tuple[Severity, ...] = (Severity.ERROR, Severity.WARNING, Severity.RECOMMENDATION)

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.ERROR: "Error",
    Severity.WARNING: "Warning",
    Severity.RECOMMENDATION: "Recommendation",
}

SEVERITY_PLURAL_LABELS: dict[Severity, str] = {
    Severity.ERROR: "errors",
    Severity.WARNING: "warnings",
    Severity.RECOMMENDATION: "recommendations",
}

# Keyed by check anchor (see templates.CHECKS), then by the non-OK status the
# check can report.
_E, _W, _R = Severity.ERROR, Severity.WARNING, Severity.RECOMMENDATION
CHECK_SEVERITY: dict[str, dict[Status, Severity]] = {
    "ontology-metadata": {Status.FAIL: _R, Status.WARN: _R},
    "imports": {Status.FAIL: _W},
    "iri-strategy": {Status.WARN: _W},
    "iri-scheme": {Status.WARN: _W},
    "license": {Status.FAIL: _R, Status.WARN: _R},
    "namespaces": {Status.FAIL: _W},
    "unused-prefixes": {Status.WARN: _R},
    "external-terms": {Status.FAIL: _E, Status.WARN: _W},
    "internal-terms": {Status.FAIL: _W},
    "term-inventory": {Status.WARN: _R},
    "domains-ranges": {Status.FAIL: _E, Status.WARN: _R},
    "datatypes": {Status.FAIL: _E},
    "non-ontology-terms": {Status.WARN: _R},
    "labels": {Status.FAIL: _R},
    "comments": {Status.FAIL: _R},
    "language-tags": {Status.WARN: _R},
    "reasoner": {Status.FAIL: _E, Status.WARN: _E},  # unsatisfiable classes are WARN but still a logic error
}


def severity_of(anchor: str, status: Status | str) -> Severity | None:
    """Severity of a result for a check, or None when it is OK/skipped."""
    return CHECK_SEVERITY.get(anchor, {}).get(Status(status))


def check_status(report: ValidationReport, anchor: str) -> Status | None:
    """Overall status of one check, or None when it did not run."""
    S = Status
    if anchor == "ontology-metadata":
        meta = report.ontology_metadata
        if not (meta and meta.checks):
            return None
        if meta.failed_checks:
            return S.FAIL
        return S.WARN if meta.warning_checks else S.OK
    if anchor == "imports":
        imp = report.imports
        if imp is None:
            return None
        return S.FAIL if imp.broken else S.OK
    if anchor == "iri-strategy":
        return report.iri_strategy.status if report.iri_strategy else None
    if anchor == "iri-scheme":
        return report.iri_scheme.status if report.iri_scheme else None
    if anchor == "license":
        return S(report.license.status) if report.license else None
    if anchor == "namespaces":
        if not report.namespaces:
            return None
        statuses = {ns.resolution.status for ns in report.namespaces}
        if S.FAIL in statuses:
            return S.FAIL
        return S.SKIP if statuses == {S.SKIP} else S.OK
    if anchor == "unused-prefixes":
        return S.WARN if report.unused_prefixes else S.OK
    if anchor == "external-terms":
        term_statuses = {t.status for ns in report.namespaces for t in ns.terms}
        if not term_statuses:
            return None
        if S.FAIL in term_statuses:
            return S.FAIL
        return S.WARN if S.WARN in term_statuses else S.OK
    if anchor == "internal-terms":
        it = report.internal_terms
        if not it:
            return None
        if it.status == S.SKIP:
            return S.SKIP
        return S.FAIL if it.undefined else S.OK
    if anchor == "term-inventory":
        inv = report.term_inventory
        if not inv:
            return None
        if inv.status == S.SKIP:
            return S.SKIP
        return S.WARN if inv.naming_issues else S.OK
    if anchor == "domains-ranges":
        return report.domains_ranges.status if report.domains_ranges else None
    if anchor == "datatypes":
        dt = report.datatypes
        if not dt:
            return None
        if dt.status == S.SKIP:
            return S.SKIP
        return S.FAIL if dt.unrecognised else S.OK
    if anchor == "non-ontology-terms":
        sk = report.non_ontology_terms
        if not sk:
            return None
        if sk.status == S.SKIP:
            return S.SKIP
        return S.WARN if sk.terms else S.OK
    if anchor in ("labels", "comments"):
        docs = report.definition_docs
        if not (docs and docs.total_definitions):
            return None
        missing = docs.missing_label if anchor == "labels" else docs.missing_comment
        return S.FAIL if missing else S.OK
    if anchor == "language-tags":
        return report.lang_tags.status if report.lang_tags else None
    if anchor == "reasoner":
        reasoner = report.reasoner
        if not reasoner:
            return None
        return S.OK if reasoner.consistent and not reasoner.unsatisfiable_classes else S.FAIL
    return None


def summarise(report: ValidationReport) -> SeveritySummary:
    """Roll a report up by severity. Parse errors count as errors."""
    findings: list[CheckFinding] = []
    for anchor in CHECK_SEVERITY:
        status = check_status(report, anchor)
        severity = severity_of(anchor, status) if status else None
        if severity is not None:
            findings.append(CheckFinding(check=anchor, status=status, severity=severity))

    findings.sort(key=lambda f: SEVERITY_ORDER.index(f.severity))
    errors = sum(1 for f in findings if f.severity == Severity.ERROR) + len(report.parse_errors)
    return SeveritySummary(
        valid=errors == 0,
        errors=errors,
        warnings=sum(1 for f in findings if f.severity == Severity.WARNING),
        recommendations=sum(1 for f in findings if f.severity == Severity.RECOMMENDATION),
        findings=findings,
    )
