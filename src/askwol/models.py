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
    deprecated: str | None = None
    """Set to the deprecation marker (e.g. ``owl:DeprecatedClass``) when a
    confirmed term is marked deprecated by the vocabulary that defines it."""


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
    deprecated: str | None = None
    """Set to the deprecation marker (e.g. ``owl:DeprecatedClass``) when this
    term is marked deprecated; label/comment issues are not raised for it."""


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


class NonOntologyTermIssue(BaseModel):
    """One term in the ontology's own namespace that is not part of the schema.

    ``type_label`` describes what it is (for example "SKOS concept" or
    "instance of Person").
    """

    term: str
    display_name: str
    type_label: str


class NonOntologyTermsReport(BaseModel):
    """Terms defined in the ontology's own namespace that are not OWL schema.

    An OWL ontology should define schema: classes, properties, and datatypes.
    Individuals, SKOS concepts, and other instance data belong in a separate
    resource. This check works from a whitelist of schema constructs; anything
    in the ontology's own namespace that carries a type but no schema type is
    flagged. External terms and the ontology header itself are ignored.
    """

    total_flagged: int = 0
    terms: list[NonOntologyTermIssue] = Field(default_factory=list)
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


class InternalTermEntry(BaseModel):
    """One term defined in the ontology's own namespace, with its category.

    ``category`` is one of: Class, Object property, Datatype property,
    Annotation property, Property (a generically typed property), Datatype,
    Named individual, Untyped. ``naming_ok`` reflects the capitalization
    convention (classes start uppercase, properties start lowercase); it is
    always True for categories the convention does not apply to.
    """

    term: str
    display_name: str
    category: str
    naming_ok: bool = True
    naming_message: str | None = None
    deprecated: str | None = None
    """Set to the deprecation marker (e.g. ``owl:DeprecatedClass``) when this
    term is marked deprecated; naming issues are not raised for it."""


class TermInventoryReport(BaseModel):
    """Categorization of the ontology's own terms plus naming conventions."""

    total_terms: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)
    entries: list[InternalTermEntry] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    @property
    def naming_issues(self) -> list[InternalTermEntry]:
        return [e for e in self.entries if not e.naming_ok]


class DomainRangeCheck(BaseModel):
    """Domain/range completeness and correctness for one property."""

    term: str
    display_name: str
    category: str  # "Object property" or "Datatype property"
    has_domain: bool = False
    has_range: bool = False
    status: Status = Status.OK
    message: str | None = None
    deprecated: str | None = None
    """Set to the deprecation marker (e.g. ``owl:DeprecatedClass``) when this
    property is marked deprecated; domain/range issues are not raised for it."""


class DomainRangeReport(BaseModel):
    """Whether object and datatype properties declare sound domains and ranges."""

    total_properties: int = 0
    object_properties: int = 0
    datatype_properties: int = 0
    checks: list[DomainRangeCheck] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    @property
    def issues(self) -> list[DomainRangeCheck]:
        return [c for c in self.checks if c.status != Status.OK]

    @property
    def with_domain(self) -> int:
        return sum(1 for c in self.checks if c.has_domain)

    @property
    def with_range(self) -> int:
        return sum(1 for c in self.checks if c.has_range)


class DatatypeUsage(BaseModel):
    """One datatype used by the ontology, and whether it is recognized."""

    datatype: str
    display_name: str
    count: int = 0
    sources: list[str] = Field(default_factory=list)  # "range", "literal", "declared"
    recognized: bool = True
    status: Status = Status.OK
    message: str | None = None


class DatatypeReport(BaseModel):
    """Inventory of datatypes used, flagging any that are not recognized."""

    total_datatypes: int = 0
    usages: list[DatatypeUsage] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    @property
    def recognized(self) -> int:
        return sum(1 for u in self.usages if u.recognized)

    @property
    def unrecognized(self) -> list[DatatypeUsage]:
        return [u for u in self.usages if not u.recognized]


class ImportsCheck(BaseModel):
    """Resolution result for one declared owl:imports target."""

    iri: str
    resolution: NamespaceCheck


class ImportsReport(BaseModel):
    """Whether the ontology's declared owl:imports targets actually resolve."""

    checks: list[ImportsCheck] = Field(default_factory=list)
    status: Status = Status.OK

    @property
    def broken(self) -> list[ImportsCheck]:
        return [c for c in self.checks if c.resolution.status == Status.FAIL]

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
    non_ontology_terms: NonOntologyTermsReport | None = None
    ontology_metadata: MetadataReport | None = None
    definition_docs: DefinitionDocumentationReport | None = None
    internal_terms: InternalTermsReport | None = None
    term_inventory: TermInventoryReport | None = None
    domains_ranges: DomainRangeReport | None = None
    datatypes: DatatypeReport | None = None
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
            if any(t.status == Status.WARN for t in ns.terms):
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
        if self.term_inventory and self.term_inventory.naming_issues:
            return True
        if self.domains_ranges and self.domains_ranges.status in (Status.FAIL, Status.WARN):
            return True
        if self.datatypes and self.datatypes.unrecognized:
            return True
        if self.imports and self.imports.broken:
            return True
        if self.iri_strategy and self.iri_strategy.status == Status.WARN:
            return True
        if self.iri_scheme and self.iri_scheme.status == Status.WARN:
            return True
        if self.reasoner and (not self.reasoner.consistent or self.reasoner.unsatisfiable_classes):
            return True
        if self.non_ontology_terms and self.non_ontology_terms.terms:
            return True
        return len(self.parse_errors) > 0
