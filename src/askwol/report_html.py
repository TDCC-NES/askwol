"""HTML rendering of the askwol validation report."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from askwol.branding import FAVICON_LINK
from askwol.models import NamespaceCheck, NamespaceReport, Status, ValidationReport
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

# CHECKS (title, description, anchors, category per check) is defined once in
# askwol.checks and shared with the landing page, README.md, and the API
# docs - re-exported here under its historical name so report.py and the
# test suite can keep importing it from this module.
#
# Each check also carries a ``category`` that groups it into a cluster shown as
# a labelled band in the overview, the results, and the guide. Clusters must be
# contiguous in this list; CATEGORIES gives their order and display labels
# (shared with the publishing guide via checks.CHECK_CATEGORIES).
CATEGORIES = CHECK_CATEGORIES
CATEGORY_LABELS: dict[str, str] = {c["key"]: c["label"] for c in CATEGORIES}

# Convenience lookups derived from CHECKS
_CHECK_BY_REPORT: dict[str, dict] = {c["report_anchor"]: c for c in CHECKS}
# report anchor -> category key
_CATEGORY_BY_REPORT: dict[str, str] = {c["report_anchor"]: c["category"] for c in CHECKS}

_CLUSTER_NUMBERS = CLUSTER_NUMBERS
_CHECK_NUMBERS = CHECK_NUMBERS

_OK_COLOR = "#2e7d32"
_NA_COLOR = "#888"


def _mark(severity: Severity | None, size: str = "1.3em") -> str:
    """The mark for a result: a tick when there is no finding, otherwise the
    glyph of the finding's severity."""
    style = f"font-size:{size};line-height:1;vertical-align:middle"
    if severity is None:
        return f'<span style="color:{_OK_COLOR};{style}">&#x2713;</span>'
    sev = SEVERITY_STYLES[severity]
    return (f'<span title="{sev.label}" aria-label="{sev.label}" '
            f'style="color:{sev.color};{style}">{sev.html_glyph}</span>')


def _na_mark(size: str = "1.3em") -> str:
    return f'<span style="color:{_NA_COLOR};font-size:{size};line-height:1;vertical-align:middle">&#x2014;</span>'


def _item_mark(status: Status, rule: Rule, size: str = "1.3em") -> str:
    """The mark for one checked item whose failure would be a finding of ``rule``."""
    if status == Status.SKIP:
        return _na_mark(size)
    return _mark(None if status == Status.OK else RULE_SEVERITY[rule], size)


def _count_text(findings: list[Finding]) -> str:
    """``"2 errors, 1 recommendation"`` for the findings of one check."""
    return ", ".join(
        count_label(sev, n) for sev in SEVERITY_ORDER if (n := sum(1 for f in findings if f.severity == sev))
    )


def _severity_summary_html(summary: SeveritySummary) -> str:
    """Headline counts of individual findings; hover a count for what the level means."""
    items = "".join(
        f'<span class="sev-count" title="{SEVERITY_STYLES[sev].label}: {SEVERITY_STYLES[sev].description}">'
        f'<span style="color:{SEVERITY_STYLES[sev].color}">{SEVERITY_STYLES[sev].html_glyph}</span> '
        f'<strong>{summary.count(sev)}</strong> {SEVERITY_STYLES[sev].plural}</span>'
        for sev in SEVERITY_ORDER
    )
    return f'<div class="severity-summary">{items}</div>'


def _guide_link(report_anchor: str) -> str:
    """HTML snippet linking from a report section to its guide section."""
    check = _CHECK_BY_REPORT.get(report_anchor)
    if not check:
        return ""
    href = f"guide#{check['guide_anchor']}"
    return (f'<p style="font-size:0.85em;color:#666;margin:0.4em 0 0;">'
            f'&rarr; Learn more in the <a href="{href}">publishing guide</a>.</p>')


def _external_link(uri: str, body_html: str, *, title: bool = False) -> str:
    """Link an untrusted RDF IRI only when it is an absolute HTTP(S) URL.

    The caller supplies already escaped body HTML; unsupported IRIs remain
    readable without becoming executable or local-file links.
    """
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return body_html
    if (parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc
            or any(ord(char) <= 32 or ord(char) == 127 for char in uri)):
        return body_html
    href = escape(uri)
    tooltip = f' title="{href}"' if title else ""
    return f'<a href="{href}" target="_blank" rel="noopener"{tooltip}>{body_html}</a>'


def render_report(report: ValidationReport, mermaid: str = "") -> str:
    return _HtmlReport(report, mermaid).render()


class _HtmlReport:
    """One HTML report, with shared state and a renderer for each check."""

    def __init__(self, report: ValidationReport, mermaid: str) -> None:
        self.report = report
        self.mermaid = mermaid
        self.parts: list[str] = []
        self._emitted_clusters: set[str] = set()

    def render(self) -> str:
        self._header()
        self._input_messages()
        if self.report.input_error or self.report.parse_errors:
            self.parts.append('<p>Ontology checks were not run.</p>')
            self.parts.append('</body></html>')
            return "\n".join(self.parts)

        self.view = ReportView(self.report)
        view = self.view
        self.sev_summary = view.summary
        self.total_ns = len(self.report.namespaces)
        self.ok_ns = sum(ns.resolution.status == Status.OK for ns in self.report.namespaces)
        self.external_terms = view.external_terms
        self.total_terms = len(self.external_terms)
        self.ok_terms = len(view.external_by_status[Status.OK])
        self.fail_terms = len(view.external_by_status[Status.FAIL])
        self.warn_terms = len(view.external_by_status[Status.WARN])
        self.terms_unchecked = self.view.terms_unchecked
        self._diagram()
        self._overview()
        self._metadata()
        self._imports()
        self._iri_strategy()
        self._iri_scheme()
        self._license()
        self._namespaces()
        self._unused_prefixes()
        self._external_terms()
        self._internal_terms()
        self._inventory()
        self._domains_ranges()
        self._datatypes()
        self._non_ontology_terms()
        self._documentation()
        self._language_tags()
        self._reasoner()
        self._footer()
        return "\n".join(self.parts)

    def _input_messages(self) -> None:
        if self.report.input_warnings:
            self.parts.extend([
                '<section class="section" aria-label="Source guidance">',
                '<h2>Source guidance</h2>',
                '<ul>',
                *(f'<li>{escape(warning)}</li>' for warning in self.report.input_warnings),
                '</ul></section>',
            ])
        diagnostic = self.report.input_error
        if diagnostic:
            label = "Parse error" if diagnostic.code == "invalid_rdf" else "Input error"
            self.parts.append(f'<div class="error"><strong>{label}:</strong> {escape(diagnostic.message)}')
            if diagnostic.source:
                url = diagnostic.source
                self.parts.append(f'<p>Context: {_external_link(url, "<code>" + escape(url) + "</code>")}</p>')
            if parser_message := diagnostic.parser_message():
                self.parts.append(f'<p>{escape(parser_message)}</p>')
            if diagnostic.guidance:
                self.parts.append(f'<p>{escape(diagnostic.guidance)}</p>')
            if diagnostic.suggested_url:
                url = diagnostic.suggested_url
                self.parts.append(f'<p>Suggested URL: {_external_link(url, "<code>" + escape(url) + "</code>")}</p>')
            if diagnostic.guide_url:
                title = "Help with RDF syntax" if diagnostic.code == "invalid_rdf" else "Learn more about ontology URLs"
                self.parts.append(f'<p>{_external_link(diagnostic.guide_url, title)}</p>')
            self.parts.append('</div>')
        for err in self.report.parse_errors:
            if diagnostic is None or err != diagnostic.message:
                self.parts.append(f'<div class="error"><strong>Parse error:</strong> {escape(err)}</div>')

    def _resolution_provenance(self, resolution: NamespaceCheck) -> None:
        if resolution.discovery_note:
            self.parts.append(f'<p>{escape(resolution.discovery_note)}</p>')
        if resolution.retrieved_url and resolution.retrieved_url != resolution.uri:
            url = resolution.retrieved_url
            self.parts.append(f'<p>Retrieved RDF: {_external_link(url, "<code>" + escape(url) + "</code>")}</p>')

    def _header(self) -> None:
        source = escape(self.report.file)
        source_html = _external_link(self.report.file, f'<code>{source}</code>')
        self.parts = [
            "<!DOCTYPE html><html><head><title>Ask Wol: results</title>",
            FAVICON_LINK,
            "<style>",
            "  body { font-family: system-ui, sans-serif; max-width: 780px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.5; overflow-wrap: anywhere; word-break: break-word; }",
            "  h1 { margin-bottom: 0.2em; font-size: 1.5em; }",
            "  h1 code { font-weight: 400; font-size: 0.75em; }",
            "  h2 { color: #555; margin-top: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }",
            "  h3 { color: #666; margin-top: 1.2em; margin-bottom: 0.3em; font-size: 1em; }",
            "  a { color: #4a7c59; }",
            "  code { background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }",
            "  .summary { background: #f9f9f9; border: 1px solid #ddd; border-radius: 8px; padding: 1.2em 1.5em; margin: 1.2em 0; }",
            "  .summary table { border-collapse: collapse; width: 100%; }",
            "  .summary td { padding: 0.45em 1.2em 0.45em 0; font-size: 1.05em; vertical-align: middle; border: none; }",
            "  .summary tr { cursor: pointer; }",
            "  .summary tr:hover td { background: #eef3ef; }",
            "  .summary tr.cluster-row { cursor: default; }",
            "  .summary tr.cluster-row:hover td { background: transparent; }",
            "  .summary tr.cluster-row td { padding: 0.9em 0 0.25em; font-size: 0.8em; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #4a7c59; border-bottom: 1px solid #e2e2e2; }",
            "  .summary tr.cluster-row:first-child td { padding-top: 0; }",
            "  .cluster-band { margin: 2em 0 0.4em; font-size: 0.85em; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #4a7c59; border: none; border-bottom: 2px solid #dfe8e1; padding-bottom: 0.3em; }",
            "  .num { color: #4a7c59; font-weight: 700; }",
            "  .ns { margin-top: 1.5em; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }",
            "  .ns-header { background: #f5f5f5; padding: 0.6em 1em; font-weight: bold; border-bottom: 1px solid #ddd; }",
            "  .ns-body { padding: 0.5em 1em; }",
            "  table { border-collapse: collapse; width: 100%; margin: 0.5em 0; table-layout: fixed; }",
            "  th, td { text-align: left; padding: 0.3em 0.8em; border-bottom: 1px solid #f0f0f0; font-size: 0.9em; overflow-wrap: anywhere; }",
            "  th { color: #666; font-weight: 600; }",
            "  .error { color: #c00; background: #fff0f0; padding: 0.8em; border-radius: 6px; }",
            "  .diagram { margin: 1.5em 0; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1em; background: #fafafa; position: relative; }",
            "  .diagram-viewport { position: relative; width: 100%; height: 500px; overflow: hidden; border: 1px solid #eee; border-radius: 4px; background: #fff; }",
            # Keep the raw Mermaid source and the freshly-rendered SVG hidden until
            # our script has fitted the viewBox, so users never see the source text
            # flash or the unpositioned diagram jump into place.
            "  .diagram-viewport pre.mermaid { visibility: hidden; margin: 0; }",
            "  .diagram-viewport.ready pre.mermaid { visibility: visible; }",
            "  .diagram-loading { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #999; font-size: 0.9em; }",
            "  .diagram-viewport.ready .diagram-loading { display: none; }",
            "  .diagram-controls { display: flex; gap: 0.4em; margin-top: 0.5em; }",
            "  .diagram-controls button { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 0.3em 0.7em; cursor: pointer; font-size: 0.85em; }",
            "  .diagram-controls button:hover { background: #e8e8e8; }",
            "  .diagram h2 { margin: 0 0 0.5em 0; font-size: 1.1em; color: #555; }",
            "  .topnav { margin-bottom: 1em; font-size: 0.95em; color: #555; background: #f7f7f7; border: 1px solid #eee; border-radius: 8px; padding: 0.6em 0.9em; }",
            "  .section { background: #f9f9f9; border: 1px solid #eee; border-radius: 8px; padding: 0.8em 1.2em; margin: 1em 0; }",
            "  .section h2 { margin: 0 0 0.2em 0; font-size: 1.1em; color: #444; border: none; padding: 0; }",
            "  .section .subtitle { font-size: 0.9em; color: #666; margin: 0.35em 0; }",
            "  .severity-summary { background: #f9f9f9; border: 1px solid #ddd; border-radius: 8px; padding: 0.6em 1.5em; margin: 1.2em 0 0; }",
            "  .sev-count { margin-right: 1.2em; white-space: nowrap; cursor: default; }",
            "  .footer { margin-top: 2em; font-size: 0.85em; color: #aaa; text-align: center; }",
            "</style>",
            "</head><body>",
            '<p class="topnav"><strong>Navigation:</strong> <a href="./">OWL ontology checker</a> &middot; <a href="guide">OWL ontology publishing guide</a> &middot; <a href="docs">API docs</a></p>',
            f'<h1>Results for {source_html}</h1>',
        ]

    def _diagram(self) -> None:
        # Ontology diagram (Mermaid)  -  shown first
        if self.mermaid:
            self.parts.append('<div class="diagram">')
            self.parts.append("<h2>Ontology diagram</h2>")
            self.parts.append('<div id="diagram-viewport" class="diagram-viewport">')
            self.parts.append('<div class="diagram-loading">Rendering diagram&hellip;</div>')
            self.parts.append(f'<pre class="mermaid">\n{escape(self.mermaid)}\n</pre>')
            self.parts.append('</div>')
            # Hidden copy of the Mermaid source so JS can copy / export it even
            # after Mermaid has replaced the <pre> with the rendered SVG.
            self.parts.append(f'<textarea id="mermaid-src" style="display:none">{escape(self.mermaid)}</textarea>')
            self.parts.append('<div class="diagram-controls">')
            self.parts.append('<button onclick="pzIn&amp;&amp;pzIn()">+ Zoom in</button>')
            self.parts.append('<button onclick="pzOut&amp;&amp;pzOut()">&minus; Zoom out</button>')
            self.parts.append('<button onclick="pzReset&amp;&amp;pzReset()">Reset view</button>')
            self.parts.append('<button onclick="copyMermaid&amp;&amp;copyMermaid(this)">Copy Mermaid</button>')
            self.parts.append('<button onclick="downloadSVG&amp;&amp;downloadSVG()">Download SVG</button>')
            self.parts.append('<button onclick="downloadPNG&amp;&amp;downloadPNG()">Download PNG</button>')
            self.parts.append('<span style="font-size:0.8em;color:#999;margin-left:0.5em;">Ctrl+scroll to zoom, drag to pan</span>')
            self.parts.append('</div>')
            self.parts.append("</div>")

    def _row(self, anchor: str, title: str, detail: str, *, na: bool = False) -> str:
        found = self.sev_summary.for_check(anchor)
        mark = _na_mark('1.1em') if na else _mark(worst_severity(found), '1.1em')
        counts = _count_text(found)
        if counts:
            detail = f'{detail} ({counts})'
        # Whole row jumps to the matching section anchor when clicked.
        # Scrolling is done explicitly (not just via location.hash) because
        # setting the hash to its current value is a no-op in browsers - it
        # would fail to (re)scroll if the user is already on that hash.
        # <details> blocks are deliberately left as-is (collapsed stays
        # collapsed) so clicking an overview row never force-expands
        # content the user didn't ask to see.
        num = _CHECK_NUMBERS.get(anchor, "")
        prefix = f'<span class="num">{num}</span> ' if num else ""
        onclick = (
            f"const t=document.getElementById('{anchor}');"
            "t.scrollIntoView();"
            f"location.hash='{anchor}';"
        )
        return (
            f'<tr onclick="{onclick}">'
            f'<td>{mark} {prefix}<strong>{title}</strong></td>'
            f'<td>{detail}</td>'
            f'</tr>'
        )

    def _summary_for(self, report_anchor: str) -> list[str]:
        meta = self.report.ontology_metadata
        docs = self.report.definition_docs
        reasoner = self.report.reasoner
        lt = self.report.lang_tags
        if report_anchor == 'namespaces':
            if self.report.namespace_resolution_skipped:
                return [self._row('namespaces', 'Namespaces', 'resolution skipped', na=True)]
            return [self._row('namespaces', 'Namespaces', f'{self.ok_ns}/{self.total_ns} resolved')]
        if report_anchor == 'external-terms':
            if self.terms_unchecked:
                return [self._row('external-terms', 'External term definitions',
                             'not checked (namespaces not resolved)', na=True)]
            if not self.total_terms:
                return [self._row('external-terms', 'External term definitions', 'no external terms to check', na=True)]
            skipped = self.total_terms - self.ok_terms - self.fail_terms - self.warn_terms
            term_bits = [f'{self.ok_terms} confirmed']
            if self.fail_terms:
                term_bits.append(f'{self.fail_terms} not found')
            if self.warn_terms:
                term_bits.append(f'{self.warn_terms} deprecated')
            if skipped:
                term_bits.append(f'{skipped} skipped')
            return [self._row('external-terms', 'External term definitions', ', '.join(term_bits))]
        if report_anchor == 'ontology-metadata':
            if not (meta and meta.total_checks):
                return []
            return [self._row('ontology-metadata', 'Ontology metadata',
                         f'{meta.passed_checks}/{meta.total_checks} present')]
        if report_anchor == 'internal-terms':
            it = self.report.internal_terms
            if not it or it.status == Status.SKIP:
                return [self._row('internal-terms', 'Internal term definitions',
                             (escape(it.message) if it and it.message else None) or 'not applicable', na=True)]
            return [self._row('internal-terms', 'Internal term definitions',
                         f'{it.defined}/{it.total_referenced} defined')]
        if report_anchor == 'term-inventory':
            inv = self.report.term_inventory
            if not inv or inv.status == Status.SKIP:
                return [self._row('term-inventory', 'Term inventory &amp; naming',
                             'no terms defined in the ontology&rsquo;s own namespace', na=True)]
            return [self._row('term-inventory', 'Term inventory &amp; naming',
                         f'{inv.total_terms} terms')]
        if report_anchor == 'domains-ranges':
            dr = self.report.domains_ranges
            if not dr or dr.status == Status.SKIP:
                return [self._row('domains-ranges', 'Domains &amp; ranges',
                             'no object or datatype properties defined', na=True)]
            return [self._row('domains-ranges', 'Domains &amp; ranges',
                         f'{dr.total_properties} property(ies) checked')]
        if report_anchor == 'datatypes':
            dt = self.report.datatypes
            if not dt or dt.status == Status.SKIP:
                return [self._row('datatypes', 'Datatypes', 'no datatypes used', na=True)]
            return [self._row('datatypes', 'Datatypes', f'{dt.total_datatypes} used')]
        if report_anchor == 'labels':
            if not (docs and docs.total_definitions):
                return [self._row('labels', 'Labels', 'no internal definitions to document', na=True)]
            return [self._row('labels', 'Labels',
                         f'{docs.with_label}/{docs.total_definitions} have a label')]
        if report_anchor == 'comments':
            if not (docs and docs.total_definitions):
                return [self._row('comments', 'Comments', 'no internal definitions to document', na=True)]
            return [self._row('comments', 'Comments',
                         f'{docs.with_comment}/{docs.total_definitions} meet the comment recommendation')]
        if report_anchor == 'imports':
            imp = self.report.imports
            if not imp:
                return []
            if not imp.checks:
                return [self._row('imports', 'Imports', 'no imports declared')]
            if imp.skipped:
                return [self._row('imports', 'Imports', 'resolution skipped', na=True)]
            if imp.discovered:
                return [self._row('imports', 'Imports',
                             f'{len(imp.discovered)} found via linked/alternative RDF, {len(imp.broken)} unresolved')]
            return [self._row('imports', 'Imports',
                         f'{len(imp.checks) - len(imp.broken)}/{len(imp.checks)} declared import(s) resolve')]
        if report_anchor == 'license':
            lcns = self.report.license
            if not lcns:
                return []
            if not lcns.license_count:
                return [self._row('license', 'Open licence', 'no licence declared')]
            kinds = [
                f'{n} {label}' for label, n in lcns.category_counts.items() if n
            ]
            plural = 's' if lcns.license_count != 1 else ''
            return [self._row('license', 'Open licence',
                         f'{lcns.license_count} licence{plural} &middot; {", ".join(kinds)}')]
        if report_anchor == 'iri-strategy':
            iri = self.report.iri_strategy
            if not iri:
                return []
            if iri.status == Status.SKIP:
                return [self._row('iri-strategy', 'IRI strategy', escape(iri.message) if iri.message else 'skipped', na=True)]
            if len(iri.namespaces) == 1:
                ns = iri.namespaces[0]
                if ns.strategy == 'mixed':
                    detail = f'mixed: {ns.hash_count} hash + {ns.slash_count} slash'
                else:
                    label = 'hash (<code>#Term</code>)' if ns.strategy == 'hash' else 'slash (<code>/Term</code>)'
                    count = ns.hash_count if ns.strategy == 'hash' else ns.slash_count
                    detail = f'{label} &middot; {count} term{"s" if count != 1 else ""}'
                return [self._row('iri-strategy', 'IRI strategy', detail)]
            return [self._row('iri-strategy', 'IRI strategy', f'{len(iri.namespaces)} base IRIs checked')]
        if report_anchor == 'iri-scheme':
            sch = self.report.iri_scheme
            if not sch:
                return []
            if sch.status == Status.SKIP:
                return [self._row('iri-scheme', 'IRI scheme', escape(sch.message) if sch.message else 'skipped', na=True)]
            return [self._row('iri-scheme', 'IRI scheme', f'{sch.total_hosts} namespace(s) checked')]
        if report_anchor == 'reasoner':
            if not reasoner:
                return []
            return [self._row('reasoner', 'Reasoner checks',
                         'no contradictions detected' if not self.sev_summary.for_check('reasoner') else 'problems found')]
        if report_anchor == 'unused-prefixes':
            return [self._row('unused-prefixes', 'Unused prefixes',
                         f'{len(self.report.unused_prefixes)} declared but never used' if self.report.unused_prefixes else 'none')]
        if report_anchor == 'language-tags':
            if lt and lt.status != Status.SKIP:
                lang_str = escape(', '.join(lt.languages_used)) or 'no language tags'
                return [self._row('language-tags', 'Language tag consistency', lang_str)]
            return [self._row('language-tags', 'Language tag consistency', 'not applicable', na=True)]
        if report_anchor == 'non-ontology-terms':
            sk = self.report.non_ontology_terms
            if not sk or sk.status == Status.SKIP:
                return [self._row('non-ontology-terms', 'Non-ontology terms', 'not applicable', na=True)]
            return [self._row('non-ontology-terms', 'Non-ontology terms',
                         f'{len(sk.terms)} SKOS concept(s) to review' if sk.terms else 'no internal SKOS concepts')]
        return []

    def _overview(self) -> None:
        self.parts.append(_severity_summary_html(self.sev_summary))
        self.parts.append('<div class="summary"><table>')
        for cat in CATEGORIES:
            rows: list[str] = []
            for check in CHECKS:
                if check["category"] != cat["key"]:
                    continue
                rows.extend(self._summary_for(check["report_anchor"]))
            if not rows:
                continue
            self.parts.append(
                f'<tr class="cluster-row"><td colspan="2">{_CLUSTER_NUMBERS[cat["key"]]}. {cat["label"]}</td></tr>'
            )
            self.parts.extend(rows)
        self.parts.append("</table></div>")

        # Tip: link to the publishing guide
        self.parts.append('<p style="font-size:0.9em;color:#666;margin:0.5em 0 1em;">Not sure what a check means? See the <a href="guide">publishing guide</a> for explanations and best practices.</p>')

    def _render_ns_card(self, ns: NamespaceReport) -> None:
        mark = _item_mark(ns.resolution.status, Rule.NAMESPACE_UNRESOLVED)
        prefix = escape(ns.prefix) or "<em>(default)</em>"
        uri = escape(ns.uri)
        self.parts.append(f'<div class="ns"><div class="ns-header">{mark} {prefix}: &lt;{uri}&gt;</div>')
        self.parts.append('<div class="ns-body">')

        res = ns.resolution
        if res.http_status:
            self.parts.append(f"<p>HTTP {res.http_status}")
            if res.content_type:
                self.parts.append(f" &middot; {escape(res.content_type)}")
            if res.is_valid_rdf is not None:
                self.parts.append(f" &middot; {'valid' if res.is_valid_rdf else 'invalid'} RDF")
            self.parts.append("</p>")
        if res.error:
            self.parts.append(f"<p style='color:#c00'>{escape(res.error)}</p>")
        self._resolution_provenance(res)

        # Term counts only - per-term details are shown in the External terms
        # definition section below to avoid duplicating the same information.
        terms = self.report.external_terms_for_namespace(ns)
        if terms:
            t_ok = sum(1 for t in terms if t.status == Status.OK)
            t_fail = sum(1 for t in terms if t.status == Status.FAIL)
            t_warn = sum(1 for t in terms if t.status == Status.WARN)
            t_skip = sum(1 for t in terms if t.status == Status.SKIP)
            summary_parts = []
            if t_ok:
                summary_parts.append(f"{t_ok} confirmed")
            if t_fail:
                summary_parts.append(f"{t_fail} not found")
            if t_warn:
                summary_parts.append(f"{t_warn} deprecated")
            if t_skip:
                summary_parts.append(f"{t_skip} skipped")
            self.parts.append(f'<p style="font-size:0.9em;color:#666;">'
                         f'{len(terms)} term{"s" if len(terms) != 1 else ""} used '
                         f'({" &middot; ".join(summary_parts)}), '
                         f'see <a href="#external-terms">External term definitions</a> section</p>')
        elif ns.terms:
            self.parts.append('<p>Datatype findings are reported under <a href="#datatypes">Datatypes</a>.</p>')
        else:
            self.parts.append("<p><em>No terms used from this namespace.</em></p>")

        self.parts.append("</div></div>")

    def _section_heading(self, anchor: str, title: str, label: str, *, na: bool = False) -> str:
        worst = worst_severity(self.sev_summary.for_check(anchor))
        if not na and worst is not None:
            label = f'{SEVERITY_STYLES[worst].label}: {label}'
        mark_html = _na_mark('1.1em') if na else _mark(worst, '1.1em')
        marked = (f'<span title="{escape(label)}" aria-label="{escape(label)}" '
                  f'style="margin-right:0.4em;">{mark_html}</span>')
        num = _CHECK_NUMBERS.get(anchor, "")
        num_html = f'<span class="num">{num}</span> ' if num else ""
        return f'<h2 id="{anchor}">{marked}{num_html}{title}</h2>'

    def _subtitle(self, text: str) -> str:
        return f'<p class="subtitle">{text}</p>'

    def _open_cluster(self, report_anchor: str) -> None:
        cat = _CATEGORY_BY_REPORT.get(report_anchor)
        if cat is None or cat in self._emitted_clusters:
            return
        self._emitted_clusters.add(cat)
        self.parts.append(f'<h2 class="cluster-band">{_CLUSTER_NUMBERS[cat]}. {CATEGORY_LABELS[cat]}</h2>')

    def _skipped_section(self, anchor: str, title: str, reason: str) -> None:
        """Render a compact 'not applicable' section so every check is visible."""
        self._open_cluster(anchor)
        self.parts.append('<section class="section">')
        self.parts.append(self._section_heading(anchor, title, reason, na=True))
        self.parts.append(_guide_link(anchor))
        self.parts.append(self._subtitle(reason))
        self.parts.append('</section>')

    def _metadata(self) -> None:
        # Ontology metadata summary
        meta = self.report.ontology_metadata
        if meta and meta.checks:
            self._open_cluster('ontology-metadata')
            core_missing = [c for c in meta.missing if c.tier == 'core']
            extra_missing = [c for c in meta.missing if c.tier != 'core']
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('ontology-metadata', 'Ontology metadata',
                                          f'{len(meta.missing)} missing' if meta.missing else 'all present'))
            self.parts.append(_guide_link('ontology-metadata'))
            self.parts.append('<p class="subtitle">The ontology header (title, creator, version, &hellip;) is checked against <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/ontology_metadata.ttl" target="_blank" rel="noopener">SHACL shapes for the ontology header</a>. A missing property is reported as a recommendation.</p>')
            summary_bits = [f"{meta.passed_checks} present"]
            if core_missing:
                summary_bits.append(f"{len(core_missing)} core missing")
            if extra_missing:
                summary_bits.append(f"{len(extra_missing)} additional missing")
            self.parts.append(self._subtitle(" &middot; ".join(summary_bits)))
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show metadata checks ({meta.total_checks})</summary>')
            self.parts.append('<table><tr><th>Property</th><th>Group</th><th>Status</th></tr>')
            for check in meta.checks:
                mark = _item_mark(check.status, Rule.METADATA_MISSING)
                if check.status == Status.OK:
                    status_label = f'<span style="color:{_OK_COLOR}">present</span>'
                else:
                    status_label = 'missing'
                self.parts.append(
                    f'<tr><td><code>{escape(check.property)}</code></td><td>{escape(check.tier)}</td><td>{mark} {status_label}</td></tr>'
                )
            self.parts.append('</table></details>')
            self.parts.append('</section>')

    def _imports(self) -> None:
        # Imports check
        imp = self.report.imports
        if imp is not None:
            self._open_cluster('imports')
            broken = imp.broken
            if imp.skipped:
                i_label = 'resolution skipped'
            elif imp.discovered:
                i_label = f'{len(imp.discovered)} found via linked/alternative RDF'
                if broken:
                    i_label += f', {len(broken)} broken'
            else:
                i_label = f'{len(broken)} broken' if broken else ('all resolve' if imp.checks else 'none declared')
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('imports', 'Imports', i_label, na=imp.skipped))
            self.parts.append(_guide_link('imports'))
            self.parts.append('<p class="subtitle">Directly declared <code>owl:imports</code> targets must provide parseable RDF. Nested imports are not followed, and imported axioms are not used by the other checks.</p>')
            if imp.skipped:
                self.parts.append(self._subtitle(f'{len(imp.checks)} declared import(s), resolution skipped'))
            elif broken:
                self.parts.append(self._subtitle(f'{len(broken)} of {len(imp.checks)} declared import(s) do not resolve'))
            elif imp.discovered:
                self.parts.append(self._subtitle(f'{len(imp.discovered)} declared import(s) required linked/alternative RDF documents; other tools may not discover them.'))
            elif imp.checks:
                self.parts.append(self._subtitle(f'{len(imp.checks)} declared import(s), all resolve'))
            else:
                self.parts.append(self._subtitle('no owl:imports declared'))
            if imp.checks:
                opened = ' open' if imp.discovered else ''
                self.parts.append(f'<details{opened}><summary style="cursor:pointer;font-weight:600;">Show imports ({len(imp.checks)})</summary>')
                for c in imp.checks:
                    rule = Rule.IMPORT_DISCOVERED if c.resolution.status == Status.WARN else Rule.IMPORT_UNRESOLVED
                    mark = _item_mark(c.resolution.status, rule)
                    iri = escape(c.iri)
                    self.parts.append(f'<div class="ns"><div class="ns-header">{mark} &lt;{_external_link(c.iri, iri)}&gt;</div>')
                    self.parts.append('<div class="ns-body">')
                    res = c.resolution
                    if res.http_status:
                        self.parts.append(f"<p>HTTP {res.http_status}")
                        if res.content_type:
                            self.parts.append(f" &middot; {escape(res.content_type)}")
                        if res.is_valid_rdf is not None:
                            self.parts.append(f" &middot; {'valid' if res.is_valid_rdf else 'invalid'} RDF")
                        self.parts.append("</p>")
                    if res.error:
                        self.parts.append(f"<p style='color:#c00'>{escape(res.error)}</p>")
                    self._resolution_provenance(res)
                    self.parts.append('</div></div>')
                self.parts.append('</details>')
            self.parts.append('</section>')

    def _iri_strategy(self) -> None:
        # IRI strategy (hash vs slash) for the ontology's own defined terms
        iri = self.report.iri_strategy
        if iri is not None:
            self._open_cluster('iri-strategy')
            multi = len(iri.namespaces) > 1
            if iri.status == Status.SKIP:
                s_label = 'skipped'
            elif multi:
                s_label = f'{len(iri.namespaces)} base IRIs'
            else:
                s_label = f'{iri.namespaces[0].strategy} style'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('iri-strategy', 'IRI strategy', s_label, na=iri.status == Status.SKIP))
            self.parts.append(_guide_link('iri-strategy'))
            self.parts.append('<p class="subtitle">A consistent IRI pattern for the ontology&rsquo;s own terms. Either every term sits under a fragment (<code>http://example.org/ont#Term</code>, the <strong>hash</strong> pattern) or every term is its own slash path (<code>http://example.org/ont/Term</code>, the <strong>slash</strong> pattern). Mixing both within the same base IRI confuses consumers and tooling; an ontology that bundles more than one base IRI may use a different, internally consistent style for each.</p>')

            if iri.status == Status.SKIP:
                self.parts.append(self._subtitle(escape(iri.message) if iri.message else 'no terms in the ontology&rsquo;s own namespace could be classified'))
            else:
                for ns in iri.namespaces:
                    if multi:
                        self.parts.append(f'<p style="margin:0.6em 0 0.2em;font-weight:600;"><code>{escape(ns.namespace)}</code></p>')
                    if ns.strategy == 'mixed':
                        self.parts.append(self._subtitle(
                            f'<strong>Mixed</strong>: {ns.hash_count} hash-style and {ns.slash_count} slash-style terms in the same namespace. Pick one and migrate the others.',
                        ))
                        self.parts.append('<details><summary style="cursor:pointer;font-weight:600;">Show examples</summary>')
                        if ns.hash_examples:
                            self.parts.append(f'<p style="margin:0.5em 0 0.2em;font-weight:600;">Hash style ({ns.hash_count}):</p>')
                            self.parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                            for ex in ns.hash_examples:
                                self.parts.append(f'<li><code>{escape(ex)}</code></li>')
                            self.parts.append('</ul>')
                        if ns.slash_examples:
                            self.parts.append(f'<p style="margin:0.5em 0 0.2em;font-weight:600;">Slash style ({ns.slash_count}):</p>')
                            self.parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                            for ex in ns.slash_examples:
                                self.parts.append(f'<li><code>{escape(ex)}</code></li>')
                            self.parts.append('</ul>')
                        self.parts.append('</details>')
                    else:
                        count = ns.hash_count if ns.strategy == 'hash' else ns.slash_count
                        pattern = '<code>#Term</code>' if ns.strategy == 'hash' else '<code>/Term</code>'
                        self.parts.append(self._subtitle(
                            f'<strong>{escape(ns.strategy.capitalize())} pattern</strong> ({pattern}) used consistently across all {count} defined term{"s" if count != 1 else ""}.',
                        ))
                        examples = ns.hash_examples if ns.strategy == 'hash' else ns.slash_examples
                        if examples:
                            self.parts.append('<details><summary style="cursor:pointer;font-weight:600;">Show examples</summary>')
                            self.parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                            for ex in examples:
                                self.parts.append(f'<li><code>{escape(ex)}</code></li>')
                            self.parts.append('</ul></details>')
            self.parts.append('</section>')

    def _iri_scheme(self) -> None:
        # IRI scheme consistency (http vs https) per namespace
        sch = self.report.iri_scheme
        if sch is not None:
            self._open_cluster('iri-scheme')
            if sch.status == Status.SKIP:
                sc_label = 'skipped'
            elif sch.status == Status.WARN:
                sc_label = f'{len(sch.conflicts)} mixed namespace(s)'
            else:
                sc_label = 'consistent'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('iri-scheme', 'IRI scheme (http vs https)', sc_label, na=sch.status == Status.SKIP))
            self.parts.append(_guide_link('iri-scheme'))
            self.parts.append('<p class="subtitle">In RDF, <code>http://example.org/X</code> and <code>https://example.org/X</code> are <strong>different IRIs</strong>. Within one ontology, each namespace should appear under exactly one scheme. Mixing schemes can prevent tools from matching references to the same intended term.</p>')

            if sch.status == Status.SKIP:
                self.parts.append(self._subtitle(escape(sch.message) if sch.message else 'no http(s) IRIs found'))
            elif sch.status == Status.WARN:
                self.parts.append(self._subtitle(
                    f'<strong>{len(sch.conflicts)}</strong> namespace(s) are referenced under both <code>http://</code> and <code>https://</code> in the same ontology.',
                ))
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show conflicting namespaces ({len(sch.conflicts)})</summary>')
                for c in sch.conflicts:
                    self.parts.append(f'<h3 style="margin:1em 0 0.3em;font-size:1em;"><code>{escape(c.host)}</code></h3>')
                    self.parts.append(
                        f'<p style="font-size:0.9em;color:#444;margin:0.2em 0;">'
                        f'<strong>{c.http_count}</strong> reference(s) use <code>http://</code> and '
                        f'<strong>{c.https_count}</strong> use <code>https://</code>. '
                        f'Pick one canonical scheme and migrate the others.</p>'
                    )
                    if c.http_examples:
                        self.parts.append('<p style="font-size:0.9em;margin:0.4em 0 0.2em;"><code>http://</code> examples:</p>')
                        self.parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                        for ex in c.http_examples:
                            self.parts.append(f'<li><code>{escape(ex)}</code></li>')
                        self.parts.append('</ul>')
                    if c.https_examples:
                        self.parts.append('<p style="font-size:0.9em;margin:0.4em 0 0.2em;"><code>https://</code> examples:</p>')
                        self.parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                        for ex in c.https_examples:
                            self.parts.append(f'<li><code>{escape(ex)}</code></li>')
                        self.parts.append('</ul>')
                self.parts.append('</details>')
            else:
                self.parts.append(self._subtitle(
                    f'<strong>{sch.total_hosts}</strong> namespace(s) referenced, each under a single scheme '
                    f'({sch.http_only_hosts} <code>http://</code>, {sch.https_only_hosts} <code>https://</code>).',
                ))
            if sch.hosts:
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show namespaces ({len(sch.hosts)})</summary>')
                self.parts.append('<table><tr><th>Namespace</th><th>Scheme</th><th>Count</th></tr>')
                for h in sch.hosts:
                    self.parts.append(
                        f'<tr><td><code>{escape(h.host)}</code></td>'
                        f'<td><code>{escape(h.scheme)}://</code></td>'
                        f'<td>{h.count}</td></tr>'
                    )
                self.parts.append('</table></details>')
            self.parts.append('</section>')

    def _license(self) -> None:
        # Licence check
        lcns = self.report.license
        if lcns is not None:
            self._open_cluster('license')
            if lcns.license_count == 0:
                i_label = 'no licence declared'
            elif lcns.license_count == 1:
                if lcns.recommended_licenses:
                    i_label = 'recommended licence declared'
                elif lcns.open_licenses:
                    i_label = 'open licence declared, not recommended'
                elif lcns.unrecognised_licenses:
                    i_label = 'unrecognised licence declared'
                else:
                    i_label = 'no open licence declared'
            else:
                i_label = 'multiple licences declared'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('license', 'Open licence', i_label))
            self.parts.append(_guide_link('license'))
            self.parts.append('<p class="subtitle">Ontology-header <code>dcterms:license</code> and <code>schema:license</code> values are checked against known licences. Missing, unrecognised, non-open, non-preferred or multiple licences are recommendations. TDCC prefers a single CC0 or CC BY licence; an unrecognised licence has not been assessed for openness.</p>')
            license_count = len(lcns.checks)
            plural = "s" if license_count > 1 else ""
            if lcns.checks:
                kinds = [
                    f'{n} {label}' for label, n in lcns.category_counts.items() if n
                ]
                self.parts.append(self._subtitle(f'<strong>{license_count}</strong> licence{plural} &middot; {", ".join(kinds)}'))
            else:
                self.parts.append(self._subtitle('no licence declared'))
            if lcns.checks:
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show licence{plural} ({len(lcns.checks)})</summary>')
                for c in lcns.checks:
                    rule = Rule.LICENSE_NOT_OPEN if c.is_open is not True else Rule.LICENSE_NOT_RECOMMENDED
                    mark = _item_mark(c.status, rule)
                    self.parts.append(f'<div class="ns"><div class="ns-header">{mark} {escape(c.name)}</div>')
                    self.parts.append('<div class="ns-body">')
                    self.parts.append(f'<p style="font-size:0.9em;color:#444;margin:0.2em 0;">Licence IRI: {_external_link(c.iri, "<code>" + escape(c.iri) + "</code>")}</p>')
                    if c.status == Status.OK:
                        self.parts.append('<p style="font-size:0.9em;color:#444;margin:0.2em 0;">This is one of the open licences we recommend.</p>')
                    elif c.is_open is None:
                        self.parts.append('<p style="font-size:0.9em;color:#444;margin:0.2em 0;">This licence is unrecognised; openness could not be established.</p>')
                    elif c.status == Status.WARN:
                        self.parts.append('<p style="font-size:0.9em;color:#444;margin:0.2em 0;">This is an open licence but we do not recommend it.</p>')
                    else:
                        self.parts.append('<p style="font-size:0.9em;color:#444;margin:0.2em 0;">This is not a known open licence.</p>')
                    self.parts.append('</div></div>')
                self.parts.append('</details>')
            self.parts.append('</section>')

    def _namespaces(self) -> None:
        # Per-namespace details  -  split into "interesting" and "standard OK"
        STANDARD_NS = {
            "http://www.w3.org/2002/07/owl#",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "http://www.w3.org/2000/01/rdf-schema#",
            "http://www.w3.org/2001/XMLSchema#",
            "http://www.w3.org/XML/1998/namespace",
            "http://www.w3.org/2004/02/skos/core#",
            "http://www.w3.org/ns/prov#",
            "http://purl.org/dc/terms/",
            "http://purl.org/dc/elements/1.1/",
            "http://xmlns.com/foaf/0.1/",
            "https://schema.org/",
            "http://schema.org/",
            "http://www.w3.org/ns/shacl#",
            "http://www.w3.org/2006/time#",
            "http://www.w3.org/ns/dcat#",
            "http://www.opengis.net/ont/geosparql#",
        }

        def _ns_has_issues(ns: NamespaceReport) -> bool:
            if ns.resolution.status != Status.OK:
                return True
            return any(t.status in (Status.FAIL, Status.WARN) for t in self.report.external_terms_for_namespace(ns))

        prominent = [ns for ns in self.report.namespaces if _ns_has_issues(ns) or ns.uri not in STANDARD_NS]
        standard_ok = sorted(
            [ns for ns in self.report.namespaces if not _ns_has_issues(ns) and ns.uri in STANDARD_NS],
            key=lambda ns: ns.prefix.lower(),
        )

        # --- Namespaces section: resolvability of each declared prefix ---
        self._open_cluster('namespaces')
        unresolved_ns = len(self.sev_summary.for_check('namespaces'))
        all_ns_skipped = self.report.namespace_resolution_skipped
        ns_label = 'resolution skipped' if all_ns_skipped else (f'{unresolved_ns} unresolved' if unresolved_ns else 'all resolved')
        self.parts.append('<section class="section">')
        self.parts.append(self._section_heading('namespaces', 'Namespaces', ns_label, na=all_ns_skipped))
        self.parts.append(_guide_link('namespaces'))
        self.parts.append('<p class="subtitle">Namespaces of terms used as subjects are fetched over HTTP and parsed as RDF where possible. If a namespace cannot be resolved, its external terms cannot be checked.</p>')
        self.parts.append(f'<p class="subtitle"><strong>{self.ok_ns}/{self.total_ns}</strong> namespaces resolved.</p>')

        if prominent:
            failed_ns = [ns for ns in prominent if ns.resolution.status == Status.FAIL]
            warn_ns = [ns for ns in prominent if ns.resolution.status == Status.WARN]
            ok_ns_list = [ns for ns in prominent if ns.resolution.status == Status.OK]

            if failed_ns:
                http_404 = [ns for ns in failed_ns if ns.resolution.http_status == 404]
                http_other = [ns for ns in failed_ns if ns.resolution.http_status and ns.resolution.http_status != 404]
                conn_err = [ns for ns in failed_ns if not ns.resolution.http_status]

                if http_404:
                    self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">404 Not Found ({len(http_404)})</summary>')
                    for ns in http_404:
                        self._render_ns_card(ns)
                    self.parts.append('</details>')
                if http_other:
                    self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Other HTTP errors ({len(http_other)})</summary>')
                    for ns in http_other:
                        self.parts.append(f'<h3>HTTP {ns.resolution.http_status}</h3>')
                        self._render_ns_card(ns)
                    self.parts.append('</details>')
                if conn_err:
                    self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Connection errors ({len(conn_err)})</summary>')
                    for ns in conn_err:
                        self._render_ns_card(ns)
                    self.parts.append('</details>')

            if warn_ns:
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Warnings ({len(warn_ns)})</summary>')
                for ns in warn_ns:
                    self._render_ns_card(ns)
                self.parts.append('</details>')

            if ok_ns_list:
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Resolved OK ({len(ok_ns_list)})</summary>')
                for ns in ok_ns_list:
                    self._render_ns_card(ns)
                self.parts.append("</details>")

        if standard_ok:
            total_std_terms = sum(
                t.status == Status.OK for ns in standard_ok for t in self.report.external_terms_for_namespace(ns)
            )
            self.parts.append('<details style="margin-top:1.5em;"><summary style="cursor:pointer;padding:0.6em 0;font-weight:bold;color:#555;">')
            self.parts.append(f'{len(standard_ok)} standard vocabularies OK ({total_std_terms} terms verified)</summary>')
            for ns in standard_ok:
                self._render_ns_card(ns)
            self.parts.append("</details>")
        self.parts.append('</section>')

    def _unused_prefixes(self) -> None:
        # Unused prefixes - styled identically to the other check sections.
        self._open_cluster('unused-prefixes')
        self.parts.append('<section class="section">')
        if self.report.unused_prefixes:
            self.parts.append(self._section_heading('unused-prefixes', 'Unused prefixes',
                                          f'{len(self.report.unused_prefixes)} to clean up'))
            self.parts.append(_guide_link('unused-prefixes'))
            self.parts.append('<p class="subtitle">Detected prefix bindings whose namespace has no matching IRI use, including header and literal datatype IRIs. Built-in declarations and source-level aliases cannot be fully distinguished after parsing.</p>')
            self.parts.append(self._subtitle(f'{len(self.report.unused_prefixes)} declared but never used'))
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show unused prefixes ({len(self.report.unused_prefixes)})</summary>')
            self.parts.append('<table><tr><th>Prefix</th><th>Namespace IRI</th></tr>')
            for up in self.report.unused_prefixes:
                pfx = escape(up.prefix) or '<em>(default)</em>'
                uri = escape(up.uri)
                self.parts.append(f'<tr><td><code>{pfx}:</code></td><td><code>&lt;{uri}&gt;</code></td></tr>')
            self.parts.append('</table></details>')
        else:
            self.parts.append(self._section_heading('unused-prefixes', 'Unused prefixes', 'all good'))
            self.parts.append(_guide_link('unused-prefixes'))
            self.parts.append('<p class="subtitle">Detected prefix bindings whose namespace has no matching IRI use, including header and literal datatype IRIs. Built-in declarations and source-level aliases cannot be fully distinguished after parsing.</p>')
            self.parts.append(self._subtitle('No unused prefix bindings detected.'))
        self.parts.append('</section>')

    def _external_terms(self) -> None:
        # --- External term definitions: per-term verification against the remote vocabulary ---
        skipped = self.total_terms - self.ok_terms - self.fail_terms - self.warn_terms
        if self.fail_terms:
            term_label = f'{self.fail_terms} not found in remote vocabulary'
        elif self.warn_terms:
            term_label = f'{self.warn_terms} deprecated upstream'
        elif self.terms_unchecked:
            term_label = 'not checked'
        elif skipped:
            term_label = f'{skipped} not checkable'
        elif not self.total_terms:
            term_label = 'no external terms to check'
        else:
            term_label = 'all verified'
        self._open_cluster('external-terms')
        self.parts.append('<section class="section">')
        self.parts.append(self._section_heading('external-terms', 'External term definitions', term_label,
                                      na=self.terms_unchecked or not self.total_terms))
        self.parts.append(_guide_link('external-terms'))
        self.parts.append('<p class="subtitle">External terms used as subjects are checked against the retrieved vocabulary. Terms not found there and terms marked deprecated are reported. Unknown datatypes are reported under <a href="#datatypes">Datatypes</a>.</p>')
        term_summary_bits = [f'<strong>{self.ok_terms}</strong> confirmed']
        if self.fail_terms:
            term_summary_bits.append(f'<strong>{self.fail_terms}</strong> not found')
        if self.warn_terms:
            term_summary_bits.append(f'<strong>{self.warn_terms}</strong> deprecated upstream')
        if skipped:
            term_summary_bits.append(f'<strong>{skipped}</strong> skipped (namespace unavailable)')
        if self.terms_unchecked:
            self.parts.append('<p class="subtitle">No external term could be checked: its namespace was not resolved.</p>')
        elif self.total_terms:
            self.parts.append(f'<p class="subtitle">{" &middot; ".join(term_summary_bits)} of {self.total_terms} total.</p>')

        # Flat list of problem terms across all namespaces
        failed_terms_flat = self.view.external_by_status[Status.FAIL]
        deprecated_terms_flat = self.view.external_by_status[Status.WARN]
        skipped_terms_flat = self.view.external_by_status[Status.SKIP]
        if failed_terms_flat:
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Terms not found in their vocabulary ({len(failed_terms_flat)})</summary>')
            self.parts.append('<p style="font-size:0.85em;color:#666;margin:0.5em 0;">Some vocabularies redirect an unresolvable term&rsquo;s IRI to a general documentation page, which can coincidentally define a similarly named term under a different namespace. The IRI below is what askwol actually checked, not necessarily where the link redirects to.</p>')
            self.parts.append('<table><tr><th>Term</th><th>Prefix</th></tr>')
            for ns, t in failed_terms_flat:

                self.parts.append(f'<tr><td>{_external_link(t.term_uri, "<code>" + escape(t.local_name) + "</code>", title=True)}</td>'
                             f'<td><code>{escape(ns.prefix)}</code></td></tr>')
            self.parts.append('</table></details>')
        if deprecated_terms_flat:
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Deprecated upstream ({len(deprecated_terms_flat)})</summary>')
            self.parts.append('<table><tr><th>Term</th><th>Prefix</th><th>Marker</th></tr>')
            for ns, t in deprecated_terms_flat:

                self.parts.append(f'<tr><td>{_external_link(t.term_uri, "<code>" + escape(t.local_name) + "</code>", title=True)}</td>'
                             f'<td><code>{escape(ns.prefix)}</code></td>'
                             f'<td>{escape(t.deprecated or "")}</td></tr>')
            self.parts.append('</table></details>')
        if skipped_terms_flat:
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Terms not checkable, namespace unavailable ({len(skipped_terms_flat)})</summary>')
            self.parts.append('<table><tr><th>Term</th><th>Prefix</th></tr>')
            for ns, t in skipped_terms_flat:

                self.parts.append(f'<tr><td>{_external_link(t.term_uri, "<code>" + escape(t.local_name) + "</code>", title=True)}</td>'
                             f'<td><code>{escape(ns.prefix)}</code></td></tr>')
            self.parts.append('</table></details>')
        if self.ok_terms:
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Confirmed terms ({self.ok_terms})</summary>')
            self.parts.append('<table><tr><th>Term</th><th>Prefix</th></tr>')
            for ns in self.report.namespaces:
                for t in self.report.external_terms_for_namespace(ns):
                    if t.status == Status.OK:

                        self.parts.append(f'<tr><td>{_external_link(t.term_uri, "<code>" + escape(t.local_name) + "</code>", title=True)}</td>'
                                     f'<td><code>{escape(ns.prefix)}</code></td></tr>')
            self.parts.append('</table></details>')
        self.parts.append('</section>')

    def _internal_terms(self) -> None:
        # Internal term definitions: referenced own-namespace terms must be defined
        it = self.report.internal_terms
        if it and it.status != Status.SKIP:
            self._open_cluster('internal-terms')
            i_label = f'{len(it.undefined)} undefined' if it.undefined else 'all defined'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('internal-terms', 'Internal term definitions', i_label))
            self.parts.append(_guide_link('internal-terms'))
            self.parts.append('<p class="subtitle">Every term you use from your own namespace must also be defined there: it has to appear as the subject of at least one triple, not only as a predicate or object. A term that is referenced but never defined is usually a typo or a forgotten declaration.</p>')
            self.parts.append(self._subtitle(f'{it.defined}/{it.total_referenced} referenced terms defined &middot; {len(it.undefined)} undefined'))
            if it.undefined:
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Referenced but never defined ({len(it.undefined)})</summary>')
                self.parts.append('<table><tr><th>Term</th></tr>')
                for issue in it.undefined:

                    self.parts.append(
                        f'<tr><td>{_external_link(issue.term, "<code>" + escape(issue.display_name) + "</code>", title=True)}</td></tr>'
                    )
                self.parts.append('</table></details>')
            if it.referenced:
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show all referenced terms ({len(it.referenced)})</summary>')
                self.parts.append('<table><tr><th>Term</th><th>Status</th></tr>')
                for ref in sorted(it.referenced, key=lambda x: (x.defined, x.display_name.lower())):

                    status_html = (_mark(None, '1.1em') + ' defined' if ref.defined
                                   else _mark(RULE_SEVERITY[Rule.INTERNAL_TERM_UNDEFINED], '1.1em') + ' undefined')
                    self.parts.append(
                        f'<tr><td>{_external_link(ref.term, "<code>" + escape(ref.display_name) + "</code>", title=True)}</td>'
                        f'<td>{status_html}</td></tr>'
                    )
                self.parts.append('</table></details>')
            self.parts.append('</section>')
        else:
            self._skipped_section('internal-terms', 'Internal term definitions',
                             (escape(it.message) if it and it.message else None) or 'No <code>owl:Ontology</code> declaration, so the ontology&rsquo;s own namespace is unknown.')

    def _inventory(self) -> None:
        # Term inventory and naming conventions
        inv = self.report.term_inventory
        if inv and inv.status != Status.SKIP and inv.entries:
            self._open_cluster('term-inventory')
            inv_label = f'{len(inv.naming_issues)} naming issue(s)' if inv.naming_issues else 'naming consistent'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('term-inventory', 'Term inventory &amp; naming', inv_label))
            self.parts.append(_guide_link('term-inventory'))
            self.parts.append('<p class="subtitle">Every term defined in the ontology&rsquo;s own namespace, grouped by category. By convention, class names start with an uppercase letter (<code>Person</code>) and property names start with a lowercase letter (<code>hasName</code>).</p>')
            counts_html = ' &middot; '.join(
                f'<strong>{n}</strong> {escape(cat)}' for cat, n in inv.category_counts.items()
            )
            self.parts.append(self._subtitle(f'{inv.total_terms} internal term{"s" if inv.total_terms != 1 else ""}: {counts_html}'))
            summary = f'Show all terms ({inv.total_terms})'
            if inv.naming_issues:
                summary += f' &middot; {len(inv.naming_issues)} to review'
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">{summary}</summary>')
            self.parts.append('<table><tr><th>Term</th><th>Category</th><th>Naming</th></tr>')
            for e in sorted(inv.entries, key=lambda x: (x.naming_ok, x.category, x.display_name.lower())):

                if e.deprecated:
                    mark = f'<span title="Deprecated ({escape(e.deprecated)}); naming not checked" style="color:#999;font-size:1.2em;line-height:1">&#x2298;</span>'
                elif e.naming_ok:
                    mark = '<span style="color:#2e7d32;font-size:1.2em;line-height:1">&#x2713;</span>'
                else:
                    mark = f'{_mark(RULE_SEVERITY[Rule.NAMING_CONVENTION], "1.2em")} {escape(e.naming_message or "")}'
                self.parts.append(
                    f'<tr><td>{_external_link(e.term, "<code>" + escape(e.display_name) + "</code>", title=True)}</td>'
                    f'<td>{escape(e.category)}</td><td>{mark}</td></tr>'
                )
            self.parts.append('</table></details>')
            self.parts.append('</section>')
        else:
            self._skipped_section('term-inventory', 'Term inventory &amp; naming',
                             'No terms are defined in the ontology&rsquo;s own namespace.')

    def _domains_ranges(self) -> None:
        # Domains and ranges of object and datatype properties
        dr = self.report.domains_ranges
        if dr and dr.status != Status.SKIP and dr.checks:
            self._open_cluster('domains-ranges')
            dr_label = f'{len(dr.issues)} to review' if dr.issues else 'no issues detected'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('domains-ranges', 'Domains &amp; ranges', dr_label))
            self.parts.append(_guide_link('domains-ranges'))
            self.parts.append('<p class="subtitle">Checks directly declared <code>rdfs:domain</code> and <code>rdfs:range</code> on internal object and datatype properties. Missing declarations are recommendations; selected named class/datatype mismatches are errors. Inherited values and anonymous expressions are not evaluated.</p>')
            self.parts.append(self._subtitle(
                f'{dr.total_properties} propert{"y" if dr.total_properties == 1 else "ies"} '
                f'({dr.object_properties} object &middot; {dr.datatype_properties} datatype) &middot; '
                f'{dr.with_domain} with a domain &middot; {dr.with_range} with a range'))
            summary = f'Show all properties ({dr.total_properties})'
            if dr.issues:
                summary += f' &middot; {len(dr.issues)} to review'
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">{summary}</summary>')
            self.parts.append('<table><tr><th>Property</th><th>Category</th><th style="width:70px;">Domain</th><th style="width:70px;">Range</th><th>Status</th></tr>')
            for c in sorted(dr.checks, key=lambda x: (x.status == Status.OK, x.category, x.display_name.lower())):

                dmark = (_mark(None, '1em') if c.has_domain
                         else _mark(RULE_SEVERITY[Rule.DOMAIN_RANGE_MISSING], '1em'))
                rmark = (_mark(None, '1em') if c.has_range
                         else _mark(RULE_SEVERITY[Rule.DOMAIN_RANGE_MISSING], '1em'))
                category = escape(c.category)
                if c.deprecated:
                    category += f' <span title="Deprecated ({escape(c.deprecated)}); not checked" style="color:#999;">&#x2298;</span>'
                findings = c.findings()
                issue = '<br>'.join(
                    f'{_mark(f.severity)} {escape(f.message or "")}' for f in findings
                ) if findings else _mark(None)
                self.parts.append(
                    f'<tr><td>{_external_link(c.term, "<code>" + escape(c.display_name) + "</code>", title=True)}</td>'
                    f'<td>{category}</td><td>{dmark}</td><td>{rmark}</td><td>{issue}</td></tr>'
                )
            self.parts.append('</table></details>')
            self.parts.append('</section>')
        else:
            self._skipped_section('domains-ranges', 'Domains &amp; ranges',
                             'No object or datatype properties are defined in the ontology&rsquo;s own namespace.')

    def _datatypes(self) -> None:
        # Datatypes used across the ontology
        dt = self.report.datatypes
        if dt and dt.status != Status.SKIP and dt.usages:
            self._open_cluster('datatypes')
            dt_label = f'{len(dt.unrecognised)} unrecognised' if dt.unrecognised else 'all recognised'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('datatypes', 'Datatypes', dt_label))
            self.parts.append(_guide_link('datatypes'))
            self.parts.append(f'<p class="subtitle">{escape(DATATYPE_SCOPE)} Unrecognised IRIs are warnings, often caused by typos.</p>')
            self.parts.append(self._subtitle(f'{dt.recognised}/{dt.total_datatypes} recognised &middot; {len(dt.unrecognised)} unrecognised'))
            summary = f'Show all datatypes ({dt.total_datatypes})'
            if dt.unrecognised:
                summary += f' &middot; {len(dt.unrecognised)} unrecognised'
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">{summary}</summary>')
            self.parts.append('<table><tr><th>Datatype</th><th style="width:60px;">Uses</th><th>Where</th><th>Status</th></tr>')
            for u in sorted(dt.usages, key=lambda x: (x.recognised, x.display_name.lower())):

                if u.recognised:
                    status = '<span style="color:#2e7d32;font-size:1.2em;line-height:1">&#x2713;</span>'
                else:
                    status = f'{_mark(RULE_SEVERITY[Rule.DATATYPE_UNRECOGNISED], "1.2em")} {escape(u.message or "")}'
                self.parts.append(
                    f'<tr><td>{_external_link(u.datatype, "<code>" + escape(u.display_name) + "</code>", title=True)}</td>'
                    f'<td>{u.count}</td><td>{escape(", ".join(u.sources))}</td><td>{status}</td></tr>'
                )
            self.parts.append('</table></details>')
            self.parts.append('</section>')
        else:
            self._skipped_section('datatypes', 'Datatypes',
                             'No datatypes are used in the ontology.')

    def _non_ontology_terms(self) -> None:
        # Non-ontology terms: the ontology's own namespace should define only schema
        sk = self.report.non_ontology_terms
        if sk and sk.status != Status.SKIP:
            self._open_cluster('non-ontology-terms')
            sk_label = f'{len(sk.terms)} to review' if sk.terms else 'none found'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('non-ontology-terms', 'Non-ontology terms', sk_label))
            self.parts.append(_guide_link('non-ontology-terms'))
            self.parts.append('<p class="subtitle">TDCC recommends considering separate management of independently maintained SKOS concept schemes. Internal <code>skos:Concept</code> instances are listed for review; mixing OWL and SKOS is valid. Other named individuals are not flagged.</p>')
            if sk.terms:
                self.parts.append(self._subtitle(f'{len(sk.terms)} skos:Concept instance{"s" if len(sk.terms) != 1 else ""} defined in the ontology&rsquo;s own namespace'))
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">SKOS concepts to review ({len(sk.terms)})</summary>')
                self.parts.append('<table><tr><th>Term</th><th>What it is</th></tr>')
                for issue in sk.terms:

                    self.parts.append(
                        f'<tr><td>{_external_link(issue.term, "<code>" + escape(issue.display_name) + "</code>", title=True)}</td>'
                        f'<td>{escape(issue.type_label)}</td></tr>'
                    )
                self.parts.append('</table></details>')
            else:
                self.parts.append(self._subtitle('The ontology&rsquo;s own namespace defines no skos:Concept instances.'))
            self.parts.append('</section>')
        else:
            self._skipped_section('non-ontology-terms', 'Non-ontology terms',
                             'No <code>owl:Ontology</code> declaration, so the ontology&rsquo;s own namespace is unknown.')

    def _documentation(self) -> None:
        # Labels and Comments: two sibling checks driven from the definition-docs data
        docs = self.report.definition_docs
        if docs and docs.total_definitions:
            self._open_cluster('labels')
            def _mark_cell(present: bool, deprecated: str | None, rule: Rule) -> str:
                if deprecated:
                    return f'<span title="Deprecated ({escape(deprecated)}); not checked" style="color:#999;font-size:1.3em;line-height:1">&#x2298;</span>'
                if present:
                    return '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>'
                return _mark(RULE_SEVERITY[rule])

            def _doc_section(anchor: str, title: str, prop: str,
                             present_count: int, missing: list) -> None:
                label = f'{len(missing)} missing' if missing else 'none missing among checked terms'
                self.parts.append('<section class="section">')
                self.parts.append(self._section_heading(anchor, title, label))
                self.parts.append(_guide_link(anchor))
                inverse_note = ' A comment on an inverse property also counts.' if anchor == 'comments' else ''
                self.parts.append(f'<p class="subtitle">Every internally defined class and property should have a value for <code>{prop}</code>.{inverse_note} Reused external vocabulary terms, and terms you have marked deprecated, are ignored. Checked against <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/definition_documentation.ttl" target="_blank" rel="noopener">SHACL shapes for term documentation</a>.</p>')
                coverage = 'have labels' if anchor == 'labels' else 'meet the comment recommendation'
                exempt = f' &middot; {docs.deprecated_count} deprecated term(s) exempt' if docs.deprecated_count else ''
                self.parts.append(self._subtitle(f'{present_count}/{docs.total_definitions} {coverage} &middot; {len(missing)} missing{exempt}'))
                self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show {title.lower()} ({docs.total_definitions})</summary>')
                self.parts.append(f'<table><tr><th>Term</th><th>Type</th><th style="width:70px;">{title.rstrip("s")}</th></tr>')
                for check in sorted(docs.checks, key=lambda c: (getattr(c, "has_label" if anchor == "labels" else "has_comment"), c.display_name.lower())):
                    term = escape(check.display_name)

                    present = check.has_label if anchor == 'labels' else check.has_comment
                    rule = Rule.LABEL_MISSING if anchor == 'labels' else Rule.COMMENT_MISSING
                    self.parts.append(
                        f'<tr><td>{_external_link(check.term, "<code>" + term + "</code>", title=True)}</td>'
                        f'<td>{escape(check.term_type)}</td><td>{_mark_cell(present, check.deprecated, rule)}</td></tr>'
                    )
                self.parts.append('</table></details>')
                self.parts.append('</section>')

            _doc_section('labels', 'Labels', 'rdfs:label', docs.with_label, docs.missing_label)
            _doc_section('comments', 'Comments', 'rdfs:comment', docs.with_comment, docs.missing_comment)
        else:
            self._skipped_section('labels', 'Labels',
                             'No classes or properties are defined in the ontology&rsquo;s own namespace to document.')
            self._skipped_section('comments', 'Comments',
                             'No classes or properties are defined in the ontology&rsquo;s own namespace to document.')

    def _language_tags(self) -> None:
        # Language tag consistency - same section/subtitle/details pattern as
        # the other checks so the layout is fully uniform.
        lt = self.report.lang_tags
        self._open_cluster('language-tags')
        self.parts.append('<section class="section">')
        if lt and lt.status == Status.WARN and lt.issues:
            n_issues = len(lt.issues)
            n_missing_tag = sum(1 for i in lt.issues if i.issue_type == "missing_tag")
            n_missing_lang = sum(1 for i in lt.issues if i.issue_type == "missing_language")

            # Build a human-readable headline that explains what's wrong, not just a count.
            all_expected: set[str] = set()
            for i in lt.issues:
                all_expected.update(i.languages_expected)
            expected_str = ", ".join(f"<code>{escape(l)}</code>" for l in sorted(all_expected)) or "a language tag"
            headline_bits = []
            if n_missing_tag:
                headline_bits.append(f"{n_missing_tag} value{'s' if n_missing_tag != 1 else ''} missing a language tag (expected {expected_str})")
            if n_missing_lang:
                headline_bits.append(f"{n_missing_lang} value{'s' if n_missing_lang != 1 else ''} missing a translation")
            headline = " &middot; ".join(headline_bits)

            self.parts.append(self._section_heading('language-tags', 'Language tag consistency',
                                          f'{n_issues} issue{"s" if n_issues != 1 else ""}'))
            self.parts.append(_guide_link('language-tags'))
            self.parts.append('<p class="subtitle">Labels and definitions (<code>rdfs:label</code>, <code>rdfs:comment</code>, <code>skos:prefLabel</code>, <code>skos:definition</code>, &hellip;) on internally defined terms should use language tags consistently.</p>')
            self.parts.append(self._subtitle(headline or f'{n_issues} consistency issue{"s" if n_issues != 1 else ""}'))
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show all issues ({n_issues})</summary>')
            self.parts.append('<table><tr><th>Subject</th><th>Property</th><th>Issue</th><th>Has</th><th>Expected</th></tr>')
            for i in lt.issues:
                if i.is_blank_node or not i.subject_uri:
                    subject = '<em>(blank node)</em>' if i.is_blank_node else f'<code>{escape(i.subject)}</code>'
                else:
                    subject = _external_link(i.subject_uri, "<code>" + escape(i.subject) + "</code>", title=True)
                has = ", ".join(f'<code>{escape(l)}</code>' for l in i.languages_found) or '&mdash;'
                expected = ", ".join(f'<code>{escape(l)}</code>' for l in i.languages_expected)
                self.parts.append(
                    f'<tr><td>{subject}</td><td><code>{escape(i.property)}</code></td>'
                    f'<td>{escape(i.detail)}</td><td>{has}</td><td>{expected}</td></tr>'
                )
            self.parts.append('</table></details>')
        elif lt and lt.status == Status.OK:
            lang_str = escape(', '.join(lt.languages_used))
            self.parts.append(self._section_heading('language-tags', 'Language tag consistency', 'consistent'))
            self.parts.append(_guide_link('language-tags'))
            self.parts.append('<p class="subtitle">Labels and definitions (<code>rdfs:label</code>, <code>rdfs:comment</code>, <code>skos:prefLabel</code>, <code>skos:definition</code>, &hellip;) on internally defined terms should use language tags consistently.</p>')
            self.parts.append(self._subtitle(f'Labels and definitions use {lang_str} consistently across subjects.'))
        elif lt and lt.status == Status.WARN:
            self.parts.append(self._section_heading('language-tags', 'Language tag consistency', 'no language tags used'))
            self.parts.append(_guide_link('language-tags'))
            self.parts.append('<p class="subtitle">Labels and definitions (<code>rdfs:label</code>, <code>rdfs:comment</code>, <code>skos:prefLabel</code>, <code>skos:definition</code>, &hellip;) on internally defined terms should use language tags consistently.</p>')
            self.parts.append(self._subtitle('None of the labels or definitions in this ontology carry a language tag (e.g. <code>"Person"@en</code>). Plain strings are valid RDF, but language tags make labels easier to localise and to filter by language.'))
        else:
            self.parts.append(self._section_heading('language-tags', 'Language tag consistency', 'not applicable', na=True))
            self.parts.append(_guide_link('language-tags'))
            self.parts.append('<p class="subtitle">Labels and definitions (<code>rdfs:label</code>, <code>rdfs:comment</code>, <code>skos:prefLabel</code>, <code>skos:definition</code>, &hellip;) on internally defined terms should use language tags consistently.</p>')
            self.parts.append(self._subtitle('This ontology has no labels or definitions to check for language tags.'))
        self.parts.append('</section>')

    def _reasoner(self) -> None:
        # Reasoner checks
        reasoner = self.report.reasoner
        if reasoner and reasoner.checks:
            self._open_cluster('reasoner')
            r_label = 'problems found' if self.sev_summary.for_check('reasoner') else 'no contradictions detected'
            self.parts.append('<section class="section">')
            self.parts.append(self._section_heading('reasoner', 'Reasoner checks', r_label))
            self.parts.append(_guide_link('reasoner'))
            self.parts.append(f'<p class="subtitle">{escape(REASONER_SCOPE)}</p>')
            self.parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show reasoner checks ({len(reasoner.checks)})</summary>')
            self.parts.append('<table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>')
            for check in reasoner.checks:
                mark = (_na_mark() if check.status == Status.SKIP else
                        _mark(worst_severity(reasoner.findings_for_check(check.key))))
                if check.status == Status.OK:
                    status_label = f'<span style="color:{_OK_COLOR}">ok</span>'
                else:
                    status_label = 'problem'
                self.parts.append(f'<tr><td>{escape(check.label)}</td><td>{mark} {status_label}</td><td>{escape(check.message or "")}</td></tr>')
            self.parts.append('</table></details>')
            self.parts.append('</section>')

    def _footer(self) -> None:
        self.parts.append('<p class="footer">askwol is in beta - some checks may be incomplete or produce false positives. Found a bug or have an idea? <a href="https://github.com/TDCC-NES/askwol/issues" target="_blank" rel="noopener">Open an issue</a> or email <a href="mailto:nes@tdcc.nl">nes@tdcc.nl</a>.</p>')
        self.parts.append('<p class="footer"><strong>External links:</strong> <a href="https://tdcc.nl/nes/ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot; <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot; <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a></p>')
        if self.mermaid:
            # Classic (non-module) script so "Copy Mermaid" works even if the
            # module below fails to load (blocked CDN) or the diagram fails to
            # render (invalid source). It only depends on the hidden textarea.
            self.parts.append("""<script>
window.copyMermaid = async (btn) => {
  const el = document.getElementById('mermaid-src');
  const src = el ? el.value : '';
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(src);
    } else {
      // Fallback for non-secure contexts (e.g. plain http)
      el.style.display = 'block';
      el.select();
      document.execCommand('copy');
      el.style.display = 'none';
    }
    if (btn) { const old = btn.textContent; btn.textContent = 'Copied!'; setTimeout(() => { btn.textContent = old; }, 1500); }
  } catch (e) {
    alert('Could not copy automatically. The Mermaid source is:\\n\\n' + src);
  }
};
</script>""")
            self.parts.append("""<script type="module">
const vp = document.getElementById('diagram-viewport');
function showError(msg) {
  if (vp) {
    const error = document.createElement('div');
    error.style.cssText = 'padding:1em;color:#c00;font-family:monospace;font-size:0.85em;white-space:pre-wrap;';
    error.textContent = 'Diagram error: ' + msg;
    vp.replaceChildren(error);
  }
  console.error('[askwol diagram]', msg);
}
let errShown = false;
function fail(msg) { showError(msg); errShown = true; }

// Load Mermaid via a dynamic import so a blocked or failed load can be caught
// and reported. A static top-level import would abort the whole script with
// no visible error, leaving the raw diagram source on screen with no
// explanation.
let mermaid;
try {
  mermaid = (await import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")).default;
} catch (e) {
  fail('The Mermaid library could not be loaded, so no diagram was produced.\\n\\n'
    + 'It is fetched from a CDN (cdn.jsdelivr.net). If you are offline, or behind a '
    + 'firewall, proxy, or Content-Security-Policy that blocks that host, the diagram '
    + 'cannot render. The rest of the report is unaffected.');
}

if (mermaid) {
  try {
    mermaid.initialize({startOnLoad:false,theme:"neutral",securityLevel:"strict"});
    // Validate the source first so we can surface the precise syntax error
    // (mermaid.run swallows parse errors, leaving only an empty container).
    const src = (document.getElementById('mermaid-src') || {}).value || '';
    if (src) {
      try {
        await mermaid.parse(src);
      } catch (e) {
        fail('The Mermaid source is invalid, so the diagram could not be rendered.\\n\\n'
          + String(e && e.message || e)
          + '\\n\\nThis is a bug in askwol\\'s diagram generation, not a problem with your ontology. '
          + 'Use the "Copy Mermaid" button to capture the source for a bug report.');
      }
    }
    if (!errShown) await mermaid.run();
  } catch (e) {
    fail(String(e && e.message || e));
  }
}
const svg = vp && vp.querySelector('svg');
if (!svg) {
  if (!errShown) {
    fail('The diagram could not be rendered for an unexpected reason. '
      + 'Use the "Copy Mermaid" button to capture the source for a bug report.');
  }
} else {
  // Prefer the diagram's true content bounds (getBBox) over Mermaid's own
  // viewBox: classDiagram reserves empty space at the top for a (here absent)
  // title, which otherwise shows up as a blank band above the graph. A small
  // uniform padding keeps the graph off the edges.
  let origX, origY, origW, origH;
  let box = null;
  try { box = svg.getBBox(); } catch (e) { box = null; }
  if (box && box.width > 0 && box.height > 0) {
    const pad = 12;
    origX = box.x - pad; origY = box.y - pad;
    origW = box.width + pad * 2; origH = box.height + pad * 2;
  } else {
    const vb = svg.viewBox.baseVal;
    origX = vb.x; origY = vb.y; origW = vb.width; origH = vb.height;
  }
  // Remember pristine values for export (before aspect-ratio padding)
  const pristineX = origX, pristineY = origY, pristineW = origW, pristineH = origH;

  // Fill the container  -  disable preserveAspectRatio so viewBox maps 1:1
  svg.removeAttribute('style');
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.style.display = 'block';

  // Adjust viewBox to match container aspect ratio so mapping is 1:1
  const cW = vp.clientWidth, cH = vp.clientHeight;
  const cAR = cW / cH, sAR = origW / origH;
  if (cAR > sAR) {
    // Container wider: expand viewBox width
    const nw = origH * cAR;
    origX -= (nw - origW) / 2; origW = nw;
  } else {
    // Container taller: expand viewBox height
    const nh = origW / cAR;
    origY -= (nh - origH) / 2; origH = nh;
  }

  let curX = origX, curY = origY, curW = origW, curH = origH;
  function setVB() { svg.setAttribute('viewBox', `${curX} ${curY} ${curW} ${curH}`); }
  setVB();

  // The diagram is now fitted: reveal it (and drop the loading placeholder) in
  // one paint so users never see the raw source or the pre-fit jump.
  vp.classList.add('ready');

  // Zoom: shrink/grow viewBox around mouse
  let dragging = false, lastMX, lastMY;
  vp.addEventListener('wheel', (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const rect = vp.getBoundingClientRect();
    const fx = (e.clientX - rect.left) / rect.width;
    const fy = (e.clientY - rect.top) / rect.height;
    const f = e.deltaY > 0 ? 1.15 : 1/1.15;
    const nw = curW * f, nh = curH * f;
    curX += (curW - nw) * fx;
    curY += (curH - nh) * fy;
    curW = nw; curH = nh;
    setVB();
  }, {passive: false});

  // Pan: drag to shift viewBox
  vp.addEventListener('mousedown', (e) => {
    dragging = true; lastMX = e.clientX; lastMY = e.clientY;
    vp.style.cursor = 'grabbing';
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const rect = vp.getBoundingClientRect();
    curX -= (e.clientX - lastMX) / rect.width * curW;
    curY -= (e.clientY - lastMY) / rect.height * curH;
    lastMX = e.clientX; lastMY = e.clientY;
    setVB();
  });
  window.addEventListener('mouseup', () => { dragging = false; vp.style.cursor = 'grab'; });
  vp.style.cursor = 'grab';

  // Button handlers
  const zf = 1.3;
  window.pzIn = () => { const nw=curW/zf, nh=curH/zf; curX+=(curW-nw)/2; curY+=(curH-nh)/2; curW=nw; curH=nh; setVB(); };
  window.pzOut = () => { const nw=curW*zf, nh=curH*zf; curX+=(curW-nw)/2; curY+=(curH-nh)/2; curW=nw; curH=nh; setVB(); };
  window.pzReset = () => { curX=origX; curY=origY; curW=origW; curH=origH; setVB(); };

  // Build a clean, exportable SVG (original size, preserved aspect ratio)
  function buildExportSVG() {
    const clone = svg.cloneNode(true);
    clone.setAttribute('viewBox', `${pristineX} ${pristineY} ${pristineW} ${pristineH}`);
    clone.setAttribute('width', String(pristineW));
    clone.setAttribute('height', String(pristineH));
    clone.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
    return '<?xml version="1.0" encoding="UTF-8"?>\\n' + new XMLSerializer().serializeToString(clone);
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.downloadSVG = () => {
    const blob = new Blob([buildExportSVG()], {type: 'image/svg+xml'});
    triggerDownload(blob, 'ontology-diagram.svg');
  };

  window.downloadPNG = () => {
    const svgStr = buildExportSVG();
    // Use a data URL (works more reliably than blob: across browsers)
    const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgStr);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const scale = 2;
      const w = Math.max(1, Math.round(pristineW * scale));
      const h = Math.max(1, Math.round(pristineH * scale));
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      try {
        canvas.toBlob((blob) => {
          if (blob) triggerDownload(blob, 'ontology-diagram.png');
          else alert('PNG conversion failed (empty blob).');
        }, 'image/png');
      } catch (e) {
        alert('Could not export PNG: ' + e.message + '\\nTry the SVG download instead.');
      }
    };
    img.onerror = () => alert('Could not render PNG. Try downloading the SVG instead.');
    img.src = dataUrl;
  };
}
</script>""")

        # External (target="_blank") links: take explicit control of the click
        # instead of relying solely on the target attribute, so a browser
        # extension or setting that forces same-tab navigation on such links
        # can't hijack the current results page. Capture phase + stopPropagation
        # so this runs before other listeners.
        self.parts.append("""<script>
document.addEventListener('click', (e) => {
  const a = e.target.closest('a[target="_blank"]');
  if (!a || !a.href) return;
  e.preventDefault();
  e.stopPropagation();
  window.open(a.href, '_blank', 'noopener,noreferrer');
}, true);
</script>""")

        self.parts.append("</body></html>")
