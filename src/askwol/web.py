"""FastAPI web application for the askwol ontology checker."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from html import escape
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from askwol import usage
from askwol.cache import OntologyCache
from askwol.definition_docs import check_definition_documentation
from askwol.imports_check import check_imports
from askwol.internal_terms import check_internal_terms
from askwol.iri_scheme import check_iri_scheme
from askwol.iri_strategy import check_iri_strategy
from askwol.iri_utils import ontology_namespaces
from askwol.lang_tags import check_lang_tags
from askwol.mermaid_diagram import build_mermaid
from askwol.metadata_validator import validate_ontology_metadata
from askwol.models import NamespaceReport, UnusedPrefix, ValidationReport
from askwol.parser import parse_ontology
from askwol.reasoner_checks import run_reasoner_checks
from askwol.report_html import render_report
from askwol.resolver import block_private_network_requests, resolve_all_namespaces
from askwol.non_ontology_terms import check_non_ontology_terms
from askwol.templates import GUIDE_HTML, UPLOAD_HTML
from askwol.term_inventory import check_datatypes, check_domains_ranges, check_term_inventory
from askwol.term_validator import validate_terms

# ASKWOL_ROOT_PATH is the reverse-proxy sub-path prefix (e.g. /askwol); empty
# for a root deployment.
ROOT_PATH = os.environ.get("ASKWOL_ROOT_PATH", "").rstrip("/")

# Generous cap for ontology uploads - real Turtle/RDF-XML/JSON-LD files are
# almost always a few MB at most. Bounds memory/disk use against oversized
# or abusive uploads.
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

# Per-IP throttle for the two validation endpoints, since each request can
# trigger many outbound HTTP fetches (namespaces, imports). In-memory only, so
# it resets on restart and is tracked per worker process - fine for abuse
# mitigation, not a strict global limit. Set ASKWOL_RATE_LIMIT=0 to disable.
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("ASKWOL_RATE_LIMIT", "20"))

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: dict[str, tuple[float, int]] = {}


def _rate_limited(client_ip: str | None) -> bool:
    """True if client_ip has exceeded the per-window request budget."""
    if not client_ip or RATE_LIMIT_MAX_REQUESTS <= 0:
        return False
    now = time.monotonic()
    with _rate_limit_lock:
        if len(_rate_limit_buckets) > 10_000:
            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            for ip in [k for k, (start, _) in _rate_limit_buckets.items() if start < cutoff]:
                del _rate_limit_buckets[ip]
        window_start, count = _rate_limit_buckets.get(client_ip, (now, 0))
        if now - window_start >= RATE_LIMIT_WINDOW_SECONDS:
            window_start, count = now, 0
        count += 1
        _rate_limit_buckets[client_ip] = (window_start, count)
        return count > RATE_LIMIT_MAX_REQUESTS

app = FastAPI(
    title="askwol",
    description=(
        "Validate OWL ontologies: namespace resolution, external term "
        "definitions (existence in remote vocabularies), internal term "
        "definitions (own-namespace terms are defined), label "
        "and comment documentation (SHACL), ontology metadata (SHACL), "
        "language-tag consistency, unused prefix declarations, owl:imports "
        "resolution, IRI strategy consistency (hash vs slash), IRI scheme "
        "consistency (http vs https), and lightweight OWL RL reasoner checks "
        "(ontology consistency, inconsistent individuals, and unsatisfiable "
        "classes)."
    ),
    version="0.1.0",
    root_path=ROOT_PATH,
)

# Global cache  -  persists across requests so repeated uploads don't re-fetch
_global_cache = OntologyCache()


def _apply_prefix(html: str) -> str:
    """Prefix app-internal nav links with the sub-path so they resolve behind a
    reverse proxy. Root-absolute URLs are used (not a <base> tag) so same-page
    fragment links keep working. A no-op at a root deployment."""
    if not ROOT_PATH:
        return html
    return (
        html.replace('href="./"', f'href="{ROOT_PATH}/"')
        .replace('href="guide"', f'href="{ROOT_PATH}/guide"')
        .replace('href="docs"', f'href="{ROOT_PATH}/docs"')
        .replace('action="validate"', f'action="{ROOT_PATH}/validate"')
        .replace('href="/#reasoner"', f'href="{ROOT_PATH}/#reasoner"')
    )


def _format_int(value: int | None) -> str:
    return "0" if value is None else f"{value:,}"


def _format_duration(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value < 1000:
        return f"{value:,} ms"
    return f"{value / 1000:.1f} s"


def _stats_bar(value: int, maximum: int) -> str:
    if maximum <= 0:
        return "0%"
    return f"{max(4, round((value / maximum) * 100))}%"


_STATUS_NOTES = {
    "200": "OK, validation succeeded",
    "400": "bad request, missing or unusable input",
    "401": "unauthorized stats access",
    "415": "URL returned HTML instead of RDF",
    "422": "ontology could not be parsed or fetched",
    "503": "usage tracking or stats disabled",
}


def _status_note(status: object) -> str:
    return _STATUS_NOTES.get(str(status) if status is not None else "", "")


def _format_ts(ts: object) -> str:
    """Shorten an ISO timestamp to `YYYY-MM-DD HH:MM`."""
    text = str(ts) if ts is not None else ""
    text = text.replace("T", " ")
    if len(text) >= 16:
        return text[:16]
    return text


def _is_local_request(request: Request) -> bool:
    host = (request.url.hostname or "").lower()
    client_host = (request.client.host if request.client else "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or client_host in {"localhost", "127.0.0.1", "::1"}


class UploadTooLargeError(Exception):
    """Raised when an uploaded file exceeds MAX_UPLOAD_SIZE."""


async def _read_upload_capped(file: UploadFile) -> bytes:
    """Read an upload in chunks, aborting once it exceeds MAX_UPLOAD_SIZE."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise UploadTooLargeError(
                f"File exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB upload limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _render_stats_page(data: dict[str, object]) -> str:
    total_events = int(data.get("total_events") or 0)
    unique_visitors = int(data.get("unique_visitors") or 0)
    avg_duration = data.get("avg_duration_ms")
    days = int(data.get("days") or 30)

    by_day = list(data.get("by_day") or [])
    by_status = list(data.get("by_status") or [])
    top_sources = list(data.get("top_sources") or [])
    all_events = list(data.get("all_events") or [])
    page = int(data.get("page") or 1)
    page_size = int(data.get("page_size") or 50)
    total_entries = int(data.get("total_entries") or 0)
    token = data.get("token") or None
    total_pages = max(1, (total_entries + page_size - 1) // page_size)
    first_index = (page - 1) * page_size + 1 if all_events else 0
    last_index = (page - 1) * page_size + len(all_events)

    max_day = max((int(row["n"]) for row in by_day), default=0)
    max_status = max((int(row["n"]) for row in by_status), default=0)
    max_source = max((int(row["n"]) for row in top_sources), default=0)

    day_rows = []
    for row in by_day:
        count = int(row["n"])
        day_rows.append(
            "<div class=\"bar-row\">"
            f"<div class=\"bar-label\">{escape(str(row['day']))}</div>"
            f"<div class=\"bar-track\"><span style=\"width:{_stats_bar(count, max_day)}\"></span></div>"
            f"<div class=\"bar-value\">{_format_int(count)}</div>"
            "</div>"
        )
    day_html = "".join(day_rows) or '<p class="empty">No events recorded in this period.</p>'

    status_rows = []
    for row in by_status:
        count = int(row["n"])
        status_rows.append(
            "<tr>"
            f"<td>{escape(str(row['status']))}</td>"
            f"<td class=\"hint\">{escape(_status_note(row['status']))}</td>"
            f"<td class=\"num\">{_format_int(count)}</td>"
            f"<td><span class=\"mini-bar\"><span style=\"width:{_stats_bar(count, max_status)}\"></span></span></td>"
            "</tr>"
        )
    status_html = "".join(status_rows) or '<tr><td colspan="4" class="empty-cell">No events recorded in this period.</td></tr>'

    source_rows = []
    for row in top_sources:
        count = int(row["n"])
        source_rows.append(
            "<tr>"
            f"<td class=\"source\">{escape(str(row['source']))}</td>"
            f"<td class=\"num\">{_format_int(count)}</td>"
            f"<td><span class=\"mini-bar\"><span style=\"width:{_stats_bar(count, max_source)}\"></span></span></td>"
            "</tr>"
        )
    source_html = "".join(source_rows) or '<tr><td colspan="3" class="empty-cell">No sources yet.</td></tr>'

    all_rows = []
    for row in all_events:
        status = str(row['status']) if row['status'] is not None else ''
        note = _status_note(row['status'])
        status_cell = (
            f"<span title=\"{escape(note)}\">{escape(status)}</span>"
            if note else escape(status)
        )
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
            f"<td>{escape(_format_duration(row.get('duration_ms')))}</td>"
            f"<td class=\"source\">{escape(str(row['source']) if row['source'] is not None else '')}</td>"
            "</tr>"
        )
    all_html = "".join(all_rows) or '<tr><td colspan="6" class="empty-cell">No database entries yet.</td></tr>'

    def _page_href(target: int) -> str:
        query = f"?page={target}"
        if token:
            query += f"&token={quote(str(token))}"
        return query

    prev_link = (
        f'<a class="page-btn" href="{_page_href(page - 1)}">&larr; Newer</a>'
        if page > 1 else '<span class="page-btn disabled">&larr; Newer</span>'
    )
    next_link = (
        f'<a class="page-btn" href="{_page_href(page + 1)}">Older &rarr;</a>'
        if page < total_pages else '<span class="page-btn disabled">Older &rarr;</span>'
    )
    pagination_html = (
        f'<div class="pagination">{prev_link}'
        f'<span class="page-info">Showing {_format_int(first_index)}&ndash;{_format_int(last_index)} '
        f'of {_format_int(total_entries)} &middot; page {_format_int(page)} of {_format_int(total_pages)}</span>'
        f'{next_link}</div>'
    )

    return _apply_prefix(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask Wol: usage dashboard</title>
<meta name="color-scheme" content="light">
<style>
    :root {{ --accent: #285c4d; --accent-soft: #dcebe6; --accent-strong: #12362f; --border: #d7e2de; --muted: #5d6b66; --bg: #f4f7f5; --card: #ffffff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; color: #18312b; background: radial-gradient(circle at top left, #edf5f1, transparent 35%), linear-gradient(180deg, #f8fbf9, var(--bg)); }}
    .shell {{ max-width: 1160px; margin: 0 auto; padding: 32px 20px 56px; }}
    .topnav {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; color: var(--muted); font-size: 0.95rem; margin-bottom: 22px; }}
    .topnav a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
    .brand {{ display: inline-flex; align-items: center; gap: 12px; width: fit-content; padding: 8px 14px; border-radius: 999px; background: rgba(220, 235, 230, 0.9); color: var(--accent-strong); font-weight: 800; letter-spacing: 0.02em; }}
    .brand-mark {{ display: inline-grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: linear-gradient(180deg, #335f53, var(--accent)); color: #fff; font-size: 1rem; }}
    .hero {{ display: grid; gap: 10px; margin-bottom: 22px; margin-top: 14px; }}
    .kicker {{ display: inline-flex; width: fit-content; padding: 5px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--accent-strong); font-size: 0.8rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: clamp(2rem, 4vw, 3.3rem); line-height: 1.03; letter-spacing: -0.04em; }}
    .lede {{ margin: 0; max-width: 72ch; color: var(--muted); font-size: 1.05rem; line-height: 1.6; }}
    .grid {{ display: grid; gap: 18px; grid-template-columns: repeat(12, minmax(0, 1fr)); }}
    .card {{ grid-column: span 12; background: var(--card); border: 1px solid var(--border); border-radius: 18px; box-shadow: 0 10px 30px rgba(24, 49, 43, 0.06); overflow: hidden; }}
    .summary {{ display: grid; gap: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 18px; }}
    .metric {{ padding: 18px; border-radius: 14px; background: linear-gradient(180deg, #fff, #f9fbfa); border: 1px solid #e4ece8; }}
    .metric .label {{ color: var(--muted); font-size: 0.84rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .metric .value {{ margin-top: 8px; font-size: 2rem; font-weight: 800; color: var(--accent-strong); }}
    .metric .sub {{ margin-top: 6px; color: var(--muted); font-size: 0.95rem; }}
    .panel {{ padding: 18px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 1.1rem; }}
    .bar-row {{ display: grid; gap: 10px; grid-template-columns: 110px 1fr 72px; align-items: center; padding: 6px 0; }}
    .bar-label, .source {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-track {{ height: 14px; background: #edf2ef; border-radius: 999px; overflow: hidden; }}
    .bar-track span {{ display: block; height: 100%; min-width: 4px; border-radius: 999px; background: linear-gradient(90deg, var(--accent), #4f907d); }}
    .bar-value, .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-top: 1px solid var(--border); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .mini-bar {{ display: block; height: 10px; background: #edf2ef; border-radius: 999px; overflow: hidden; margin-top: 3px; }}
    .mini-bar span {{ display: block; height: 100%; min-width: 4px; background: linear-gradient(90deg, #7cae9e, var(--accent)); border-radius: 999px; }}
    .empty, .empty-cell {{ color: var(--muted); padding: 12px 0; }}
    .source {{ max-width: 520px; word-break: break-word; }}
    .table-wrap {{ overflow-x: auto; }}
    .hint {{ color: var(--muted); font-size: 0.9em; }}
    .pagination {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-top: 14px; }}
    .page-btn {{ padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg-soft, #f9fbfa); color: var(--accent); text-decoration: none; font-weight: 600; font-size: 0.9rem; }}
    .page-btn.disabled {{ color: #b3c1bc; border-color: #eaf0ed; cursor: default; }}
    .page-info {{ color: var(--muted); font-size: 0.9rem; }}
    @media (max-width: 900px) {{ .summary {{ grid-template-columns: 1fr; }} .bar-row {{ grid-template-columns: 1fr; }} .bar-value {{ text-align: left; }} }}
</style>
</head>
<body>
    <div class="shell">
        <div class="topnav">
            <span class="brand"><span class="brand-mark" aria-hidden="true">🦉</span> Ask Wol usage</span>
            <a href="./">Home</a>
            <a href="guide">Publishing guide</a>
            <a href="docs">API docs</a>
        </div>
        <div class="hero">
            <span class="kicker">Internal dashboard</span>
            <h1>Ask Wol usage dashboard</h1>
            <p class="lede">A read-only view of validation activity in the local usage database. The page shows overall volume, recent traffic, and the most common response codes and sources for the last {days} days.</p>
        </div>
        <div class="grid">
            <section class="card summary" aria-label="Usage summary">
                <div class="metric"><div class="label">Events</div><div class="value">{_format_int(total_events)}</div><div class="sub">Validation requests tracked in the window.</div></div>
                <div class="metric"><div class="label">Unique visitors</div><div class="value">{_format_int(unique_visitors)}</div><div class="sub">Distinct hashed IPs seen in the window.</div></div>
                <div class="metric"><div class="label">Average duration</div><div class="value">{escape(_format_duration(int(avg_duration) if avg_duration is not None else None))}</div><div class="sub">Average handler time across recorded events.</div></div>
            </section>

            <section class="card panel" style="grid-column: span 12;">
                <h2>Events by day</h2>
                {day_html}
            </section>

            <section class="card panel" style="grid-column: span 6;">
                <h2>By status</h2>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Status</th><th>Meaning</th><th class="num">Events</th><th>Share</th></tr></thead>
                        <tbody>{status_html}</tbody>
                    </table>
                </div>
            </section>

            <section class="card panel" style="grid-column: span 6;">
                <h2>Top sources</h2>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Source</th><th class="num">Events</th><th>Share</th></tr></thead>
                        <tbody>{source_html}</tbody>
                    </table>
                </div>
            </section>

            <section class="card panel" style="grid-column: span 12;">
                <h2>All events</h2>
                <p class="lede">The complete history stored in the usage database, newest first. Hover a status code to see what it means. The visitor column is a salted hash of the IP address; the raw IP is never stored.</p>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Timestamp</th><th>Visitor</th><th>Kind</th><th>Status</th><th>Duration</th><th>Source</th></tr></thead>
                        <tbody>{all_html}</tbody>
                    </table>
                </div>
                {pagination_html}
            </section>
        </div>
    </div>
</body>
</html>""")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    return HTMLResponse(_apply_prefix(UPLOAD_HTML))


@app.get("/health", summary="Health check", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/stats", response_class=HTMLResponse, include_in_schema=False)
async def stats_page(request: Request, token: str | None = None, page: int = 1):
    """Internal usage dashboard. Requires ASKWOL_STATS_TOKEN env var to match `?token=`."""
    expected = usage.stats_token()
    if not expected:
        return HTMLResponse(
            "<p>stats disabled - set ASKWOL_STATS_TOKEN to enable the usage dashboard.</p>",
            status_code=503,
        )
    if token != expected and not _is_local_request(request):
        return HTMLResponse("<p>unauthorized</p>", status_code=401)

    page_size = 50
    page = max(1, page)
    data = usage.stats(days=30)
    data["total_entries"] = usage.events_count()
    data["all_events"] = usage.all_events(limit=page_size, offset=(page - 1) * page_size)
    data["page"] = page
    data["page_size"] = page_size
    data["token"] = token
    return HTMLResponse(_render_stats_page(data))


@app.get("/api/stats", include_in_schema=False)
async def stats_endpoint(request: Request, token: str | None = None, page: int = 1):
    """Internal usage data. Requires ASKWOL_STATS_TOKEN env var to match `?token=`."""
    expected = usage.stats_token()
    if not expected:
        return JSONResponse(
            {"error": "stats disabled - set ASKWOL_STATS_TOKEN to enable"},
            status_code=503,
        )
    if token != expected and not _is_local_request(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    page_size = 50
    page = max(1, page)
    payload = usage.stats(days=30)
    payload["total_entries"] = usage.events_count()
    payload["page"] = page
    payload["page_size"] = page_size
    payload["all_events"] = usage.all_events(limit=page_size, offset=(page - 1) * page_size)
    return JSONResponse(payload)


@app.get("/guide", response_class=HTMLResponse, include_in_schema=False)
async def guide():
    return HTMLResponse(_apply_prefix(GUIDE_HTML))

@app.get("/validate", include_in_schema=False)
async def validate_get():
    """Redirect browser GETs to the home form instead of a 405 error."""
    return RedirectResponse(url="./", status_code=303)


@app.post("/validate", include_in_schema=False)
async def validate(
    request: Request,
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
):
    """Validate an ontology from file upload or URL."""
    started = time.perf_counter()
    client_ip = request.client.host if request.client else None
    source: str | None = None
    kind = "validate"

    if _rate_limited(client_ip):
        source = "(rate limited)"
        response = HTMLResponse(
            "<p>Too many requests. Please wait a minute and try again.</p>",
            status_code=429,
        )
    elif url and url.strip():
        source = url.strip()
        response = await _validate_url(source)
    elif file and file.filename:
        source = file.filename
        kind = "validate_upload"
        response = await _validate_upload(file)
    else:
        source = "(no input)"
        response = HTMLResponse(
            '<p>Please provide an ontology URL or upload a file. '
            '<a href="./">Back to the form</a>.</p>',
            status_code=400,
        )

    usage.record(
        kind,
        source=source,
        status=str(response.status_code),
        duration_ms=int((time.perf_counter() - started) * 1000),
        ip=client_ip,
    )
    return response


async def _validate_url(url: str) -> HTMLResponse:
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        return HTMLResponse("<p>Only http/https URLs are supported.</p>", status_code=400)

    # Ask the server for RDF via content negotiation. Many namespace URIs
    # return HTML by default and only serve RDF when explicitly asked.
    accept_header = (
        "text/turtle, application/rdf+xml;q=0.9, application/ld+json;q=0.8, "
        "application/n-triples;q=0.7, text/n3;q=0.6, */*;q=0.1"
    )

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30,
            event_hooks={"request": [block_private_network_requests]},
        ) as client, client.stream("GET", url, headers={"Accept": accept_header}) as resp:
            resp.raise_for_status()

            # Pick a suffix from the Content-Type so the parser can sniff the
            # format. Fall back to the URL path, then to .ttl.
            ctype = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            ctype_suffix = {
                "text/turtle": ".ttl",
                "application/x-turtle": ".ttl",
                "application/rdf+xml": ".rdf",
                "application/xml": ".rdf",
                "text/xml": ".rdf",
                "application/ld+json": ".jsonld",
                "application/json": ".jsonld",
                "application/n-triples": ".nt",
                # Note: text/plain is intentionally NOT mapped. Many servers (e.g.
                # raw.githubusercontent.com) serve Turtle/RDF as text/plain, so we
                # fall back to the URL path extension instead of assuming N-Triples.
                "text/n3": ".n3",
            }.get(ctype)

            if ctype in ("text/html", "application/xhtml+xml"):
                return HTMLResponse(
                    f"<p>The URL <code>{escape(url)}</code> returned an HTML page "
                    f"(<code>{escape(ctype)}</code>) instead of RDF. The server does not "
                    f"support content negotiation for this namespace. Try a direct link "
                    f"to the ontology file (e.g. <code>.ttl</code> or <code>.rdf</code>).</p>",
                    status_code=415,
                )

            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    return HTMLResponse(
                        f"<p>The URL response exceeds the "
                        f"{MAX_UPLOAD_SIZE // (1024 * 1024)} MB limit.</p>",
                        status_code=413,
                    )
                chunks.append(chunk)
            content = b"".join(chunks)
    except httpx.HTTPError as exc:
        return HTMLResponse(f"<p>Could not fetch URL: {escape(str(exc))}</p>", status_code=422)

    suffix = ctype_suffix or Path(parsed_url.path).suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    return await _run_validation(tmp_path, url)


async def _validate_upload(file: UploadFile) -> HTMLResponse:
    try:
        content = await _read_upload_capped(file)
    except UploadTooLargeError as exc:
        return HTMLResponse(f"<p>{escape(str(exc))}.</p>", status_code=413)
    suffix = Path(file.filename or "ontology.ttl").suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    return await _run_validation(tmp_path, file.filename or "upload")

async def _run_validation(tmp_path: Path, source_name: str) -> HTMLResponse:
    report = ValidationReport(file=source_name)
    cache = _global_cache
    mermaid = ""

    try:
        parsed = parse_ontology(tmp_path)
    except Exception as exc:
        report.parse_errors.append(str(exc))
        return HTMLResponse(_apply_prefix(render_report(report, mermaid)), status_code=422)
    finally:
        tmp_path.unlink(missing_ok=True)

    mermaid = build_mermaid(parsed.graph, parsed.namespaces)

    # Detect unused prefixes
    used_prefixes = set(parsed.namespaces.keys())
    for pfx, uri in parsed.declared_prefixes.items():
        if pfx not in used_prefixes:
            report.unused_prefixes.append(UnusedPrefix(prefix=pfx, uri=uri))

    # Language tag consistency
    report.lang_tags = check_lang_tags(parsed.graph, parsed.namespaces)

    # Ontology metadata completeness
    report.ontology_metadata = validate_ontology_metadata(parsed.graph)

    # Internal definition documentation
    report.definition_docs = check_definition_documentation(parsed.graph)

    # Internal terms referenced in the ontology's own namespace must be defined
    report.internal_terms = check_internal_terms(parsed.graph)

    # Categorize the ontology's own terms and check naming conventions
    report.term_inventory = check_term_inventory(parsed.graph)

    # Domains and ranges of object and datatype properties
    report.domains_ranges = check_domains_ranges(parsed.graph)

    # Datatypes used across the ontology
    report.datatypes = check_datatypes(parsed.graph)

    # Declared owl:imports targets must actually resolve
    report.imports = await check_imports(parsed.graph, cache)

    # IRI strategy (hash vs slash) for the ontology's own terms
    report.iri_strategy = check_iri_strategy(parsed.graph)

    # IRI scheme consistency (http vs https) per host
    report.iri_scheme = check_iri_scheme(parsed.graph, parsed.namespaces)

    # Reasoner checks (current ontology only; imports are not followed)
    report.reasoner = run_reasoner_checks(parsed.graph)

    # Terms in the ontology's own namespace that are not OWL schema
    report.non_ontology_terms = check_non_ontology_terms(parsed.graph)

    # Only resolve and report namespaces that have subject-position terms
    active_ns = {pfx: uri for pfx, uri in parsed.namespaces.items()
                 if parsed.terms_by_namespace.get(pfx)}
    own_ns = ontology_namespaces(parsed.graph)

    ns_checks = await resolve_all_namespaces(active_ns, cache)
    ns_check_map = {c.uri: c for c in ns_checks}

    for prefix, uri in active_ns.items():
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())
        term_checks = [] if uri in own_ns else validate_terms(prefix, uri, local_names, cache)

        report.namespaces.append(
            NamespaceReport(
                prefix=prefix,
                uri=uri,
                resolution=ns_check,
                terms=term_checks,
            )
        )

    return HTMLResponse(_apply_prefix(render_report(report, mermaid)))


@app.post(
    "/api/validate",
    response_model=ValidationReport,
    summary="Validate an ontology",
    tags=["validation"],
    responses={
        422: {"description": "Parse error  -  the file could not be parsed as RDF"},
        429: {"description": "Too many requests from this client"},
    },
)
async def validate_api(
    request: Request,
    file: UploadFile = File(..., description="OWL ontology file (Turtle, RDF/XML, JSON-LD, N-Triples, or N3)"),
):
    """Upload an OWL ontology and get a full validation report as JSON.

    The report includes:

    - **Namespaces** - each declared prefix is fetched over HTTP and parsed as RDF where possible.
    - **External term definitions** - every term reused from an external vocabulary is looked up in the resolved namespace to confirm it is defined there.
    - **Internal term definitions** - terms in the ontology's own namespace that are referenced but never defined are flagged.
    - **Labels** - SHACL check that internally defined classes and properties carry an `rdfs:label`. Reused external terms are ignored.
    - **Comments** - SHACL check that internally defined classes and properties carry an `rdfs:comment`. Reused external terms are ignored.
    - **Unused prefixes** - prefixes declared with `@prefix` but never used in a triple.
    - **Language-tag consistency** - labels and definitions (`rdfs:label`, `rdfs:comment`, `skos:prefLabel`, `skos:definition`, ...) should use the same language tags across subjects.
    - **Ontology metadata** - SHACL check on the ontology header (title, creator, license, version, ...).
    - **Imports** - every `owl:imports` target declared in the ontology header is fetched over HTTP and parsed as RDF.
    - **IRI strategy** - the ontology's own defined terms should consistently use either hash (`#Term`) or slash (`/Term`), not mix both.
    - **IRI scheme** - each host should be referenced under a single URI scheme (either `http://` or `https://`), never both.
    - **Reasoner checks** - lightweight OWL RL reasoning on the current ontology only (`owl:imports` are not followed), with three facets:
        - *Ontology consistency* - the ontology as a whole has a model.
        - *Inconsistent individuals* - specific named individuals that violate a class restriction (e.g. typed in two `owl:disjointWith` classes).
        - *Unsatisfiable classes* - named classes whose definition forces them to be empty (equivalent to `owl:Nothing`).

    Only terms that appear as subjects in triples are validated against
    remote vocabularies. Terms used only as predicates or objects are
    treated as well-known vocabulary.
    """
    client_ip = request.client.host if request.client else None
    if _rate_limited(client_ip):
        return JSONResponse(
            content={"detail": "Too many requests. Please wait a minute and try again."},
            status_code=429,
        )
    try:
        content = await _read_upload_capped(file)
    except UploadTooLargeError as exc:
        return JSONResponse(content={"detail": str(exc)}, status_code=413)
    suffix = Path(file.filename or "ontology.ttl").suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    report = ValidationReport(file=file.filename or "upload")
    cache = _global_cache
    try:
        parsed = parse_ontology(tmp_path)
    except Exception as exc:
        report.parse_errors.append(str(exc))
        return JSONResponse(content=report.model_dump(mode="json"), status_code=422)
    finally:
        tmp_path.unlink(missing_ok=True)

    active_ns = {pfx: uri for pfx, uri in parsed.namespaces.items()
                 if parsed.terms_by_namespace.get(pfx)}
    own_ns = ontology_namespaces(parsed.graph)

    ns_checks = await resolve_all_namespaces(active_ns, cache)
    ns_check_map = {c.uri: c for c in ns_checks}
    for prefix, uri in active_ns.items():
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())
        term_checks = [] if uri in own_ns else validate_terms(prefix, uri, local_names, cache)
        report.namespaces.append(
            NamespaceReport(prefix=prefix, uri=uri, resolution=ns_check, terms=term_checks)
        )

    used_prefixes = set(parsed.namespaces.keys())
    for pfx, uri in parsed.declared_prefixes.items():
        if pfx not in used_prefixes:
            report.unused_prefixes.append(UnusedPrefix(prefix=pfx, uri=uri))

    report.lang_tags = check_lang_tags(parsed.graph, parsed.namespaces)
    report.ontology_metadata = validate_ontology_metadata(parsed.graph)
    report.definition_docs = check_definition_documentation(parsed.graph)
    report.internal_terms = check_internal_terms(parsed.graph)
    report.term_inventory = check_term_inventory(parsed.graph)
    report.domains_ranges = check_domains_ranges(parsed.graph)
    report.datatypes = check_datatypes(parsed.graph)
    report.imports = await check_imports(parsed.graph, cache)
    report.iri_strategy = check_iri_strategy(parsed.graph)
    report.iri_scheme = check_iri_scheme(parsed.graph, parsed.namespaces)
    report.reasoner = run_reasoner_checks(parsed.graph)
    report.non_ontology_terms = check_non_ontology_terms(parsed.graph)

    return report.model_dump(mode="json")

