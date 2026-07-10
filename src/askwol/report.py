"""Format validation reports for terminal, JSON, and Markdown output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from askwol.models import Status, ValidationReport


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

    # SKOS concepts
    sk = report.skos_concepts
    if sk and sk.status != Status.SKIP and sk.internal_concepts:
        w("## SKOS concepts")
        w("")
        w("An OWL ontology defines classes and properties. Individual "
          "`skos:Concept` instances belong in a separate SKOS concept scheme, "
          "not in the ontology itself.")
        w("")
        w(f"> {len(sk.internal_concepts)} skos:Concept defined in the ontology's own namespace")
        w("")
        w("| Concept | Full IRI |")
        w("|---------|----------|")
        for issue in sk.internal_concepts:
            w(f"| `{issue.display_name}` | {issue.term} |")
        w("")

    return "\n".join(lines)


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
