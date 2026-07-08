"""HTML rendering of the askwol validation report."""

from __future__ import annotations

from html import escape

from askwol.models import NamespaceReport, Status, ValidationReport
from askwol.templates import GUIDE_SECTIONS


# Single source of truth: every automated check maps its report section anchor
# to the matching modeling-guide section anchor (and vice versa). The summary
# table, the per-section "Learn more" links, and the back-links shown in the
# guide are all driven from this registry, so they cannot drift apart.
# An assertion below enforces that the order and anchors here match the
# check-group sections in GUIDE_SECTIONS.
CHECKS: list[dict[str, str]] = [
    {"report_anchor": "ontology-metadata", "title": "Ontology metadata",         "guide_anchor": "metadata"},
    {"report_anchor": "imports",           "title": "Imports",                   "guide_anchor": "imports"},
    {"report_anchor": "iri-strategy",      "title": "IRI strategy",              "guide_anchor": "iri-strategy"},
    {"report_anchor": "iri-scheme",        "title": "IRI scheme (http vs https)","guide_anchor": "https-http"},
    {"report_anchor": "namespaces",        "title": "Namespaces",                "guide_anchor": "resolvable"},
    {"report_anchor": "terms",             "title": "Terms",                     "guide_anchor": "reuse"},
    {"report_anchor": "definition-docs",   "title": "Definition documentation",  "guide_anchor": "definition-docs"},
    {"report_anchor": "language-tags",     "title": "Language tag consistency",  "guide_anchor": "lang-tags"},
    {"report_anchor": "reasoner",          "title": "Reasoner checks",           "guide_anchor": "reasoner"},
    {"report_anchor": "unused-prefixes",   "title": "Unused prefixes",           "guide_anchor": "prefixes"},
]

# Enforce alignment between CHECKS and GUIDE_SECTIONS at import time. If they
# ever drift (someone renames an anchor, reorders a section, etc.) the module
# fails to load and the failure is caught by the test suite. This is the
# architectural guarantee that the report and the guide stay in sync.
_GUIDE_CHECK_ANCHORS = [s["anchor"] for s in GUIDE_SECTIONS if s["group"] == "check"]
_CHECK_GUIDE_ANCHORS = [c["guide_anchor"] for c in CHECKS]
assert _CHECK_GUIDE_ANCHORS == _GUIDE_CHECK_ANCHORS, (
    "CHECKS and GUIDE_SECTIONS (group=check) must list the same anchors in "
    f"the same order. CHECKS guide_anchors={_CHECK_GUIDE_ANCHORS}, "
    f"GUIDE check anchors={_GUIDE_CHECK_ANCHORS}"
)

# Convenience lookups derived from CHECKS
_CHECK_BY_REPORT: dict[str, dict] = {c["report_anchor"]: c for c in CHECKS}
# guide anchor -> report anchor (for back-links shown in the modeling guide)
_REPORT_BY_GUIDE: dict[str, str] = {c["guide_anchor"]: c["report_anchor"] for c in CHECKS}


def _guide_link(report_anchor: str) -> str:
    """HTML snippet linking from a report section to its guide section."""
    check = _CHECK_BY_REPORT.get(report_anchor)
    if not check:
        return ""
    href = f"guide#{check['guide_anchor']}"
    return (f'<p style="font-size:0.85em;color:#666;margin:0.4em 0 0;">'
            f'&rarr; Learn more in the <a href="{href}">modeling guide</a>.</p>')


def render_report(report: ValidationReport, mermaid: str = "") -> str:
    source = escape(report.file)
    # If the source is a URL, render it as a clickable link; otherwise (an
    # uploaded filename) keep it as inline code.
    if report.file.startswith(("http://", "https://")):
        source_html = f'<a href="{source}" target="_blank" rel="noopener"><code>{source}</code></a>'
    else:
        source_html = f'<code>{source}</code>'
    parts = [
        "<!DOCTYPE html><html><head><title>Ask Wol: results</title>",
        '<link rel="icon" href="data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><text y=\'.9em\' font-size=\'90\'>&#x1F989;</text></svg>">',
        "<style>",
        "  body { font-family: system-ui, sans-serif; max-width: 780px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.5; }",
        "  h1 { margin-bottom: 0.2em; }",
        "  h2 { color: #555; margin-top: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }",
        "  h3 { color: #666; margin-top: 1.2em; margin-bottom: 0.3em; font-size: 1em; }",
        "  a { color: #4a7c59; }",
        "  code { background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }",
        "  .summary { background: #f9f9f9; border: 1px solid #ddd; border-radius: 8px; padding: 1.2em 1.5em; margin: 1.2em 0; }",
        "  .summary table { border-collapse: collapse; }",
        "  .summary td { padding: 0.45em 1.2em 0.45em 0; font-size: 1.05em; vertical-align: middle; border: none; }",
        "  .summary tr { cursor: pointer; }",
        "  .summary tr:hover td { background: #eef3ef; }",
        "  .ns { margin-top: 1.5em; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }",
        "  .ns-header { background: #f5f5f5; padding: 0.6em 1em; font-weight: bold; border-bottom: 1px solid #ddd; }",
        "  .ns-body { padding: 0.5em 1em; }",
        "  table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }",
        "  th, td { text-align: left; padding: 0.3em 0.8em; border-bottom: 1px solid #f0f0f0; font-size: 0.9em; }",
        "  th { color: #666; font-weight: 600; }",
        "  .back { margin-top: 2em; }",
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
        "  .warn-box { background: #fef9f0; border: 1px solid #e8d5a3; border-radius: 8px; padding: 0.8em 1.2em; margin: 1em 0; }",
        "  .footer { margin-top: 2em; font-size: 0.85em; color: #aaa; text-align: center; }",
        "</style>",
        "</head><body>",
        '<p class="topnav"><strong>Navigation:</strong> <a href="./">Home</a> &middot; <a href="guide">Modeling guide</a> &middot; <a href="docs">API docs</a></p>',
        f'<h1>Results for {source_html}</h1>',
    ]

    if report.parse_errors:
        for err in report.parse_errors:
            parts.append(f'<div class="error"><strong>Parse error:</strong> {escape(err)}</div>')
        parts.append('</body></html>')
        return "\n".join(parts)

    def _status_mark(status: Status) -> str:
        return {
            'ok': '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>',
            'fail': '<span style="color:#c62828;font-size:1.3em;line-height:1">&#x2717;</span>',
            'warn': '<span style="color:#e6a700;font-size:1.3em;line-height:1">&#x26A0;</span>',
            'skip': '<span style="color:#888;font-size:1.3em;line-height:1">&#x2014;</span>',
        }[status.value]

    # Summary stats (computed now, rendered after diagram)
    total_ns = len(report.namespaces)
    ok_ns = sum(1 for ns in report.namespaces if ns.resolution.status == Status.OK)
    total_terms = sum(len(ns.terms) for ns in report.namespaces)
    ok_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.OK)
    fail_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.FAIL)

    # Ontology diagram (Mermaid)  -  shown first
    if mermaid:
        parts.append('<div class="diagram">')
        parts.append("<h2>Ontology diagram</h2>")
        parts.append('<div id="diagram-viewport" class="diagram-viewport">')
        parts.append('<div class="diagram-loading">Rendering diagram&hellip;</div>')
        parts.append(f'<pre class="mermaid">\n{mermaid}\n</pre>')
        parts.append('</div>')
        # Hidden copy of the Mermaid source so JS can copy / export it even
        # after Mermaid has replaced the <pre> with the rendered SVG.
        parts.append(f'<textarea id="mermaid-src" style="display:none">{escape(mermaid)}</textarea>')
        parts.append('<div class="diagram-controls">')
        parts.append('<button onclick="pzIn&amp;&amp;pzIn()">+ Zoom in</button>')
        parts.append('<button onclick="pzOut&amp;&amp;pzOut()">&minus; Zoom out</button>')
        parts.append('<button onclick="pzReset&amp;&amp;pzReset()">Reset view</button>')
        parts.append('<button onclick="copyMermaid&amp;&amp;copyMermaid(this)">Copy Mermaid</button>')
        parts.append('<button onclick="downloadSVG&amp;&amp;downloadSVG()">Download SVG</button>')
        parts.append('<button onclick="downloadPNG&amp;&amp;downloadPNG()">Download PNG</button>')
        parts.append('<span style="font-size:0.8em;color:#999;margin-left:0.5em;">Ctrl+scroll to zoom, drag to pan</span>')
        parts.append('</div>')
        parts.append("</div>")

    # Summary  -  one row per check, in the exact same order as the detail
    # sections below (driven by CHECKS so it can never drift). Each row jumps
    # to the matching #anchor when clicked.
    _ok = '<span style="color:#2e7d32;font-size:1.1em;line-height:1;vertical-align:middle">&#x2713;</span>'
    _fail = '<span style="color:#c62828;font-size:1.1em;line-height:1;vertical-align:middle">&#x2717;</span>'
    _warn = '<span style="color:#e6a700;font-size:1.1em;line-height:1;vertical-align:middle">&#x26A0;</span>'
    _info = '<span style="color:#888;font-size:1.1em;line-height:1;vertical-align:middle">&#x2014;</span>'

    def _row(anchor: str, mark: str, title: str, detail: str) -> str:
        # Whole row jumps to the matching section anchor when clicked.
        return (
            f'<tr onclick="location.hash=\'{anchor}\'">'
            f'<td>{mark} <strong>{title}</strong></td>'
            f'<td>{detail}</td>'
            f'</tr>'
        )

    # Build one summary row per check. Order is fixed by CHECKS and matches the
    # detail sections below 1:1. Namespaces + remote terms are deliberately a
    # single row because they share one report section.
    def _summary_for(report_anchor: str) -> list[str]:
        if report_anchor == 'namespaces':
            ns_mark = _ok if ok_ns == total_ns else _fail
            return [_row('namespaces', ns_mark, 'Namespaces',
                         f'{ok_ns}/{total_ns} resolved')]
        if report_anchor == 'terms':
            term_mark = _ok if fail_terms == 0 else _fail
            skipped = total_terms - ok_terms - fail_terms
            term_bits = [f'{ok_terms} confirmed']
            if fail_terms:
                term_bits.append(f'{fail_terms} failed')
            if skipped:
                term_bits.append(f'{skipped} skipped')
            return [_row('terms', term_mark, 'Terms', ', '.join(term_bits))]
        if report_anchor == 'ontology-metadata':
            if not (meta and meta.total_checks):
                return []
            mark = _ok if not meta.failed_checks and not meta.warning_checks else (_warn if not meta.failed_checks else _fail)
            if meta.failed_checks or meta.warning_checks:
                bits = [f'{meta.passed_checks}/{meta.total_checks} OK']
                if meta.failed_checks:
                    bits.append(f'{meta.failed_checks} required missing')
                if meta.warning_checks:
                    bits.append(f'{meta.warning_checks} recommended missing')
                detail = ', '.join(bits)
            else:
                detail = f'{meta.total_checks}/{meta.total_checks} OK'
            return [_row('ontology-metadata', mark, 'Ontology metadata', detail)]
        if report_anchor == 'definition-docs':
            if not (docs and docs.total_definitions):
                return []
            mark = _ok if not docs.issues else _fail
            if docs.issues:
                detail = f'{docs.documented_definitions}/{docs.total_definitions} complete, {len(docs.issues)} missing label/comment'
            else:
                detail = f'{docs.total_definitions}/{docs.total_definitions} complete'
            return [_row('definition-docs', mark, 'Definition documentation', detail)]
        if report_anchor == 'imports':
            imp = report.imports
            if not imp:
                return []
            if imp.status == Status.SKIP:
                return [_row('imports', _info, 'Imports',
                             'skipped (no owl:Ontology declaration)')]
            missing = imp.missing
            if missing:
                return [_row('imports', _warn, 'Imports',
                             f'{len(missing)} external vocabulary(ies) used but not declared in owl:imports')]
            if not imp.checks:
                return [_row('imports', _ok, 'Imports', 'no external vocabularies used')]
            return [_row('imports', _ok, 'Imports',
                         f'{len(imp.checks)}/{len(imp.checks)} declared')]
        if report_anchor == 'iri-strategy':
            iri = report.iri_strategy
            if not iri:
                return []
            if iri.status == Status.SKIP:
                return [_row('iri-strategy', _info, 'IRI strategy',
                             iri.message or 'skipped')]
            if iri.status == Status.WARN:
                return [_row('iri-strategy', _warn, 'IRI strategy',
                             f'mixed: {iri.hash_count} hash + {iri.slash_count} slash')]
            label = 'hash (<code>#Term</code>)' if iri.strategy == 'hash' else 'slash (<code>/Term</code>)'
            count = iri.hash_count if iri.strategy == 'hash' else iri.slash_count
            return [_row('iri-strategy', _ok, 'IRI strategy',
                         f'{label} &middot; {count} term{"s" if count != 1 else ""}')]
        if report_anchor == 'iri-scheme':
            sch = report.iri_scheme
            if not sch:
                return []
            if sch.status == Status.SKIP:
                return [_row('iri-scheme', _info, 'IRI scheme', sch.message or 'skipped')]
            if sch.status == Status.WARN:
                return [_row('iri-scheme', _warn, 'IRI scheme',
                             f'{len(sch.conflicts)} host(s) use both http:// and https://')]
            return [_row('iri-scheme', _ok, 'IRI scheme',
                         f'{sch.total_hosts} host(s), each on a single scheme')]
        if report_anchor == 'reasoner':
            if not reasoner:
                return []
            reas_ok = reasoner.consistent and not reasoner.unsatisfiable_classes
            mark = _ok if reas_ok else _fail
            if reas_ok:
                detail = 'consistent'
            else:
                detail = f'{len(reasoner.inconsistent_individuals)} inconsistency issue(s), {len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)'
            return [_row('reasoner', mark, 'Reasoner checks', detail)]
        if report_anchor == 'unused-prefixes':
            if report.unused_prefixes:
                return [_row('unused-prefixes', _warn, 'Unused prefixes',
                             f'{len(report.unused_prefixes)} declared but never used')]
            return [_row('unused-prefixes', _ok, 'Unused prefixes', 'none')]
        if report_anchor == 'language-tags':
            if lt and lt.languages_used:
                lang_str = ', '.join(lt.languages_used)
                issue_count = len(lt.issues)
                if issue_count:
                    return [_row('language-tags', _warn, 'Language tag consistency',
                                 f'{lang_str} &middot; {issue_count} issue{"s" if issue_count != 1 else ""}')]
                return [_row('language-tags', _ok, 'Language tag consistency', f'{lang_str} &middot; consistent')]
            return [_row('language-tags', _info, 'Language tag consistency',
                         'no language tags used in labels/definitions')]
        return []

    # The data the summary needs (already computed earlier in the function).
    meta = report.ontology_metadata
    docs = report.definition_docs
    reasoner = report.reasoner
    lt = report.lang_tags

    parts.append('<div class="summary"><table>')
    for check in CHECKS:
        parts.extend(_summary_for(check['report_anchor']))
    parts.append("</table></div>")

    # Tip: link to the modeling guide
    parts.append('<p style="font-size:0.9em;color:#666;margin:0.5em 0 1em;">Not sure what a check means? See the <a href="guide">modeling guide</a> for explanations and best practices.</p>')

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
        return any(t.status == Status.FAIL for t in ns.terms)

    prominent = [ns for ns in report.namespaces if _ns_has_issues(ns) or ns.uri not in STANDARD_NS]
    standard_ok = sorted(
        [ns for ns in report.namespaces if not _ns_has_issues(ns) and ns.uri in STANDARD_NS],
        key=lambda ns: ns.prefix.lower(),
    )

    def _render_ns_card(ns: NamespaceReport) -> None:
        mark = _status_mark(ns.resolution.status)
        prefix = escape(ns.prefix) or "<em>(default)</em>"
        uri = escape(ns.uri)
        parts.append(f'<div class="ns"><div class="ns-header">{mark} {prefix}: &lt;{uri}&gt;</div>')
        parts.append('<div class="ns-body">')

        res = ns.resolution
        if res.http_status:
            parts.append(f"<p>HTTP {res.http_status}")
            if res.content_type:
                parts.append(f" &middot; {escape(res.content_type)}")
            if res.is_valid_rdf is not None:
                parts.append(f" &middot; {'valid' if res.is_valid_rdf else 'invalid'} RDF")
            parts.append("</p>")
        if res.error:
            parts.append(f"<p style='color:#c00'>{escape(res.error)}</p>")

        # Term counts only - per-term details are shown in the Terms section
        # below to avoid duplicating the same information twice.
        if ns.terms:
            t_ok = sum(1 for t in ns.terms if t.status == Status.OK)
            t_fail = sum(1 for t in ns.terms if t.status == Status.FAIL)
            t_skip = sum(1 for t in ns.terms if t.status == Status.SKIP)
            summary_parts = []
            if t_ok:
                summary_parts.append(f"{t_ok} confirmed")
            if t_fail:
                summary_parts.append(f"{t_fail} not found")
            if t_skip:
                summary_parts.append(f"{t_skip} skipped")
            parts.append(f'<p style="font-size:0.9em;color:#666;">'
                         f'{len(ns.terms)} term{"s" if len(ns.terms) != 1 else ""} used '
                         f'({" &middot; ".join(summary_parts)}), '
                         f'see <a href="#terms">Terms</a> section</p>')
        else:
            parts.append("<p><em>No terms used from this namespace.</em></p>")

        parts.append("</div></div>")

    # Section helper: status mark FIRST, then title. Uses the same colored
    # marks as the summary table so the visual language is consistent.
    # `label` becomes a tooltip / accessible name on the mark.
    def _section_heading(anchor: str, title: str, status: str, label: str) -> str:
        mark_html = {'ok': _ok, 'fail': _fail, 'warn': _warn, 'info': _info}[status]
        # Wrap in a span carrying the tooltip; keep the visual identical to
        # the summary table marks.
        marked = (f'<span title="{escape(label)}" aria-label="{escape(label)}" '
                  f'style="margin-right:0.4em;">{mark_html}</span>')
        return f'<h2 id="{anchor}">{marked}{title}</h2>'

    # Plain descriptive subtitle - no status mark here, because the section
    # heading already carries the colored status. Avoids duplicate ✗/✓ icons.
    def _status_subtitle(status: str, text: str) -> str:
        return f'<p class="subtitle">{text}</p>'

    # Ontology metadata summary
    meta = report.ontology_metadata
    if meta and meta.checks:
        missing_required = [c for c in meta.checks if c.status == Status.FAIL]
        missing_recommended = [c for c in meta.checks if c.status == Status.WARN]
        if missing_required:
            m_status, m_label = 'fail', 'needs attention'
        elif missing_recommended:
            m_status, m_label = 'warn', 'recommended fields missing'
        else:
            m_status, m_label = 'ok', 'all good'
        parts.append('<section class="section">')
        parts.append(_section_heading('ontology-metadata', 'Ontology metadata', m_status, m_label))
        parts.append(_guide_link('ontology-metadata'))
        parts.append('<p class="subtitle">The ontology header (title, creator, license, version, &hellip;) is checked against <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/ontology_metadata.ttl" target="_blank" rel="noopener">SHACL shapes for the ontology header</a>.</p>')
        summary_bits = [f"{meta.passed_checks} present"]
        if missing_required:
            summary_bits.append(f"{len(missing_required)} required missing")
        if missing_recommended:
            summary_bits.append(f"{len(missing_recommended)} recommended missing")
        parts.append(_status_subtitle(m_status, " &middot; ".join(summary_bits)))
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show metadata checks ({meta.total_checks})</summary>')
        parts.append('<table><tr><th>Property</th><th>Level</th><th>Status</th></tr>')
        for check in meta.checks:
            mark = _status_mark(check.status)
            if check.status == Status.OK:
                status_label = '<span style="color:#2e7d32">ok</span>'
            elif check.status == Status.WARN:
                status_label = '<span style="color:#e6a700">warning</span>'
            else:
                status_label = '<span style="color:#c62828">missing</span>'
            parts.append(
                f'<tr><td><code>{escape(check.property)}</code></td><td>{escape(check.severity)}</td><td>{mark} {status_label}</td></tr>'
            )
        parts.append('</table></details>')
        parts.append('</section>')

    # Imports check
    imp = report.imports
    if imp is not None:
        if imp.status == Status.SKIP:
            i_status, i_label = 'info', 'skipped'
        elif imp.missing:
            i_status, i_label = 'warn', f'{len(imp.missing)} missing'
        else:
            i_status, i_label = 'ok', 'all declared'
        parts.append('<section class="section">')
        parts.append(_section_heading('imports', 'Imports', i_status, i_label))
        parts.append(_guide_link('imports'))
        parts.append('<p class="subtitle">External vocabularies whose terms you use as subjects should be declared with <code>owl:imports</code> in the ontology header. Core RDF/OWL vocabularies and your ontology&rsquo;s own namespace are excluded.</p>')
        if imp.status == Status.SKIP:
            parts.append(_status_subtitle('info', 'no <code>owl:Ontology</code> declaration found; declare one to enable this check'))
        elif imp.missing:
            parts.append(_status_subtitle('warn', f'{len(imp.missing)} external vocabulary(ies) used but not declared in <code>owl:imports</code>'))
        elif imp.checks:
            parts.append(_status_subtitle('ok', f'{len(imp.checks)} external vocabulary(ies) all declared'))
        else:
            parts.append(_status_subtitle('ok', 'no external vocabularies used'))
        if imp.checks:
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show vocabularies ({len(imp.checks)})</summary>')
            parts.append('<table><tr><th>Prefix</th><th>Namespace</th><th>Status</th></tr>')
            for c in imp.checks:
                mark = _status_mark(c.status)
                if c.status == Status.OK:
                    status_label = '<span style="color:#2e7d32">imported</span>'
                else:
                    status_label = '<span style="color:#e6a700">not imported</span>'
                parts.append(
                    f'<tr><td><code>{escape(c.prefix)}</code></td><td><code>{escape(c.namespace)}</code></td><td>{mark} {status_label}</td></tr>'
                )
            parts.append('</table></details>')
        if imp.declared:
            non_empty = [d for d in imp.declared if d and d.strip()]
            if non_empty:
                parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Declared owl:imports ({len(non_empty)})</summary>')
                parts.append('<ul>')
                for d in non_empty:
                    safe = escape(d)
                    parts.append(f'<li><a href="{safe}" target="_blank" rel="noopener"><code>{safe}</code></a></li>')
                parts.append('</ul></details>')
        parts.append('</section>')

    # IRI strategy (hash vs slash) for the ontology's own defined terms
    iri = report.iri_strategy
    if iri is not None:
        if iri.status == Status.SKIP:
            s_status, s_label = 'info', 'skipped'
        elif iri.status == Status.WARN:
            s_status, s_label = 'warn', 'mixed strategy'
        else:
            s_status, s_label = 'ok', f'{iri.strategy} style'
        parts.append('<section class="section">')
        parts.append(_section_heading('iri-strategy', 'IRI strategy', s_status, s_label))
        parts.append(_guide_link('iri-strategy'))
        parts.append('<p class="subtitle">A consistent IRI pattern for the ontology&rsquo;s own terms. Either every term sits under a fragment (<code>http://example.org/ont#Term</code>, the <strong>hash</strong> pattern) or every term is its own slash path (<code>http://example.org/ont/Term</code>, the <strong>slash</strong> pattern). Mixing both within one ontology confuses consumers and tooling.</p>')

        if iri.status == Status.SKIP:
            parts.append(_status_subtitle('info', iri.message or 'no terms in the ontology&rsquo;s own namespace could be classified'))
        elif iri.status == Status.WARN:
            parts.append(_status_subtitle(
                'warn',
                f'<strong>Mixed</strong>: {iri.hash_count} hash-style and {iri.slash_count} slash-style terms in the same ontology. Pick one and migrate the others.',
            ))
            parts.append(f'<details open><summary style="cursor:pointer;font-weight:600;">Show examples</summary>')
            if iri.hash_examples:
                parts.append(f'<p style="margin:0.5em 0 0.2em;font-weight:600;">Hash style ({iri.hash_count}):</p>')
                parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                for ex in iri.hash_examples:
                    parts.append(f'<li><code>{escape(ex)}</code></li>')
                parts.append('</ul>')
            if iri.slash_examples:
                parts.append(f'<p style="margin:0.5em 0 0.2em;font-weight:600;">Slash style ({iri.slash_count}):</p>')
                parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                for ex in iri.slash_examples:
                    parts.append(f'<li><code>{escape(ex)}</code></li>')
                parts.append('</ul>')
            parts.append('</details>')
        else:
            count = iri.hash_count if iri.strategy == 'hash' else iri.slash_count
            pattern = '<code>#Term</code>' if iri.strategy == 'hash' else '<code>/Term</code>'
            parts.append(_status_subtitle(
                'ok',
                f'<strong>{iri.strategy.capitalize()} pattern</strong> ({pattern}) used consistently across all {count} defined term{"s" if count != 1 else ""}.',
            ))
            examples = iri.hash_examples if iri.strategy == 'hash' else iri.slash_examples
            if examples:
                parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show examples</summary>')
                parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                for ex in examples:
                    parts.append(f'<li><code>{escape(ex)}</code></li>')
                parts.append('</ul></details>')
        parts.append('</section>')

    # IRI scheme consistency (http vs https) per host
    sch = report.iri_scheme
    if sch is not None:
        if sch.status == Status.SKIP:
            sc_status, sc_label = 'info', 'skipped'
        elif sch.status == Status.WARN:
            sc_status, sc_label = 'warn', f'{len(sch.conflicts)} mixed host(s)'
        else:
            sc_status, sc_label = 'ok', 'consistent'
        parts.append('<section class="section">')
        parts.append(_section_heading('iri-scheme', 'IRI scheme (http vs https)', sc_status, sc_label))
        parts.append(_guide_link('iri-scheme'))
        parts.append('<p class="subtitle">In RDF, <code>http://example.org/X</code> and <code>https://example.org/X</code> are <strong>different IRIs</strong>. Within one ontology, each host should appear under exactly one scheme. Mixing schemes silently breaks SPARQL joins, <code>owl:sameAs</code>, and any tool that compares URIs as strings.</p>')

        if sch.status == Status.SKIP:
            parts.append(_status_subtitle('info', sch.message or 'no http(s) IRIs found'))
        elif sch.status == Status.WARN:
            parts.append(_status_subtitle(
                'warn',
                f'<strong>{len(sch.conflicts)}</strong> host(s) are referenced under both <code>http://</code> and <code>https://</code> in the same ontology.',
            ))
            parts.append('<details open><summary style="cursor:pointer;font-weight:600;">Show conflicting hosts</summary>')
            for c in sch.conflicts:
                parts.append(f'<h3 style="margin:1em 0 0.3em;font-size:1em;"><code>{escape(c.host)}</code></h3>')
                parts.append(
                    f'<p style="font-size:0.9em;color:#444;margin:0.2em 0;">'
                    f'<strong>{c.http_count}</strong> reference(s) use <code>http://</code> and '
                    f'<strong>{c.https_count}</strong> use <code>https://</code>. '
                    f'Pick one canonical scheme and migrate the others.</p>'
                )
                if c.http_examples:
                    parts.append('<p style="font-size:0.9em;margin:0.4em 0 0.2em;"><code>http://</code> examples:</p>')
                    parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                    for ex in c.http_examples:
                        parts.append(f'<li><code>{escape(ex)}</code></li>')
                    parts.append('</ul>')
                if c.https_examples:
                    parts.append('<p style="font-size:0.9em;margin:0.4em 0 0.2em;"><code>https://</code> examples:</p>')
                    parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;font-size:0.9em;">')
                    for ex in c.https_examples:
                        parts.append(f'<li><code>{escape(ex)}</code></li>')
                    parts.append('</ul>')
            parts.append('</details>')
        else:
            parts.append(_status_subtitle(
                'ok',
                f'<strong>{sch.total_hosts}</strong> host(s) referenced, each under a single scheme '
                f'({sch.http_only_hosts} <code>http://</code>, {sch.https_only_hosts} <code>https://</code>).',
            ))
        parts.append('</section>')

    # --- Namespaces section: resolvability of each declared prefix ---
    ns_only_status = 'ok' if ok_ns == total_ns else 'fail'
    ns_label = 'all resolved' if ns_only_status == 'ok' else f'{total_ns - ok_ns} unresolved'
    parts.append('<section class="section">')
    parts.append(_section_heading('namespaces', 'Namespaces', ns_only_status, ns_label))
    parts.append(_guide_link('namespaces'))
    parts.append('<p class="subtitle">Each prefix declared in the ontology is fetched over HTTP and parsed as RDF where possible. A namespace that does not resolve makes its terms uncheckable downstream.</p>')
    parts.append(f'<p class="subtitle"><strong>{ok_ns}/{total_ns}</strong> namespaces resolved.</p>')

    if prominent:
        failed_ns = [ns for ns in prominent if ns.resolution.status == Status.FAIL]
        warn_ns = [ns for ns in prominent if ns.resolution.status == Status.WARN]
        ok_ns_list = [ns for ns in prominent if ns.resolution.status == Status.OK]

        if failed_ns:
            http_404 = [ns for ns in failed_ns if ns.resolution.http_status == 404]
            http_other = [ns for ns in failed_ns if ns.resolution.http_status and ns.resolution.http_status != 404]
            conn_err = [ns for ns in failed_ns if not ns.resolution.http_status]

            if http_404:
                parts.append(f'<h3>404 Not Found ({len(http_404)})</h3>')
                for ns in http_404:
                    _render_ns_card(ns)
            if http_other:
                for ns in http_other:
                    parts.append(f'<h3>HTTP {ns.resolution.http_status}</h3>')
                    _render_ns_card(ns)
            if conn_err:
                parts.append(f'<h3>Connection errors ({len(conn_err)})</h3>')
                for ns in conn_err:
                    _render_ns_card(ns)

        if warn_ns:
            parts.append(f'<h3>Warnings ({len(warn_ns)})</h3>')
            for ns in warn_ns:
                _render_ns_card(ns)

        if ok_ns_list:
            parts.append(f'<h3>Resolved OK ({len(ok_ns_list)})</h3>')
            for ns in ok_ns_list:
                _render_ns_card(ns)

    if standard_ok:
        total_std_terms = sum(len(ns.terms) for ns in standard_ok)
        parts.append(f'<details style="margin-top:1.5em;"><summary style="cursor:pointer;padding:0.6em 0;font-weight:bold;color:#555;">')
        parts.append(f'{len(standard_ok)} standard vocabularies OK ({total_std_terms} terms verified)</summary>')
        for ns in standard_ok:
            _render_ns_card(ns)
        parts.append("</details>")
    parts.append('</section>')

    # --- Terms section: per-term verification against the remote vocabulary ---
    term_only_status = 'ok' if fail_terms == 0 else 'fail'
    skipped = total_terms - ok_terms - fail_terms
    if fail_terms:
        term_label = f'{fail_terms} not found in remote vocabulary'
    elif skipped:
        term_label = f'{skipped} not checkable'
    else:
        term_label = 'all verified'
    parts.append('<section class="section">')
    parts.append(_section_heading('terms', 'Terms', term_only_status, term_label))
    parts.append(_guide_link('terms'))
    parts.append('<p class="subtitle">Each term used from a remote vocabulary is looked up in the resolved namespace. Terms that are missing remotely are likely typos or made-up reuse of an established prefix.</p>')
    term_summary_bits = [f'<strong>{ok_terms}</strong> confirmed']
    if fail_terms:
        term_summary_bits.append(f'<strong>{fail_terms}</strong> not found')
    if skipped:
        term_summary_bits.append(f'<strong>{skipped}</strong> skipped (namespace unavailable)')
    parts.append(f'<p class="subtitle">{" &middot; ".join(term_summary_bits)} of {total_terms} total.</p>')

    # Flat list of problem terms across all namespaces
    failed_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.FAIL]
    skipped_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.SKIP]
    if failed_terms_flat:
        parts.append(f'<details open><summary style="cursor:pointer;font-weight:600;">Terms not found in their vocabulary ({len(failed_terms_flat)})</summary>')
        parts.append('<table><tr><th>Term</th><th>Prefix</th><th>Full IRI</th></tr>')
        for ns, t in failed_terms_flat:
            t_iri = escape(t.term_uri)
            parts.append(f'<tr><td><code>{escape(t.local_name)}</code></td>'
                         f'<td><code>{escape(ns.prefix)}</code></td>'
                         f'<td><a href="{t_iri}" target="_blank" rel="noopener"><code>{t_iri}</code></a></td></tr>')
        parts.append('</table></details>')
    if skipped_terms_flat:
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Terms not checkable, namespace unavailable ({len(skipped_terms_flat)})</summary>')
        parts.append('<table><tr><th>Term</th><th>Prefix</th></tr>')
        for ns, t in skipped_terms_flat:
            parts.append(f'<tr><td><code>{escape(t.local_name)}</code></td>'
                         f'<td><code>{escape(ns.prefix)}</code></td></tr>')
        parts.append('</table></details>')
    if ok_terms:
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Confirmed terms ({ok_terms})</summary>')
        parts.append('<table><tr><th>Term</th><th>Prefix</th></tr>')
        for ns in report.namespaces:
            for t in ns.terms:
                if t.status == Status.OK:
                    t_iri = escape(t.term_uri)
                    parts.append(f'<tr><td><a href="{t_iri}" target="_blank" rel="noopener"><code>{escape(t.local_name)}</code></a></td>'
                                 f'<td><code>{escape(ns.prefix)}</code></td></tr>')
        parts.append('</table></details>')
    parts.append('</section>')

    # Internal definition documentation summary
    docs = report.definition_docs
    if docs and docs.total_definitions:
        incomplete = docs.total_definitions - docs.documented_definitions
        d_status = 'ok' if not docs.issues else 'fail'
        d_label = 'all good' if d_status == 'ok' else f'{incomplete} incomplete'
        parts.append('<section class="section">')
        parts.append(_section_heading('definition-docs', 'Definition documentation', d_status, d_label))
        parts.append(_guide_link('definition-docs'))
        parts.append('<p class="subtitle">Internally defined classes and properties must each carry an <code>rdfs:label</code> and an <code>rdfs:comment</code>. Reused external vocabulary terms are ignored. Checked against <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/definition_documentation.ttl" target="_blank" rel="noopener">SHACL shapes for term documentation</a>.</p>')
        parts.append(_status_subtitle(d_status, f'{docs.documented_definitions} complete &middot; {incomplete} incomplete'))
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show documentation checks ({docs.total_definitions})</summary>')
        parts.append('<table><tr><th>Term</th><th>Type</th><th>Label</th><th>Comment</th></tr>')
        for check in sorted(docs.checks, key=lambda c: (c.status == Status.OK, c.display_name.lower())):
            term = escape(check.display_name)
            term_uri = escape(check.term)
            label_status = '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>' if check.has_label else '<span style="color:#c62828;font-size:1.3em;line-height:1">&#x2717;</span>'
            comment_status = '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>' if check.has_comment else '<span style="color:#c62828;font-size:1.3em;line-height:1">&#x2717;</span>'
            parts.append(
                f'<tr><td><a href="{term_uri}" target="_blank" rel="noopener"><code>{term}</code></a></td><td>{escape(check.term_type)}</td><td>{label_status}</td><td>{comment_status}</td></tr>'
            )
        parts.append('</table></details>')
        parts.append('</section>')

    # Language tag consistency - same section/subtitle/details pattern as
    # the other checks so the layout is fully uniform.
    lt = report.lang_tags
    parts.append('<section class="section">')
    if lt and lt.issues:
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

        parts.append(_section_heading('language-tags', 'Language tag consistency', 'warn',
                                      f'{n_issues} issue{"s" if n_issues != 1 else ""}'))
        parts.append(_guide_link('language-tags'))
        parts.append('<p class="subtitle">Labels and definitions (<code>rdfs:label</code>, <code>rdfs:comment</code>, <code>skos:prefLabel</code>, <code>skos:definition</code>, &hellip;) should use language tags consistently across all subjects.</p>')
        parts.append(_status_subtitle('warn', headline or f'{n_issues} consistency issue{"s" if n_issues != 1 else ""}'))
        parts.append(f'<details open><summary style="cursor:pointer;font-weight:600;">Show details by property ({n_issues})</summary>')

        # Build a quick lookup from property name to its summary
        prop_summary_map = {ps.property: ps for ps in (lt.property_summaries or [])}

        # Group issues by property, then by issue_type, then split named vs blank-node.
        by_prop: dict[str, list] = {}
        for issue in lt.issues:
            by_prop.setdefault(issue.property, []).append(issue)

        for prop, issues in sorted(by_prop.items()):
            ps = prop_summary_map.get(prop)
            parts.append(f'<h3 style="margin:1.2em 0 0.3em;font-size:1em;"><code>{escape(prop)}</code></h3>')

            if ps:
                bad = ps.total_subjects - ps.consistent_subjects
                langs_str = ", ".join(f"<code>{escape(l)}</code>" for l in ps.languages)
                parts.append(
                    f'<p style="font-size:0.9em;color:#444;margin:0.2em 0;">'
                    f'<strong>{bad} of {ps.total_subjects}</strong> values of <code>{escape(prop)}</code> '
                    f'are missing a language tag. ({ps.consistent_subjects} already use {langs_str}.)'
                    f'</p>'
                )

            # Group within the property by issue type
            by_type: dict[str, list] = {}
            for i in issues:
                by_type.setdefault(i.issue_type, []).append(i)

            for itype, group in by_type.items():
                named = [i for i in group if not i.is_blank_node]
                bnodes = [i for i in group if i.is_blank_node]
                expected_here = sorted({l for i in group for l in i.languages_expected})
                expected_html = ", ".join(f"<code>{escape(l)}</code>" for l in expected_here)

                if itype == "missing_tag":
                    explanation = f"Untagged values - add the language tag {expected_html}:"
                else:
                    explanation = f"Values that are missing a translation in {expected_html}:"

                if named:
                    parts.append(f'<p style="font-size:0.9em;margin:0.6em 0 0.2em;">{explanation}</p>')
                    parts.append('<ul style="margin:0.2em 0 0.4em 1.2em;padding:0;font-size:0.9em;">')
                    for i in named:
                        if itype == "missing_language":
                            # Bold-highlight what's missing for this subject.
                            missing = [l for l in i.languages_expected if l not in i.languages_found]
                            missing_html = ", ".join(f"<strong><code>{escape(l)}</code></strong>" for l in missing)
                            parts.append(f'<li><code>{escape(i.subject)}</code> - missing {missing_html}</li>')
                        elif i.languages_found:
                            # missing_tag with some tags already present
                            has = ", ".join(f"<code>{escape(l)}</code>" for l in i.languages_found)
                            parts.append(f'<li><code>{escape(i.subject)}</code> (has {has})</li>')
                        else:
                            parts.append(f'<li><code>{escape(i.subject)}</code></li>')
                    parts.append('</ul>')

                if bnodes:
                    parts.append(
                        f'<p style="font-size:0.85em;color:#666;margin:0.2em 0 0.6em;">'
                        f'Plus <strong>{len(bnodes)}</strong> anonymous node{"s" if len(bnodes) != 1 else ""} '
                        f'(e.g. OWL restrictions or SHACL shapes) with the same problem.'
                        f'</p>'
                    )
        parts.append('</details>')
    elif lt and lt.languages_used:
        lang_str = ', '.join(lt.languages_used)
        parts.append(_section_heading('language-tags', 'Language tag consistency', 'ok', 'consistent'))
        parts.append(_guide_link('language-tags'))
        parts.append('<p class="subtitle">Labels and definitions (<code>rdfs:label</code>, <code>rdfs:comment</code>, <code>skos:prefLabel</code>, <code>skos:definition</code>, &hellip;) should use language tags consistently across all subjects.</p>')
        parts.append(_status_subtitle('ok', f'Labels and definitions use {lang_str} consistently across subjects.'))
    else:
        parts.append(_section_heading('language-tags', 'Language tag consistency', 'info', 'no tags used'))
        parts.append(_guide_link('language-tags'))
        parts.append('<p class="subtitle">Labels and definitions (<code>rdfs:label</code>, <code>rdfs:comment</code>, <code>skos:prefLabel</code>, <code>skos:definition</code>, &hellip;) should use language tags consistently across all subjects.</p>')
        parts.append(_status_subtitle('info', 'No labels or definitions in this ontology carry language tags (e.g. <code>"Person"@en</code>). This is not an error, but adding language tags makes labels easier to localise.'))
    parts.append('</section>')

    # Reasoner checks
    reasoner = report.reasoner
    if reasoner and reasoner.checks:
        r_ok = reasoner.consistent and not reasoner.unsatisfiable_classes
        r_status = 'ok' if r_ok else 'fail'
        r_label = 'consistent' if r_ok else 'needs attention'
        parts.append('<section class="section">')
        parts.append(_section_heading('reasoner', 'Reasoner checks', r_status, r_label))
        parts.append(_guide_link('reasoner'))
        parts.append('<p class="subtitle">A lightweight OWL RL reasoner runs against the <strong>current ontology only</strong>; <code>owl:imports</code> are not followed. It surfaces three things: overall <strong>ontology consistency</strong>, specific <strong>inconsistent individuals</strong> (e.g. typed in two <code>owl:disjointWith</code> classes), and <strong>unsatisfiable classes</strong> (definitions equivalent to <code>owl:Nothing</code>).</p>')
        reas_summary = 'consistent' if r_ok else f'{len(reasoner.inconsistent_individuals)} inconsistency issue(s), {len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)'
        parts.append(_status_subtitle(r_status, reas_summary))
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show reasoner checks ({len(reasoner.checks)})</summary>')
        parts.append('<table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>')
        for check in reasoner.checks:
            mark = _status_mark(check.status)
            if check.status == Status.OK:
                status_label = '<span style="color:#2e7d32">ok</span>'
            elif check.status == Status.WARN:
                status_label = '<span style="color:#e6a700">warning</span>'
            else:
                status_label = '<span style="color:#c62828">fail</span>'
            parts.append(f'<tr><td>{escape(check.label)}</td><td>{mark} {status_label}</td><td>{escape(check.message or "")}</td></tr>')
        parts.append('</table></details>')
        parts.append('</section>')

    # Unused prefixes - styled identically to the other check sections.
    parts.append('<section class="section">')
    if report.unused_prefixes:
        parts.append(_section_heading('unused-prefixes', 'Unused prefixes', 'warn',
                                      f'{len(report.unused_prefixes)} to clean up'))
        parts.append(_guide_link('unused-prefixes'))
        parts.append('<p class="subtitle">Prefixes that are declared in the file but never appear in any triple. Removing them keeps the ontology clean and avoids suggesting dependencies that do not exist.</p>')
        parts.append(_status_subtitle('warn', f'{len(report.unused_prefixes)} declared but never used'))
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show unused prefixes ({len(report.unused_prefixes)})</summary>')
        parts.append('<table><tr><th>Prefix</th><th>Namespace IRI</th></tr>')
        for up in report.unused_prefixes:
            pfx = escape(up.prefix) or '<em>(default)</em>'
            uri = escape(up.uri)
            parts.append(f'<tr><td><code>{pfx}:</code></td><td><code>&lt;{uri}&gt;</code></td></tr>')
        parts.append('</table></details>')
    else:
        parts.append(_section_heading('unused-prefixes', 'Unused prefixes', 'ok', 'all good'))
        parts.append(_guide_link('unused-prefixes'))
        parts.append('<p class="subtitle">Prefixes that are declared in the file but never appear in any triple. Removing them keeps the ontology clean and avoids suggesting dependencies that do not exist.</p>')
        parts.append(_status_subtitle('ok', 'Every declared prefix is used in at least one triple.'))
    parts.append('</section>')

    parts.append('<p class="footer"><strong>External links:</strong> <a href="https://tdcc.nl/nes-ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot; <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot; <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a></p>')
    if mermaid:
        # Classic (non-module) script so "Copy Mermaid" works even if the
        # module below fails to load (blocked CDN) or the diagram fails to
        # render (invalid source). It only depends on the hidden textarea.
        parts.append("""<script>
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
        parts.append("""<script type="module">
const vp = document.getElementById('diagram-viewport');
function showError(msg) {
  if (vp) vp.innerHTML = '<div style="padding:1em;color:#c00;font-family:monospace;font-size:0.85em;white-space:pre-wrap;">Diagram error: ' + msg + '</div>';
  console.error('[askwol diagram]', msg);
}
let errShown = false;
function fail(msg) { showError(msg); errShown = true; }

// Load Mermaid via a dynamic import so a blocked or failed load can be caught
// and reported. A static top-level import would abort the whole script
// silently, leaving the raw diagram source on screen with no explanation.
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
    mermaid.initialize({startOnLoad:false,theme:"neutral",securityLevel:"loose"});
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
    parts.append("</body></html>")
    return "\n".join(parts)
