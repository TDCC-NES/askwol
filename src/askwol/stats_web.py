"""Authenticated usage dashboard routes and rendering."""

from __future__ import annotations

import math
import secrets
from collections.abc import Callable
from html import escape
from urllib.parse import quote, urlparse

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from askwol import usage
from askwol.branding import FAVICON_LINK
from askwol.web_utils import apply_prefix

EVENTS_PAGE_SIZE = 15
AGG_PAGE_SIZE = 25

def _format_int(value: int | None) -> str:
    return "0" if value is None else f"{value:,}"


def _format_duration(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / 1000:.2f} s"


def _format_duration_seconds(value: int | None) -> str:
    """Whole seconds, no unit (the "s" lives in the column header instead)."""
    if value is None:
        return "n/a"
    return str(round(value / 1000))


def _stats_bar(value: int, maximum: int) -> str:
    if maximum <= 0:
        return "0%"
    return f"{max(4, round((value / maximum) * 100))}%"


_STATUS_NOTES = {
    "200": "OK, validation completed",
    "400": "bad request, missing or unusable input",
    "401": "unauthorised stats access",
    "413": "upload or fetched content exceeded the size limit",
    "415": "URL didn't return recognised RDF content",
    "422": "ontology could not be parsed or fetched",
    "429": "rate limited, too many requests in a short time",
    "503": "too many validations running at once, try again shortly",
    "504": "validation timed out",
}


def _status_note(status: object) -> str:
    """A human-readable note for a status code. Always returns non-empty text
    so a tooltip is available even for codes with no specific entry."""
    text = str(status) if status is not None else ""
    note = _STATUS_NOTES.get(text, "")
    if note:
        return note
    return "no status recorded" if text in ("", "(none)") else "unrecognised status code"


def _status_badge(status: object) -> str:
    """Colour-code a status code: green for a successful 2xx response, amber
    otherwise. Always carries a title tooltip."""
    text = str(status) if status is not None else ""
    if not text:
        return '<span class="hint">unknown</span>'
    ok = text.isdigit() and text.startswith("2")
    css_class = "status-badge status-ok" if ok else "status-badge status-warn"
    return f'<span class="{css_class}" title="{escape(_status_note(status))}">{escape(text)}</span>'


def _format_ts(ts: object) -> str:
    """Shorten an ISO timestamp to `YYYY-MM-DD HH:MM`."""
    text = str(ts) if ts is not None else ""
    text = text.replace("T", " ")
    if len(text) >= 16:
        return text[:16]
    return text


def _source_link(source: object) -> str:
    """Render a usage-log source as a link to the tested ontology when it is
    an http(s) URL; anything else (an uploaded filename, a placeholder like
    "(no input)") is shown as plain text. Always carries the full value in a
    title attribute since the cell itself may be truncated with an ellipsis."""
    text = str(source) if source is not None else ""
    if not text:
        return ""
    escaped = escape(text)
    if urlparse(text).scheme in ("http", "https"):
        return f'<a href="{escaped}" title="{escaped}" target="_blank" rel="noopener">{escaped}</a>'
    return f'<span title="{escaped}">{escaped}</span>'


def _render_pagination(
    *,
    page: int,
    page_size: int,
    total: int,
    shown: int,
    param: str,
    other_pages: dict[str, int],
    token: str | None,
    anchor: str,
    prev_label: str = "&larr;",
    next_label: str = "&rarr;",
    first_label: str = "&laquo;",
    last_label: str = "&raquo;",
    compact: bool = False,
) -> str:
    """Render a first/prev/next/last bar for one table, preserving the other
    tables' current page numbers (and the token) in the query string. Links
    include a `#anchor` fragment pointing back at that table's own section,
    so paging doesn't reset the browser's scroll position to the top of the
    whole page. `compact=True` drops the "page X of Y" suffix so the whole
    bar fits on one line in a narrower card."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    first_index = (page - 1) * page_size + 1 if shown else 0
    last_index = (page - 1) * page_size + shown

    def href(target: int) -> str:
        params = {**other_pages, param: target}
        query = "&".join(f"{key}={quote(str(value))}" for key, value in params.items())
        if token:
            query += f"&token={quote(str(token))}"
        return f"?{query}#{anchor}"

    def link(target: int, label: str, aria: str) -> str:
        return f'<a class="page-btn" href="{href(target)}" aria-label="{aria}">{label}</a>'

    def disabled(label: str, aria: str) -> str:
        return f'<span class="page-btn disabled" aria-label="{aria}" aria-disabled="true">{label}</span>'

    at_first, at_last = page <= 1, page >= total_pages
    first_link = disabled(first_label, "First page") if at_first else link(1, first_label, "First page")
    prev_link = disabled(prev_label, "Previous page") if at_first else link(page - 1, prev_label, "Previous page")
    next_link = disabled(next_label, "Next page") if at_last else link(page + 1, next_label, "Next page")
    last_link = disabled(last_label, "Last page") if at_last else link(total_pages, last_label, "Last page")
    info_text = (
        f'{_format_int(first_index)}&ndash;{_format_int(last_index)} of {_format_int(total)}'
        if compact else
        f'Showing {_format_int(first_index)}&ndash;{_format_int(last_index)} '
        f'of {_format_int(total)} &middot; page {_format_int(page)} of {_format_int(total_pages)}'
    )
    return (
        f'<div class="pagination">'
        f'<span class="page-nav">{first_link}{prev_link}</span>'
        f'<span class="page-info">{info_text}</span>'
        f'<span class="page-nav">{next_link}{last_link}</span>'
        f'</div>'
    )



def _log_ticks(max_value: int) -> list[int]:
    """Nice round tick values for a log10 y-axis: 1, then powers of 10 below
    the max, then the max itself (every displayed count is >= 1). Merges a
    candidate into the next one if they'd land within 8% of the chart's log
    range of each other (e.g. 100 and 106), so labels never overlap."""
    ticks = sorted({1, max_value} | {p for p in _powers_of_ten_below(max_value)})
    if max_value <= 1:
        return ticks
    threshold = 0.08 * math.log10(max_value)
    merged = [ticks[0]]
    for value in ticks[1:]:
        if math.log10(value) - math.log10(merged[-1]) < threshold:
            merged[-1] = value  # keep the larger, more specific value
        else:
            merged.append(value)
    return merged


def _powers_of_ten_below(max_value: int) -> list[int]:
    powers = []
    power = 10
    while power < max_value:
        powers.append(power)
        power *= 10
    return powers


def _log_y_frac(value: float, max_value: float) -> float:
    """Fraction from the chart's bottom (0.0) to top (1.0) for a value on a
    log10 scale anchored at 1, since every displayed count is >= 1."""
    if max_value <= 1:
        return 1.0
    return math.log10(max(value, 1)) / math.log10(max_value)



def _render_day_chart(by_day: list[dict], max_day: int) -> str:
    """Render "Events by day" as an inline SVG line chart: dates on the X
    axis, event counts on a log-scale Y axis. No JavaScript or external
    assets; each point carries a native <title> so the count still shows
    on hover."""
    if not by_day or max_day <= 0:
        return '<p class="empty">No events recorded in this period.</p>'

    rows = sorted(by_day, key=lambda row: str(row["day"]))
    n = len(rows)

    width, height = 880, 260
    left, right, top, bottom = 44, 12, 14, 44
    chart_w = width - left - right
    chart_h = height - top - bottom
    slot_w = chart_w / n
    label_step = max(1, round(n / 10))

    points = []
    labels = []
    for i, row in enumerate(rows):
        day = str(row["day"])
        count = int(row["n"])
        x = left + slot_w * (i + 0.5)
        y = top + chart_h * (1 - _log_y_frac(count, max_day))
        points.append((x, y, day, count))
        if i % label_step == 0 or i == n - 1:
            label_y = height - bottom + 16
            label_text = escape(day[5:] if len(day) >= 7 else day)
            labels.append(
                f'<text class="day-axis-label" text-anchor="end" x="{x:.1f}" y="{label_y}" '
                f'transform="rotate(-40 {x:.1f} {label_y})">{label_text}</text>'
            )

    polyline = (
        '<polyline class="day-line" points="'
        + " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in points)
        + '"></polyline>'
    )
    dots = "".join(
        f'<circle class="day-point" cx="{x:.1f}" cy="{y:.1f}" r="3">'
        f'<title>{escape(day)}: {_format_int(count)} events</title></circle>'
        for x, y, day, count in points
    )

    ticks = []
    for value in _log_ticks(max_day):
        y = top + chart_h * (1 - _log_y_frac(value, max_day))
        ticks.append(f'<line class="day-grid" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"></line>')
        ticks.append(
            f'<text class="day-axis-label day-axis-y" text-anchor="end" x="{left - 8}" y="{y + 4:.1f}">'
            f'{_format_int(value)}</text>'
        )

    total = sum(int(row["n"]) for row in rows)
    aria_label = (
        f"Events per day, log scale: {_format_int(total)} events across {n} days, "
        f"most recent {_format_int(int(rows[-1]['n']))}."
    )
    return (
        f'<svg class="day-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(aria_label)}">'
        + "".join(ticks) + polyline + dots + "".join(labels)
        + "</svg>"
    )


def _render_events_filter(
    *,
    source: str | None,
    status: str | None,
    source_options: list[dict],
    status_options: list[dict],
    token: str | None,
    url_source_page: int,
    upload_source_page: int,
) -> str:
    """Render the All events source/status filter: a plain GET form (no JS)
    plus a "Clear filter(s)" link when a filter is active. Options are the
    all-time distinct sources/statuses with their event counts."""

    def option(value: str, label: str, selected: str | None) -> str:
        is_selected = " selected" if selected == value else ""
        return f'<option value="{escape(value)}"{is_selected}>{escape(label)}</option>'

    source_opts = ['<option value="">All sources</option>']
    for row in source_options:
        value = str(row["source"])
        source_opts.append(option(value, f'{value} ({_format_int(int(row["n"]))})', source))

    status_opts = ['<option value="">All statuses</option>']
    for row in status_options:
        value = str(row["status"])
        status_opts.append(option(value, f'{value} ({_format_int(int(row["n"]))})', status))

    hidden = (
        f'<input type="hidden" name="url_source_page" value="{url_source_page}">'
        f'<input type="hidden" name="upload_source_page" value="{upload_source_page}">'
    )
    if token:
        hidden += f'<input type="hidden" name="token" value="{escape(str(token))}">'

    clear_link = ""
    if source or status:
        params = {"url_source_page": url_source_page, "upload_source_page": upload_source_page}
        if token:
            params["token"] = token
        query = "&".join(f"{key}={quote(str(value))}" for key, value in params.items())
        clear_link = f'<a class="page-btn" href="?{query}#all-events">Clear filter(s)</a>'

    return (
        '<form method="get" class="filter-form">'
        + hidden
        + f'<label class="filter-field">Source<select name="source">{"".join(source_opts)}</select></label>'
        + f'<label class="filter-field">Status<select name="status">{"".join(status_opts)}</select></label>'
        + '<button type="submit" class="page-btn">Filter</button>'
        + clear_link
        + '</form>'
    )


def _render_stats_page(data: dict[str, object]) -> str:
    total_events = int(data.get("total_events") or 0)
    unique_visitors = int(data.get("unique_visitors") or 0)
    avg_duration = data.get("avg_duration_ms")
    token = data.get("token") or None

    by_day = list(data.get("by_day") or [])
    url_sources = list(data.get("url_sources") or [])
    upload_sources = list(data.get("upload_sources") or [])
    all_events = list(data.get("all_events") or [])

    filter_source = data.get("filter_source") or None
    filter_status = data.get("filter_status") or None
    source_options = list(data.get("source_options") or [])
    status_options = list(data.get("status_options") or [])

    page = int(data.get("page") or 1)
    page_size = int(data.get("page_size") or 25)
    total_entries = int(data.get("total_entries") or 0)

    url_source_page = int(data.get("url_source_page") or 1)
    url_source_page_size = int(data.get("url_source_page_size") or 25)
    url_source_total = int(data.get("url_source_total") or 0)

    upload_source_page = int(data.get("upload_source_page") or 1)
    upload_source_page_size = int(data.get("upload_source_page_size") or 25)
    upload_source_total = int(data.get("upload_source_total") or 0)

    max_day = max((int(row["n"]) for row in by_day), default=0)
    max_url_source = int(data.get("url_source_max") or 0)
    max_upload_source = int(data.get("upload_source_max") or 0)

    day_html = _render_day_chart(by_day, max_day)

    def _source_rows(rows: list[dict], maximum: int) -> str:
        out = []
        for row in rows:
            count = int(row["n"])
            out.append(
                "<tr>"
                f"<td class=\"source\">{_source_link(row['source'])}</td>"
                f"<td class=\"num\">{_format_int(count)}</td>"
                f"<td><span class=\"mini-bar\"><span style=\"width:{_stats_bar(count, maximum)}\"></span></span></td>"
                "</tr>"
            )
        return "".join(out) or '<tr><td colspan="3" class="empty-cell">No sources yet.</td></tr>'

    url_source_html = _source_rows(url_sources, max_url_source)
    upload_source_html = _source_rows(upload_sources, max_upload_source)

    all_rows = []
    for row in all_events:
        status_cell = _status_badge(row['status'])
        visitor = str(row['ip_hash']) if row.get('ip_hash') else ''
        visitor_cell = (
            f"<code title=\"Salted hash of the visitor IP (raw IP is never stored)\">{escape(visitor)}</code>"
            if visitor else '<span class="hint">unknown</span>'
        )
        all_rows.append(
            "<tr>"
            f"<td>{escape(_format_ts(row['ts']))}</td>"
            f"<td>{visitor_cell}</td>"
            f"<td>{escape(str(row['kind']))}</td>"
            f"<td>{status_cell}</td>"
            f"<td class=\"num\">{escape(_format_duration_seconds(row.get('duration_ms')))}</td>"
            f"<td class=\"source\">{_source_link(row['source'])}</td>"
            "</tr>"
        )
    all_html = "".join(all_rows) or '<tr><td colspan="6" class="empty-cell">No events match this filter.</td></tr>'

    events_filter = _render_events_filter(
        source=filter_source, status=filter_status,
        source_options=source_options, status_options=status_options,
        token=token, url_source_page=url_source_page, upload_source_page=upload_source_page,
    )

    filter_params: dict[str, int | str] = {}
    if filter_source:
        filter_params["source"] = filter_source
    if filter_status:
        filter_params["status"] = filter_status

    events_pagination = _render_pagination(
        page=page, page_size=page_size, total=total_entries, shown=len(all_events),
        param="page", other_pages={"url_source_page": url_source_page, "upload_source_page": upload_source_page, **filter_params},
        token=token, anchor="all-events", prev_label="&larr; Newer", next_label="Older &rarr;",
        first_label="&laquo; Newest", last_label="Oldest &raquo;",
    )
    url_source_pagination = _render_pagination(
        page=url_source_page, page_size=url_source_page_size, total=url_source_total, shown=len(url_sources),
        param="url_source_page", other_pages={"page": page, "upload_source_page": upload_source_page, **filter_params},
        token=token, anchor="top-sources-urls", compact=True,
    )
    upload_source_pagination = _render_pagination(
        page=upload_source_page, page_size=upload_source_page_size, total=upload_source_total, shown=len(upload_sources),
        param="upload_source_page", other_pages={"page": page, "url_source_page": url_source_page, **filter_params},
        token=token, anchor="top-sources-uploads", compact=True,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask Wol: usage dashboard</title>
{FAVICON_LINK}
<meta name="color-scheme" content="light">
<style>
    :root {{ --accent: #285c4d; --accent-soft: #dcebe6; --accent-strong: #12362f; --border: #d7e2de; --muted: #5d6b66; --bg: #f4f7f5; --card: #ffffff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; color: #18312b; background: radial-gradient(circle at top left, #edf5f1, transparent 35%), linear-gradient(180deg, #f8fbf9, var(--bg)); }}
    .shell {{ max-width: 1160px; margin: 0 auto; padding: 32px 20px 56px; }}
    .topnav {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; color: var(--muted); font-size: 0.95rem; margin-bottom: 22px; }}
    .topnav a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
    .brand {{ display: inline-flex; align-items: center; gap: 12px; width: fit-content; padding: 8px 14px; border-radius: 999px; background: rgba(220, 235, 230, 0.9); color: var(--accent-strong); font-weight: 800; letter-spacing: 0.02em; }}
    .brand-mark {{ display: inline-grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: #fff; border: 1px solid var(--border); }}
    .brand-mark img {{ height: 24px; width: auto; }}
    .hero {{ display: grid; gap: 10px; margin-bottom: 22px; margin-top: 14px; }}
    .kicker {{ display: inline-flex; width: fit-content; padding: 5px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--accent-strong); font-size: 0.8rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: clamp(2rem, 4vw, 3.3rem); line-height: 1.03; letter-spacing: -0.04em; }}
    .grid {{ display: grid; gap: 18px; grid-template-columns: repeat(12, minmax(0, 1fr)); }}
    .card {{ grid-column: span 12; background: var(--card); border: 1px solid var(--border); border-radius: 18px; box-shadow: 0 10px 30px rgba(24, 49, 43, 0.06); overflow: hidden; }}
    .summary {{ display: grid; gap: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 18px; }}
    .metric {{ padding: 18px; border-radius: 14px; background: linear-gradient(180deg, #fff, #f9fbfa); border: 1px solid #e4ece8; }}
    .metric .label {{ color: var(--muted); font-size: 0.84rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .metric .value {{ margin-top: 8px; font-size: 2rem; font-weight: 800; color: var(--accent-strong); }}
    .panel {{ padding: 18px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 1.1rem; }}
    .source {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .day-chart {{ width: 100%; height: auto; overflow: visible; }}
    .day-line {{ fill: none; stroke: var(--accent); stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }}
    .day-point {{ fill: var(--accent); }}
    .day-point:hover {{ fill: var(--accent-strong); }}
    .day-grid {{ stroke: #e2ece7; stroke-width: 1; }}
    .day-axis-label {{ fill: var(--muted); font-size: 9px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-top: 1px solid var(--border); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .mini-bar {{ display: block; height: 10px; background: #edf2ef; border-radius: 999px; overflow: hidden; margin-top: 3px; }}
    .mini-bar span {{ display: block; height: 100%; min-width: 4px; background: linear-gradient(90deg, #7cae9e, var(--accent)); border-radius: 999px; }}
    .empty, .empty-cell {{ color: var(--muted); padding: 12px 0; }}
    .source {{ max-width: 520px; word-break: break-word; }}
    .table-wrap {{ overflow-x: auto; }}
    .ranked-table {{ table-layout: fixed; }}
    .ranked-table .source {{ max-width: none; }}
    .ranked-table .num {{ width: 78px; }}
    .ranked-table .share-col {{ width: 70px; }}
    .hint {{ color: var(--muted); font-size: 0.9em; }}
    .status-badge {{ display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; font-weight: 700; font-size: 0.85em; white-space: nowrap; }}
    .status-ok {{ background: #e3f3e9; color: #1f7a4d; }}
    .status-warn {{ background: #fdf0dc; color: #9a5b12; }}
    .filter-form {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 0 0 16px; }}
    .filter-field {{ display: flex; flex-direction: column; gap: 4px; font-size: 0.8rem; color: var(--muted); font-weight: 600; }}
    .filter-field select {{ padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border); font-size: 0.9rem; color: #18312b; background: #fff; max-width: 320px; }}
    .pagination {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-top: 14px; }}
    .page-nav {{ display: flex; gap: 8px; }}
    .page-btn {{ padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg-soft, #f9fbfa); color: var(--accent); text-decoration: none; font-weight: 600; font-size: 0.9rem; }}
    .page-btn.disabled {{ color: #b3c1bc; border-color: #eaf0ed; cursor: default; }}
    .page-info {{ color: var(--muted); font-size: 0.9rem; }}
    @media (max-width: 900px) {{ .summary {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
    <div class="shell">
        <div class="topnav">
            <span class="brand"><span class="brand-mark" aria-hidden="true"><img src="static/wollie-h1.png" alt="" width="18" height="24"></span> Ask Wol usage</span>
            <a href="./">OWL ontology checker</a>
            <a href="guide">OWL ontology publishing guide</a>
            <a href="docs">API docs</a>
        </div>
        <div class="hero">
            <span class="kicker">Internal dashboard</span>
            <h1>Ask Wol usage dashboard</h1>
        </div>
        <div class="grid">
            <section class="card summary" aria-label="Usage summary">
                <div class="metric"><div class="label">Events</div><div class="value">{_format_int(total_events)}</div></div>
                <div class="metric"><div class="label">Unique visitors</div><div class="value">{_format_int(unique_visitors)}</div></div>
                <div class="metric"><div class="label">Average duration (30 days)</div><div class="value">{escape(_format_duration(int(avg_duration) if avg_duration is not None else None))}</div></div>
            </section>

            <section class="card panel" style="grid-column: span 12;">
                <h2>Events by day</h2>
                {day_html}
            </section>

            <section class="card panel" id="all-events" style="grid-column: span 12;">
                <h2>All events</h2>
                {events_filter}
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Timestamp</th><th>Visitor</th><th>Kind</th><th>Status</th><th class="num">Duration (s)</th><th>Source</th></tr></thead>
                        <tbody>{all_html}</tbody>
                    </table>
                </div>
                {events_pagination}
            </section>

            <section class="card panel" id="top-sources-urls" style="grid-column: span 6;">
                <h2>Top sources: URLs <span class="hint">(all time)</span></h2>
                <div class="table-wrap">
                    <table class="ranked-table">
                        <thead><tr><th>Source</th><th class="num">Events</th><th class="share-col">Share</th></tr></thead>
                        <tbody>{url_source_html}</tbody>
                    </table>
                </div>
                {url_source_pagination}
            </section>

            <section class="card panel" id="top-sources-uploads" style="grid-column: span 6;">
                <h2>Top sources: uploads <span class="hint">(all time)</span></h2>
                <div class="table-wrap">
                    <table class="ranked-table">
                        <thead><tr><th>Source</th><th class="num">Events</th><th class="share-col">Share</th></tr></thead>
                        <tbody>{upload_source_html}</tbody>
                    </table>
                </div>
                {upload_source_pagination}
            </section>
        </div>
    </div>
</body>
</html>"""


def _stats_data(
    page: int,
    url_source_page: int,
    upload_source_page: int,
    source: str | None,
    status: str | None,
) -> dict:
    page = max(1, page)
    data = usage.stats(
        days=30,
        url_source_page=max(1, url_source_page),
        url_source_page_size=AGG_PAGE_SIZE,
        upload_source_page=max(1, upload_source_page),
        upload_source_page_size=AGG_PAGE_SIZE,
    )
    data["total_entries"] = usage.events_count(source=source, status=status)
    data["all_events"] = usage.all_events(
        limit=EVENTS_PAGE_SIZE, offset=(page - 1) * EVENTS_PAGE_SIZE, source=source, status=status,
    )
    data["page"] = page
    data["page_size"] = EVENTS_PAGE_SIZE
    return data


def _valid_token(token: str | None, expected: str) -> bool:
    return token is not None and secrets.compare_digest(token.encode(), expected.encode())


def create_stats_router(get_root_path: Callable[[], str]) -> APIRouter:
    router = APIRouter()

    @router.get("/stats", response_class=HTMLResponse, include_in_schema=False)
    async def stats_page(
        token: str | None = None,
        page: int = 1,
        url_source_page: int = 1,
        upload_source_page: int = 1,
        source: str | None = None,
        status: str | None = None,
    ):
        expected = usage.stats_token()
        if not expected:
            return HTMLResponse(
                "<p>stats disabled - set ASKWOL_STATS_TOKEN to enable the usage dashboard.</p>",
                status_code=503,
            )
        if not _valid_token(token, expected):
            return HTMLResponse("<p>unauthorised</p>", status_code=401)

        source, status = source or None, status or None
        data = _stats_data(page, url_source_page, upload_source_page, source, status)
        data["filter_source"] = source
        data["filter_status"] = status
        data["source_options"] = usage.distinct_sources()
        data["status_options"] = usage.distinct_statuses()
        data["token"] = token
        return HTMLResponse(apply_prefix(_render_stats_page(data), get_root_path()))

    @router.get("/api/stats", include_in_schema=False)
    async def stats_endpoint(
        token: str | None = None,
        page: int = 1,
        url_source_page: int = 1,
        upload_source_page: int = 1,
        source: str | None = None,
        status: str | None = None,
    ):
        expected = usage.stats_token()
        if not expected:
            return JSONResponse(
                {"error": "stats disabled - set ASKWOL_STATS_TOKEN to enable"},
                status_code=503,
            )
        if not _valid_token(token, expected):
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        return JSONResponse(_stats_data(page, url_source_page, upload_source_page, source or None, status or None))

    return router
