"""Format validation reports for terminal, JSON, and Markdown output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from askwol.models import Status, ValidationReport
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
from askwol.templates import CHECK_CATEGORIES, CHECK_NUMBERS, CHECKS, CLUSTER_NUMBERS

CATEGORIES = CHECK_CATEGORIES


def report_as_json(report: ValidationReport) -> str:
    return report.model_dump_json(indent=2)


_CHECK_TITLES = {c["report_anchor"]: c["title"].replace("&amp;", "&") for c in CHECKS}


def _md_severity(rule: Rule) -> str:
    return RULE_SEVERITY[rule].value


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
    lines: list[str] = []
    w = lines.append

    w("# Ontology Check Report")
    w("")
    w(f"**File:** `{report.file}`")
    w("")

    if report.parse_errors:
        w("## Parse Errors")
        w("")
        for err in report.parse_errors:
            w(f"- {err}")
        w("")

    # Summary box at top
    w("## Summary")
    w("")
    ok_ns = [ns for ns in report.namespaces if ns.resolution.status == Status.OK and ns.resolution.is_valid_rdf]
    html_ns = [ns for ns in report.namespaces if ns.resolution.status == Status.OK and not ns.resolution.is_valid_rdf]
    fail_ns = [ns for ns in report.namespaces if ns.resolution.status == Status.FAIL]

    external_terms = report.external_term_checks
    ok_terms = sum(1 for _, t in external_terms if t.status == Status.OK)
    fail_terms = sum(1 for _, t in external_terms if t.status == Status.FAIL)
    warn_terms = sum(1 for _, t in external_terms if t.status == Status.WARN)
    skip_terms = sum(1 for _, t in external_terms if t.status == Status.SKIP)

    w("| | Count |")
    w("|---|---|")
    w(f"| Namespaces checked | {sum(ns.resolution.status != Status.SKIP for ns in report.namespaces)} |")
    w(f"| Namespaces with RDF | {len(ok_ns)} |")
    if html_ns:
        w(f"| Namespaces returning HTML (no RDF) | {len(html_ns)} |")
    if fail_ns:
        w(f"| Namespaces unreachable | {len(fail_ns)} |")
    w(f"| External terms to check | {len(external_terms)} |")
    w(f"| Terms confirmed in vocabulary | {ok_terms} |")
    meta = report.ontology_metadata
    if meta and meta.total_checks:
        w(f"| Ontology metadata present | {meta.passed_checks}/{meta.total_checks} |")
    docs = report.definition_docs
    if docs and docs.total_definitions:
        w(f"| Definitions with a label | {docs.with_label}/{docs.total_definitions} |")
        w(f"| Definitions with a comment | {docs.with_comment}/{docs.total_definitions} |")
    it = report.internal_terms
    if it and it.status != Status.SKIP:
        w(f"| Internal terms defined | {it.defined}/{it.total_referenced} |")
        if it.undefined:
            w(f"| **Internal terms referenced but not defined** | **{len(it.undefined)}** |")
    reasoner = report.reasoner
    if reasoner:
        w(f"| Contradictions | {'detected' if reasoner.inconsistent_individuals else 'none detected'} |")
        if reasoner.unsatisfiable_classes:
            w(f"| Unsatisfiable classes | {len(reasoner.unsatisfiable_classes)} |")
    if fail_terms:
        w(f"| **Terms NOT found in vocabulary** | **{fail_terms}** |")
    if warn_terms:
        w(f"| Terms deprecated upstream | {warn_terms} |")
    if skip_terms:
        w(f"| Terms not checkable (namespace unavailable) | {skip_terms} |")
    w("")

    summary = report.severity_summary
    counts = "  ".join(
        f"{SEVERITY_STYLES[sev].glyph} {count_label(sev, summary.count(sev))}" for sev in SEVERITY_ORDER
    )
    w(f"> {counts}")
    w("")
    rollup = _check_rollup(summary)
    if rollup:
        w("| Level | Check | Findings |")
        w("|-------|-------|----------|")
        for severity, anchor, n in rollup:
            style = SEVERITY_STYLES[severity]
            w(f"| {style.glyph} {style.label} | {_CHECK_TITLES[anchor]} | {n} |")
        w("")

    # Imports
    imp = report.imports
    if imp is not None:
        w("## Imports")
        w("")
        w("Every `owl:imports` target declared in the ontology header is fetched over HTTP "
          "and parsed as RDF, the same way a reasoner would follow it.")
        w("")
        if imp.skipped:
            w(f"> {len(imp.checks)} declared import(s), resolution skipped")
        elif imp.broken:
            w(f"> {len(imp.broken)} of {len(imp.checks)} declared import(s) do not resolve")
        elif imp.checks:
            w(f"> {len(imp.checks)} declared import(s), all resolve")
        else:
            w("> no `owl:imports` declared")
        w("")
        if imp.checks:
            w("| Import | Status | Detail |")
            w("|--------|--------|--------|")
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
                w(f"| {c.iri} | {status_label} | {', '.join(bits)} |")
            w("")

    # IRI strategy (hash vs slash) for the ontology's own defined terms
    iri = report.iri_strategy
    if iri is not None and iri.status != Status.SKIP:
        w("## IRI strategy")
        w("")
        w("A consistent IRI pattern for the ontology's own terms: either every term sits under a "
          "fragment (`http://example.org/ont#Term`, hash) or every term is its own slash path "
          "(`http://example.org/ont/Term`, slash). Mixing both within the same base IRI confuses "
          "consumers and tooling; an ontology that bundles more than one base IRI may use a "
          "different, internally consistent style for each.")
        w("")
        multi = len(iri.namespaces) > 1
        for ns in iri.namespaces:
            label = f" for `{ns.namespace}`" if multi else ""
            if ns.strategy == "mixed":
                w(f"> **Mixed**{label}: {ns.hash_count} hash-style and {ns.slash_count} slash-style terms in the same namespace.")
                w("")
                if ns.hash_examples:
                    w("<details>")
                    w(f"<summary>Hash style examples ({ns.hash_count})</summary>")
                    w("")
                    for ex in ns.hash_examples:
                        w(f"- `{ex}`")
                    w("")
                    w("</details>")
                    w("")
                if ns.slash_examples:
                    w("<details>")
                    w(f"<summary>Slash style examples ({ns.slash_count})</summary>")
                    w("")
                    for ex in ns.slash_examples:
                        w(f"- `{ex}`")
                    w("")
                    w("</details>")
                    w("")
            else:
                count = ns.hash_count if ns.strategy == "hash" else ns.slash_count
                w(f"> **{ns.strategy.capitalize()} pattern**{label} used consistently across all {count} defined term(s).")
                w("")
                examples = ns.hash_examples if ns.strategy == "hash" else ns.slash_examples
                if examples:
                    w("<details>")
                    w(f"<summary>Show examples ({len(examples)})</summary>")
                    w("")
                    for ex in examples:
                        w(f"- `{ex}`")
                    w("")
                    w("</details>")
                    w("")

    # IRI scheme consistency (http vs https) per namespace
    sch = report.iri_scheme
    if sch is not None and sch.status != Status.SKIP:
        w("## IRI scheme (http vs https)")
        w("")
        w("In RDF, `http://example.org/X` and `https://example.org/X` are **different IRIs**. "
          "Within one ontology, each namespace should appear under exactly one scheme.")
        w("")
        if sch.status == Status.WARN:
            w(f"> **{len(sch.conflicts)}** namespace(s) are referenced under both `http://` and `https://` in the same ontology.")
            w("")
            w("<details>")
            w(f"<summary>Show conflicting namespaces ({len(sch.conflicts)})</summary>")
            w("")
            w("| Namespace | http:// count | https:// count |")
            w("|------|---------------|----------------|")
            for c in sch.conflicts:
                w(f"| `{c.host}` | {c.http_count} | {c.https_count} |")
            w("")
            w("</details>")
            w("")
        else:
            w(f"> **{sch.total_hosts}** namespace(s) referenced, each under a single scheme "
              f"({sch.http_only_hosts} http://, {sch.https_only_hosts} https://).")
            w("")
        if sch.hosts:
            w("<details>")
            w(f"<summary>Show namespaces ({len(sch.hosts)})</summary>")
            w("")
            w("| Namespace | Scheme | Count |")
            w("|------|--------|-------|")
            for h in sch.hosts:
                w(f"| `{h.host}` | {h.scheme}:// | {h.count} |")
            w("")
            w("</details>")
            w("")

    # Open licence compliance
    lcns = report.license
    if lcns is not None:
        w("## Open licence")
        w("")
        w("Every `dcterms:license` value declared in the ontology header is checked "
            "against a list of open licences following the Open Definition.")
        w("")
        if lcns.status != Status.OK:
            license_count = len(lcns.checks)
            if license_count == 0:
                w("> No licence declared.")
                w("")
            else:
                plural = "s" if license_count > 1 else ""
                w(f"> {license_count} licence{plural} declared.")
                w("")
                w("<details>")
                w("")
                w("| Licence | Licence IRI | Licence Category |")
                w("|---------|-------------|------------------|")
                for c in lcns.checks:
                    license_category = "recommended" if c.is_recommended else ("open" if c.is_open else "non-open")
                    w(f"| {c.name} | {c.iri} | {license_category} |")
                w("")
                w("</details>")
                w("")
        else:
            c = lcns.checks[0]
            w(f"> 1 recommended licence declared"
              f" ({c.name}: `{c.iri}`).")
            w("")

    # Group namespaces by status for clarity
    if ok_ns:
        w("## Namespaces with valid RDF")
        w("")
        w("These namespaces resolved and returned parseable RDF. All terms from these vocabularies could be verified.")
        w("")
        w("| Prefix | URI | Terms | Verified |")
        w("|--------|-----|-------|----------|")
        for ns in ok_ns:
            terms = report.external_terms_for_namespace(ns)
            ok = sum(t.status == Status.OK for t in terms)
            total = len(terms)
            check = "all" if ok == total else f"{ok}/{total}"
            w(f"| `{ns.prefix}` | {ns.uri} | {total} | {check} |")
        w("")

    if html_ns:
        w("## Namespaces returning HTML")
        w("")
        w("These namespaces resolved (HTTP 200) but returned an HTML page instead of RDF data. "
          "The server may not support content negotiation, or the RDF is hosted at a different URL. "
          "Terms from these namespaces could **not** be verified.")
        w("")
        w("| Prefix | URI | Terms | Content-Type |")
        w("|--------|-----|-------|-------------|")
        for ns in html_ns:
            ct = ns.resolution.content_type or "unknown"
            w(f"| `{ns.prefix}` | {ns.uri} | {len(report.external_terms_for_namespace(ns))} | `{ct}` |")
        w("")

    if fail_ns:
        w("## Unreachable namespaces")
        w("")
        w("These namespace URIs could not be reached. This might mean the URL is wrong, "
          "the server is down, or the ontology is not published yet.")
        w("")
        w("| Prefix | URI | Error |")
        w("|--------|-----|-------|")
        for ns in fail_ns:
            err = ns.resolution.error or "unknown"
            w(f"| `{ns.prefix}` | {ns.uri} | {err} |")
        w("")

    # External term definitions: per-term verification against the remote vocabulary
    if report.namespaces:
        w("## External term definitions")
        w("")
        w("External terms used as subjects are checked against the retrieved vocabulary. "
          "Terms not found there and terms marked deprecated are reported. "
          "Unknown datatypes are reported under Datatypes.")
        w("")
        term_summary_bits = [f"{ok_terms} confirmed"]
        if fail_terms:
            term_summary_bits.append(f"{fail_terms} not found")
        if warn_terms:
            term_summary_bits.append(f"{warn_terms} deprecated upstream")
        if skip_terms:
            term_summary_bits.append(f"{skip_terms} skipped (namespace unavailable)")
        if report.external_terms_unchecked:
            w("> Not checked (namespaces not resolved).")
        elif not external_terms:
            w("> No external terms to check.")
        else:
            w(f"> {', '.join(term_summary_bits)} of {len(external_terms)} total.")
        w("")

        failed_terms_flat = [(ns, t) for ns, t in external_terms if t.status == Status.FAIL]
        deprecated_terms_flat = [(ns, t) for ns, t in external_terms if t.status == Status.WARN]
        skipped_terms_flat = [(ns, t) for ns, t in external_terms if t.status == Status.SKIP]
        ok_terms_flat = [(ns, t) for ns, t in external_terms if t.status == Status.OK]

        if failed_terms_flat:
            w("<details>")
            w(f"<summary>Terms not found in their vocabulary ({len(failed_terms_flat)})</summary>")
            w("")
            w("| Term | Prefix | Full URI |")
            w("|------|--------|----------|")
            for ns, t in failed_terms_flat:
                w(f"| `{t.local_name}` | `{ns.prefix}` | {t.term_uri} |")
            w("")
            w("</details>")
            w("")

        if deprecated_terms_flat:
            w("<details>")
            w(f"<summary>Deprecated upstream ({len(deprecated_terms_flat)})</summary>")
            w("")
            w("| Term | Prefix | Marker | Full URI |")
            w("|------|--------|--------|----------|")
            for ns, t in deprecated_terms_flat:
                w(f"| `{t.local_name}` | `{ns.prefix}` | {t.deprecated} | {t.term_uri} |")
            w("")
            w("</details>")
            w("")

        if skipped_terms_flat:
            w("<details>")
            w(f"<summary>Terms not checkable, namespace unavailable ({len(skipped_terms_flat)})</summary>")
            w("")
            w("| Term | Prefix |")
            w("|------|--------|")
            for ns, t in skipped_terms_flat:
                w(f"| `{t.local_name}` | `{ns.prefix}` |")
            w("")
            w("</details>")
            w("")

        if ok_terms_flat:
            w("<details>")
            w(f"<summary>Confirmed terms ({len(ok_terms_flat)})</summary>")
            w("")
            w("| Term | Prefix |")
            w("|------|--------|")
            for ns, t in ok_terms_flat:
                w(f"| `{t.local_name}` | `{ns.prefix}` |")
            w("")
            w("</details>")
            w("")

    # Unused prefixes
    if report.unused_prefixes:
        w("## Unused prefixes")
        w("")
        w("These prefixes are declared with `@prefix` but never used in any triple. "
          "Consider removing them to keep the ontology clean.")
        w("")
        w("| Prefix | URI |")
        w("|--------|-----|")
        for up in report.unused_prefixes:
            pfx = up.prefix or "(default)"
            w(f"| `{pfx}` | {up.uri} |")
        w("")

    # Ontology metadata
    meta = report.ontology_metadata
    if meta and meta.checks:
        w("## Ontology metadata")
        w("")
        w("These checks are evaluated from SHACL shapes on the ontology header.")
        w("")
        w("<details>")
        w(f"<summary>Show metadata checks ({meta.total_checks})</summary>")
        w("")
        w("| Property | Group | Status |")
        w("|----------|-------|--------|")
        for check in meta.checks:
            status_label = "ok" if check.status == Status.OK else _md_severity(Rule.METADATA_MISSING) + " (missing)"
            w(f"| `{check.property}` | {check.tier} | {status_label} |")
        w("")
        w("</details>")
        w("")

    # Internal term definitions
    it = report.internal_terms
    if it and it.status != Status.SKIP and it.undefined:
        w("## Internal term definitions")
        w("")
        w("Terms in the ontology's own namespace that are referenced but never "
          "defined (they never appear as the subject of a triple). Usually a typo "
          "or a forgotten declaration.")
        w("")
        w(f"> {it.defined}/{it.total_referenced} referenced terms defined, {len(it.undefined)} undefined")
        w("")
        w("| Term | Full IRI |")
        w("|------|----------|")
        for issue in it.undefined:
            w(f"| `{issue.display_name}` | {issue.term} |")
        w("")

    # Term inventory and naming conventions
    inv = report.term_inventory
    if inv and inv.status != Status.SKIP and inv.entries:
        w("## Term inventory and naming")
        w("")
        w("Every term defined in the ontology's own namespace, by category. "
          "Classes should start with an uppercase letter, properties with a lowercase letter.")
        w("")
        counts = ", ".join(f"{n} {cat}" for cat, n in inv.category_counts.items())
        w(f"> {inv.total_terms} internal terms ({counts})")
        w("")
        if inv.naming_issues:
            w(f"> {len(inv.naming_issues)} naming convention issue(s)")
            w("")
            w("| Term | Category | Issue |")
            w("|------|----------|-------|")
            for e in inv.naming_issues:
                w(f"| `{e.display_name}` | {e.category} | {e.naming_message} |")
            w("")
        w("<details>")
        w(f"<summary>Show all terms ({inv.total_terms})</summary>")
        w("")
        w("| Term | Category | Naming |")
        w("|------|----------|--------|")
        for e in sorted(inv.entries, key=lambda x: (x.category, x.display_name.lower())):
            if e.deprecated:
                naming = f"deprecated ({e.deprecated}), not checked"
            elif e.naming_ok:
                naming = "ok"
            else:
                naming = "check"
            w(f"| `{e.display_name}` | {e.category} | {naming} |")
        w("")
        w("</details>")
        w("")

    # Domains and ranges
    dr = report.domains_ranges
    if dr and dr.status != Status.SKIP and dr.checks:
        w("## Domains and ranges")
        w("")
        w("Object and datatype properties should declare a domain and a range. "
          "Object properties range over classes; datatype properties range over datatypes.")
        w("")
        w(f"> {dr.with_domain}/{dr.total_properties} have a domain, "
          f"{dr.with_range}/{dr.total_properties} have a range, {len(dr.issues)} issue(s)")
        w("")
        w("<details>")
        summary = f"Show all properties ({dr.total_properties})"
        if dr.issues:
            summary += f" &middot; {len(dr.issues)} to review"
        w(f"<summary>{summary}</summary>")
        w("")
        w("| Property | Category | Domain | Range | Findings |")
        w("|----------|----------|--------|-------|----------|")
        for c in sorted(dr.checks, key=lambda x: (x.category, x.display_name.lower())):
            category = c.category + (f" (deprecated: {c.deprecated})" if c.deprecated else "")
            msg = "<br>".join(
                f"{f.severity.value}: {(f.message or '').replace('<code>', '`').replace('</code>', '`')}"
                for f in c.findings()
            )
            w(f"| `{c.display_name}` | {category} | {'yes' if c.has_domain else 'no'} | {'yes' if c.has_range else 'no'} | {msg} |")
        w("")
        w("</details>")
        w("")

    # Datatypes
    dt = report.datatypes
    if dt and dt.status != Status.SKIP and dt.usages:
        w("## Datatypes")
        w("")
        w("Datatypes used as property ranges and literal datatypes. "
          "Unrecognised datatypes are usually typos.")
        w("")
        w(f"> {dt.recognised}/{dt.total_datatypes} recognised, {len(dt.unrecognised)} unrecognised")
        w("")
        if dt.unrecognised:
            w("| Datatype | Uses |")
            w("|----------|------|")
            for u in dt.unrecognised:
                w(f"| `{u.display_name}` | {u.count} |")
            w("")
        w("<details>")
        w(f"<summary>Show all datatypes ({dt.total_datatypes})</summary>")
        w("")
        w("| Datatype | Uses | Where |")
        w("|----------|------|-------|")
        for u in sorted(dt.usages, key=lambda x: x.display_name.lower()):
            w(f"| {'ok' if u.recognised else 'unrecognised'} `{u.display_name}` | {u.count} | {', '.join(u.sources)} |")
        w("")
        w("</details>")
        w("")

    # Labels and comments
    docs = report.definition_docs
    if docs and docs.total_definitions:
        w("## Labels")
        w("")
        w("Internal classes and properties only. Reused external vocabulary terms are ignored.")
        w("")
        w(f"> {docs.with_label}/{docs.total_definitions} have an rdfs:label")
        w("")
        w("<details>")
        w(f"<summary>Show labels ({docs.total_definitions})</summary>")
        w("")
        w("| Term | Type | Label |")
        w("|------|------|-------|")
        for check in sorted(docs.checks, key=lambda c: (c.has_label, c.display_name.lower())):
            label = "ok" if check.has_label else f"{_md_severity(Rule.LABEL_MISSING)}: missing"
            w(f"| `{check.display_name}` | {check.term_type} | {label} |")
        w("")
        w("</details>")
        w("")

        w("## Comments")
        w("")
        w("Internal classes and properties only. Reused external vocabulary terms are ignored.")
        w("")
        w(f"> {docs.with_comment}/{docs.total_definitions} have an rdfs:comment")
        w("")
        w("<details>")
        w(f"<summary>Show comments ({docs.total_definitions})</summary>")
        w("")
        w("| Term | Type | Comment |")
        w("|------|------|---------|")
        for check in sorted(docs.checks, key=lambda c: (c.has_comment, c.display_name.lower())):
            comment = "ok" if check.has_comment else f"{_md_severity(Rule.COMMENT_MISSING)}: missing"
            w(f"| `{check.display_name}` | {check.term_type} | {comment} |")
        w("")
        w("</details>")
        w("")

    # Reasoner checks
    reasoner = report.reasoner
    if reasoner and reasoner.checks:
        w("## Reasoner checks")
        w("")
        w("Limited OWL RL checks on the current document; imports excluded.")
        w("")
        w("| Check | Status | Detail |")
        w("|-------|--------|--------|")
        for check in reasoner.checks:
            severity = worst_severity(reasoner.findings_for_check(check.key))
            status_label = ("not checked" if check.status == Status.SKIP else
                            severity.value if severity else "ok")
            w(f"| {check.label} | {status_label} | {check.message or ''} |")
        w("")

    # Language tag consistency
    lt = report.lang_tags
    if lt and lt.status == Status.WARN and lt.issues:
        w("## Language tag consistency")
        w("")
        w(f"Languages used: {', '.join(f'`{l}`' for l in lt.languages_used)}")
        w("")
        n_missing_tag = sum(1 for i in lt.issues if i.issue_type == "missing_tag")
        n_missing_lang = sum(1 for i in lt.issues if i.issue_type == "missing_language")
        parts = []
        if n_missing_tag:
            parts.append(f"{n_missing_tag} untagged value{'s' if n_missing_tag != 1 else ''}")
        if n_missing_lang:
            parts.append(f"{n_missing_lang} missing translation{'s' if n_missing_lang != 1 else ''}")
        if parts:
            w(f"> **{len(lt.issues)} issue{'s' if len(lt.issues) != 1 else ''}:** {' · '.join(parts)}")
            w("")
        w("| Subject | Property | Issue | Has | Expected |")
        w("|---------|----------|-------|-----|----------|")
        for issue in lt.issues:
            has = ", ".join(issue.languages_found) if issue.languages_found else " - "
            expected = ", ".join(issue.languages_expected)
            w(f"| `{issue.subject}` | `{issue.property}` | {issue.detail} | {has} | {expected} |")
        w("")
    elif lt and lt.status == Status.WARN:
        w("## Language tag consistency")
        w("")
        w(f"> **{SEVERITY_STYLES[RULE_SEVERITY[Rule.LANG_TAG_MISSING]].label}:** "
          "labels or definitions are present, but none carry a language tag (e.g. `\"Person\"@en`).")
        w("")

    # Non-ontology terms
    sk = report.non_ontology_terms
    if sk and sk.status != Status.SKIP and sk.terms:
        w("## Non-ontology terms")
        w("")
        w("An OWL ontology should define schema: classes, properties, and "
          "datatypes. A skos:Concept scheme is subject-matter data, not "
          "schema, and belongs in a separate resource.")
        w("")
        w(f"> {len(sk.terms)} skos:Concept instance(s) defined in the ontology's own namespace")
        w("")
        w("| Term | What it is | Full IRI |")
        w("|------|------------|----------|")
        for issue in sk.terms:
            w(f"| `{issue.display_name}` | {issue.type_label} | {issue.term} |")
        w("")

    return "\n".join(lines)


def _overview_badge(report: ValidationReport, anchor: str, applicable: bool) -> str:
    """OK, "-" (not applicable), or the badge of the worst finding of the check."""
    if not applicable:
        return "[dim]-[/dim]"
    worst = worst_severity(report.severity_summary.for_check(anchor))
    return "[green]OK[/green]" if worst is None else _severity_badge(worst)


def _overview_line(report: ValidationReport, anchor: str) -> tuple[bool, str] | None:
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
        return True, f"{sch.total_hosts} host(s) checked"
    if anchor == "license":
        lcns = report.license
        if not lcns:
            return None
        if not lcns.license_count:
            return True, "no licence declared"
        kinds = [
            f"{n} {label}" for n, label in (
                (len(lcns.recommended_licenses), "recommended"),
                (len(lcns.open_licenses), "open"),
                (len(lcns.non_open_licenses), "non-open"),
            ) if n
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
        terms = report.external_term_checks
        total = len(terms)
        ok = sum(1 for _, t in terms if t.status == S.OK)
        fail = sum(1 for _, t in terms if t.status == S.FAIL)
        warn = sum(1 for _, t in terms if t.status == S.WARN)
        if report.external_terms_unchecked:
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
            return True, f"{len(sk.terms)} that belong in a separate resource"
        return True, "only schema terms defined"
    if anchor in ("labels", "comments"):
        docs = report.definition_docs
        if not docs:
            return None
        if not docs.total_definitions:
            return False, "no internal definitions to document"
        present = docs.with_label if anchor == "labels" else docs.with_comment
        noun = "a label" if anchor == "labels" else "a comment"
        return True, f"{present}/{docs.total_definitions} have {noun}"
    if anchor == "language-tags":
        lt = report.lang_tags
        if not lt or lt.status == Status.SKIP:
            return False, "not applicable"
        return True, ", ".join(lt.languages_used) or "no language tags"
    if anchor == "reasoner":
        reasoner = report.reasoner
        if not reasoner or not reasoner.checks:
            return None
        if not report.severity_summary.for_check("reasoner"):
            return True, "no contradictions detected"
        return True, (
            f"{len(reasoner.inconsistent_individuals)} inconsistent individual(s), "
            f"{len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)"
        )
    return None


def _print_overview(report: ValidationReport, console: Console) -> None:
    """Render the clustered checks overview, mirroring the web report."""
    overview = Table(title="Checks overview", show_header=True, header_style="bold")
    overview.add_column("Check")
    overview.add_column("Status", justify="center")
    overview.add_column("Detail", overflow="fold")

    summary = report.severity_summary
    first = True
    for cat in CATEGORIES:
        rows = []
        for check in CHECKS:
            if check["category"] != cat["key"]:
                continue
            anchor = check["report_anchor"]
            line = _overview_line(report, anchor)
            if line is None:
                continue
            applicable, detail = line
            counts = _finding_counts(summary.for_check(anchor))
            if counts:
                detail = f"{detail} ({counts})"
            title = check["title"].replace("&amp;", "&")
            num = CHECK_NUMBERS.get(anchor, "")
            label = f"  {num} {title}" if num else f"  {title}"
            rows.append((label, _overview_badge(report, anchor, applicable), detail))
        if not rows:
            continue
        if not first:
            overview.add_section()
        first = False
        label = cat["label"].replace("&amp;", "&")
        overview.add_row(f"[bold cyan]{CLUSTER_NUMBERS[cat['key']]}. {label}[/bold cyan]", "", "")
        for title, badge, detail in rows:
            overview.add_row(title, badge, detail)

    if overview.row_count == 0:
        return
    console.print(overview)
    console.print()


def print_report(report: ValidationReport, console: Console | None = None) -> None:
    """Pretty-print a validation report to the terminal using rich."""
    if console is None:
        console = Console()

    console.print()
    console.rule(f"[bold]Ontology Check: {report.file}[/bold]")
    console.print()

    if report.parse_errors:
        console.print("[bold red]Parse errors:[/bold red]")
        for err in report.parse_errors:
            console.print(f"  {err}")
        console.print()

    # Clustered checks overview, mirroring the web report and markdown output.
    _print_overview(report, console)

    # Imports
    imp = report.imports
    if imp is not None and imp.checks:
        console.print()
        if imp.skipped:
            console.print(f"[dim]- Imports  -  {len(imp.checks)} declared, resolution skipped[/dim]")
        elif imp.broken:
            console.print(_flag(RULE_SEVERITY[Rule.IMPORT_UNRESOLVED], f"Imports  -  {len(imp.broken)} of {len(imp.checks)} do not resolve"))
        else:
            console.print(f"[green]\u2713 Imports  -  {len(imp.checks)} declared, all resolve[/green]")
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
            imp_table.add_row(c.iri, _item_badge(res.status, Rule.IMPORT_UNRESOLVED), ", ".join(bits))
        console.print(imp_table)

    # Open licence compliance
    lcns = report.license
    if lcns is not None:
        console.print()
        license_table = Table(title="Licences", show_lines=True)
        license_table.add_column("IRI")
        license_table.add_column("Name")
        license_table.add_column("Status")
        license_table.add_column("Category")
        for c in lcns.checks:
            license_category = "recommended" if c.is_recommended else ("open" if c.is_open else "non-open")
            license_rule = Rule.LICENSE_NOT_OPEN if c.status == Status.FAIL else Rule.LICENSE_NOT_RECOMMENDED
            license_table.add_row(c.iri, c.name, _item_badge(c.status, license_rule), license_category)
        license_count = len(lcns.checks)
        license_worst = worst_severity(lcns.findings())
        if license_worst is None:
            console.print(f"[green]\u2713 Open licence  -  1 recommended licence declared ({lcns.checks[0].name})[/green]")
        elif license_count == 0:
            console.print(_flag(license_worst, "Open licence  -  no licence declared"))
        else:
            kinds = ", ".join(
                f"{n} {label}" for n, label in (
                    (len(lcns.recommended_licenses), "recommended"),
                    (len(lcns.open_licenses), "open"),
                    (len(lcns.non_open_licenses), "non-open"),
                ) if n
            )
            plural = "s" if license_count > 1 else ""
            console.print(_flag(license_worst, f"Open licence  -  {license_count} licence{plural} declared, {kinds}"))
        if license_count > 0:
            console.print()
            console.print(license_table)

    # IRI strategy (hash vs slash) for the ontology's own defined terms
    iri = report.iri_strategy
    if iri is not None and iri.status != Status.SKIP:
        console.print()
        multi = len(iri.namespaces) > 1
        if iri.status == Status.WARN:
            mixed = [ns for ns in iri.namespaces if ns.strategy == "mixed"]
            hash_n = sum(ns.hash_count for ns in mixed)
            slash_n = sum(ns.slash_count for ns in mixed)
            suffix = f" in {len(mixed)} of {len(iri.namespaces)} base IRI(s)" if multi else ""
            console.print(_flag(RULE_SEVERITY[Rule.IRI_STRATEGY_MIXED], f"IRI strategy  -  mixed: {hash_n} hash + {slash_n} slash{suffix}"))
            for ns in mixed:
                if ns.hash_examples:
                    console.print(f"  [dim]hash:[/dim] {', '.join(ns.hash_examples)}")
                if ns.slash_examples:
                    console.print(f"  [dim]slash:[/dim] {', '.join(ns.slash_examples)}")
        elif multi:
            console.print(f"[green]\u2713 IRI strategy  -  {len(iri.namespaces)} base IRIs, each consistent[/green]")
        else:
            ns = iri.namespaces[0]
            count = ns.hash_count if ns.strategy == "hash" else ns.slash_count
            console.print(f"[green]\u2713 IRI strategy  -  {ns.strategy} style, {count} term(s)[/green]")

    # IRI scheme consistency (http vs https) per host
    sch = report.iri_scheme
    if sch is not None and sch.status != Status.SKIP:
        console.print()
        if sch.status == Status.WARN:
            console.print(_flag(RULE_SEVERITY[Rule.IRI_SCHEME_MIXED], f"IRI scheme  -  {len(sch.conflicts)} host(s) on both http and https"))
            for c in sch.conflicts:
                console.print(f"  [dim]{c.host}:[/dim] {c.http_count} http, {c.https_count} https")
        else:
            console.print(f"[green]\u2713 IRI scheme  -  {sch.total_hosts} host(s), single scheme each[/green]")
            if sch.hosts:
                console.print("  [dim]hosts:[/dim] " + ", ".join(f"{h.host} ({h.scheme})" for h in sch.hosts))

    # Namespace resolution table
    ns_table = Table(title="Namespace Resolution", show_lines=True)
    ns_table.add_column("Prefix", style="cyan")
    ns_table.add_column("URI")
    ns_table.add_column("HTTP", justify="center")
    ns_table.add_column("Valid RDF", justify="center")
    ns_table.add_column("Status", justify="center")

    for ns in report.namespaces:
        r = ns.resolution
        status_str = _item_badge(r.status, Rule.NAMESPACE_UNRESOLVED)
        http_str = str(r.http_status) if r.http_status else "-"
        rdf_str = "yes" if r.is_valid_rdf else ("no" if r.is_valid_rdf is False else "-")
        ns_table.add_row(ns.prefix or "(default)", ns.uri, http_str, rdf_str, status_str)

    console.print(ns_table)
    console.print()

    # Term validation  -  grouped by status for clarity
    terms = report.external_term_checks
    ok_terms = [(ns, t) for ns, t in terms if t.status == Status.OK]
    fail_terms = [(ns, t) for ns, t in terms if t.status == Status.FAIL]
    warn_terms = [(ns, t) for ns, t in terms if t.status == Status.WARN]
    skip_terms = [(ns, t) for ns, t in terms if t.status == Status.SKIP]

    if fail_terms:
        fail_table = Table(title="Terms not found in remote vocabulary", show_lines=True)
        fail_table.add_column("Term")
        fail_table.add_column("Prefix")
        fail_table.add_column("Details")
        for ns, t in fail_terms:
            fail_table.add_row(t.local_name, ns.prefix, t.error or "")
        console.print(fail_table)
        console.print()

    if ok_terms:
        console.print(f"[green]{len(ok_terms)} terms verified[/green] in vocabularies: "
                       + ", ".join(sorted({ns.prefix for ns, _ in ok_terms})))

    if warn_terms:
        console.print(_flag(RULE_SEVERITY[Rule.EXTERNAL_TERM_DEPRECATED], f"{len(warn_terms)} term(s) deprecated upstream:"))
        for ns, t in warn_terms:
            console.print(f"  [dim]{ns.prefix}:[/dim]{t.local_name} ({t.deprecated})")

    if skip_terms:
        console.print(f"[dim]{len(skip_terms)} terms could not be checked[/dim] (namespace unavailable)")

    # Internal term definitions: referenced own-namespace terms must be defined
    it = report.internal_terms
    if it and it.status != Status.SKIP and it.undefined:
        console.print()
        console.print(_flag(RULE_SEVERITY[Rule.INTERNAL_TERM_UNDEFINED], f"Internal term definitions  -  {len(it.undefined)} referenced but never defined"))
        it_table = Table(title="Undefined internal terms", show_lines=True)
        it_table.add_column("Term")
        it_table.add_column("Full IRI")
        for issue in it.undefined:
            it_table.add_row(issue.display_name, issue.term)
        console.print(it_table)

    # Deprecated internal terms (own-namespace terms carrying a deprecation marker)
    inv_for_deprecated = report.term_inventory
    deprecated_entries = [e for e in inv_for_deprecated.entries if e.deprecated] if inv_for_deprecated else []
    if deprecated_entries:
        console.print()
        console.print(f"[yellow]\u26A0 {len(deprecated_entries)} internal term(s) marked deprecated:[/yellow]")
        for e in deprecated_entries:
            console.print(f"  [dim]{e.display_name}[/dim] ({e.deprecated})")

    # Non-ontology terms: the ontology's own namespace should define only schema
    sk = report.non_ontology_terms
    if sk and sk.status != Status.SKIP and sk.terms:
        console.print()
        console.print(_flag(RULE_SEVERITY[Rule.NON_ONTOLOGY_TERM], f"Non-ontology terms  -  {len(sk.terms)} skos:Concept instance(s) in the ontology's own namespace"))
        sk_table = Table(title="Non-ontology terms", show_lines=True)
        sk_table.add_column("Term")
        sk_table.add_column("What it is")
        sk_table.add_column("Full IRI")
        for issue in sk.terms:
            sk_table.add_row(issue.display_name, issue.type_label, issue.term)
        console.print(sk_table)

    # Unused prefixes
    if report.unused_prefixes:
        console.print()
        console.print(_flag(RULE_SEVERITY[Rule.UNUSED_PREFIX], f"{len(report.unused_prefixes)} unused prefix{'es' if len(report.unused_prefixes) != 1 else ''}:"))
        for up in report.unused_prefixes:
            pfx = up.prefix or "(default)"
            console.print(f"  [dim]{pfx}:[/dim] <{up.uri}>")

    # Ontology metadata
    meta = report.ontology_metadata
    if meta and meta.checks:
        console.print()
        if not meta.missing:
            console.print(f"[green]✓ Ontology metadata complete[/green] ({meta.passed_checks}/{meta.total_checks} checks)")
        else:
            console.print(_flag(RULE_SEVERITY[Rule.METADATA_MISSING], "Ontology metadata") + f" - {meta.passed_checks}/{meta.total_checks} present")
            meta_table = Table(title="Ontology metadata checks", show_lines=True)
            meta_table.add_column("Property")
            meta_table.add_column("Group")
            meta_table.add_column("Status")
            meta_table.add_column("Detail")
            for check in meta.missing:
                meta_table.add_row(check.property, check.tier, _item_badge(check.status, Rule.METADATA_MISSING), check.message or "")
            console.print(meta_table)

    # Term inventory naming issues
    inv = report.term_inventory
    if inv and inv.naming_issues:
        console.print()
        console.print(_flag(RULE_SEVERITY[Rule.NAMING_CONVENTION], f"Naming conventions  -  {len(inv.naming_issues)} issue{'s' if len(inv.naming_issues) != 1 else ''}"))
        inv_table = Table(title="Term naming issues", show_lines=True)
        inv_table.add_column("Term")
        inv_table.add_column("Category")
        inv_table.add_column("Issue")
        for e in inv.naming_issues:
            inv_table.add_row(e.display_name, e.category, e.naming_message or "")
        console.print(inv_table)

    # Domain and range problems
    dr = report.domains_ranges
    if dr and dr.issues:
        console.print()
        console.print(_flag(worst_severity(dr.findings()), f"Domains and ranges  -  {len(dr.issues)} to review"))
        dr_table = Table(title="Domain and range issues", show_lines=True)
        dr_table.add_column("Property")
        dr_table.add_column("Category")
        dr_table.add_column("Level", justify="center")
        dr_table.add_column("Issue")
        for c in dr.issues:
            for finding in c.findings():
                msg = (finding.message or "").replace("<code>", "").replace("</code>", "")
                dr_table.add_row(c.display_name, c.category, _severity_badge(finding.severity), msg)
        console.print(dr_table)

    # Unrecognised datatypes
    dt = report.datatypes
    if dt and dt.unrecognised:
        console.print()
        console.print(_flag(RULE_SEVERITY[Rule.DATATYPE_UNRECOGNISED], f"Datatypes  -  {len(dt.unrecognised)} unrecognised"))
        dt_table = Table(title="Unrecognised datatypes", show_lines=True)
        dt_table.add_column("Datatype")
        dt_table.add_column("Uses", justify="center")
        dt_table.add_column("Full IRI")
        for u in dt.unrecognised:
            dt_table.add_row(u.display_name, str(u.count), u.datatype)
        console.print(dt_table)

    # Language tag consistency
    lt = report.lang_tags
    if lt and lt.status == Status.WARN and lt.issues:
        console.print()
        console.print(_flag(RULE_SEVERITY[Rule.LANG_TAG_INCONSISTENT], f"Language tags  -  {len(lt.issues)} consistency issue{'s' if len(lt.issues) != 1 else ''}"))
        if lt.languages_used:
            console.print(f"  Languages used: {', '.join(lt.languages_used)}")
        lang_table = Table(title="Language tag issues", show_lines=True)
        lang_table.add_column("Subject")
        lang_table.add_column("Property")
        lang_table.add_column("Issue")
        lang_table.add_column("Has")
        lang_table.add_column("Expected")
        for issue in lt.issues:
            has = ", ".join(issue.languages_found) if issue.languages_found else " - "
            expected = ", ".join(issue.languages_expected)
            lang_table.add_row(issue.subject, issue.property, issue.detail, has, expected)
        console.print(lang_table)
    elif lt and lt.status == Status.WARN:
        console.print()
        console.print(_flag(RULE_SEVERITY[Rule.LANG_TAG_MISSING], "Language tags  -  labels or definitions present but none carry a language tag"))

    # Reasoner checks
    reasoner = report.reasoner
    if reasoner and reasoner.checks:
        console.print()
        reas_ok = not reasoner.findings()
        if reas_ok:
            console.print("[green]\u2713 Reasoner checks  -  no contradictions detected[/green]")
        else:
            console.print(_flag(
                worst_severity(reasoner.findings()),
                f"Reasoner checks  -  {len(reasoner.inconsistent_individuals)} inconsistent individual(s), "
                f"{len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)",
            ))
        reasoner_table = Table(title="Reasoner checks", show_lines=True)
        console.print("[dim]Limited OWL RL checks on the current document; imports excluded.[/dim]")
        reasoner_table.add_column("Check")
        reasoner_table.add_column("Status", justify="center")
        reasoner_table.add_column("Detail")
        for check in reasoner.checks:
            level = worst_severity(reasoner.findings_for_check(check.key))
            badge = ("[dim]-[/dim]" if check.status == Status.SKIP else
                     _severity_badge(level) if level else "[green]OK[/green]")
            reasoner_table.add_row(check.label, badge, check.message or "")
        console.print(reasoner_table)

    console.print()

    # Summary
    summary = report.severity_summary
    console.print(_severity_summary_line(summary))
    console.print()


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
