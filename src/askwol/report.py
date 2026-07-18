"""Format validation reports for terminal, JSON, and Markdown output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from askwol.models import Status, ValidationReport
from askwol.report_html import CATEGORIES, CHECKS, _CHECK_NUMBERS, _CLUSTER_NUMBERS


def report_as_json(report: ValidationReport) -> str:
    return report.model_dump_json(indent=2)


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

    ok_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.OK)
    fail_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.FAIL)
    warn_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.WARN)
    skip_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.SKIP)

    w("| | Count |")
    w("|---|---|")
    w(f"| Namespaces checked | {report.total_namespaces} |")
    w(f"| Namespaces with RDF | {len(ok_ns)} |")
    if html_ns:
        w(f"| Namespaces returning HTML (no RDF) | {len(html_ns)} |")
    if fail_ns:
        w(f"| Namespaces unreachable | {len(fail_ns)} |")
    w(f"| Total terms used | {report.total_terms} |")
    w(f"| Terms confirmed in vocabulary | {ok_terms} |")
    meta = report.ontology_metadata
    if meta and meta.total_checks:
        w(f"| Ontology metadata checks OK | {meta.passed_checks}/{meta.total_checks} |")
        if meta.failed_checks:
            w(f"| **Required metadata missing** | **{meta.failed_checks}** |")
        if meta.warning_checks:
            w(f"| Recommended metadata missing | {meta.warning_checks} |")
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
        w(f"| Ontology consistency | {'ok' if reasoner.consistent else 'problem found'} |")
        if reasoner.unsatisfiable_classes:
            w(f"| Unsatisfiable classes | {len(reasoner.unsatisfiable_classes)} |")
    if fail_terms:
        w(f"| **Terms NOT found in vocabulary** | **{fail_terms}** |")
    if warn_terms:
        w(f"| Terms deprecated upstream | {warn_terms} |")
    if skip_terms:
        w(f"| Terms not checkable (namespace unavailable) | {skip_terms} |")
    w("")

    if not report.has_issues:
        w("> **All checks passed.**")
        w("")
    else:
        w("> **Issues were found**  -  see details below.")
        w("")

    # Imports
    imp = report.imports
    if imp is not None:
        w("## Imports")
        w("")
        w("Every `owl:imports` target declared in the ontology header is fetched over HTTP "
          "and parsed as RDF, the same way a reasoner would follow it.")
        w("")
        if imp.broken:
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
                status_label = "ok" if res.status == Status.OK else "fail"
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
          "(`http://example.org/ont/Term`, slash). Mixing both within one ontology confuses "
          "consumers and tooling.")
        w("")
        if iri.status == Status.WARN:
            w(f"> **Mixed**: {iri.hash_count} hash-style and {iri.slash_count} slash-style terms in the same ontology.")
            w("")
            if iri.hash_examples:
                w("<details>")
                w(f"<summary>Hash style examples ({iri.hash_count})</summary>")
                w("")
                for ex in iri.hash_examples:
                    w(f"- `{ex}`")
                w("")
                w("</details>")
                w("")
            if iri.slash_examples:
                w("<details>")
                w(f"<summary>Slash style examples ({iri.slash_count})</summary>")
                w("")
                for ex in iri.slash_examples:
                    w(f"- `{ex}`")
                w("")
                w("</details>")
                w("")
        else:
            count = iri.hash_count if iri.strategy == "hash" else iri.slash_count
            w(f"> **{iri.strategy.capitalize()} pattern** used consistently across all {count} defined term(s).")
            w("")
            examples = iri.hash_examples if iri.strategy == "hash" else iri.slash_examples
            if examples:
                w("<details>")
                w(f"<summary>Show examples ({len(examples)})</summary>")
                w("")
                for ex in examples:
                    w(f"- `{ex}`")
                w("")
                w("</details>")
                w("")

    # IRI scheme consistency (http vs https) per host
    sch = report.iri_scheme
    if sch is not None and sch.status != Status.SKIP:
        w("## IRI scheme (http vs https)")
        w("")
        w("In RDF, `http://example.org/X` and `https://example.org/X` are **different IRIs**. "
          "Within one ontology, each host should appear under exactly one scheme.")
        w("")
        if sch.status == Status.WARN:
            w(f"> **{len(sch.conflicts)}** host(s) are referenced under both `http://` and `https://` in the same ontology.")
            w("")
            w("<details>")
            w(f"<summary>Show conflicting hosts ({len(sch.conflicts)})</summary>")
            w("")
            w("| Host | http:// count | https:// count |")
            w("|------|---------------|----------------|")
            for c in sch.conflicts:
                w(f"| `{c.host}` | {c.http_count} | {c.https_count} |")
            w("")
            w("</details>")
            w("")
        else:
            w(f"> **{sch.total_hosts}** host(s) referenced, each under a single scheme "
              f"({sch.http_only_hosts} http://, {sch.https_only_hosts} https://).")
            w("")
        if sch.hosts:
            w("<details>")
            w(f"<summary>Show hosts ({len(sch.hosts)})</summary>")
            w("")
            w("| Host | Scheme | Count |")
            w("|------|--------|-------|")
            for h in sch.hosts:
                w(f"| `{h.host}` | {h.scheme}:// | {h.count} |")
            w("")
            w("</details>")
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
            ok = ns.valid_terms
            total = ns.total_terms
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
            w(f"| `{ns.prefix}` | {ns.uri} | {ns.total_terms} | `{ct}` |")
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
        w("Every term you reuse from an external vocabulary must actually be defined in that vocabulary. "
          "askwol looks each one up in the resolved namespace; a term that is missing there is usually a "
          "typo or made-up reuse of an established prefix. A term that exists but is marked deprecated there "
          "(`owl:deprecated`, `owl:DeprecatedClass`/`owl:DeprecatedProperty`, or a `vs:term_status` of "
          "\"deprecated\"/\"archaic\") is flagged so you don't build on a term the source vocabulary is phasing out.")
        w("")
        term_summary_bits = [f"{ok_terms} confirmed"]
        if fail_terms:
            term_summary_bits.append(f"{fail_terms} not found")
        if warn_terms:
            term_summary_bits.append(f"{warn_terms} deprecated upstream")
        if skip_terms:
            term_summary_bits.append(f"{skip_terms} skipped (namespace unavailable)")
        w(f"> {', '.join(term_summary_bits)} of {report.total_terms} total.")
        w("")

        failed_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.FAIL]
        deprecated_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.WARN]
        skipped_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.SKIP]
        ok_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.OK]

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
        w("| Property | Level | Status |")
        w("|----------|-------|--------|")
        for check in meta.checks:
            status_label = "ok" if check.status == Status.OK else ("warning" if check.status == Status.WARN else "missing")
            w(f"| `{check.property}` | {check.severity} | {status_label} |")
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
        w("| Property | Category | Domain | Range | Issue |")
        w("|----------|----------|--------|-------|-------|")
        for c in sorted(dr.checks, key=lambda x: (x.category, x.display_name.lower())):
            category = c.category + (f" (deprecated: {c.deprecated})" if c.deprecated else "")
            msg = (c.message or "").replace("<code>", "`").replace("</code>", "`") if c.status != Status.OK else ""
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
          "Unrecognized datatypes are usually typos.")
        w("")
        w(f"> {dt.recognized}/{dt.total_datatypes} recognized, {len(dt.unrecognized)} unrecognized")
        w("")
        if dt.unrecognized:
            w("| Datatype | Uses |")
            w("|----------|------|")
            for u in dt.unrecognized:
                w(f"| `{u.display_name}` | {u.count} |")
            w("")
        w("<details>")
        w(f"<summary>Show all datatypes ({dt.total_datatypes})</summary>")
        w("")
        w("| Datatype | Uses | Where |")
        w("|----------|------|-------|")
        for u in sorted(dt.usages, key=lambda x: x.display_name.lower()):
            w(f"| {'ok' if u.recognized else 'unrecognized'} `{u.display_name}` | {u.count} | {', '.join(u.sources)} |")
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
            w(f"| `{check.display_name}` | {check.term_type} | {'ok' if check.has_label else 'missing'} |")
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
            w(f"| `{check.display_name}` | {check.term_type} | {'ok' if check.has_comment else 'missing'} |")
        w("")
        w("</details>")
        w("")

    # Reasoner checks
    reasoner = report.reasoner
    if reasoner and reasoner.checks:
        w("## Reasoner checks")
        w("")
        w("These checks run on the current ontology only. owl:imports are not followed.")
        w("")
        w("| Check | Status | Detail |")
        w("|-------|--------|--------|")
        for check in reasoner.checks:
            status_label = "ok" if check.status == Status.OK else ("warning" if check.status == Status.WARN else "fail")
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
        w("> **Warning:** labels or definitions are present, but none of them carry a language tag (e.g. `\"Person\"@en`).")
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


def _kind_badge(kind: str) -> str:
    return {
        "ok": "[green]OK[/green]",
        "fail": "[red]FAIL[/red]",
        "warn": "[yellow]WARN[/yellow]",
        "info": "[dim]-[/dim]",
        "skip": "[dim]SKIP[/dim]",
    }[kind]


def _overview_line(report: ValidationReport, anchor: str) -> tuple[str, str] | None:
    """Return (kind, detail) for one check anchor, mirroring the HTML overview.

    Returns None when the check did not run (so it is omitted from the table),
    matching the behaviour of the web report's summary.
    """
    S = Status
    if anchor == "ontology-metadata":
        meta = report.ontology_metadata
        if not (meta and meta.checks):
            return None
        if meta.failed_checks:
            kind = "fail"
        elif meta.warning_checks:
            kind = "warn"
        else:
            kind = "ok"
        bits = [f"{meta.passed_checks}/{meta.total_checks} present"]
        if meta.failed_checks:
            bits.append(f"{meta.failed_checks} required missing")
        if meta.warning_checks:
            bits.append(f"{meta.warning_checks} recommended missing")
        return kind, ", ".join(bits)
    if anchor == "imports":
        imp = report.imports
        if not imp:
            return None
        if imp.broken:
            return "fail", f"{len(imp.broken)} of {len(imp.checks)} do not resolve"
        if not imp.checks:
            return "ok", "no owl:imports declared"
        return "ok", f"{len(imp.checks)} declared, all resolve"
    if anchor == "iri-strategy":
        iri = report.iri_strategy
        if not iri:
            return None
        if iri.status == S.SKIP:
            return "info", "skipped"
        if iri.status == S.WARN:
            return "warn", f"mixed: {iri.hash_count} hash + {iri.slash_count} slash"
        count = iri.hash_count if iri.strategy == "hash" else iri.slash_count
        return "ok", f"{iri.strategy} style, {count} term(s)"
    if anchor == "iri-scheme":
        sch = report.iri_scheme
        if not sch:
            return None
        if sch.status == S.SKIP:
            return "info", "skipped"
        if sch.status == S.WARN:
            return "warn", f"{len(sch.conflicts)} host(s) on both http and https"
        return "ok", f"{sch.total_hosts} host(s), single scheme each"
    if anchor == "namespaces":
        total = len(report.namespaces)
        if total == 0:
            return None
        if all(ns.resolution.status == S.SKIP for ns in report.namespaces):
            return "info", "resolution skipped"
        ok = sum(1 for ns in report.namespaces if ns.resolution.status == S.OK)
        return ("ok" if ok == total else "fail"), f"{ok}/{total} resolved"
    if anchor == "unused-prefixes":
        if report.unused_prefixes:
            return "warn", f"{len(report.unused_prefixes)} declared but unused"
        return "ok", "none"
    if anchor == "external-terms":
        total = sum(len(ns.terms) for ns in report.namespaces)
        if total == 0:
            return None
        ok = sum(1 for ns in report.namespaces for t in ns.terms if t.status == S.OK)
        fail = sum(1 for ns in report.namespaces for t in ns.terms if t.status == S.FAIL)
        warn = sum(1 for ns in report.namespaces for t in ns.terms if t.status == S.WARN)
        skipped = total - ok - fail - warn
        bits = [f"{ok} confirmed"]
        if fail:
            bits.append(f"{fail} not found")
        if warn:
            bits.append(f"{warn} deprecated")
        if skipped:
            bits.append(f"{skipped} skipped")
        status = "fail" if fail else ("warn" if warn else "ok")
        return status, ", ".join(bits)
    if anchor == "internal-terms":
        it = report.internal_terms
        if not it:
            return None
        if it.status == S.SKIP:
            return "info", "not applicable"
        if it.undefined:
            return "fail", f"{len(it.undefined)} referenced but never defined"
        return "ok", f"{it.defined}/{it.total_referenced} defined"
    if anchor == "term-inventory":
        inv = report.term_inventory
        if not inv:
            return None
        if inv.status == S.SKIP:
            return "info", "no terms in the ontology's own namespace"
        if inv.naming_issues:
            return "fail", f"{inv.total_terms} terms, {len(inv.naming_issues)} naming issue(s)"
        return "ok", f"{inv.total_terms} terms, naming consistent"
    if anchor == "domains-ranges":
        dr = report.domains_ranges
        if not dr:
            return None
        if dr.status == S.SKIP:
            return "info", "no object or datatype properties"
        if dr.status == S.FAIL:
            fails = sum(1 for c in dr.issues if c.status == S.FAIL)
            return "fail", f"{fails} property(ies) with a domain/range problem"
        if dr.status == S.WARN:
            return "warn", f"{len(dr.issues)} missing a domain or range"
        return "ok", f"{dr.total_properties} property(ies), all sound"
    if anchor == "datatypes":
        dt = report.datatypes
        if not dt:
            return None
        if dt.status == S.SKIP:
            return "info", "no datatypes used"
        if dt.unrecognized:
            return "fail", f"{len(dt.unrecognized)} unrecognized of {dt.total_datatypes}"
        return "ok", f"{dt.total_datatypes} used, all recognized"
    if anchor == "non-ontology-terms":
        sk = report.non_ontology_terms
        if not sk:
            return None
        if sk.status == S.SKIP:
            return "info", "not applicable"
        if sk.terms:
            return "warn", f"{len(sk.terms)} that belong in a separate resource"
        return "ok", "only schema terms defined"
    if anchor == "labels":
        docs = report.definition_docs
        if not docs:
            return None
        if not docs.total_definitions:
            return "info", "no internal definitions to document"
        missing = docs.missing_label
        if missing:
            return "fail", f"{docs.with_label}/{docs.total_definitions} labelled, {len(missing)} missing"
        return "ok", f"{docs.total_definitions}/{docs.total_definitions} have a label"
    if anchor == "comments":
        docs = report.definition_docs
        if not docs:
            return None
        if not docs.total_definitions:
            return "info", "no internal definitions to document"
        missing = docs.missing_comment
        if missing:
            return "fail", f"{docs.with_comment}/{docs.total_definitions} commented, {len(missing)} missing"
        return "ok", f"{docs.total_definitions}/{docs.total_definitions} have a comment"
    if anchor == "language-tags":
        lt = report.lang_tags
        if not lt or lt.status == Status.SKIP:
            return "info", "not applicable"
        if lt.status == Status.WARN and lt.issues:
            langs = ", ".join(lt.languages_used)
            return "warn", f"{langs}, {len(lt.issues)} issue(s)"
        if lt.status == Status.WARN:
            return "warn", "labels/definitions present but none carry a language tag"
        langs = ", ".join(lt.languages_used)
        return "ok", f"{langs}, consistent"
    if anchor == "reasoner":
        reasoner = report.reasoner
        if not reasoner or not reasoner.checks:
            return None
        ok = reasoner.consistent and not reasoner.unsatisfiable_classes
        if ok:
            return "ok", "consistent"
        return "fail", (
            f"{len(reasoner.inconsistent_individuals)} inconsistency issue(s), "
            f"{len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)"
        )
    return None


def _print_overview(report: ValidationReport, console: Console) -> None:
    """Render the clustered checks overview, mirroring the web report."""
    overview = Table(title="Checks overview", show_header=True, header_style="bold")
    overview.add_column("Check")
    overview.add_column("Status", justify="center")
    overview.add_column("Detail", overflow="fold")

    first = True
    for cat in CATEGORIES:
        rows = []
        for check in CHECKS:
            if check["category"] != cat["key"]:
                continue
            line = _overview_line(report, check["report_anchor"])
            if line is None:
                continue
            kind, detail = line
            title = check["title"].replace("&amp;", "&")
            num = _CHECK_NUMBERS.get(check["report_anchor"], "")
            label = f"  {num} {title}" if num else f"  {title}"
            rows.append((label, _kind_badge(kind), detail))
        if not rows:
            continue
        if not first:
            overview.add_section()
        first = False
        label = cat["label"].replace("&amp;", "&")
        overview.add_row(f"[bold cyan]{_CLUSTER_NUMBERS[cat['key']]}. {label}[/bold cyan]", "", "")
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
        if imp.broken:
            console.print(f"[red]\u2717 Imports  -  {len(imp.broken)} of {len(imp.checks)} do not resolve[/red]")
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
            imp_table.add_row(c.iri, _status_badge(res.status), ", ".join(bits))
        console.print(imp_table)

    # IRI strategy (hash vs slash) for the ontology's own defined terms
    iri = report.iri_strategy
    if iri is not None and iri.status != Status.SKIP:
        console.print()
        if iri.status == Status.WARN:
            console.print(f"[yellow]\u26A0 IRI strategy  -  mixed: {iri.hash_count} hash + {iri.slash_count} slash[/yellow]")
            if iri.hash_examples:
                console.print(f"  [dim]hash:[/dim] {', '.join(iri.hash_examples)}")
            if iri.slash_examples:
                console.print(f"  [dim]slash:[/dim] {', '.join(iri.slash_examples)}")
        else:
            count = iri.hash_count if iri.strategy == "hash" else iri.slash_count
            console.print(f"[green]\u2713 IRI strategy  -  {iri.strategy} style, {count} term(s)[/green]")

    # IRI scheme consistency (http vs https) per host
    sch = report.iri_scheme
    if sch is not None and sch.status != Status.SKIP:
        console.print()
        if sch.status == Status.WARN:
            console.print(f"[yellow]\u26A0 IRI scheme  -  {len(sch.conflicts)} host(s) on both http and https[/yellow]")
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
        status_str = _status_badge(r.status)
        http_str = str(r.http_status) if r.http_status else "-"
        rdf_str = "yes" if r.is_valid_rdf else ("no" if r.is_valid_rdf is False else "-")
        ns_table.add_row(ns.prefix or "(default)", ns.uri, http_str, rdf_str, status_str)

    console.print(ns_table)
    console.print()

    # Term validation  -  grouped by status for clarity
    ok_terms = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.OK]
    fail_terms = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.FAIL]
    warn_terms = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.WARN]
    skip_terms = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.SKIP]

    if fail_terms:
        fail_table = Table(title="[red]Terms NOT found in remote vocabulary[/red]", show_lines=True)
        fail_table.add_column("Term", style="red bold")
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
        console.print(f"[yellow]⚠ {len(warn_terms)} term(s) deprecated upstream:[/yellow]")
        for ns, t in warn_terms:
            console.print(f"  [dim]{ns.prefix}:[/dim]{t.local_name} ({t.deprecated})")

    if skip_terms:
        console.print(f"[dim]{len(skip_terms)} terms could not be checked[/dim] (namespace unavailable)")

    # Internal term definitions: referenced own-namespace terms must be defined
    it = report.internal_terms
    if it and it.status != Status.SKIP and it.undefined:
        console.print()
        console.print(f"[red]\u2717 Internal term definitions  -  {len(it.undefined)} referenced but never defined[/red]")
        it_table = Table(title="Undefined internal terms", show_lines=True)
        it_table.add_column("Term", style="red bold")
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
        console.print(f"[yellow]\u26A0 Non-ontology terms  -  {len(sk.terms)} skos:Concept instance(s) in the ontology's own namespace[/yellow]")
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
        console.print(f"[yellow]⚠ {len(report.unused_prefixes)} unused prefix{'es' if len(report.unused_prefixes) != 1 else ''}:[/yellow]")
        for up in report.unused_prefixes:
            pfx = up.prefix or "(default)"
            console.print(f"  [dim]{pfx}:[/dim] <{up.uri}>")

    # Ontology metadata
    meta = report.ontology_metadata
    if meta and meta.checks:
        console.print()
        if meta.failed_checks == 0 and meta.warning_checks == 0:
            console.print(f"[green]✓ Ontology metadata complete[/green] ({meta.passed_checks}/{meta.total_checks} checks)")
        else:
            console.print(f"[yellow]⚠ Ontology metadata[/yellow] - {meta.passed_checks}/{meta.total_checks} checks OK")
            meta_table = Table(title="Ontology metadata checks", show_lines=True)
            meta_table.add_column("Property")
            meta_table.add_column("Level")
            meta_table.add_column("Status")
            meta_table.add_column("Detail")
            for check in meta.checks:
                if check.status == Status.OK:
                    continue
                meta_table.add_row(check.property, check.severity, check.status.value.upper(), check.message or "")
            console.print(meta_table)

    # Term inventory naming issues
    inv = report.term_inventory
    if inv and inv.naming_issues:
        console.print()
        console.print(f"[red]\u2717 Naming conventions  -  {len(inv.naming_issues)} issue{'s' if len(inv.naming_issues) != 1 else ''}[/red]")
        inv_table = Table(title="Term naming issues", show_lines=True)
        inv_table.add_column("Term", style="red bold")
        inv_table.add_column("Category")
        inv_table.add_column("Issue")
        for e in inv.naming_issues:
            inv_table.add_row(e.display_name, e.category, e.naming_message or "")
        console.print(inv_table)

    # Domain and range problems
    dr = report.domains_ranges
    if dr and dr.issues:
        console.print()
        console.print(f"[yellow]\u26A0 Domains and ranges  -  {len(dr.issues)} to review[/yellow]")
        dr_table = Table(title="Domain and range issues", show_lines=True)
        dr_table.add_column("Property")
        dr_table.add_column("Category")
        dr_table.add_column("Status", justify="center")
        dr_table.add_column("Issue")
        for c in dr.issues:
            msg = (c.message or "").replace("<code>", "").replace("</code>", "")
            dr_table.add_row(c.display_name, c.category, _status_badge(c.status), msg)
        console.print(dr_table)

    # Unrecognized datatypes
    dt = report.datatypes
    if dt and dt.unrecognized:
        console.print()
        console.print(f"[red]\u2717 Datatypes  -  {len(dt.unrecognized)} unrecognized[/red]")
        dt_table = Table(title="Unrecognized datatypes", show_lines=True)
        dt_table.add_column("Datatype", style="red bold")
        dt_table.add_column("Uses", justify="center")
        dt_table.add_column("Full IRI")
        for u in dt.unrecognized:
            dt_table.add_row(u.display_name, str(u.count), u.datatype)
        console.print(dt_table)

    # Language tag consistency
    lt = report.lang_tags
    if lt and lt.status == Status.WARN and lt.issues:
        console.print()
        console.print(f"[yellow]⚠ Language tags  -  {len(lt.issues)} consistency issue{'s' if len(lt.issues) != 1 else ''}[/yellow]")
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
        console.print("[yellow]⚠ Language tags  -  labels/definitions present but none carry a language tag[/yellow]")

    # Reasoner checks
    reasoner = report.reasoner
    if reasoner and reasoner.checks:
        console.print()
        reas_ok = reasoner.consistent and not reasoner.unsatisfiable_classes
        if reas_ok:
            console.print("[green]\u2713 Reasoner checks  -  consistent[/green]")
        else:
            console.print(
                f"[red]\u2717 Reasoner checks  -  {len(reasoner.inconsistent_individuals)} inconsistency(ies), "
                f"{len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)[/red]"
            )
        reasoner_table = Table(title="Reasoner checks", show_lines=True)
        reasoner_table.add_column("Check")
        reasoner_table.add_column("Status", justify="center")
        reasoner_table.add_column("Detail")
        for check in reasoner.checks:
            reasoner_table.add_row(check.label, _status_badge(check.status), check.message or "")
        console.print(reasoner_table)

    console.print()

    # Summary
    if report.has_issues:
        console.print("[bold red]Issues found.[/bold red]")
    else:
        console.print("[bold green]All checks passed.[/bold green]")

    console.print()


def _status_badge(status: Status) -> str:
    match status:
        case Status.OK:
            return "[green]OK[/green]"
        case Status.FAIL:
            return "[red]FAIL[/red]"
        case Status.WARN:
            return "[yellow]WARN[/yellow]"
        case Status.SKIP:
            return "[dim]SKIP[/dim]"
