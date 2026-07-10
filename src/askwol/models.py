"""Pydantic models for validation results and reports."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Status(str, Enum):
    OK = "ok"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class NamespaceCheck(BaseModel):
    """Result of checking whether a namespace URI resolves."""

    prefix: str
    uri: str
    status: Status
    http_status: int | None = None
    content_type: str | None = None
    is_valid_rdf: bool | None = None
    error: str | None = None


class TermCheck(BaseModel):
    """Result of checking whether a term exists in its remote vocabulary."""

    term_uri: str
    prefix: str
    local_name: str
    status: Status
    error: str | None = None


class NamespaceReport(BaseModel):
    """Aggregated results for one namespace: resolution + term checks."""

    prefix: str
    uri: str
    resolution: NamespaceCheck
    terms: list[TermCheck] = Field(default_factory=list)

    @property
    def total_terms(self) -> int:
        return len(self.terms)

    @property
    def valid_terms(self) -> int:
        return sum(1 for t in self.terms if t.status == Status.OK)

    @property
    def invalid_terms(self) -> int:
        return sum(1 for t in self.terms if t.status == Status.FAIL)


class UnusedPrefix(BaseModel):
    """A prefix declared but never used in any triple."""

    prefix: str
    uri: str


class LangTagIssue(BaseModel):
    """A single language-tag consistency issue on one subject+property."""

    subject: str
    property: str
    issue_type: str  # "missing_tag" or "missing_language"
    languages_found: list[str] = Field(default_factory=list)
    languages_expected: list[str] = Field(default_factory=list)
    detail: str
    is_blank_node: bool = False


class LangTagPropertySummary(BaseModel):
    """Per-property summary of language tag usage."""

    property: str
    languages: list[str] = Field(default_factory=list)
    total_subjects: int = 0
    consistent_subjects: int = 0
    examples: list[str] = Field(default_factory=list)


class LangTagReport(BaseModel):
    """Summary of language tag consistency across the ontology."""

    properties_checked: int = 0
    languages_used: list[str] = Field(default_factory=list)
    property_summaries: list[LangTagPropertySummary] = Field(default_factory=list)
    issues: list[LangTagIssue] = Field(default_factory=list)


class MetadataCheck(BaseModel):
    """One ontology metadata check derived from the SHACL shapes."""

    key: str
    label: str
    property: str
    severity: str  # required or recommended
    status: Status
    message: str | None = None


class MetadataReport(BaseModel):
    """Summary of ontology-level metadata completeness."""

    checks: list[MetadataCheck] = Field(default_factory=list)

    @property
    def passed_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.OK)

    @property
    def failed_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.FAIL)

    @property
    def warning_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.WARN)

    @property
    def total_checks(self) -> int:
        return len(self.checks)


class DefinitionDocumentationIssue(BaseModel):
    """One internal class or property definition missing a label or comment."""

    term: str
    display_name: str
    term_type: str
    missing: list[str] = Field(default_factory=list)
    message: str | None = None


class DefinitionDocumentationCheck(BaseModel):
    """Documentation status for one internal class or property definition."""

    term: str
    display_name: str
    term_type: str
    has_label: bool = False
    has_comment: bool = False
    status: Status
    message: str | None = None


class DefinitionDocumentationReport(BaseModel):
    """Summary of documentation completeness for internal definitions."""

    total_definitions: int = 0
    documented_definitions: int = 0
    checks: list[DefinitionDocumentationCheck] = Field(default_factory=list)
    issues: list[DefinitionDocumentationIssue] = Field(default_factory=list)

    @property
    def with_label(self) -> int:
        return sum(1 for c in self.checks if c.has_label)

    @property
    def with_comment(self) -> int:
        return sum(1 for c in self.checks if c.has_comment)

    @property
    def missing_label(self) -> list[DefinitionDocumentationCheck]:
        return [c for c in self.checks if not c.has_label]

    @property
    def missing_comment(self) -> list[DefinitionDocumentationCheck]:
        return [c for c in self.checks if not c.has_comment]


class InternalTermIssue(BaseModel):
    """One term in the ontology's own namespace that is referenced but never defined."""

    term: str
    display_name: str


class SkosConceptIssue(BaseModel):
    """One skos:Concept defined in the ontology's own namespace."""

    term: str
    display_name: str


class SkosConceptsReport(BaseModel):
    """Whether the ontology defines skos:Concept instances in its own namespace.

    Concepts belong in a separate SKOS concept scheme, not mixed into the OWL
    ontology that defines classes and properties. Only concepts in the
    ontology's own namespace are flagged; external concepts referenced as
    objects are fine.
    """

    total_concepts: int = 0
    internal_concepts: list[SkosConceptIssue] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None


class InternalTermsReport(BaseModel):
    """Whether terms in the ontology's own namespace are actually defined.

    A term is considered *defined* when it appears as the subject of at least
    one triple, and *referenced* when it appears as a predicate or object.
    Referenced-but-never-defined terms are usually typos or forgotten
    declarations.
    """

    total_referenced: int = 0
    defined: int = 0
    undefined: list[InternalTermIssue] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None


class ImportsCheck(BaseModel):
    """One namespace used by the ontology, and whether it is imported."""

    prefix: str
    namespace: str
    status: Status
    message: str | None = None


class ImportsReport(BaseModel):
    """Summary of owl:imports completeness for used external vocabularies."""

    ontology_iri: str | None = None
    declared: list[str] = Field(default_factory=list)
    checks: list[ImportsCheck] = Field(default_factory=list)
    status: Status = Status.OK

    @property
    def missing(self) -> list[ImportsCheck]:
        return [c for c in self.checks if c.status == Status.WARN]

    @property
    def total(self) -> int:
        return len(self.checks)


class IRIStrategyReport(BaseModel):
    """Hash vs slash IRI strategy used by the ontology's own defined terms."""

    ontology_iri: str | None = None
    strategy: str = "none"  # "hash" | "slash" | "mixed" | "none"
    hash_count: int = 0
    slash_count: int = 0
    hash_examples: list[str] = Field(default_factory=list)
    slash_examples: list[str] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None


class IRISchemeConflict(BaseModel):
    """One host that is referenced under both http:// and https://."""

    host: str
    http_count: int = 0
    https_count: int = 0
    http_examples: list[str] = Field(default_factory=list)
    https_examples: list[str] = Field(default_factory=list)


class IRISchemeReport(BaseModel):
    """Per-host http vs https scheme consistency across all IRIs used."""

    total_hosts: int = 0
    http_only_hosts: int = 0
    https_only_hosts: int = 0
    conflicts: list[IRISchemeConflict] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

class ReasonerCheck(BaseModel):
    """One result from the consistency and satisfiability checks."""

    key: str
    label: str
    status: Status
    message: str | None = None


class ReasonerReport(BaseModel):
    """Summary of lightweight reasoner checks on the current ontology."""

    scoped_to_current_ontology: bool = True
    imports_followed: bool = False
    consistent: bool = True
    inconsistent_individuals: list[str] = Field(default_factory=list)
    unsatisfiable_classes: list[str] = Field(default_factory=list)
    checks: list[ReasonerCheck] = Field(default_factory=list)


class ValidationReport(BaseModel):
    """Full validation report for an ontology file."""

    file: str
    namespaces: list[NamespaceReport] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)
    unused_prefixes: list[UnusedPrefix] = Field(default_factory=list)
    lang_tags: LangTagReport | None = None
    skos_concepts: SkosConceptsReport | None = None
    ontology_metadata: MetadataReport | None = None
    definition_docs: DefinitionDocumentationReport | None = None
    internal_terms: InternalTermsReport | None = None
    imports: ImportsReport | None = None
    iri_strategy: IRIStrategyReport | None = None
    iri_scheme: IRISchemeReport | None = None
    reasoner: ReasonerReport | None = None

    @property
    def total_namespaces(self) -> int:
        return len(self.namespaces)

    @property
    def total_terms(self) -> int:
        return sum(ns.total_terms for ns in self.namespaces)

    @property
    def has_issues(self) -> bool:
        for ns in self.namespaces:
            if ns.resolution.status == Status.FAIL:
                return True
            if ns.invalid_terms > 0:
                return True
        if self.unused_prefixes:
            return True
        if self.lang_tags and self.lang_tags.issues:
            return True
        if self.ontology_metadata and any(c.status != Status.OK for c in self.ontology_metadata.checks):
            return True
        if self.definition_docs and self.definition_docs.issues:
            return True
        if self.internal_terms and self.internal_terms.undefined:
            return True
        if self.imports and self.imports.missing:
            return True
        if self.iri_strategy and self.iri_strategy.status == Status.WARN:
            return True
        if self.iri_scheme and self.iri_scheme.status == Status.WARN:
            return True
        if self.reasoner and (not self.reasoner.consistent or self.reasoner.unsatisfiable_classes):
            return True
        if self.skos_concepts and self.skos_concepts.internal_concepts:
            return True
        return len(self.parse_errors) > 0
