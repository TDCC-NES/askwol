"""Format validation reports for terminal, JSON, and Markdown output."""

from __future__ import annotations

from html import escape as escape_html
from urllib.parse import quote, urlsplit

from rich.console import Console
from rich.markup import escape as escape_markup
from rich.text import Text
from rich.table import Table

from askwol.models import Status, ValidationReport
from askwol.report_data import ReportView
from askwol.severity import (
    RULE_SEVERITY,
    SEVERITY_ORDER,
    SEVERITY_STYLES,
    Finding,
    Rule,
    Severity,
    SeveritySummary,
    count_label,
    worst_severity,
)
from askwol.checks import CHECK_CATEGORIES, CHECK_NUMBERS, CHECKS, CLUSTER_NUMBERS, DATATYPE_SCOPE, REASONER_SCOPE

CATEGORIES = CHECK_CATEGORIES


def report_as_json(report: ValidationReport) -> str:
    return report.model_dump_json(indent=2)


_CHECK_TITLES = {c["report_anchor"]: c["title"].replace("&amp;", "&") for c in CHECKS}


def _md_severity(rule: Rule) -> str:
    return RULE_SEVERITY[rule].value


def _md_text(value: str) -> str:
    """Keep source diagnostics and provenance as literal Markdown text."""
    value = escape_html(value, quote=False).replace("\\", "\\\\")
    for char in "`*_[]|#":
        value = value.replace(char, "\\" + char)
    return value.replace("\n", "<br>")


def _md_link(url: str) -> str:
    body = _md_text(url)
    try:
        parsed = urlsplit(url)
    except ValueError:
        return body
    if (parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc
            or any(ord(char) <= 32 or ord(char) == 127 for char in url)):
        return body
    target = quote(url, safe=":/?#[]@!$&'*+,;=%")
    return f"[{body}](<{target}>)"


def _guidance_links(summary: SeveritySummary) -> list[tuple[str, str]]:
    """One guide link per check with actionable findings."""
    found = {finding.check: finding.guide_url for finding in summary.findings if finding.guide_url}
    return [(_CHECK_TITLES[check["report_anchor"]], found[check["report_anchor"]])
            for check in CHECKS if check["report_anchor"] in found]


def _check_rollup(summary: SeveritySummary) -> list[tuple[Severity, str, int]]:
    """Count each check's findings separately for each severity."""
    rollup: list[tuple[Severity, str, int]] = []
    for severity in SEVERITY_ORDER:
        for check in CHECKS:
            anchor = check["report_anchor"]
            count = sum(f.severity == severity for f in summary.for_check(anchor))
            if count:
                rollup.append((severity, anchor, count))
    return rollup


def report_as_markdown(report: ValidationReport) -> str:
    """Generate a clear, human-readable Markdown report."""
    return _MarkdownReport(report).render()


class _MarkdownReport:
    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        self.lines: list[str] = []
        self.w = self.lines.append
        self.view = ReportView(report)
        self.summary = self.view.summary
        self.external_terms = self.view.external_terms
        self.ok_terms = len(self.view.external_by_status[Status.OK])
        self.fail_terms = len(self.view.external_by_status[Status.FAIL])
        self.warn_terms = len(self.view.external_by_status[Status.WARN])
        self.skip_terms = len(self.view.external_by_status[Status.SKIP])

    def render(self) -> str:
        self._header()
        self._input_messages()
        if self.report.input_error or self.report.parse_errors:
            self.w("**Ontology checks were not run.**")
            self.w("")
            self._severity_counts()
            return "\n".join(self.lines)
        self._summary()
        self._imports()
        self._iri_strategy()
        self._iri_scheme()
        self._license()
        self._namespaces()
        self._external_terms()
        self._unused_prefixes()
        self._metadata()
        self._internal_terms()
        self._inventory()
        self._domains_ranges()
        self._datatypes()
        self._documentation()
        self._reasoner()
        self._language_tags()
        self._non_ontology_terms()
        self._guidance()
        return "\n".join(self.lines)

    def _header(self) -> None:
        self.w("# Ontology Check Report")
        self.w("")
        self.w(f"**File:** `{self.report.file}`")
        self.w("")

    def _input_messages(self) -> None:
        if self.report.input_warnings:
            self.w("## Source guidance")
            self.w("")
            for warning in self.report.input_warnings:
                self.w(f"- {_md_text(warning)}")
            self.w("")
        diagnostic = self.report.input_error
        if diagnostic:
            label = "Parse error" if diagnostic.code == "invalid_rdf" else "Input error"
            self.w(f"## {label}")
            self.w("")
            self.w(_md_text(diagnostic.message))
            if diagnostic.source:
                self.w("")
                self.w(f"Context: {_md_link(diagnostic.source)}")
            if parser_message := diagnostic.parser_message():
                self.w("")
                self.w(_md_text(parser_message))
            if diagnostic.guidance:
                self.w("")
                self.w(_md_text(diagnostic.guidance))
            if diagnostic.suggested_url:
                self.w("")
                self.w(f"Suggested URL: {_md_link(diagnostic.suggested_url)}")
            if diagnostic.guide_url:
                self.w("")
                title = "Help with RDF syntax" if diagnostic.code == "invalid_rdf" else "Learn more"
                self.w(f"{title}: {_md_link(diagnostic.guide_url)}")
            self.w("")
        remaining_errors = [err for err in self.report.parse_errors
                            if diagnostic is None or err != diagnostic.message]
        if remaining_errors:
            self.w("## Parse Errors")
            self.w("")
            for err in remaining_errors:
                self.w(f"- {_md_text(err)}")
            self.w("")

    def _severity_counts(self) -> None:
        counts = "  ".join(
            f"{SEVERITY_STYLES[sev].glyph} {count_label(sev, self.summary.count(sev))}" for sev in SEVERITY_ORDER
        )
        self.w(f"> {counts}")
        self.w("")

    def _guidance(self) -> None:
        links = _guidance_links(self.summary)
        if links:
            self.w("## Learn more")
            self.w("")
            for title, url in links:
                self.w(f"- {title}: {_md_link(url)}")
            self.w("")

    def _summary(self) -> None:
        # Summary box at top
        self.w("## Summary")
        self.w("")
        self.ok_ns = [ns for ns in self.report.namespaces if ns.resolution.status == Status.OK and ns.resolution.is_valid_rdf]
        self.html_ns = [ns for ns in self.report.namespaces if ns.resolution.status == Status.OK and not ns.resolution.is_valid_rdf]
        self.fail_ns = [ns for ns in self.report.namespaces if ns.resolution.status == Status.FAIL]

        self.w("| | Count |")
        self.w("|---|---|")
        self.w(f"| Namespaces checked | {sum(ns.resolution.status != Status.SKIP for ns in self.report.namespaces)} |")
        self.w(f"| Namespaces with RDF | {len(self.ok_ns)} |")
        if self.html_ns:
            self.w(f"| Namespaces without retrieved RDF | {len(self.html_ns)} |")
        if self.fail_ns:
            self.w(f"| Namespace retrieval failures | {len(self.fail_ns)} |")
        self.w(f"| External terms to check | {len(self.external_terms)} |")
        self.w(f"| Terms confirmed in vocabulary | {self.ok_terms} |")
        meta = self.report.ontology_metadata
        if meta and meta.total_checks:
            self.w(f"| Ontology metadata present | {meta.passed_checks}/{meta.total_checks} |")
        docs = self.report.definition_docs
        if docs and docs.total_definitions:
            self.w(f"| Definitions with a label | {docs.with_label}/{docs.total_definitions} |")
            self.w(f"| Comment recommendation met | {docs.with_comment}/{docs.total_definitions} |")
            if docs.deprecated_count:
                self.w(f"| Deprecated terms exempt from documentation checks | {docs.deprecated_count} |")
        it = self.report.internal_terms
        if it and it.status != Status.SKIP:
            self.w(f"| Internal terms defined | {it.defined}/{it.total_referenced} |")
            if it.undefined:
                self.w(f"| **Internal terms referenced but not defined** | **{len(it.undefined)}** |")
        reasoner = self.report.reasoner
        if reasoner:
            self.w(f"| Contradictions | {'detected' if reasoner.inconsistent_individuals else 'none detected'} |")
            if reasoner.unsatisfiable_classes:
                self.w(f"| Unsatisfiable classes | {len(reasoner.unsatisfiable_classes)} |")
        if self.fail_terms:
            self.w(f"| **Terms NOT found in vocabulary** | **{self.fail_terms}** |")
        if self.warn_terms:
            self.w(f"| Terms deprecated upstream | {self.warn_terms} |")
        if self.skip_terms:
            self.w(f"| Terms not checkable (namespace unavailable) | {self.skip_terms} |")
        self.w("")

        self._severity_counts()
        rollup = _check_rollup(self.summary)
        if rollup:
            self.w("| Level | Check | Findings |")
            self.w("|-------|-------|----------|")
            for severity, anchor, n in rollup:
                style = SEVERITY_STYLES[severity]
                self.w(f"| {style.glyph} {style.label} | {_CHECK_TITLES[anchor]} | {n} |")
            self.w("")

    def _imports(self) -> None:
        # Imports
        imp = self.report.imports
        if imp is not None:
            self.w("## Imports")
            self.w("")
            self.w("Directly declared `owl:imports` targets must provide parseable RDF. "
              "Nested imports are not followed, and imported axioms are not used by the other checks.")
            self.w("")
            if imp.skipped:
                self.w(f"> {len(imp.checks)} declared import(s), resolution skipped")
            elif imp.broken:
                self.w(f"> {len(imp.broken)} of {len(imp.checks)} declared import(s) do not resolve")
            elif imp.discovered:
                self.w(f"> {len(imp.discovered)} declared import(s) required linked/alternative RDF documents; other tools may not discover them.")
            elif imp.checks:
                self.w(f"> {len(imp.checks)} declared import(s), all resolve")
            else:
                self.w("> no `owl:imports` declared")
            self.w("")
            if imp.checks:
                self.w("| Import | Status | Detail |")
                self.w("|--------|--------|--------|")
                for c in imp.checks:
                    res = c.resolution
                    status_label = ("not checked" if res.status == Status.SKIP else
                                    "ok" if res.status == Status.OK else _md_severity(Rule.IMPORT_UNRESOLVED))
                    bits = []
                    if res.http_status:
                        bits.append(f"HTTP {res.http_status}")
                    if res.content_type:
                        bits.append(res.content_type)
                    if res.is_valid_rdf is not None:
                        bits.append("valid RDF" if res.is_valid_rdf else "invalid RDF")
                    if res.error:
                        bits.append(res.error)
                    detail = ", ".join(_md_text(bit) for bit in bits)
                    if res.discovery_note:
                        detail += f"; {_md_text(res.discovery_note)}"
                    if res.retrieved_url and res.retrieved_url != res.uri:
                        detail += f"; Retrieved RDF: {_md_link(res.retrieved_url)}"
                    self.w(f"| {_md_link(c.iri)} | {status_label} | {detail} |")
                self.w("")

    def _iri_strategy(self) -> None:
        # IRI strategy (hash vs slash) for the ontology's own defined terms
        iri = self.report.iri_strategy
        if iri is not None and iri.status != Status.SKIP:
            self.w("## IRI strategy")
            self.w("")
            self.w("A consistent IRI pattern for the ontology's own terms: either every term sits under a "
              "fragment (`http://example.org/ont#Term`, hash) or every term is its own slash path "
              "(`http://example.org/ont/Term`, slash). Mixing both within the same base IRI confuses "
              "consumers and tooling; an ontology that bundles more than one base IRI may use a "
              "different, internally consistent style for each.")
            self.w("")
            multi = len(iri.namespaces) > 1
            for ns in iri.namespaces:
                label = f" for `{ns.namespace}`" if multi else ""
                if ns.strategy == "mixed":
                    self.w(f"> **Mixed**{label}: {ns.hash_count} hash-style and {ns.slash_count} slash-style terms in the same namespace.")
                    self.w("")
                    if ns.hash_examples:
                        self.w("<details>")
                        self.w(f"<summary>Hash style examples ({ns.hash_count})</summary>")
                        self.w("")
                        for ex in ns.hash_examples:
                            self.w(f"- `{ex}`")
                        self.w("")
                        self.w("</details>")
                        self.w("")
                    if ns.slash_examples:
                        self.w("<details>")
                        self.w(f"<summary>Slash style examples ({ns.slash_count})</summary>")
                        self.w("")
                        for ex in ns.slash_examples:
                            self.w(f"- `{ex}`")
                        self.w("")
                        self.w("</details>")
                        self.w("")
                else:
                    count = ns.hash_count if ns.strategy == "hash" else ns.slash_count
                    self.w(f"> **{ns.strategy.capitalize()} pattern**{label} used consistently across all {count} defined term(s).")
                    self.w("")
                    examples = ns.hash_examples if ns.strategy == "hash" else ns.slash_examples
                    if examples:
                        self.w("<details>")
                        self.w(f"<summary>Show examples ({len(examples)})</summary>")
                        self.w("")
                        for ex in examples:
                            self.w(f"- `{ex}`")
                        self.w("")
                        self.w("</details>")
                        self.w("")

    def _iri_scheme(self) -> None:
        # IRI scheme consistency (http vs https) per namespace
        sch = self.report.iri_scheme
        if sch is not None and sch.status != Status.SKIP:
            self.w("## IRI scheme (http vs https)")
            self.w("")
            self.w("In RDF, `http://example.org/X` and `https://example.org/X` are **different IRIs**. "
              "Within one ontology, each namespace should appear under exactly one scheme.")
            self.w("")
            if sch.status == Status.WARN:
                self.w(f"> **{len(sch.conflicts)}** namespace(s) are referenced under both `http://` and `https://` in the same ontology.")
                self.w("")
                self.w("<details>")
                self.w(f"<summary>Show conflicting namespaces ({len(sch.conflicts)})</summary>")
                self.w("")
                self.w("| Namespace | http:// count | https:// count |")
                self.w("|------|---------------|----------------|")
                for c in sch.conflicts:
                    self.w(f"| `{c.host}` | {c.http_count} | {c.https_count} |")
                self.w("")
                self.w("</details>")
                self.w("")
            else:
                self.w(f"> **{sch.total_hosts}** namespace(s) referenced, each under a single scheme "
                  f"({sch.http_only_hosts} http://, {sch.https_only_hosts} https://).")
                self.w("")
            if sch.hosts:
                self.w("<details>")
                self.w(f"<summary>Show namespaces ({len(sch.hosts)})</summary>")
                self.w("")
                self.w("| Namespace | Scheme | Count |")
                self.w("|------|--------|-------|")
                for h in sch.hosts:
                    self.w(f"| `{h.host}` | {h.scheme}:// | {h.count} |")
                self.w("")
                self.w("</details>")
                self.w("")

    def _license(self) -> None:
        # Open licence compliance
        lcns = self.report.license
        if lcns is not None:
            self.w("## Open licence")
            self.w("")
            self.w("Ontology-header `dcterms:license` and `schema:license` values are checked "
                "against known licences. Unrecognised licences have not been assessed for openness.")
            self.w("")
            if lcns.status != Status.OK:
                license_count = len(lcns.checks)
                if license_count == 0:
                    self.w("> No licence declared.")
                    self.w("")
                else:
                    plural = "s" if license_count > 1 else ""
                    self.w(f"> {license_count} licence{plural} declared.")
                    self.w("")
                    self.w("<details>")
                    self.w("")
                    self.w("| Licence | Licence IRI | Licence Category |")
                    self.w("|---------|-------------|------------------|")
                    for c in lcns.checks:
                        self.w(f"| {c.name} | {c.iri} | {c.category} |")
                    self.w("")
                    self.w("</details>")
                    self.w("")
            else:
                c = lcns.checks[0]
                self.w(f"> 1 recommended licence declared"
                  f" ({c.name}: `{c.iri}`).")
                self.w("")

    def _namespaces(self) -> None:
        # Group namespaces by status for clarity
        if self.ok_ns:
            self.w("## Namespaces with valid RDF")
            self.w("")
            self.w("These namespaces returned parseable RDF for the subject-position term checks.")
            self.w("")
            provenance_present = any(
                ns.resolution.discovery_note or (
                    ns.resolution.retrieved_url and ns.resolution.retrieved_url != ns.uri
                ) for ns in self.ok_ns
            )
            self.w("| Prefix | URI | Terms | Verified |" + (" Retrieval |" if provenance_present else ""))
            self.w("|--------|-----|-------|----------|" + ("-----------|" if provenance_present else ""))
            for ns in self.ok_ns:
                terms = self.report.external_terms_for_namespace(ns)
                ok = sum(t.status == Status.OK for t in terms)
                total = len(terms)
                check = "all" if ok == total else f"{ok}/{total}"
                provenance = _md_text(ns.resolution.discovery_note or "")
                retrieved = ns.resolution.retrieved_url
                if retrieved and retrieved != ns.uri:
                    provenance += f" Retrieved RDF: {_md_link(retrieved)}"
                row = f"| `{ns.prefix}` | {ns.uri} | {total} | {check} |"
                self.w(row + (f" {provenance} |" if provenance_present else ""))
            self.w("")

        if self.html_ns:
            self.w("## Namespaces without retrieved RDF")
            self.w("")
            self.w("No parseable RDF was retrieved for these namespaces. "
              "Terms can still be checked against a built-in term list where available.")
            self.w("")
            self.w("| Prefix | URI | Terms | Content-Type |")
            self.w("|--------|-----|-------|-------------|")
            for ns in self.html_ns:
                ct = ns.resolution.content_type or "unknown"
                self.w(f"| `{ns.prefix}` | {ns.uri} | {len(self.report.external_terms_for_namespace(ns))} | `{ct}` |")
            self.w("")

        if self.fail_ns:
            self.w("## Namespace retrieval failures")
            self.w("")
            self.w("Retrieval failed for these namespace URLs. See the reported errors.")
            self.w("")
            self.w("| Prefix | URI | Error |")
            self.w("|--------|-----|-------|")
            for ns in self.fail_ns:
                err = ns.resolution.error or "unknown"
                self.w(f"| `{ns.prefix}` | {ns.uri} | {err} |")
            self.w("")

    def _external_terms(self) -> None:
        # External term definitions: per-term verification against the remote vocabulary
        if self.report.namespaces:
            self.w("## External term definitions")
            self.w("")
            self.w("External terms used as subjects are checked against the retrieved vocabulary. "
              "Terms not found there and terms marked deprecated are reported. "
              "Unknown datatypes are reported under Datatypes.")
            self.w("")
            term_summary_bits = [f"{self.ok_terms} confirmed"]
            if self.fail_terms:
                term_summary_bits.append(f"{self.fail_terms} not found")
            if self.warn_terms:
                term_summary_bits.append(f"{self.warn_terms} deprecated upstream")
            if self.skip_terms:
                term_summary_bits.append(f"{self.skip_terms} skipped (namespace unavailable)")
            if self.view.terms_unchecked:
                self.w("> Not checked (namespaces not resolved).")
            elif not self.external_terms:
                self.w("> No external terms to check.")
            else:
                self.w(f"> {', '.join(term_summary_bits)} of {len(self.external_terms)} total.")
            self.w("")

            failed_terms_flat = self.view.external_by_status[Status.FAIL]
            deprecated_terms_flat = self.view.external_by_status[Status.WARN]
            skipped_terms_flat = self.view.external_by_status[Status.SKIP]
            ok_terms_flat = self.view.external_by_status[Status.OK]

            if failed_terms_flat:
                self.w("<details>")
                self.w(f"<summary>Terms not found in their vocabulary ({len(failed_terms_flat)})</summary>")
                self.w("")
                self.w("| Term | Prefix | Full URI |")
                self.w("|------|--------|----------|")
                for ns, t in failed_terms_flat:
                    self.w(f"| `{t.local_name}` | `{ns.prefix}` | {t.term_uri} |")
                self.w("")
                self.w("</details>")
                self.w("")

            if deprecated_terms_flat:
                self.w("<details>")
                self.w(f"<summary>Deprecated upstream ({len(deprecated_terms_flat)})</summary>")
                self.w("")
                self.w("| Term | Prefix | Marker | Full URI |")
                self.w("|------|--------|--------|----------|")
                for ns, t in deprecated_terms_flat:
                    self.w(f"| `{t.local_name}` | `{ns.prefix}` | {t.deprecated} | {t.term_uri} |")
                self.w("")
                self.w("</details>")
                self.w("")

            if skipped_terms_flat:
                self.w("<details>")
                self.w(f"<summary>Terms not checkable, namespace unavailable ({len(skipped_terms_flat)})</summary>")
                self.w("")
                self.w("| Term | Prefix |")
                self.w("|------|--------|")
                for ns, t in skipped_terms_flat:
                    self.w(f"| `{t.local_name}` | `{ns.prefix}` |")
                self.w("")
                self.w("</details>")
                self.w("")

            if ok_terms_flat:
                self.w("<details>")
                self.w(f"<summary>Confirmed terms ({len(ok_terms_flat)})</summary>")
                self.w("")
                self.w("| Term | Prefix |")
                self.w("|------|--------|")
                for ns, t in ok_terms_flat:
                    self.w(f"| `{t.local_name}` | `{ns.prefix}` |")
                self.w("")
                self.w("</details>")
                self.w("")

    def _unused_prefixes(self) -> None:
        # Unused prefixes
        if self.report.unused_prefixes:
            self.w("## Unused prefixes")
            self.w("")
            self.w("These detected prefix bindings have no matching namespace IRI use. "
              "Consider removing them to keep the ontology clean.")
            self.w("")
            self.w("| Prefix | URI |")
            self.w("|--------|-----|")
            for up in self.report.unused_prefixes:
                pfx = up.prefix or "(default)"
                self.w(f"| `{pfx}` | {up.uri} |")
            self.w("")

    def _metadata(self) -> None:
        # Ontology metadata
        meta = self.report.ontology_metadata
        if meta and meta.checks:
            self.w("## Ontology metadata")
            self.w("")
            self.w("These checks are evaluated from SHACL shapes on the ontology header.")
            self.w("")
            self.w("<details>")
            self.w(f"<summary>Show metadata checks ({meta.total_checks})</summary>")
            self.w("")
            self.w("| Property | Group | Status |")
            self.w("|----------|-------|--------|")
            for check in meta.checks:
                status_label = "ok" if check.status == Status.OK else _md_severity(Rule.METADATA_MISSING) + " (missing)"
                self.w(f"| `{check.property}` | {check.tier} | {status_label} |")
            self.w("")
            self.w("</details>")
            self.w("")

    def _internal_terms(self) -> None:
        # Internal term definitions
        it = self.report.internal_terms
        if it and it.status != Status.SKIP and it.undefined:
            self.w("## Internal term definitions")
            self.w("")
            self.w("Terms in the ontology's own namespace that are referenced but never "
              "defined (they never appear as the subject of a triple). Usually a typo "
              "or a forgotten declaration.")
            self.w("")
            self.w(f"> {it.defined}/{it.total_referenced} referenced terms defined, {len(it.undefined)} undefined")
            self.w("")
            self.w("| Term | Full IRI |")
            self.w("|------|----------|")
            for issue in it.undefined:
                self.w(f"| `{issue.display_name}` | {issue.term} |")
            self.w("")

    def _inventory(self) -> None:
        # Term inventory and naming conventions
        inv = self.report.term_inventory
        if inv and inv.status != Status.SKIP and inv.entries:
            self.w("## Term inventory and naming")
            self.w("")
            self.w("Every term defined in the ontology's own namespace, by category. "
              "Classes should start with an uppercase letter, properties with a lowercase letter.")
            self.w("")
            counts = ", ".join(f"{n} {cat}" for cat, n in inv.category_counts.items())
            self.w(f"> {inv.total_terms} internal terms ({counts})")
            self.w("")
            if inv.naming_issues:
                self.w(f"> {len(inv.naming_issues)} naming convention issue(s)")
                self.w("")
                self.w("| Term | Category | Issue |")
                self.w("|------|----------|-------|")
                for e in inv.naming_issues:
                    self.w(f"| `{e.display_name}` | {e.category} | {e.naming_message} |")
                self.w("")
            self.w("<details>")
            self.w(f"<summary>Show all terms ({inv.total_terms})</summary>")
            self.w("")
            self.w("| Term | Category | Naming |")
            self.w("|------|----------|--------|")
            for e in sorted(inv.entries, key=lambda x: (x.category, x.display_name.lower())):
                if e.deprecated:
                    naming = f"deprecated ({e.deprecated}), not checked"
                elif e.naming_ok:
                    naming = "ok"
                else:
                    naming = "check"
                self.w(f"| `{e.display_name}` | {e.category} | {naming} |")
            self.w("")
            self.w("</details>")
            self.w("")

    def _domains_ranges(self) -> None:
        # Domains and ranges
        dr = self.report.domains_ranges
        if dr and dr.status != Status.SKIP and dr.checks:
            self.w("## Domains and ranges")
            self.w("")
            self.w("Checks directly declared domains and ranges of internal object and datatype properties. "
              "Selected named class/datatype mismatches are checked; inherited values and anonymous expressions are not evaluated.")
            self.w("")
            self.w(f"> {dr.with_domain}/{dr.total_properties} have a domain, "
              f"{dr.with_range}/{dr.total_properties} have a range, {len(dr.issues)} issue(s)")
            self.w("")
            self.w("<details>")
            summary = f"Show all properties ({dr.total_properties})"
            if dr.issues:
                summary += f" &middot; {len(dr.issues)} to review"
            self.w(f"<summary>{summary}</summary>")
            self.w("")
            self.w("| Property | Category | Domain | Range | Findings |")
            self.w("|----------|----------|--------|-------|----------|")
            for c in sorted(dr.checks, key=lambda x: (x.category, x.display_name.lower())):
                category = c.category + (f" (deprecated: {c.deprecated})" if c.deprecated else "")
                msg = "<br>".join(
                    f"{f.severity.value}: {(f.message or '').replace('<code>', '`').replace('</code>', '`')}"
                    for f in c.findings()
                )
                self.w(f"| `{c.display_name}` | {category} | {'yes' if c.has_domain else 'no'} | {'yes' if c.has_range else 'no'} | {msg} |")
            self.w("")
            self.w("</details>")
            self.w("")

    def _datatypes(self) -> None:
        # Datatypes
        dt = self.report.datatypes
        if dt and dt.status != Status.SKIP and dt.usages:
            self.w("## Datatypes")
            self.w("")
            self.w(DATATYPE_SCOPE)
            self.w("")
            self.w(f"> {dt.recognised}/{dt.total_datatypes} recognised, {len(dt.unrecognised)} unrecognised")
            self.w("")
            if dt.unrecognised:
                self.w("| Datatype | Uses |")
                self.w("|----------|------|")
                for u in dt.unrecognised:
                    self.w(f"| `{u.display_name}` | {u.count} |")
                self.w("")
            self.w("<details>")
            self.w(f"<summary>Show all datatypes ({dt.total_datatypes})</summary>")
            self.w("")
            self.w("| Datatype | Uses | Where |")
            self.w("|----------|------|-------|")
            for u in sorted(dt.usages, key=lambda x: x.display_name.lower()):
                self.w(f"| {'ok' if u.recognised else 'unrecognised'} `{u.display_name}` | {u.count} | {', '.join(u.sources)} |")
            self.w("")
            self.w("</details>")
            self.w("")

    def _documentation(self) -> None:
        # Labels and comments
        docs = self.report.definition_docs
        if docs and docs.total_definitions:
            self.w("## Labels")
            self.w("")
            self.w("Internal classes and properties only; deprecated terms are exempt.")
            self.w("")
            self.w(f"> {docs.with_label}/{docs.total_definitions} have an rdfs:label")
            if docs.deprecated_count:
                self.w(f"> {docs.deprecated_count} deprecated term(s) exempt.")
            self.w("")
            self.w("<details>")
            self.w(f"<summary>Show labels ({docs.total_definitions})</summary>")
            self.w("")
            self.w("| Term | Type | Label |")
            self.w("|------|------|-------|")
            for check in sorted(docs.checks, key=lambda c: (c.has_label, c.display_name.lower())):
                label = "exempt (deprecated)" if check.deprecated else "ok" if check.has_label else f"{_md_severity(Rule.LABEL_MISSING)}: missing"
                self.w(f"| `{check.display_name}` | {check.term_type} | {label} |")
            self.w("")
            self.w("</details>")
            self.w("")

            self.w("## Comments")
            self.w("")
            self.w("Internal classes and properties only; deprecated terms are exempt. A comment on an inverse property also satisfies this recommendation.")
            self.w("")
            self.w(f"> {docs.with_comment}/{docs.total_definitions} meet the comment recommendation")
            if docs.deprecated_count:
                self.w(f"> {docs.deprecated_count} deprecated term(s) exempt.")
            self.w("")
            self.w("<details>")
            self.w(f"<summary>Show comments ({docs.total_definitions})</summary>")
            self.w("")
            self.w("| Term | Type | Comment |")
            self.w("|------|------|---------|")
            for check in sorted(docs.checks, key=lambda c: (c.has_comment, c.display_name.lower())):
                comment = "exempt (deprecated)" if check.deprecated else "ok" if check.has_comment else f"{_md_severity(Rule.COMMENT_MISSING)}: missing"
                self.w(f"| `{check.display_name}` | {check.term_type} | {comment} |")
            self.w("")
            self.w("</details>")
            self.w("")

    def _reasoner(self) -> None:
        # Reasoner checks
        reasoner = self.report.reasoner
        if reasoner and reasoner.checks:
            self.w("## Reasoner checks")
            self.w("")
            self.w(REASONER_SCOPE)
            self.w("")
            self.w("| Check | Status | Detail |")
            self.w("|-------|--------|--------|")
            for check in reasoner.checks:
                severity = worst_severity(reasoner.findings_for_check(check.key))
                status_label = ("not checked" if check.status == Status.SKIP else
                                severity.value if severity else "ok")
                self.w(f"| {check.label} | {status_label} | {check.message or ''} |")
            self.w("")

    def _language_tags(self) -> None:
        # Language tag consistency
        lt = self.report.lang_tags
        if lt and lt.status == Status.WARN and lt.issues:
            self.w("## Language tag consistency")
            self.w("")
            self.w(f"Languages used: {', '.join(f'`{l}`' for l in lt.languages_used)}")
            self.w("")
            n_missing_tag = sum(1 for i in lt.issues if i.issue_type == "missing_tag")
            n_missing_lang = sum(1 for i in lt.issues if i.issue_type == "missing_language")
            parts = []
            if n_missing_tag:
                parts.append(f"{n_missing_tag} issue{'s' if n_missing_tag != 1 else ''} with untagged values")
            if n_missing_lang:
                parts.append(f"{n_missing_lang} issue{'s' if n_missing_lang != 1 else ''} with missing languages")
            if parts:
                self.w(f"> **{len(lt.issues)} issue{'s' if len(lt.issues) != 1 else ''}:** {' · '.join(parts)}")
                self.w("")
            self.w("| Subject | Property | Issue | Has | Expected |")
            self.w("|---------|----------|-------|-----|----------|")
            for issue in lt.issues:
                has = ", ".join(issue.languages_found) if issue.languages_found else " - "
                expected = ", ".join(issue.languages_expected)
                self.w(f"| `{issue.subject}` | `{issue.property}` | {issue.detail} | {has} | {expected} |")
            self.w("")
        elif lt and lt.status == Status.WARN:
            self.w("## Language tag consistency")
            self.w("")
            self.w(f"> **{SEVERITY_STYLES[RULE_SEVERITY[Rule.LANG_TAG_MISSING]].label}:** "
              "none of the checked labels or definitions carry a language tag (e.g. `\"Person\"@en`).")
            self.w("")

    def _non_ontology_terms(self) -> None:
        # Non-ontology terms
        sk = self.report.non_ontology_terms
        if sk and sk.status != Status.SKIP and sk.terms:
            self.w("## Non-ontology terms")
            self.w("")
            self.w("TDCC recommends considering separate management of independently maintained "
              "SKOS concept schemes. Mixing OWL and SKOS is valid.")
            self.w("")
            self.w(f"> {len(sk.terms)} skos:Concept instance(s) defined in the ontology's own namespace")
            self.w("")
            self.w("| Term | What it is | Full IRI |")
            self.w("|------|------------|----------|")
            for issue in sk.terms:
                self.w(f"| `{issue.display_name}` | {issue.type_label} | {issue.term} |")
            self.w("")


def _overview_badge(summary: SeveritySummary, anchor: str, applicable: bool) -> str:
    """OK, "-" (not applicable), or the badge of the worst finding of the check."""
    if not applicable:
        return "[dim]-[/dim]"
    worst = worst_severity(summary.for_check(anchor))
    return "[green]OK[/green]" if worst is None else _severity_badge(worst)


def _overview_line(report: ValidationReport, anchor: str, view: ReportView) -> tuple[bool, str] | None:
    """Return (applicable, detail) for one check anchor, mirroring the HTML overview.

    Returns None when the check did not run (so it is omitted from the table),
    matching the behaviour of the web report's summary. The status badge is
    not decided here: it comes from the check's findings.
    """
    S = Status
    if anchor == "ontology-metadata":
        meta = report.ontology_metadata
        if not (meta and meta.checks):
            return None
        return True, f"{meta.passed_checks}/{meta.total_checks} present"
    if anchor == "imports":
        imp = report.imports
        if not imp:
            return None
        if not imp.checks:
            return True, "no owl:imports declared"
        if imp.skipped:
            return False, "resolution skipped"
        if imp.discovered:
            return True, f"{len(imp.discovered)} found via linked/alternative RDF, {len(imp.broken)} unresolved"
        return True, f"{len(imp.checks) - len(imp.broken)}/{len(imp.checks)} declared imports resolve"
    if anchor == "iri-strategy":
        iri = report.iri_strategy
        if not iri:
            return None
        if iri.status == S.SKIP:
            return False, "skipped"
        if len(iri.namespaces) == 1:
            ns = iri.namespaces[0]
            if ns.strategy == "mixed":
                return True, f"mixed: {ns.hash_count} hash + {ns.slash_count} slash"
            count = ns.hash_count if ns.strategy == "hash" else ns.slash_count
            return True, f"{ns.strategy} style, {count} term(s)"
        return True, f"{len(iri.namespaces)} base IRIs checked"
    if anchor == "iri-scheme":
        sch = report.iri_scheme
        if not sch:
            return None
        if sch.status == S.SKIP:
            return False, "skipped"
        return True, f"{sch.total_hosts} namespace(s) checked"
    if anchor == "license":
        lcns = report.license
        if not lcns:
            return None
        if not lcns.license_count:
            return True, "no licence declared"
        kinds = [
            f"{n} {label}" for label, n in lcns.category_counts.items() if n
        ]
        plural = "s" if lcns.license_count > 1 else ""
        return True, f"{lcns.license_count} licence{plural} declared, {', '.join(kinds)}"
    if anchor == "namespaces":
        total = len(report.namespaces)
        if total == 0:
            return None
        if report.namespace_resolution_skipped:
            return False, "resolution skipped"
        ok = sum(1 for ns in report.namespaces if ns.resolution.status == S.OK)
        return True, f"{ok}/{total} resolved"
    if anchor == "unused-prefixes":
        if report.unused_prefixes:
            return True, f"{len(report.unused_prefixes)} declared but unused"
        return True, "none"
    if anchor == "external-terms":
        total = len(view.external_terms)
        ok = len(view.external_by_status[S.OK])
        fail = len(view.external_by_status[S.FAIL])
        warn = len(view.external_by_status[S.WARN])
        if view.terms_unchecked:
            return False, "not checked (namespaces not resolved)"
        if total == 0:
            return False, "no external terms to check"
        skipped = total - ok - fail - warn
        bits = [f"{ok} confirmed"]
        if fail:
            bits.append(f"{fail} not found")
        if warn:
            bits.append(f"{warn} deprecated")
        if skipped:
            bits.append(f"{skipped} skipped")
        return True, ", ".join(bits)
    if anchor == "internal-terms":
        it = report.internal_terms
        if not it:
            return None
        if it.status == S.SKIP:
            return False, "not applicable"
        return True, f"{it.defined}/{it.total_referenced} defined"
    if anchor == "term-inventory":
        inv = report.term_inventory
        if not inv:
            return None
        if inv.status == S.SKIP:
            return False, "no terms in the ontology's own namespace"
        return True, f"{inv.total_terms} terms"
    if anchor == "domains-ranges":
        dr = report.domains_ranges
        if not dr:
            return None
        if dr.status == S.SKIP:
            return False, "no object or datatype properties"
        return True, f"{dr.total_properties} property(ies) checked"
    if anchor == "datatypes":
        dt = report.datatypes
        if not dt:
            return None
        if dt.status == S.SKIP:
            return False, "no datatypes used"
        return True, f"{dt.total_datatypes} used"
    if anchor == "non-ontology-terms":
        sk = report.non_ontology_terms
        if not sk:
            return None
        if sk.status == S.SKIP:
            return False, "not applicable"
        if sk.terms:
            return True, f"{len(sk.terms)} SKOS concept(s) to review"
        return True, "no internal SKOS concepts"
    if anchor in ("labels", "comments"):
        docs = report.definition_docs
        if not docs:
            return None
        if not docs.total_definitions:
            return False, "no internal definitions to document"
        present = docs.with_label if anchor == "labels" else docs.with_comment
        detail = "have a label" if anchor == "labels" else "meet the comment recommendation"
        return True, f"{present}/{docs.total_definitions} {detail}"
    if anchor == "language-tags":
        lt = report.lang_tags
        if not lt or lt.status == Status.SKIP:
            return False, "not applicable"
        return True, ", ".join(lt.languages_used) or "no language tags"
    if anchor == "reasoner":
        reasoner = report.reasoner
        if not reasoner or not reasoner.checks:
            return None
        if not view.summary.for_check("reasoner"):
            return True, "no contradictions detected"
        return True, (
            f"{len(reasoner.inconsistent_individuals)} inconsistent individual(s), "
            f"{len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)"
        )
    return None


def _print_overview(report: ValidationReport, console: Console, view: ReportView) -> None:
    """Render the clustered checks overview, mirroring the web report."""
    overview = Table(title="Checks overview", show_header=True, header_style="bold")
    overview.add_column("Check")
    overview.add_column("Status", justify="center")
    overview.add_column("Detail", overflow="fold")

    summary = view.summary
    first = True
    for cat in CATEGORIES:
        rows = []
        for check in CHECKS:
            if check["category"] != cat["key"]:
                continue
            anchor = check["report_anchor"]
            line = _overview_line(report, anchor, view)
            if line is None:
                continue
            applicable, detail = line
            counts = _finding_counts(summary.for_check(anchor))
            if counts:
                detail = f"{detail} ({counts})"
            title = check["title"].replace("&amp;", "&")
            num = CHECK_NUMBERS.get(anchor, "")
            label = f"  {num} {title}" if num else f"  {title}"
            rows.append((label, _overview_badge(summary, anchor, applicable), detail))
        if not rows:
            continue
        if not first:
            overview.add_section()
        first = False
        label = cat["label"].replace("&amp;", "&")
        overview.add_row(f"[bold cyan]{CLUSTER_NUMBERS[cat['key']]}. {label}[/bold cyan]", "", "")
        for title, badge, detail in rows:
            overview.add_row(title, badge, Text(detail))

    if overview.row_count == 0:
        return
    console.print(overview)
    console.print()


def print_report(report: ValidationReport, console: Console | None = None) -> None:
    """Pretty-print a validation report to the terminal using rich."""
    _ConsoleReport(report, console if console is not None else Console()).render()


class _ConsoleReport:
    def __init__(self, report: ValidationReport, console: Console) -> None:
        self.report = report
        self.console = console
        self.view = ReportView(report)
        self.summary = self.view.summary

    def render(self) -> None:
        self._header()
        self._input_messages()
        if self.report.input_error or self.report.parse_errors:
            self.console.print("Ontology checks were not run.")
            self._summary()
            return
        _print_overview(self.report, self.console, self.view)
        self._imports()
        self._license()
        self._iri_strategy()
        self._iri_scheme()
        self._namespaces()
        self._external_terms()
        self._internal_terms()
        self._deprecated_terms()
        self._non_ontology_terms()
        self._unused_prefixes()
        self._metadata()
        self._inventory()
        self._domains_ranges()
        self._datatypes()
        self._documentation()
        self._language_tags()
        self._reasoner()
        self._summary()
        self._guidance()

    def _header(self) -> None:
        self.console.print()
        self.console.rule(Text("Ontology Check: " + self.report.file, style="bold"))
        self.console.print()

    def _input_messages(self) -> None:
        if self.report.input_warnings:
            self.console.print("[bold]Source guidance:[/bold]")
            for warning in self.report.input_warnings:
                self.console.print(Text("  " + warning))
            self.console.print()
        diagnostic = self.report.input_error
        if diagnostic:
            label = "Parse error" if diagnostic.code == "invalid_rdf" else "Input error"
            self.console.print(f"[bold red]{label}:[/bold red]")
            self.console.print(Text("  " + diagnostic.message))
            if diagnostic.source:
                self.console.print(Text("Context: " + diagnostic.source))
            if parser_message := diagnostic.parser_message():
                self.console.print(Text("  " + parser_message))
            if diagnostic.guidance:
                self.console.print(Text(diagnostic.guidance))
            if diagnostic.suggested_url:
                self.console.print(Text("Suggested URL: " + diagnostic.suggested_url))
            if diagnostic.guide_url:
                title = "Help with RDF syntax" if diagnostic.code == "invalid_rdf" else "Learn more"
                self.console.print(Text(title + ": " + diagnostic.guide_url))
            self.console.print()
        remaining_errors = [err for err in self.report.parse_errors
                            if diagnostic is None or err != diagnostic.message]
        if remaining_errors:
            self.console.print("[bold red]Parse errors:[/bold red]")
            for err in remaining_errors:
                self.console.print("  " + err, markup=False)
            self.console.print()

    def _guidance(self) -> None:
        links = _guidance_links(self.summary)
        if links:
            self.console.print("[bold]Learn more:[/bold]")
            for title, url in links:
                self.console.print(Text(f"  {title}: {url}"))
            self.console.print()

    def _documentation(self) -> None:
        docs = self.report.definition_docs
        if docs is None:
            return
        missing = [check for check in docs.checks
                   if not check.deprecated and (not check.has_label or not check.has_comment)]
        if missing:
            table = Table(title="Missing labels and comments", show_lines=True)
            table.add_column("Term")
            table.add_column("Full IRI")
            table.add_column("Missing")
            for check in missing:
                properties = []
                if not check.has_label:
                    properties.append("rdfs:label")
                if not check.has_comment:
                    properties.append("rdfs:comment")
                table.add_row(Text(check.display_name), Text(check.term), Text(", ".join(properties)))
            self.console.print(table)
            self.console.print()

    def _imports(self) -> None:
        # Imports
        imp = self.report.imports
        if imp is not None and imp.checks:
            self.console.print()
            if imp.skipped:
                self.console.print(f"[dim]- Imports  -  {len(imp.checks)} declared, resolution skipped[/dim]")
            elif imp.broken:
                self.console.print(_flag(RULE_SEVERITY[Rule.IMPORT_UNRESOLVED], f"Imports  -  {len(imp.broken)} of {len(imp.checks)} do not resolve"))
            elif imp.discovered:
                self.console.print(_flag(RULE_SEVERITY[Rule.IMPORT_DISCOVERED], f"Imports  -  {len(imp.discovered)} required linked/alternative RDF documents; other tools may not discover them"))
            else:
                self.console.print(f"[green]\u2713 Imports  -  {len(imp.checks)} declared, all resolve[/green]")
            imp_table = Table(title="Imports", show_lines=True)
            imp_table.add_column("Import")
            imp_table.add_column("Status", justify="center")
            imp_table.add_column("Detail")
            for c in imp.checks:
                res = c.resolution
                bits = []
                if res.http_status:
                    bits.append(f"HTTP {res.http_status}")
                if res.content_type:
                    bits.append(res.content_type)
                if res.is_valid_rdf is not None:
                    bits.append("valid RDF" if res.is_valid_rdf else "invalid RDF")
                if res.error:
                    bits.append(res.error)
                if res.discovery_note:
                    bits.append(res.discovery_note)
                if res.retrieved_url and res.retrieved_url != res.uri:
                    bits.append("Retrieved RDF: " + res.retrieved_url)
                rule = Rule.IMPORT_DISCOVERED if res.status == Status.WARN else Rule.IMPORT_UNRESOLVED
                imp_table.add_row(Text(c.iri), _item_badge(res.status, rule), Text(", ".join(bits)))
            self.console.print(imp_table)

    def _license(self) -> None:
        # Open licence compliance
        lcns = self.report.license
        if lcns is not None:
            self.console.print()
            license_table = Table(title="Licences", show_lines=True)
            license_table.add_column("IRI")
            license_table.add_column("Name")
            license_table.add_column("Status")
            license_table.add_column("Category")
            for c in lcns.checks:
                license_rule = Rule.LICENSE_NOT_OPEN if c.is_open is not True else Rule.LICENSE_NOT_RECOMMENDED
                license_table.add_row(Text(c.iri), Text(c.name), _item_badge(c.status, license_rule), c.category)
            license_count = len(lcns.checks)
            license_worst = worst_severity(lcns.findings())
            if license_worst is None:
                self.console.print(f"[green]\u2713 Open licence  -  1 recommended licence declared ({escape_markup(lcns.checks[0].name)})[/green]")
            elif license_count == 0:
                self.console.print(_flag(license_worst, "Open licence  -  no licence declared"))
            else:
                kinds = ", ".join(
                    f"{n} {label}" for label, n in lcns.category_counts.items() if n
                )
                plural = "s" if license_count > 1 else ""
                self.console.print(_flag(license_worst, f"Open licence  -  {license_count} licence{plural} declared, {kinds}"))
            if license_count > 0:
                self.console.print()
                self.console.print(license_table)

    def _iri_strategy(self) -> None:
        # IRI strategy (hash vs slash) for the ontology's own defined terms
        iri = self.report.iri_strategy
        if iri is not None and iri.status != Status.SKIP:
            self.console.print()
            multi = len(iri.namespaces) > 1
            if iri.status == Status.WARN:
                mixed = [ns for ns in iri.namespaces if ns.strategy == "mixed"]
                hash_n = sum(ns.hash_count for ns in mixed)
                slash_n = sum(ns.slash_count for ns in mixed)
                suffix = f" in {len(mixed)} of {len(iri.namespaces)} base IRI(s)" if multi else ""
                self.console.print(_flag(RULE_SEVERITY[Rule.IRI_STRATEGY_MIXED], f"IRI strategy  -  mixed: {hash_n} hash + {slash_n} slash{suffix}"))
                for ns in mixed:
                    if ns.hash_examples:
                        self.console.print(f"  [dim]hash:[/dim] {escape_markup(', '.join(ns.hash_examples))}")
                    if ns.slash_examples:
                        self.console.print(f"  [dim]slash:[/dim] {escape_markup(', '.join(ns.slash_examples))}")
            elif multi:
                self.console.print(f"[green]\u2713 IRI strategy  -  {len(iri.namespaces)} base IRIs, each consistent[/green]")
            else:
                ns = iri.namespaces[0]
                count = ns.hash_count if ns.strategy == "hash" else ns.slash_count
                self.console.print(f"[green]\u2713 IRI strategy  -  {escape_markup(ns.strategy)} style, {count} term(s)[/green]")

    def _iri_scheme(self) -> None:
        # IRI scheme consistency (http vs https) per host
        sch = self.report.iri_scheme
        if sch is not None and sch.status != Status.SKIP:
            self.console.print()
            if sch.status == Status.WARN:
                self.console.print(_flag(RULE_SEVERITY[Rule.IRI_SCHEME_MIXED], f"IRI scheme  -  {len(sch.conflicts)} namespace(s) on both http and https"))
                for c in sch.conflicts:
                    self.console.print(f"  [dim]{escape_markup(c.host)}:[/dim] {c.http_count} http, {c.https_count} https")
            else:
                self.console.print(f"[green]\u2713 IRI scheme  -  {sch.total_hosts} namespace(s), single scheme each[/green]")
                if sch.hosts:
                    self.console.print("  [dim]namespaces:[/dim] " + ", ".join(f"{escape_markup(h.host)} ({escape_markup(h.scheme)})" for h in sch.hosts))

    def _namespaces(self) -> None:
        # Namespace resolution table
        ns_table = Table(title="Namespace Resolution", show_lines=True)
        ns_table.add_column("Prefix", style="cyan")
        ns_table.add_column("URI")
        ns_table.add_column("HTTP", justify="center")
        ns_table.add_column("Valid RDF", justify="center")
        ns_table.add_column("Status", justify="center")
        provenance_present = any(
            ns.resolution.discovery_note or (
                ns.resolution.retrieved_url and ns.resolution.retrieved_url != ns.uri
            ) for ns in self.report.namespaces
        )
        if provenance_present:
            ns_table.add_column("Retrieval")

        for ns in self.report.namespaces:
            r = ns.resolution
            status_str = _item_badge(r.status, Rule.NAMESPACE_UNRESOLVED)
            http_str = str(r.http_status) if r.http_status else "-"
            rdf_str = "yes" if r.is_valid_rdf else ("no" if r.is_valid_rdf is False else "-")
            provenance = r.discovery_note or ""
            if r.retrieved_url and r.retrieved_url != r.uri:
                provenance += (" " if provenance else "") + "Retrieved RDF: " + r.retrieved_url
            row = [Text(ns.prefix or "(default)"), Text(ns.uri), http_str, rdf_str, status_str]
            if provenance_present:
                row.append(Text(provenance))
            ns_table.add_row(*row)

        self.console.print(ns_table)
        self.console.print()

    def _external_terms(self) -> None:
        # Term validation  -  grouped by status for clarity
        ok_terms = self.view.external_by_status[Status.OK]
        fail_terms = self.view.external_by_status[Status.FAIL]
        warn_terms = self.view.external_by_status[Status.WARN]
        skip_terms = self.view.external_by_status[Status.SKIP]

        if fail_terms:
            fail_table = Table(title="Terms not found in remote vocabulary", show_lines=True)
            fail_table.add_column("Term")
            fail_table.add_column("Prefix")
            fail_table.add_column("Details")
            for ns, t in fail_terms:
                fail_table.add_row(Text(t.local_name), Text(ns.prefix), Text(t.error or ""))
            self.console.print(fail_table)
            self.console.print()

        if ok_terms:
            self.console.print(f"[green]{len(ok_terms)} terms verified[/green] in vocabularies: "
                           + escape_markup(", ".join(sorted({ns.prefix for ns, _ in ok_terms}))))

        if warn_terms:
            self.console.print(_flag(RULE_SEVERITY[Rule.EXTERNAL_TERM_DEPRECATED], f"{len(warn_terms)} term(s) deprecated upstream:"))
            for ns, t in warn_terms:
                self.console.print(f"  [dim]{escape_markup(ns.prefix)}:[/dim]{escape_markup(t.local_name)} ({escape_markup(t.deprecated or '')})")

        if skip_terms:
            self.console.print(f"[dim]{len(skip_terms)} terms could not be checked[/dim] (namespace unavailable)")

    def _internal_terms(self) -> None:
        # Internal term definitions: referenced own-namespace terms must be defined
        it = self.report.internal_terms
        if it and it.status != Status.SKIP and it.undefined:
            self.console.print()
            self.console.print(_flag(RULE_SEVERITY[Rule.INTERNAL_TERM_UNDEFINED], f"Internal term definitions  -  {len(it.undefined)} referenced but never defined"))
            it_table = Table(title="Undefined internal terms", show_lines=True)
            it_table.add_column("Term")
            it_table.add_column("Full IRI")
            for issue in it.undefined:
                it_table.add_row(Text(issue.display_name), Text(issue.term))
            self.console.print(it_table)

    def _deprecated_terms(self) -> None:
        # Deprecated internal terms (own-namespace terms carrying a deprecation marker)
        inv_for_deprecated = self.report.term_inventory
        deprecated_entries = [e for e in inv_for_deprecated.entries if e.deprecated] if inv_for_deprecated else []
        if deprecated_entries:
            self.console.print()
            self.console.print(f"[yellow]\u26A0 {len(deprecated_entries)} internal term(s) marked deprecated:[/yellow]")
            for e in deprecated_entries:
                self.console.print(f"  [dim]{escape_markup(e.display_name)}[/dim] ({escape_markup(e.deprecated or '')})")

    def _non_ontology_terms(self) -> None:
        # Non-ontology terms: the ontology's own namespace should define only schema
        sk = self.report.non_ontology_terms
        if sk and sk.status != Status.SKIP and sk.terms:
            self.console.print()
            self.console.print(_flag(RULE_SEVERITY[Rule.NON_ONTOLOGY_TERM], f"Non-ontology terms  -  {len(sk.terms)} skos:Concept instance(s) in the ontology's own namespace"))
            sk_table = Table(title="Non-ontology terms", show_lines=True)
            sk_table.add_column("Term")
            sk_table.add_column("What it is")
            sk_table.add_column("Full IRI")
            for issue in sk.terms:
                sk_table.add_row(Text(issue.display_name), Text(issue.type_label), Text(issue.term))
            self.console.print(sk_table)

    def _unused_prefixes(self) -> None:
        # Unused prefixes
        if self.report.unused_prefixes:
            self.console.print()
            self.console.print(_flag(RULE_SEVERITY[Rule.UNUSED_PREFIX], f"{len(self.report.unused_prefixes)} unused prefix{'es' if len(self.report.unused_prefixes) != 1 else ''}:"))
            for up in self.report.unused_prefixes:
                pfx = up.prefix or "(default)"
                self.console.print(f"  [dim]{escape_markup(pfx)}:[/dim] <{escape_markup(up.uri)}>")

    def _metadata(self) -> None:
        # Ontology metadata
        meta = self.report.ontology_metadata
        if meta and meta.checks:
            self.console.print()
            if not meta.missing:
                self.console.print(f"[green]✓ All metadata checks passed[/green] ({meta.passed_checks}/{meta.total_checks} checks)")
            else:
                self.console.print(_flag(RULE_SEVERITY[Rule.METADATA_MISSING], "Ontology metadata") + f" - {meta.passed_checks}/{meta.total_checks} present")
                meta_table = Table(title="Ontology metadata checks", show_lines=True)
                meta_table.add_column("Property")
                meta_table.add_column("Group")
                meta_table.add_column("Status")
                meta_table.add_column("Detail")
                for check in meta.missing:
                    meta_table.add_row(Text(check.property), Text(check.tier), _item_badge(check.status, Rule.METADATA_MISSING), Text(check.message or ""))
                self.console.print(meta_table)

    def _inventory(self) -> None:
        # Term inventory naming issues
        inv = self.report.term_inventory
        if inv and inv.naming_issues:
            self.console.print()
            self.console.print(_flag(RULE_SEVERITY[Rule.NAMING_CONVENTION], f"Naming conventions  -  {len(inv.naming_issues)} issue{'s' if len(inv.naming_issues) != 1 else ''}"))
            inv_table = Table(title="Term naming issues", show_lines=True)
            inv_table.add_column("Term")
            inv_table.add_column("Category")
            inv_table.add_column("Issue")
            for e in inv.naming_issues:
                inv_table.add_row(Text(e.display_name), Text(e.category), Text(e.naming_message or ""))
            self.console.print(inv_table)

    def _domains_ranges(self) -> None:
        # Domain and range problems
        dr = self.report.domains_ranges
        if dr and dr.issues:
            self.console.print()
            self.console.print(_flag(worst_severity(dr.findings()), f"Domains and ranges  -  {len(dr.issues)} to review"))
            dr_table = Table(title="Domain and range issues", show_lines=True)
            dr_table.add_column("Property")
            dr_table.add_column("Category")
            dr_table.add_column("Level", justify="center")
            dr_table.add_column("Issue")
            for c in dr.issues:
                for finding in c.findings():
                    msg = (finding.message or "").replace("<code>", "").replace("</code>", "")
                    dr_table.add_row(Text(c.display_name), Text(c.category), _severity_badge(finding.severity), Text(msg))
            self.console.print(dr_table)

    def _datatypes(self) -> None:
        # Unrecognised datatypes
        dt = self.report.datatypes
        if dt and dt.unrecognised:
            self.console.print()
            self.console.print(_flag(RULE_SEVERITY[Rule.DATATYPE_UNRECOGNISED], f"Datatypes  -  {len(dt.unrecognised)} unrecognised"))
            dt_table = Table(title="Unrecognised datatypes", show_lines=True)
            dt_table.add_column("Datatype")
            dt_table.add_column("Uses", justify="center")
            dt_table.add_column("Full IRI")
            for u in dt.unrecognised:
                dt_table.add_row(Text(u.display_name), str(u.count), Text(u.datatype))
            self.console.print(dt_table)

    def _language_tags(self) -> None:
        # Language tag consistency
        lt = self.report.lang_tags
        if lt and lt.status == Status.WARN and lt.issues:
            self.console.print()
            self.console.print(_flag(RULE_SEVERITY[Rule.LANG_TAG_INCONSISTENT], f"Language tags  -  {len(lt.issues)} consistency issue{'s' if len(lt.issues) != 1 else ''}"))
            if lt.languages_used:
                self.console.print(f"  Languages used: {escape_markup(', '.join(lt.languages_used))}")
            lang_table = Table(title="Language tag issues", show_lines=True)
            lang_table.add_column("Subject")
            lang_table.add_column("Property")
            lang_table.add_column("Issue")
            lang_table.add_column("Has")
            lang_table.add_column("Expected")
            for issue in lt.issues:
                has = ", ".join(issue.languages_found) if issue.languages_found else " - "
                expected = ", ".join(issue.languages_expected)
                lang_table.add_row(Text(issue.subject), Text(issue.property), Text(issue.detail), Text(has), Text(expected))
            self.console.print(lang_table)
        elif lt and lt.status == Status.WARN:
            self.console.print()
            self.console.print(_flag(RULE_SEVERITY[Rule.LANG_TAG_MISSING], "Language tags  -  none of the checked labels or definitions carry a language tag"))

    def _reasoner(self) -> None:
        # Reasoner checks
        reasoner = self.report.reasoner
        if reasoner and reasoner.checks:
            self.console.print()
            reas_ok = not reasoner.findings()
            if reas_ok:
                self.console.print("[green]\u2713 Reasoner checks  -  no contradictions detected by these checks[/green]")
            else:
                self.console.print(_flag(
                    worst_severity(reasoner.findings()),
                    f"Reasoner checks  -  {len(reasoner.inconsistent_individuals)} inconsistent individual(s), "
                    f"{len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)",
                ))
            reasoner_table = Table(title="Reasoner checks", show_lines=True)
            self.console.print(Text(REASONER_SCOPE, style="dim"))
            reasoner_table.add_column("Check")
            reasoner_table.add_column("Status", justify="center")
            reasoner_table.add_column("Detail")
            for check in reasoner.checks:
                level = worst_severity(reasoner.findings_for_check(check.key))
                badge = ("[dim]-[/dim]" if check.status == Status.SKIP else
                         _severity_badge(level) if level else "[green]OK[/green]")
                reasoner_table.add_row(Text(check.label), badge, Text(check.message or ""))
            self.console.print(reasoner_table)

    def _summary(self) -> None:
        self.console.print()

        # Summary
        self.console.print(_severity_summary_line(self.summary))
        self.console.print()


def _flag(severity: Severity | None, text: str) -> str:
    """One-line finding, coloured and iconised by its severity."""
    if severity is None:
        return f"[green]\u2713 {text}[/green]"
    style = SEVERITY_STYLES[severity]
    return f"[{style.rich}]{style.glyph} {text}[/{style.rich}]"


def _finding_counts(findings: list[Finding]) -> str:
    """``"2 errors, 1 recommendation"`` for the findings of one check."""
    return ", ".join(
        count_label(sev, n) for sev in SEVERITY_ORDER if (n := sum(1 for f in findings if f.severity == sev))
    )


def _severity_summary_line(summary: SeveritySummary) -> str:
    return "  ".join(
        f"[{SEVERITY_STYLES[sev].rich}]{SEVERITY_STYLES[sev].glyph} {count_label(sev, summary.count(sev))}"
        f"[/{SEVERITY_STYLES[sev].rich}]"
        for sev in SEVERITY_ORDER
    )


def _severity_badge(severity: Severity) -> str:
    style = SEVERITY_STYLES[severity]
    return f"[{style.rich}]{style.glyph} {style.label.upper()}[/{style.rich}]"


def _item_badge(status: Status, rule: Rule) -> str:
    """Badge for one checked item whose failure would be a finding of ``rule``."""
    match status:
        case Status.OK:
            return "[green]OK[/green]"
        case Status.SKIP:
            return "[dim]SKIP[/dim]"
        case _:
            return _severity_badge(RULE_SEVERITY[rule])
