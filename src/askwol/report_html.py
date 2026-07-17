"""HTML rendering of the askwol validation report."""

from __future__ import annotations

from html import escape

from askwol.models import NamespaceReport, Status, ValidationReport
from askwol.templates import CHECK_CATEGORIES, GUIDE_SECTIONS


# Single source of truth: every automated check maps its report section anchor
# to the matching modeling-guide section anchor (and vice versa). The summary
# table, the per-section "Learn more" links, and the back-links shown in the
# guide are all driven from this registry, so they cannot drift apart.
# An assertion below enforces that the order and anchors here match the
# check-group sections in GUIDE_SECTIONS.
# Single source of truth: every automated check maps its report section anchor
# to the matching modeling-guide section anchor (and vice versa). The summary
# table, the per-section "Learn more" links, and the back-links shown in the
# guide are all driven from this registry, so they cannot drift apart.
# An assertion below enforces that the order and anchors here match the
# check-group sections in GUIDE_SECTIONS.
#
# Each check also carries a ``category`` that groups it into a cluster shown as
# a labelled band in the overview, the results, and the guide. Clusters must be
# contiguous in this list; CATEGORIES gives their order and display labels
# (shared with the publishing guide via templates.CHECK_CATEGORIES).
CATEGORIES = CHECK_CATEGORIES
CATEGORY_LABELS: dict[str, str] = {c["key"]: c["label"] for c in CATEGORIES}

CHECKS: list[dict[str, str]] = [
    {"report_anchor": "ontology-metadata", "title": "Ontology metadata",          "guide_anchor": "metadata",         "category": "basics"},
    {"report_anchor": "imports",           "title": "Imports",                    "guide_anchor": "imports",          "category": "basics"},
    {"report_anchor": "iri-strategy",      "title": "IRI strategy",               "guide_anchor": "iri-strategy",     "category": "basics"},
    {"report_anchor": "iri-scheme",        "title": "IRI scheme (http vs https)", "guide_anchor": "https-http",       "category": "basics"},
    {"report_anchor": "namespaces",        "title": "Namespaces",                 "guide_anchor": "resolvable",       "category": "reuse"},
    {"report_anchor": "unused-prefixes",   "title": "Unused prefixes",            "guide_anchor": "prefixes",         "category": "reuse"},
    {"report_anchor": "external-terms",    "title": "External term definitions",  "guide_anchor": "external-terms",   "category": "reuse"},
    {"report_anchor": "internal-terms",    "title": "Internal term definitions",  "guide_anchor": "internal-terms",   "category": "structure"},
    {"report_anchor": "term-inventory",    "title": "Term inventory &amp; naming","guide_anchor": "term-inventory",   "category": "structure"},
    {"report_anchor": "domains-ranges",    "title": "Domains &amp; ranges",       "guide_anchor": "domains-ranges",   "category": "structure"},
    {"report_anchor": "datatypes",         "title": "Datatypes",                  "guide_anchor": "datatypes",        "category": "structure"},
    {"report_anchor": "non-ontology-terms","title": "Non-ontology terms",         "guide_anchor": "non-ontology-terms","category": "structure"},
    {"report_anchor": "labels",            "title": "Labels",                     "guide_anchor": "labels",           "category": "docs"},
    {"report_anchor": "comments",          "title": "Comments",                   "guide_anchor": "comments",         "category": "docs"},
    {"report_anchor": "language-tags",     "title": "Language tag consistency",   "guide_anchor": "lang-tags",        "category": "docs"},
    {"report_anchor": "reasoner",          "title": "Reasoner checks",            "guide_anchor": "reasoner",         "category": "logic"},
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

# The category assigned to each check must match between the report registry
# and the guide, so the clusters stay identical across surfaces.
_GUIDE_CHECK_CATEGORIES = [s.get("category") for s in GUIDE_SECTIONS if s["group"] == "check"]
_CHECK_CATEGORIES = [c["category"] for c in CHECKS]
assert _CHECK_CATEGORIES == _GUIDE_CHECK_CATEGORIES, (
    "CHECKS and GUIDE_SECTIONS (group=check) must assign the same category to "
    f"each check. CHECKS categories={_CHECK_CATEGORIES}, "
    f"GUIDE categories={_GUIDE_CHECK_CATEGORIES}"
)

# Categories must be contiguous blocks and appear in CATEGORIES order.
_CHECK_CATEGORY_ORDER = [c["category"] for c in CHECKS]
_seen_categories: list[str] = []
for _cat in _CHECK_CATEGORY_ORDER:
    if not _seen_categories or _seen_categories[-1] != _cat:
        _seen_categories.append(_cat)
assert _seen_categories == [c["key"] for c in CATEGORIES], (
    "CHECKS categories must form contiguous blocks in CATEGORIES order. "
    f"Got block order {_seen_categories}, expected {[c['key'] for c in CATEGORIES]}"
)

# Convenience lookups derived from CHECKS
_CHECK_BY_REPORT: dict[str, dict] = {c["report_anchor"]: c for c in CHECKS}
# guide anchor -> report anchor (for back-links shown in the publishing guide)
_REPORT_BY_GUIDE: dict[str, str] = {c["guide_anchor"]: c["report_anchor"] for c in CHECKS}
# report anchor -> category key
_CATEGORY_BY_REPORT: dict[str, str] = {c["report_anchor"]: c["category"] for c in CHECKS}

# Cluster number (1..5) per category, and "cluster.position" number per check,
# so the results page can be numbered exactly like the guide and home page.
_CLUSTER_NUMBERS: dict[str, int] = {c["key"]: i + 1 for i, c in enumerate(CATEGORIES)}


def _compute_check_numbers() -> dict[str, str]:
    counters: dict[str, int] = {}
    labels: dict[str, str] = {}
    for c in CHECKS:
        cat = c["category"]
        counters[cat] = counters.get(cat, 0) + 1
        labels[c["report_anchor"]] = f"{_CLUSTER_NUMBERS[cat]}.{counters[cat]}"
    return labels


_CHECK_NUMBERS: dict[str, str] = _compute_check_numbers()



def _guide_link(report_anchor: str) -> str:
    """HTML snippet linking from a report section to its guide section."""
    check = _CHECK_BY_REPORT.get(report_anchor)
    if not check:
        return ""
    href = f"guide#{check['guide_anchor']}"
    return (f'<p style="font-size:0.85em;color:#666;margin:0.4em 0 0;">'
            f'&rarr; Learn more in the <a href="{href}">publishing guide</a>.</p>')


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
        '<p class="topnav"><strong>Navigation:</strong> <a href="./">Home</a> &middot; <a href="guide">Publishing guide</a> &middot; <a href="docs">API docs</a></p>',
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
    warn_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.WARN)

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
        num = _CHECK_NUMBERS.get(anchor, "")
        prefix = f'<span class="num">{num}</span> ' if num else ""
        return (
            f'<tr onclick="location.hash=\'{anchor}\'">'
            f'<td>{mark} {prefix}<strong>{title}</strong></td>'
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
        if report_anchor == 'external-terms':
            term_mark = _ok if fail_terms == 0 else _fail
            if fail_terms == 0 and warn_terms:
                term_mark = _warn
            skipped = total_terms - ok_terms - fail_terms - warn_terms
            term_bits = [f'{ok_terms} confirmed']
            if fail_terms:
                term_bits.append(f'{fail_terms} failed')
            if warn_terms:
                term_bits.append(f'{warn_terms} deprecated')
            if skipped:
                term_bits.append(f'{skipped} skipped')
            return [_row('external-terms', term_mark, 'External term definitions', ', '.join(term_bits))]
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
        if report_anchor == 'internal-terms':
            it = report.internal_terms
            if not it or it.status == Status.SKIP:
                return [_row('internal-terms', _info, 'Internal term definitions',
                             (it.message if it else None) or 'not applicable')]
            if it.undefined:
                return [_row('internal-terms', _fail, 'Internal term definitions',
                             f'{len(it.undefined)} referenced but never defined')]
            return [_row('internal-terms', _ok, 'Internal term definitions',
                         f'{it.defined}/{it.total_referenced} defined')]
        if report_anchor == 'term-inventory':
            inv = report.term_inventory
            if not inv or inv.status == Status.SKIP:
                return [_row('term-inventory', _info, 'Term inventory &amp; naming',
                             'no terms defined in the ontology&rsquo;s own namespace')]
            if inv.naming_issues:
                return [_row('term-inventory', _fail, 'Term inventory &amp; naming',
                             f'{inv.total_terms} terms &middot; {len(inv.naming_issues)} naming issue(s)')]
            return [_row('term-inventory', _ok, 'Term inventory &amp; naming',
                         f'{inv.total_terms} terms &middot; naming consistent')]
        if report_anchor == 'domains-ranges':
            dr = report.domains_ranges
            if not dr or dr.status == Status.SKIP:
                return [_row('domains-ranges', _info, 'Domains &amp; ranges',
                             'no object or datatype properties defined')]
            if dr.status == Status.FAIL:
                fails = sum(1 for c in dr.issues if c.status == Status.FAIL)
                return [_row('domains-ranges', _fail, 'Domains &amp; ranges',
                             f'{fails} property(ies) with a domain/range problem')]
            if dr.status == Status.WARN:
                return [_row('domains-ranges', _warn, 'Domains &amp; ranges',
                             f'{len(dr.issues)} property(ies) missing a domain or range')]
            return [_row('domains-ranges', _ok, 'Domains &amp; ranges',
                         f'{dr.total_properties} property(ies), all sound')]
        if report_anchor == 'datatypes':
            dt = report.datatypes
            if not dt or dt.status == Status.SKIP:
                return [_row('datatypes', _info, 'Datatypes', 'no datatypes used')]
            if dt.unrecognized:
                return [_row('datatypes', _fail, 'Datatypes',
                             f'{len(dt.unrecognized)} unrecognized of {dt.total_datatypes}')]
            return [_row('datatypes', _ok, 'Datatypes',
                         f'{dt.total_datatypes} used, all recognized')]
        if report_anchor == 'labels':
            if not (docs and docs.total_definitions):
                return [_row('labels', _info, 'Labels', 'no internal definitions to document')]
            missing = docs.missing_label
            mark = _ok if not missing else _fail
            if missing:
                detail = f'{docs.with_label}/{docs.total_definitions} have a label, {len(missing)} missing'
            else:
                detail = f'{docs.total_definitions}/{docs.total_definitions} have a label'
            return [_row('labels', mark, 'Labels', detail)]
        if report_anchor == 'comments':
            if not (docs and docs.total_definitions):
                return [_row('comments', _info, 'Comments', 'no internal definitions to document')]
            missing = docs.missing_comment
            mark = _ok if not missing else _fail
            if missing:
                detail = f'{docs.with_comment}/{docs.total_definitions} have a comment, {len(missing)} missing'
            else:
                detail = f'{docs.total_definitions}/{docs.total_definitions} have a comment'
            return [_row('comments', mark, 'Comments', detail)]
        if report_anchor == 'imports':
            imp = report.imports
            if not imp:
                return []
            broken = imp.broken
            if broken:
                return [_row('imports', _fail, 'Imports',
                             f'{len(broken)} of {len(imp.checks)} declared import(s) do not resolve')]
            if not imp.checks:
                return [_row('imports', _ok, 'Imports', 'no imports declared')]
            return [_row('imports', _ok, 'Imports',
                         f'{len(imp.checks)} declared import(s), all resolve')]
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
        if report_anchor == 'non-ontology-terms':
            sk = report.non_ontology_terms
            if not sk or sk.status == Status.SKIP:
                return [_row('non-ontology-terms', _info, 'Non-ontology terms', 'not applicable')]
            if sk.terms:
                return [_row('non-ontology-terms', _warn, 'Non-ontology terms',
                             f'{len(sk.terms)} that belong in a separate resource')]
            return [_row('non-ontology-terms', _ok, 'Non-ontology terms', 'only schema terms defined')]
        return []

    # The data the summary needs (already computed earlier in the function).
    meta = report.ontology_metadata
    docs = report.definition_docs
    reasoner = report.reasoner
    lt = report.lang_tags

    parts.append('<div class="summary"><table>')
    for cat in CATEGORIES:
        rows: list[str] = []
        for check in CHECKS:
            if check["category"] != cat["key"]:
                continue
            rows.extend(_summary_for(check["report_anchor"]))
        if not rows:
            continue
        parts.append(
            f'<tr class="cluster-row"><td colspan="2">{_CLUSTER_NUMBERS[cat["key"]]}. {cat["label"]}</td></tr>'
        )
        parts.extend(rows)
    parts.append("</table></div>")

    # Tip: link to the publishing guide
    parts.append('<p style="font-size:0.9em;color:#666;margin:0.5em 0 1em;">Not sure what a check means? See the <a href="guide">publishing guide</a> for explanations and best practices.</p>')

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
        return any(t.status in (Status.FAIL, Status.WARN) for t in ns.terms)

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

        # Term counts only - per-term details are shown in the External terms
        # definition section below to avoid duplicating the same information.
        if ns.terms:
            t_ok = sum(1 for t in ns.terms if t.status == Status.OK)
            t_fail = sum(1 for t in ns.terms if t.status == Status.FAIL)
            t_warn = sum(1 for t in ns.terms if t.status == Status.WARN)
            t_skip = sum(1 for t in ns.terms if t.status == Status.SKIP)
            summary_parts = []
            if t_ok:
                summary_parts.append(f"{t_ok} confirmed")
            if t_fail:
                summary_parts.append(f"{t_fail} not found")
            if t_warn:
                summary_parts.append(f"{t_warn} deprecated")
            if t_skip:
                summary_parts.append(f"{t_skip} skipped")
            parts.append(f'<p style="font-size:0.9em;color:#666;">'
                         f'{len(ns.terms)} term{"s" if len(ns.terms) != 1 else ""} used '
                         f'({" &middot; ".join(summary_parts)}), '
                         f'see <a href="#external-terms">External term definitions</a> section</p>')
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
        num = _CHECK_NUMBERS.get(anchor, "")
        num_html = f'<span class="num">{num}</span> ' if num else ""
        return f'<h2 id="{anchor}">{marked}{num_html}{title}</h2>'

    # Plain descriptive subtitle - no status mark here, because the section
    # heading already carries the colored status. Avoids duplicate ✗/✓ icons.
    def _status_subtitle(status: str, text: str) -> str:
        return f'<p class="subtitle">{text}</p>'

    # Cluster bands: emit a labelled divider before the first rendered section
    # of each category. Lazy so a category with no rendered sections shows no
    # band. Categories are emitted in CHECKS/CATEGORIES order because the
    # sections below are laid out in that order.
    _emitted_clusters: set[str] = set()

    def _open_cluster(report_anchor: str) -> None:
        cat = _CATEGORY_BY_REPORT.get(report_anchor)
        if cat is None or cat in _emitted_clusters:
            return
        _emitted_clusters.add(cat)
        parts.append(f'<h2 class="cluster-band">{_CLUSTER_NUMBERS[cat]}. {CATEGORY_LABELS[cat]}</h2>')

    def _skipped_section(anchor: str, title: str, reason: str) -> None:
        """Render a compact 'not applicable' section so every check is visible."""
        _open_cluster(anchor)
        parts.append('<section class="section">')
        parts.append(_section_heading(anchor, title, 'info', 'not applicable'))
        parts.append(_guide_link(anchor))
        parts.append(_status_subtitle('info', reason))
        parts.append('</section>')

    # Ontology metadata summary
    meta = report.ontology_metadata
    if meta and meta.checks:
        _open_cluster('ontology-metadata')
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
        _open_cluster('imports')
        broken = imp.broken
        if broken:
            i_status, i_label = 'fail', f'{len(broken)} broken'
        elif imp.checks:
            i_status, i_label = 'ok', 'all resolve'
        else:
            i_status, i_label = 'ok', 'none declared'
        parts.append('<section class="section">')
        parts.append(_section_heading('imports', 'Imports', i_status, i_label))
        parts.append(_guide_link('imports'))
        parts.append('<p class="subtitle">Every <code>owl:imports</code> target declared in the ontology header is fetched over HTTP and parsed as RDF, the same way a reasoner would follow it.</p>')
        if broken:
            parts.append(_status_subtitle('fail', f'{len(broken)} of {len(imp.checks)} declared import(s) do not resolve'))
        elif imp.checks:
            parts.append(_status_subtitle('ok', f'{len(imp.checks)} declared import(s), all resolve'))
        else:
            parts.append(_status_subtitle('ok', 'no owl:imports declared'))
        if imp.checks:
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show imports ({len(imp.checks)})</summary>')
            for c in imp.checks:
                mark = _status_mark(c.resolution.status)
                iri = escape(c.iri)
                parts.append(f'<div class="ns"><div class="ns-header">{mark} &lt;<a href="{iri}" target="_blank" rel="noopener">{iri}</a>&gt;</div>')
                parts.append('<div class="ns-body">')
                res = c.resolution
                if res.http_status:
                    parts.append(f"<p>HTTP {res.http_status}")
                    if res.content_type:
                        parts.append(f" &middot; {escape(res.content_type)}")
                    if res.is_valid_rdf is not None:
                        parts.append(f" &middot; {'valid' if res.is_valid_rdf else 'invalid'} RDF")
                    parts.append("</p>")
                if res.error:
                    parts.append(f"<p style='color:#c00'>{escape(res.error)}</p>")
                parts.append('</div></div>')
            parts.append('</details>')
        parts.append('</section>')

    # IRI strategy (hash vs slash) for the ontology's own defined terms
    iri = report.iri_strategy
    if iri is not None:
        _open_cluster('iri-strategy')
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
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show examples</summary>')
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
        _open_cluster('iri-scheme')
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
            parts.append('<details><summary style="cursor:pointer;font-weight:600;">Show conflicting hosts</summary>')
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
    _open_cluster('namespaces')
    ns_only_status = 'ok' if ok_ns == total_ns else 'fail'
    ns_label = 'all resolved' if ns_only_status == 'ok' else f'{total_ns - ok_ns} unresolved'
    parts.append('<section class="section">')
    parts.append(_section_heading('namespaces', 'Namespaces', ns_only_status, ns_label))
    parts.append(_guide_link('namespaces'))
    parts.append('<p class="subtitle">Each namespace URI declared in the ontology (the target of a <code>@prefix</code>) is fetched over HTTP and parsed as RDF where possible. A namespace that does not resolve makes its terms uncheckable downstream.</p>')
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
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Resolved OK ({len(ok_ns_list)})</summary>')
            for ns in ok_ns_list:
                _render_ns_card(ns)
            parts.append("</details>")

    if standard_ok:
        total_std_terms = sum(len(ns.terms) for ns in standard_ok)
        parts.append(f'<details style="margin-top:1.5em;"><summary style="cursor:pointer;padding:0.6em 0;font-weight:bold;color:#555;">')
        parts.append(f'{len(standard_ok)} standard vocabularies OK ({total_std_terms} terms verified)</summary>')
        for ns in standard_ok:
            _render_ns_card(ns)
        parts.append("</details>")
    parts.append('</section>')

    # Unused prefixes - styled identically to the other check sections.
    _open_cluster('unused-prefixes')
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

    # --- External term definitions: per-term verification against the remote vocabulary ---
    skipped = total_terms - ok_terms - fail_terms - warn_terms
    if fail_terms:
        term_only_status = 'fail'
        term_label = f'{fail_terms} not found in remote vocabulary'
    elif warn_terms:
        term_only_status = 'warn'
        term_label = f'{warn_terms} deprecated upstream'
    elif skipped:
        term_only_status = 'ok'
        term_label = f'{skipped} not checkable'
    else:
        term_only_status = 'ok'
        term_label = 'all verified'
    _open_cluster('external-terms')
    parts.append('<section class="section">')
    parts.append(_section_heading('external-terms', 'External term definitions', term_only_status, term_label))
    parts.append(_guide_link('external-terms'))
    parts.append('<p class="subtitle">Every term you reuse from an external vocabulary must actually be defined in that vocabulary. askwol looks each one up in the resolved namespace; a term that is missing there is usually a typo or made-up reuse of an established prefix. A term that exists but is marked deprecated there (<code>owl:deprecated</code>, <code>owl:DeprecatedClass</code>/<code>owl:DeprecatedProperty</code>, or a <code>vs:term_status</code> of &ldquo;deprecated&rdquo;/&ldquo;archaic&rdquo;) is flagged so you don&rsquo;t build on a term the source vocabulary is phasing out.</p>')
    term_summary_bits = [f'<strong>{ok_terms}</strong> confirmed']
    if fail_terms:
        term_summary_bits.append(f'<strong>{fail_terms}</strong> not found')
    if warn_terms:
        term_summary_bits.append(f'<strong>{warn_terms}</strong> deprecated upstream')
    if skipped:
        term_summary_bits.append(f'<strong>{skipped}</strong> skipped (namespace unavailable)')
    parts.append(f'<p class="subtitle">{" &middot; ".join(term_summary_bits)} of {total_terms} total.</p>')

    # Flat list of problem terms across all namespaces
    failed_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.FAIL]
    deprecated_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.WARN]
    skipped_terms_flat = [(ns, t) for ns in report.namespaces for t in ns.terms if t.status == Status.SKIP]
    if failed_terms_flat:
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Terms not found in their vocabulary ({len(failed_terms_flat)})</summary>')
        parts.append('<table><tr><th>Term</th><th>Prefix</th><th>Full IRI</th></tr>')
        for ns, t in failed_terms_flat:
            t_iri = escape(t.term_uri)
            parts.append(f'<tr><td><code>{escape(t.local_name)}</code></td>'
                         f'<td><code>{escape(ns.prefix)}</code></td>'
                         f'<td><a href="{t_iri}" target="_blank" rel="noopener"><code>{t_iri}</code></a></td></tr>')
        parts.append('</table></details>')
    if deprecated_terms_flat:
        parts.append(f'<details open><summary style="cursor:pointer;font-weight:600;">Deprecated upstream ({len(deprecated_terms_flat)})</summary>')
        parts.append('<table><tr><th>Term</th><th>Prefix</th><th>Marker</th><th>Full IRI</th></tr>')
        for ns, t in deprecated_terms_flat:
            t_iri = escape(t.term_uri)
            parts.append(f'<tr><td><code>{escape(t.local_name)}</code></td>'
                         f'<td><code>{escape(ns.prefix)}</code></td>'
                         f'<td>{escape(t.deprecated or "")}</td>'
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

    # Internal term definitions: referenced own-namespace terms must be defined
    it = report.internal_terms
    if it and it.status != Status.SKIP:
        _open_cluster('internal-terms')
        i_status = 'ok' if not it.undefined else 'fail'
        i_label = 'all defined' if i_status == 'ok' else f'{len(it.undefined)} undefined'
        parts.append('<section class="section">')
        parts.append(_section_heading('internal-terms', 'Internal term definitions', i_status, i_label))
        parts.append(_guide_link('internal-terms'))
        parts.append('<p class="subtitle">Every term you use from your own namespace must also be defined there: it has to appear as the subject of at least one triple, not only as a predicate or object. A term that is referenced but never defined is usually a typo or a forgotten declaration.</p>')
        parts.append(_status_subtitle(i_status, f'{it.defined}/{it.total_referenced} referenced terms defined &middot; {len(it.undefined)} undefined'))
        if it.undefined:
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Referenced but never defined ({len(it.undefined)})</summary>')
            parts.append('<table><tr><th>Term</th><th>Full IRI</th></tr>')
            for issue in it.undefined:
                t_iri = escape(issue.term)
                parts.append(
                    f'<tr><td><code>{escape(issue.display_name)}</code></td>'
                    f'<td><a href="{t_iri}" target="_blank" rel="noopener"><code>{t_iri}</code></a></td></tr>'
                )
            parts.append('</table></details>')
        parts.append('</section>')
    else:
        _skipped_section('internal-terms', 'Internal term definitions',
                         (it.message if it else None) or 'No <code>owl:Ontology</code> declaration, so the ontology&rsquo;s own namespace is unknown.')

    # Term inventory and naming conventions
    inv = report.term_inventory
    if inv and inv.status != Status.SKIP and inv.entries:
        _open_cluster('term-inventory')
        inv_status = 'ok' if not inv.naming_issues else 'fail'
        inv_label = 'naming consistent' if inv_status == 'ok' else f'{len(inv.naming_issues)} naming issue(s)'
        parts.append('<section class="section">')
        parts.append(_section_heading('term-inventory', 'Term inventory &amp; naming', inv_status, inv_label))
        parts.append(_guide_link('term-inventory'))
        parts.append('<p class="subtitle">Every term defined in the ontology&rsquo;s own namespace, grouped by category. By convention, class names start with an uppercase letter (<code>Person</code>) and property names start with a lowercase letter (<code>hasName</code>).</p>')
        counts_html = ' &middot; '.join(
            f'<strong>{n}</strong> {escape(cat)}' for cat, n in inv.category_counts.items()
        )
        parts.append(_status_subtitle(inv_status, f'{inv.total_terms} internal term{"s" if inv.total_terms != 1 else ""}: {counts_html}'))
        if inv.naming_issues:
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Naming convention issues ({len(inv.naming_issues)})</summary>')
            parts.append('<table><tr><th>Term</th><th>Category</th><th>Issue</th></tr>')
            for e in inv.naming_issues:
                t_iri = escape(e.term)
                parts.append(
                    f'<tr><td><a href="{t_iri}" target="_blank" rel="noopener"><code>{escape(e.display_name)}</code></a></td>'
                    f'<td>{escape(e.category)}</td><td>{escape(e.naming_message or "")}</td></tr>'
                )
            parts.append('</table></details>')
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show all terms ({inv.total_terms})</summary>')
        parts.append('<table><tr><th>Term</th><th>Category</th><th>Naming</th></tr>')
        for e in sorted(inv.entries, key=lambda x: (x.category, x.display_name.lower())):
            t_iri = escape(e.term)
            if e.deprecated:
                mark = f'<span title="Deprecated ({escape(e.deprecated)}); naming not checked" style="color:#999;font-size:1.2em;line-height:1">&#x2298;</span>'
            elif e.naming_ok:
                mark = '<span style="color:#2e7d32;font-size:1.2em;line-height:1">&#x2713;</span>'
            else:
                mark = '<span style="color:#c62828;font-size:1.2em;line-height:1">&#x2717;</span>'
            parts.append(
                f'<tr><td><a href="{t_iri}" target="_blank" rel="noopener"><code>{escape(e.display_name)}</code></a></td>'
                f'<td>{escape(e.category)}</td><td>{mark}</td></tr>'
            )
        parts.append('</table></details>')
        parts.append('</section>')
    else:
        _skipped_section('term-inventory', 'Term inventory &amp; naming',
                         'No terms are defined in the ontology&rsquo;s own namespace.')

    # Domains and ranges of object and datatype properties
    dr = report.domains_ranges
    if dr and dr.status != Status.SKIP and dr.checks:
        _open_cluster('domains-ranges')
        if dr.status == Status.FAIL:
            dr_status = 'fail'
        elif dr.status == Status.WARN:
            dr_status = 'warn'
        else:
            dr_status = 'ok'
        dr_label = 'all sound' if dr_status == 'ok' else f'{len(dr.issues)} to review'
        parts.append('<section class="section">')
        parts.append(_section_heading('domains-ranges', 'Domains &amp; ranges', dr_status, dr_label))
        parts.append(_guide_link('domains-ranges'))
        parts.append('<p class="subtitle">Object and datatype properties should declare an <code>rdfs:domain</code> and <code>rdfs:range</code>. An object property should range over a <strong>class</strong>; a datatype property over a <strong>datatype</strong>. Domain and range are read directly; they are not inherited from super-properties here.</p>')
        parts.append(_status_subtitle(dr_status,
            f'{dr.total_properties} propert{"y" if dr.total_properties == 1 else "ies"} '
            f'({dr.object_properties} object &middot; {dr.datatype_properties} datatype) &middot; '
            f'{dr.with_domain} with a domain &middot; {dr.with_range} with a range'))
        if dr.issues:
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Properties to review ({len(dr.issues)})</summary>')
            parts.append('<table><tr><th>Property</th><th>Category</th><th>Issue</th></tr>')
            for c in dr.issues:
                t_iri = escape(c.term)
                mark = _status_mark(c.status)
                parts.append(
                    f'<tr><td><a href="{t_iri}" target="_blank" rel="noopener"><code>{escape(c.display_name)}</code></a></td>'
                    f'<td>{escape(c.category)}</td><td>{mark} {c.message or ""}</td></tr>'
                )
            parts.append('</table></details>')
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show all properties ({dr.total_properties})</summary>')
        parts.append('<table><tr><th>Property</th><th>Category</th><th>Domain</th><th>Range</th></tr>')
        for c in sorted(dr.checks, key=lambda x: (x.category, x.display_name.lower())):
            t_iri = escape(c.term)
            dmark = ('<span style="color:#2e7d32">&#x2713;</span>' if c.has_domain
                     else '<span style="color:#c62828">&#x2717;</span>')
            rmark = ('<span style="color:#2e7d32">&#x2713;</span>' if c.has_range
                     else '<span style="color:#c62828">&#x2717;</span>')
            category = escape(c.category)
            if c.deprecated:
                category += f' <span title="Deprecated ({escape(c.deprecated)}); not checked" style="color:#999;">&#x2298;</span>'
            parts.append(
                f'<tr><td><a href="{t_iri}" target="_blank" rel="noopener"><code>{escape(c.display_name)}</code></a></td>'
                f'<td>{category}</td><td>{dmark}</td><td>{rmark}</td></tr>'
            )
        parts.append('</table></details>')
        parts.append('</section>')
    else:
        _skipped_section('domains-ranges', 'Domains &amp; ranges',
                         'No object or datatype properties are defined in the ontology&rsquo;s own namespace.')

    # Datatypes used across the ontology
    dt = report.datatypes
    if dt and dt.status != Status.SKIP and dt.usages:
        _open_cluster('datatypes')
        dt_status = 'ok' if not dt.unrecognized else 'fail'
        dt_label = 'all recognized' if dt_status == 'ok' else f'{len(dt.unrecognized)} unrecognized'
        parts.append('<section class="section">')
        parts.append(_section_heading('datatypes', 'Datatypes', dt_status, dt_label))
        parts.append(_guide_link('datatypes'))
        parts.append('<p class="subtitle">Datatypes used as property ranges and as literal datatypes should be recognized XSD built-ins (<code>xsd:string</code>, <code>xsd:integer</code>, &hellip;), <code>rdfs:Literal</code>, <code>rdf:langString</code>, or a datatype you declare with <code>rdfs:Datatype</code>. An unrecognized datatype is usually a typo.</p>')
        parts.append(_status_subtitle(dt_status, f'{dt.recognized}/{dt.total_datatypes} recognized &middot; {len(dt.unrecognized)} unrecognized'))
        if dt.unrecognized:
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Unrecognized datatypes ({len(dt.unrecognized)})</summary>')
            parts.append('<table><tr><th>Datatype</th><th>Uses</th><th>Full IRI</th></tr>')
            for u in dt.unrecognized:
                t_iri = escape(u.datatype)
                parts.append(
                    f'<tr><td><code>{escape(u.display_name)}</code></td>'
                    f'<td>{u.count}</td>'
                    f'<td><a href="{t_iri}" target="_blank" rel="noopener"><code>{t_iri}</code></a></td></tr>'
                )
            parts.append('</table></details>')
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show all datatypes ({dt.total_datatypes})</summary>')
        parts.append('<table><tr><th>Datatype</th><th>Uses</th><th>Where</th></tr>')
        for u in sorted(dt.usages, key=lambda x: x.display_name.lower()):
            mark = ('<span style="color:#2e7d32">&#x2713;</span>' if u.recognized
                    else '<span style="color:#c62828">&#x2717;</span>')
            parts.append(
                f'<tr><td>{mark} <code>{escape(u.display_name)}</code></td>'
                f'<td>{u.count}</td><td>{escape(", ".join(u.sources))}</td></tr>'
            )
        parts.append('</table></details>')
        parts.append('</section>')
    else:
        _skipped_section('datatypes', 'Datatypes',
                         'No datatypes are used in the ontology.')

    # Non-ontology terms: the ontology's own namespace should define only schema
    sk = report.non_ontology_terms
    if sk and sk.status != Status.SKIP:
        _open_cluster('non-ontology-terms')
        sk_status = 'ok' if not sk.terms else 'warn'
        sk_label = 'schema only' if sk_status == 'ok' else f'{len(sk.terms)} to move out'
        parts.append('<section class="section">')
        parts.append(_section_heading('non-ontology-terms', 'Non-ontology terms', sk_status, sk_label))
        parts.append(_guide_link('non-ontology-terms'))
        parts.append('<p class="subtitle">An OWL ontology should define schema: classes, properties, and datatypes. Individuals, <code>skos:Concept</code> instances, and other instance data belong in a separate data resource or concept scheme. A term in the ontology&rsquo;s own namespace that carries a type but no schema type is flagged; external terms and the ontology header are ignored.</p>')
        if sk.terms:
            parts.append(_status_subtitle('warn', f'{len(sk.terms)} non-schema term{"s" if len(sk.terms) != 1 else ""} defined in the ontology&rsquo;s own namespace'))
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Terms to move into a separate resource ({len(sk.terms)})</summary>')
            parts.append('<table><tr><th>Term</th><th>What it is</th><th>Full IRI</th></tr>')
            for issue in sk.terms:
                t_iri = escape(issue.term)
                parts.append(
                    f'<tr><td><code>{escape(issue.display_name)}</code></td>'
                    f'<td>{escape(issue.type_label)}</td>'
                    f'<td><a href="{t_iri}" target="_blank" rel="noopener"><code>{t_iri}</code></a></td></tr>'
                )
            parts.append('</table></details>')
        else:
            parts.append(_status_subtitle('ok', 'The ontology&rsquo;s own namespace defines only schema terms (classes, properties, and datatypes).'))
        parts.append('</section>')
    else:
        _skipped_section('non-ontology-terms', 'Non-ontology terms',
                         'No <code>owl:Ontology</code> declaration, so the ontology&rsquo;s own namespace is unknown.')

    # Labels and Comments: two sibling checks driven from the definition-docs data
    docs = report.definition_docs
    if docs and docs.total_definitions:
        _open_cluster('labels')
        def _mark_cell(present: bool, deprecated: str | None) -> str:
            if deprecated:
                return f'<span title="Deprecated ({escape(deprecated)}); not checked" style="color:#999;font-size:1.3em;line-height:1">&#x2298;</span>'
            if present:
                return '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>'
            return '<span style="color:#c62828;font-size:1.3em;line-height:1">&#x2717;</span>'

        def _doc_section(anchor: str, title: str, prop: str,
                         present_count: int, missing: list) -> None:
            status = 'ok' if not missing else 'fail'
            label = 'all present' if status == 'ok' else f'{len(missing)} missing'
            parts.append('<section class="section">')
            parts.append(_section_heading(anchor, title, status, label))
            parts.append(_guide_link(anchor))
            parts.append(f'<p class="subtitle">Every internally defined class and property should carry an <code>{prop}</code>. Reused external vocabulary terms, and terms you have marked deprecated, are ignored. Checked against <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/definition_documentation.ttl" target="_blank" rel="noopener">SHACL shapes for term documentation</a>.</p>')
            parts.append(_status_subtitle(status, f'{present_count}/{docs.total_definitions} have an <code>{prop}</code> &middot; {len(missing)} missing'))
            parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show {title.lower()} ({docs.total_definitions})</summary>')
            parts.append(f'<table><tr><th>Term</th><th>Type</th><th>{title.rstrip("s")}</th></tr>')
            for check in sorted(docs.checks, key=lambda c: (getattr(c, "has_label" if anchor == "labels" else "has_comment"), c.display_name.lower())):
                term = escape(check.display_name)
                term_uri = escape(check.term)
                present = check.has_label if anchor == 'labels' else check.has_comment
                parts.append(
                    f'<tr><td><a href="{term_uri}" target="_blank" rel="noopener"><code>{term}</code></a></td>'
                    f'<td>{escape(check.term_type)}</td><td>{_mark_cell(present, check.deprecated)}</td></tr>'
                )
            parts.append('</table></details>')
            parts.append('</section>')

        _doc_section('labels', 'Labels', 'rdfs:label', docs.with_label, docs.missing_label)
        _doc_section('comments', 'Comments', 'rdfs:comment', docs.with_comment, docs.missing_comment)
    else:
        _skipped_section('labels', 'Labels',
                         'No classes or properties are defined in the ontology&rsquo;s own namespace to document.')
        _skipped_section('comments', 'Comments',
                         'No classes or properties are defined in the ontology&rsquo;s own namespace to document.')

    # Language tag consistency - same section/subtitle/details pattern as
    # the other checks so the layout is fully uniform.
    lt = report.lang_tags
    _open_cluster('language-tags')
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
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show details by property ({n_issues})</summary>')

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
        _open_cluster('reasoner')
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
