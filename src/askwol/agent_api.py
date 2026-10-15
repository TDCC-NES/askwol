"""Request and compact-response models for programmatic validation."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from askwol.checks import CHECKS, REASONER_SCOPE
from askwol.input_utils import RDF_FORMAT_SUFFIXES, validate_base_uri
from askwol.models import InputDiagnostic, ReasonerReport, Status, ValidationReport
from askwol.severity import SeveritySummary

RDFFormat = Literal["json-ld", "turtle", "xml", "nt", "n3"]
CoverageStatus = Literal["completed", "partial", "skipped", "unavailable"]

class OntologyContent(BaseModel):
    """An RDF document carried inside a JSON request, rather than a file upload."""

    model_config = ConfigDict(extra="forbid")

    format: RDFFormat = Field(description="RDF syntax; use json-ld for JSON-LD objects or arrays.")
    content: str | dict[str, Any] | list[Any] = Field(
        description="JSON-LD object/array or RDF source text in the selected format.",
    )
    base_uri: str | None = Field(
        default=None,
        description="Absolute base IRI for relative IRIs; this field does not fetch the ontology.",
    )

    @field_validator("base_uri")
    @classmethod
    def validate_base_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_base_uri(value)

    @model_validator(mode="after")
    def validate_content(self) -> OntologyContent:
        if not isinstance(self.content, str) and self.format != "json-ld":
            raise ValueError("Objects and arrays require format json-ld")
        try:
            self.as_bytes()
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("content must be valid UTF-8 text or JSON values") from exc
        return self

    @property
    def suffix(self) -> str:
        """Filename suffix recognised by the existing RDF loader."""
        return RDF_FORMAT_SUFFIXES[self.format]

    def as_bytes(self) -> bytes:
        """Preserve source text; serialise structured JSON-LD as UTF-8."""
        text = self.content if isinstance(self.content, str) else json.dumps(
            self.content, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        )
        return text.encode("utf-8")


class ApiError(BaseModel):
    """An operational error, such as a limit or worker failure."""

    detail: str


class RequestValidationIssue(BaseModel):
    """A FastAPI request-validation issue; optional fields vary by version."""

    loc: list[str | int]
    msg: str
    type: str
    input: Any = None
    ctx: dict[str, Any] | None = None


class ApiValidationError(BaseModel):
    """Invalid request parameters, distinct from an RDF parse-error report."""

    detail: list[RequestValidationIssue]


class CheckCoverage(BaseModel):
    """Execution coverage only; findings carry severity and outcomes."""

    check: str
    status: CoverageStatus = Field(
        description="completed is execution coverage, not a passing verdict; partial means some targets were unchecked.",
    )
    message: str | None = None


class ReasoningScope(BaseModel):
    """Reasoning limits retained without repeating affected-term inventories."""

    description: str = REASONER_SCOPE
    scoped_to_current_ontology: bool
    imports_followed: bool
    consistent: bool | None

    @classmethod
    def from_report(cls, report: ReasonerReport) -> ReasoningScope:
        return cls(
            scoped_to_current_ontology=report.scoped_to_current_ontology,
            imports_followed=report.imports_followed,
            consistent=report.consistent,
        )


class CompactValidationReport(BaseModel):
    """Findings and execution scope, without the full per-term inventories."""

    file: str
    severity_summary: SeveritySummary
    checks: list[CheckCoverage]
    reasoner: ReasoningScope | None = None
    input_error: InputDiagnostic | None = None
    input_warnings: list[str] = Field(default_factory=list)


_SECTION_FIELDS = {
    "ontology-metadata": "ontology_metadata", "imports": "imports",
    "iri-strategy": "iri_strategy", "iri-scheme": "iri_scheme", "license": "license",
    "internal-terms": "internal_terms", "term-inventory": "term_inventory",
    "domains-ranges": "domains_ranges", "datatypes": "datatypes",
    "non-ontology-terms": "non_ontology_terms", "labels": "definition_docs",
    "comments": "definition_docs", "language-tags": "lang_tags", "reasoner": "reasoner",
}


def _resolution_coverage(check: str, statuses: list[Status]) -> CheckCoverage:
    if statuses and all(status == Status.SKIP for status in statuses):
        return CheckCoverage(check=check, status="skipped", message="Resolution was skipped.")
    if any(status == Status.SKIP for status in statuses):
        return CheckCoverage(check=check, status="partial", message="Some resolution targets were skipped.")
    return CheckCoverage(check=check, status="completed")


def _external_term_coverage(report: ValidationReport) -> CheckCoverage:
    terms = report.external_term_checks
    if not terms:
        return _resolution_coverage("external-terms", [ns.resolution.status for ns in report.namespaces])
    unchecked = [(ns, term) for ns, term in terms if term.status == Status.SKIP]
    if not unchecked:
        return CheckCoverage(check="external-terms", status="completed")
    if len(unchecked) < len(terms):
        return CheckCoverage(check="external-terms", status="partial", message="Some external terms could not be checked.")
    if all(ns.resolution.status == Status.SKIP for ns, _ in unchecked):
        return CheckCoverage(check="external-terms", status="skipped", message="Resolution was skipped.")
    return CheckCoverage(check="external-terms", status="unavailable", message="Vocabulary RDF was unavailable for external-term checking.")


def compact_report(report: ValidationReport) -> CompactValidationReport:
    """Reduce the existing report without rerunning or reinterpreting checks."""
    coverage: list[CheckCoverage] = []
    for definition in CHECKS:
        check = definition["report_anchor"]
        if report.input_error or report.parse_errors:
            result = CheckCoverage(check=check, status="skipped")
        elif check == "namespaces":
            result = _resolution_coverage(check, [ns.resolution.status for ns in report.namespaces])
        elif check == "external-terms":
            result = _external_term_coverage(report)
        elif check == "unused-prefixes":
            result = CheckCoverage(check=check, status="completed")
        else:
            section = getattr(report, _SECTION_FIELDS[check])
            if section is None:
                result = CheckCoverage(check=check, status="unavailable")
            elif check == "imports":
                result = _resolution_coverage(check, [item.resolution.status for item in section.checks])
            elif getattr(section, "status", None) == Status.SKIP:
                result = CheckCoverage(check=check, status="skipped", message=getattr(section, "message", None))
            else:
                result = CheckCoverage(check=check, status="completed")
        coverage.append(result)
    return CompactValidationReport(
        file=report.file,
        severity_summary=report.severity_summary,
        checks=coverage,
        reasoner=ReasoningScope.from_report(report.reasoner) if report.reasoner is not None else None,
        input_error=report.input_error,
        input_warnings=report.input_warnings,
    )
