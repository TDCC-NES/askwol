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

    w(f"# Ontology Check Report")
    w(f"")
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
    skip_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.SKIP)

    w(f"| | Count |")
    w(f"|---|---|")
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
    if skip_terms:
        w(f"| Terms not checkable (namespace unavailable) | {skip_terms} |")
    w("")

    if not report.has_issues:
        w("> **All checks passed.**")
        w("")
    else:
        w("> **Issues were found**  -  see details below.")
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

        # Show any FAIL terms from these namespaces
        failed_in_ok = [(ns, t) for ns in ok_ns for t in ns.terms if t.status == Status.FAIL]
        if failed_in_ok:
            w("### Terms not found in their vocabulary")
            w("")
            w("These terms are used in your ontology but **do not exist** in the remote vocabulary. This might indicate a typo or a made-up term.")
            w("")
            w("| Term | Prefix | Full URI |")
            w("|------|--------|----------|")
            for ns, t in failed_in_ok:
                w(f"| `{t.local_name}` | `{ns.prefix}` | {t.term_uri} |")
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

        # List the unverifiable terms
        html_terms = [(ns, t) for ns in html_ns for t in ns.terms]
        if html_terms:
            w("<details>")
            w(f"<summary>Show {len(html_terms)} unverified terms from HTML namespaces</summary>")
            w("")
            for ns in html_ns:
                if ns.terms:
                    w(f"**`{ns.prefix}:`** " + ", ".join(f"`{t.local_name}`" for t in ns.terms))
                    w("")
            w("</details>")
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

        # List terms from unreachable namespaces
        fail_terms_list = [(ns, t) for ns in fail_ns for t in ns.terms]
        if fail_terms_list:
            w("<details>")
            w(f"<summary>Show {len(fail_terms_list)} terms from unreachable namespaces</summary>")
            w("")
            for ns in fail_ns:
                if ns.terms:
                    w(f"**`{ns.prefix}:`** " + ", ".join(f"`{t.local_name}`" for t in ns.terms))
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
            w(f"| `{e.display_name}` | {e.category} | {'ok' if e.naming_ok else 'check'} |")
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
        if dr.issues:
            w("| Property | Category | Issue |")
            w("|----------|----------|-------|")
            for c in dr.issues:
                msg = (c.message or "").replace("<code>", "`").replace("</code>", "`")
                w(f"| `{c.display_name}` | {c.category} | {msg} |")
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
    if lt and lt.issues:
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

    # Non-ontology terms
    sk = report.non_ontology_terms
    if sk and sk.status != Status.SKIP and sk.terms:
        w("## Non-ontology terms")
        w("")
        w("An OWL ontology should define schema: classes, properties, and "
          "datatypes. Individuals, SKOS concepts, and other instance data "
          "belong in a separate resource.")
        w("")
        w(f"> {len(sk.terms)} non-schema term(s) defined in the ontology's own namespace")
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
        skipped = total - ok - fail
        bits = [f"{ok} confirmed"]
        if fail:
            bits.append(f"{fail} not found")
        if skipped:
            bits.append(f"{skipped} skipped")
        return ("fail" if fail else "ok"), ", ".join(bits)
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
        if lt and lt.languages_used:
            langs = ", ".join(lt.languages_used)
            if lt.issues:
                return "warn", f"{langs}, {len(lt.issues)} issue(s)"
            return "ok", f"{langs}, consistent"
        return "info", "no language tags used"
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

    if skip_terms:
        console.print(f"[dim]{len(skip_terms)} terms could not be checked[/dim] (namespace unavailable)")

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
    if lt and lt.issues:
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
