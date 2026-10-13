"""Pydantic models for validation results and reports."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, computed_field

from askwol.severity import Finding, Rule, SeveritySummary, summarise


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

    def findings(self) -> list[Finding]:
        found: list[Finding] = []
        if self.resolution.status == Status.FAIL:
            found.append(Finding.of(Rule.NAMESPACE_UNRESOLVED, self.uri, self.resolution.error))
        for term in self.terms:
            if term.status == Status.FAIL:
                found.append(Finding.of(Rule.EXTERNAL_TERM_NOT_FOUND, term.term_uri, term.error))
            elif term.status == Status.WARN:
                found.append(Finding.of(
                    Rule.EXTERNAL_TERM_DEPRECATED, term.term_uri,
                    f"Deprecated upstream ({term.deprecated})." if term.deprecated else None,
                ))
        return found


class UnusedPrefix(BaseModel):
    """A prefix declared but never used in any triple."""

    prefix: str
    uri: str


class LangTagIssue(BaseModel):
    """A single language-tag consistency issue on one subject+property."""

    subject: str
    subject_uri: str = ""
    """Full IRI of the subject, empty for blank nodes. `subject` is the
    shortened prefix:local form used for display."""
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
    """Summary of language tag consistency across internally defined terms."""

    properties_checked: int = 0
    languages_used: list[str] = Field(default_factory=list)
    property_summaries: list[LangTagPropertySummary] = Field(default_factory=list)
    issues: list[LangTagIssue] = Field(default_factory=list)
    status: Status = Status.SKIP

    def findings(self) -> list[Finding]:
        found = [Finding.of(Rule.LANG_TAG_INCONSISTENT, i.subject_uri or i.subject, i.detail) for i in self.issues]
        if not found and self.status == Status.WARN:
            found.append(Finding.of(
                Rule.LANG_TAG_MISSING,
                message="Labels or definitions are present but none carry a language tag.",
            ))
        return found


class LicenseCheck(BaseModel):
    """Ontology licence check."""

    iri: str
    name: str
    is_open: bool
    is_recommended: bool
    status: Status


class LicenseReport(BaseModel):
    """Summary of ontology licence compliance."""

    checks: list[LicenseCheck] = Field(default_factory=list)

    @property
    def status(self) -> str:
        if len(self.checks) == 0 or any(c.status == Status.FAIL for c in self.checks):
            return Status.FAIL
        elif any(c.status == Status.WARN for c in self.checks) or len(self.checks) > 1:
            return Status.WARN
        return Status.OK

    @property
    def recommended_licenses(self) -> list:
        return [c for c in self.checks if c.status == Status.OK]

    @property
    def open_licenses(self) -> list:
        return [c for c in self.checks if c.status == Status.WARN]

    @property
    def non_open_licenses(self) -> list:
        return [c for c in self.checks if c.status == Status.FAIL]

    @property
    def license_count(self) -> int:
        return len(self.checks)

    def findings(self) -> list[Finding]:
        if not self.checks:
            return [Finding.of(Rule.LICENSE_MISSING, message="No licence declared.")]
        found: list[Finding] = []
        for c in self.checks:
            if c.status == Status.FAIL:
                found.append(Finding.of(Rule.LICENSE_NOT_OPEN, c.iri, f"{c.name} is not an open licence."))
            elif c.status == Status.WARN:
                found.append(Finding.of(
                    Rule.LICENSE_NOT_RECOMMENDED, c.iri,
                    f"{c.name} is open, but not one of the recommended licences.",
                ))
        if len(self.checks) > 1:
            found.append(Finding.of(Rule.LICENSE_MULTIPLE, message=f"{len(self.checks)} licences declared."))
        return found


class MetadataCheck(BaseModel):
    """One ontology metadata check derived from the SHACL shapes."""

    key: str
    label: str
    property: str
    tier: str  # "core" or "additional"; both are recommendations
    status: Status
    message: str | None = None


class MetadataReport(BaseModel):
    """Summary of ontology-level metadata completeness."""

    checks: list[MetadataCheck] = Field(default_factory=list)

    @property
    def passed_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.OK)

    @property
    def missing(self) -> list[MetadataCheck]:
        return [c for c in self.checks if c.status != Status.OK]

    @property
    def total_checks(self) -> int:
        return len(self.checks)

    def findings(self) -> list[Finding]:
        return [Finding.of(Rule.METADATA_MISSING, c.property, c.message or f"Missing {c.label}.") for c in self.missing]


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

    def findings(self) -> list[Finding]:
        found: list[Finding] = []
        for c in self.checks:
            if not c.has_label:
                found.append(Finding.of(Rule.LABEL_MISSING, c.term, f"{c.display_name} has no rdfs:label."))
            if not c.has_comment:
                found.append(Finding.of(Rule.COMMENT_MISSING, c.term, f"{c.display_name} has no rdfs:comment."))
        return found


class InternalTermIssue(BaseModel):
    """One term in the ontology's own namespace that is referenced but never defined."""

    term: str
    display_name: str


class InternalTermReference(BaseModel):
    """One term referenced in the ontology's own namespace, and whether it is defined."""

    term: str
    display_name: str
    defined: bool


class NonOntologyTermIssue(BaseModel):
    """A skos:Concept defined in the ontology's own namespace.

    ``type_label`` is always "SKOS concept"; kept as a field for display
    consistency with other issue tables.
    """

    term: str
    display_name: str
    type_label: str


class NonOntologyTermsReport(BaseModel):
    """skos:Concept instances defined in the ontology's own namespace.

    An OWL ontology should define schema: classes, properties, and datatypes.
    A SKOS concept scheme is subject-matter data, not schema, so it is
    flagged when mixed into the same namespace. Named individuals are
    deliberately not flagged: many ontologies define a small, fixed set of
    individuals alongside their schema (e.g. OWL-Time's days of week), which
    is a common, legitimate pattern rather than accidental instance data.
    """

    total_flagged: int = 0
    terms: list[NonOntologyTermIssue] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    def findings(self) -> list[Finding]:
        return [
            Finding.of(Rule.NON_ONTOLOGY_TERM, t.term, f"{t.display_name} is a skos:Concept in the ontology's own namespace.")
            for t in self.terms
        ]


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
    referenced: list[InternalTermReference] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    def findings(self) -> list[Finding]:
        return [
            Finding.of(Rule.INTERNAL_TERM_UNDEFINED, t.term, f"{t.display_name} is referenced but never defined.")
            for t in self.undefined
        ]


class InternalTermEntry(BaseModel):
    """One term defined in the ontology's own namespace, with its category.

    ``category`` is one of: Class, Object property, Datatype property,
    Annotation property, Property (a generically typed property), Datatype,
    Named individual, Untyped. ``naming_ok`` reflects the capitalisation
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
    """Categorisation of the ontology's own terms plus naming conventions."""

    total_terms: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)
    entries: list[InternalTermEntry] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    @property
    def naming_issues(self) -> list[InternalTermEntry]:
        return [e for e in self.entries if not e.naming_ok]

    def findings(self) -> list[Finding]:
        return [Finding.of(Rule.NAMING_CONVENTION, e.term, e.naming_message) for e in self.naming_issues]


class DomainRangeCheck(BaseModel):
    """Domain and range completeness and correctness for one property."""

    term: str
    display_name: str
    category: str  # "Object property" or "Datatype property"
    has_domain: bool = False
    has_range: bool = False
    status: Status = Status.OK
    message: str | None = None
    mismatches: list[str] = Field(default_factory=list)
    """Messages for a domain or range of the wrong kind (a datatype used as a
    domain, an object property ranging over a datatype, and so on)."""
    omissions: list[str] = Field(default_factory=list)
    """Messages for a missing domain or range."""
    deprecated: str | None = None
    """Set to the deprecation marker (e.g. ``owl:DeprecatedClass``) when this
    property is marked deprecated; domain and range issues are not raised for it."""

    def findings(self) -> list[Finding]:
        return [
            Finding.of(Rule.DOMAIN_RANGE_MISMATCH, self.term, message)
            for message in self.mismatches
        ] + [
            Finding.of(Rule.DOMAIN_RANGE_MISSING, self.term, message)
            for message in self.omissions
        ]


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

    def findings(self) -> list[Finding]:
        return [finding for check in self.checks for finding in check.findings()]


class DatatypeUsage(BaseModel):
    """One datatype used by the ontology, and whether it is recognised."""

    datatype: str
    display_name: str
    count: int = 0
    sources: list[str] = Field(default_factory=list)  # "range", "literal", "declared"
    recognised: bool = True
    status: Status = Status.OK
    message: str | None = None


class DatatypeReport(BaseModel):
    """Inventory of datatypes used, flagging any that are not recognised."""

    total_datatypes: int = 0
    usages: list[DatatypeUsage] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    @property
    def recognised(self) -> int:
        return sum(1 for u in self.usages if u.recognised)

    @property
    def unrecognised(self) -> list[DatatypeUsage]:
        return [u for u in self.usages if not u.recognised]

    def findings(self) -> list[Finding]:
        return [Finding.of(Rule.DATATYPE_UNRECOGNISED, u.datatype, u.message) for u in self.unrecognised]


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
    def skipped(self) -> bool:
        """True when imports are declared but resolution was not attempted."""
        return bool(self.checks) and all(c.resolution.status == Status.SKIP for c in self.checks)

    @property
    def total(self) -> int:
        return len(self.checks)

    def findings(self) -> list[Finding]:
        return [Finding.of(Rule.IMPORT_UNRESOLVED, c.iri, c.resolution.error) for c in self.broken]


class IRINamespaceStrategy(BaseModel):
    """Hash vs slash usage for one declared owl:Ontology base IRI's own terms."""

    namespace: str
    strategy: str = "none"  # "hash" | "slash" | "mixed"
    hash_count: int = 0
    slash_count: int = 0
    hash_examples: list[str] = Field(default_factory=list)
    slash_examples: list[str] = Field(default_factory=list)


class IRIStrategyReport(BaseModel):
    """Hash vs slash IRI strategy used by the ontology's own defined terms.

    Consistency is judged per declared owl:Ontology base IRI, not pooled
    across all of them: an ontology that bundles more than one base IRI
    (e.g. the W3C PROV family's prov/prov-o) may use a different, but
    internally consistent, style per base IRI without being flagged. Only
    mixing hash and slash within ONE base IRI's own terms triggers a warning.
    """

    ontology_iri: str | None = None
    namespaces: list[IRINamespaceStrategy] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    def findings(self) -> list[Finding]:
        return [
            Finding.of(
                Rule.IRI_STRATEGY_MIXED, ns.namespace,
                f"{ns.hash_count} hash-style and {ns.slash_count} slash-style terms in the same namespace.",
            )
            for ns in self.namespaces
            if ns.strategy == "mixed"
        ]


class IRISchemeConflict(BaseModel):
    """One host that is referenced under both http:// and https://."""

    host: str
    http_count: int = 0
    https_count: int = 0
    http_examples: list[str] = Field(default_factory=list)
    https_examples: list[str] = Field(default_factory=list)


class IRISchemeHost(BaseModel):
    """One host referenced under a single, consistent scheme."""

    host: str
    scheme: str
    count: int = 0
    examples: list[str] = Field(default_factory=list)


class IRISchemeReport(BaseModel):
    """Per-host http vs https scheme consistency across all IRIs used."""

    total_hosts: int = 0
    http_only_hosts: int = 0
    https_only_hosts: int = 0
    hosts: list[IRISchemeHost] = Field(default_factory=list)
    conflicts: list[IRISchemeConflict] = Field(default_factory=list)
    status: Status = Status.SKIP
    message: str | None = None

    def findings(self) -> list[Finding]:
        return [
            Finding.of(
                Rule.IRI_SCHEME_MIXED, c.host,
                f"{c.http_count} http:// and {c.https_count} https:// references.",
            )
            for c in self.conflicts
        ]


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

    def findings(self) -> list[Finding]:
        return [
            Finding.of(Rule.INCONSISTENT_INDIVIDUAL, iri, "Named individual is inconsistent with its class restrictions.")
            for iri in self.inconsistent_individuals
        ] + [
            Finding.of(Rule.UNSATISFIABLE_CLASS, iri, "Class is unsatisfiable (equivalent to owl:Nothing).")
            for iri in self.unsatisfiable_classes
        ]

    def findings_for_check(self, key: str) -> list[Finding]:
        findings = self.findings()
        if key == "ontology_consistency":
            return findings
        rule = {
            "inconsistent_individuals": Rule.INCONSISTENT_INDIVIDUAL,
            "unsatisfiable_classes": Rule.UNSATISFIABLE_CLASS,
        }[key]
        return [finding for finding in findings if finding.rule == rule]


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
    license: LicenseReport | None = None
    reasoner: ReasonerReport | None = None

    def external_terms_for_namespace(self, namespace: NamespaceReport) -> list[TermCheck]:
        """Exclude missing datatypes already covered by the datatype check."""
        datatypes = {u.datatype for u in self.datatypes.unrecognised} if self.datatypes else set()
        return [
            term for term in namespace.terms
            if not (term.status == Status.FAIL and term.term_uri in datatypes)
        ]

    @property
    def external_term_checks(self) -> list[tuple[NamespaceReport, TermCheck]]:
        return [
            (namespace, term)
            for namespace in self.namespaces
            for term in self.external_terms_for_namespace(namespace)
        ]

    @property
    def namespace_resolution_skipped(self) -> bool:
        return bool(self.namespaces) and all(
            ns.resolution.status == Status.SKIP for ns in self.namespaces
        )

    @property
    def external_terms_unchecked(self) -> bool:
        terms = self.external_term_checks
        return self.namespace_resolution_skipped or (
            bool(terms) and all(term.status == Status.SKIP for _, term in terms)
        )

    def findings(self) -> list[Finding]:
        """Every individual finding across all checks."""
        found = [Finding.of(Rule.PARSE_ERROR, message=err) for err in self.parse_errors]
        # An unrecognised datatype is reported once, by the datatypes check,
        # even when the datatype's namespace check also rejects it.
        for ns in self.namespaces:
            term_iris = {t.term_uri for t in self.external_terms_for_namespace(ns)}
            found += [
                f for f in ns.findings()
                if f.rule != Rule.EXTERNAL_TERM_NOT_FOUND or f.subject in term_iris
            ]
        found += [
            Finding.of(Rule.UNUSED_PREFIX, p.uri, f"Prefix {p.prefix or '(default)'}: is declared but never used.")
            for p in self.unused_prefixes
        ]
        for section in (
            self.ontology_metadata, self.imports, self.iri_strategy, self.iri_scheme, self.license,
            self.internal_terms, self.term_inventory, self.domains_ranges, self.datatypes,
            self.non_ontology_terms, self.definition_docs, self.lang_tags, self.reasoner,
        ):
            if section is not None:
                found += section.findings()
        return found

    @computed_field  # type: ignore[prop-decorator]
    @property
    def severity_summary(self) -> SeveritySummary:
        """Counts of individual errors, warnings and recommendations."""
        return summarise(self.findings())

    @property
    def has_errors(self) -> bool:
        """True only for errors; warnings and recommendations never count."""
        return self.severity_summary.has_errors

    @property
    def total_namespaces(self) -> int:
        return len(self.namespaces)

    @property
    def total_terms(self) -> int:
        return sum(ns.total_terms for ns in self.namespaces)
