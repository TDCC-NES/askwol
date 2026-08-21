"""FastAPI web application for the askwol ontology checker."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import os
import sys
import tempfile
import threading
import time
import uuid
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from askwol import usage
from askwol.models import ValidationReport
from askwol.report_html import render_report
from askwol.resolver import block_private_network_requests
from askwol.templates import GUIDE_HTML, UPLOAD_HTML, render_checks_api_description

# ASKWOL_ROOT_PATH is the reverse-proxy sub-path prefix (e.g. /askwol); empty
# for a root deployment.
ROOT_PATH = os.environ.get("ASKWOL_ROOT_PATH", "").rstrip("/")

# Generous cap for ontology uploads - real Turtle, RDF/XML, or JSON-LD files
# are almost always a few MB at most. Bounds memory and disk use against
# oversized or abusive uploads.
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

# "All events" is kept short so paging never has to scroll far back up to
# the top of the table (the other two /stats tables stay at 25/page).
EVENTS_PAGE_SIZE = 15
AGG_PAGE_SIZE = 25

# Per-IP throttle for the two validation endpoints, since each request can
# trigger many outbound HTTP fetches (namespaces, imports). In-memory only, so
# it resets on restart and is tracked per worker process - fine for abuse
# mitigation, not a strict global limit. Set ASKWOL_RATE_LIMIT=0 to disable.
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("ASKWOL_RATE_LIMIT", "20"))

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: dict[str, tuple[float, int]] = {}


def _is_trusted_proxy_peer(peer_ip: str | None) -> bool:
    """True if peer_ip is loopback, private, or link-local - i.e. could
    plausibly be our own reverse proxy rather than an arbitrary internet
    host. Only such peers are trusted to supply an accurate
    X-Forwarded-For header; anyone else could set that header to anything."""
    if not peer_ip:
        return False
    try:
        ip = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _client_ip(request: Request) -> str | None:
    """Best-effort real client IP, for usage tracking and rate limiting.

    `request.client.host` is the direct TCP peer. Behind the reverse proxy
    documented in docker-compose.yml, that peer is always the proxy itself
    (or the Docker gateway) - the same value for every visitor, which is
    why every event ends up with the same ip_hash on the stats page. When
    the peer is trusted (private or loopback), prefer the address the proxy
    appended to X-Forwarded-For: the rightmost entry is the one our own
    proxy added, while anything to its left could be forged by the
    original client and is ignored.
    """
    peer_ip = request.client.host if request.client else None
    if _is_trusted_proxy_peer(peer_ip):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",")[-1].strip()
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                candidate = ""
            if candidate:
                return candidate
    return peer_ip


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


# Isolated validation. Each job parses and checks the ontology in its own OS
# process (validate_worker.py), never inline in this event loop, so a slow
# or hung ontology can be killed outright without blocking /health or any
# other concurrent request. Both /validate and /api/validate call
# run_isolated_validation() below - the one place this is implemented.
VALIDATION_TIMEOUT = float(os.environ.get("ASKWOL_VALIDATION_TIMEOUT", "300"))
MAX_CONCURRENT_VALIDATIONS = int(os.environ.get("ASKWOL_MAX_CONCURRENT_VALIDATIONS", "2"))

# The command used to spawn the worker, as a plain module-level list rather
# than hardcoded inline, so tests can monkeypatch it to a small fake process
# to exercise timeout/kill/concurrency behaviour without a real slow ontology.
WORKER_CMD: list[str] = [sys.executable, "-m", "askwol.validate_worker"]

_validation_slots_lock = asyncio.Lock()
_validation_slots_in_use = 0

_OWL_BUSY_MESSAGE = "Wol is busy validating other ontologies right now. Please try again in a few minutes."
_OWL_TIMEOUT_MESSAGE = "This ontology took too long to validate. Please try a smaller file, or try again later."
_OWL_ERROR_MESSAGE = "Something went wrong while validating this ontology. Please try again."


def _owl_message_html(message: str) -> str:
    """A small, friendly owl-branded message for the 503/504 HTML responses."""
    return (
        '<div style="text-align:center;padding:48px 20px;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;\">"
        '<div style="font-size:3.5rem;line-height:1;" aria-hidden="true">🦉</div>'
        f'<p style="font-size:1.15rem;color:#3d6a4a;margin:18px 0 0;font-weight:600;">{escape(message)}</p>'
        "</div>"
    )


class ValidationBusyError(Exception):
    """Raised when the global concurrent-validation limit is reached."""


class ValidationTimeoutError(Exception):
    """Raised when a validation job exceeds VALIDATION_TIMEOUT."""


async def _try_acquire_validation_slot() -> bool:
    global _validation_slots_in_use
    async with _validation_slots_lock:
        if _validation_slots_in_use >= MAX_CONCURRENT_VALIDATIONS:
            return False
        _validation_slots_in_use += 1
        return True


async def _release_validation_slot() -> None:
    global _validation_slots_in_use
    async with _validation_slots_lock:
        _validation_slots_in_use = max(0, _validation_slots_in_use - 1)


async def _drain_phase_updates(request_id: str, stream: asyncio.StreamReader) -> None:
    """Read phase-update lines from the worker's stderr as it runs, logging
    each one so a job that never finishes still shows its last known phase."""
    async for raw_line in stream:
        try:
            data = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        phase = data.get("phase")
        if phase:
            usage.job_phase(request_id, phase)


async def run_isolated_validation(
    tmp_path: Path,
    display_name: str,
    *,
    kind: str,
    base_uri: str | None = None,
) -> tuple[ValidationReport, str]:
    """Validate one ontology file in an isolated child process.

    Shared by /validate and /api/validate so both get identical protection:
    a global concurrency limit (raises ValidationBusyError past it) and a
    hard wall-clock timeout that kills the child process outright (raises
    ValidationTimeoutError). Any other unexpected failure is turned into a
    plain error result rather than propagating, so a bug in one job can
    never take down the request. Job start, phase, and outcome are logged
    via askwol.usage so a job that never finishes can still be identified.
    """
    request_id = uuid.uuid4().hex[:12]
    usage.job_started(request_id, kind=kind, source=display_name)

    if _TEST_INPROCESS_PIPELINE is not None:
        return await _TEST_INPROCESS_PIPELINE(tmp_path, display_name=display_name, base_uri=base_uri)

    if not await _try_acquire_validation_slot():
        usage.job_finished(request_id, outcome="rejected", status="503", duration_ms=0)
        raise ValidationBusyError()

    started = time.perf_counter()

    def _fail(outcome: str, status: str) -> tuple[ValidationReport, str]:
        usage.job_finished(
            request_id, outcome=outcome, status=status,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        failed_report = ValidationReport(file=display_name)
        failed_report.parse_errors.append(_OWL_ERROR_MESSAGE)
        return failed_report, ""

    try:
        cmd = [*WORKER_CMD, str(tmp_path), "--display-name", display_name]
        if base_uri:
            cmd += ["--base-uri", base_uri]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None and proc.stderr is not None
        stdout_task = asyncio.create_task(proc.stdout.read())
        phase_task = asyncio.create_task(_drain_phase_updates(request_id, proc.stderr))
        wait_task = asyncio.create_task(proc.wait())

        try:
            await asyncio.wait_for(asyncio.gather(stdout_task, phase_task, wait_task), timeout=VALIDATION_TIMEOUT)
        except asyncio.TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            for task in (stdout_task, phase_task, wait_task):
                task.cancel()
            usage.job_finished(
                request_id, outcome="timeout", status="504",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise ValidationTimeoutError() from None

        if proc.returncode != 0:
            report, mermaid = _fail("error", "500")
            return report, mermaid

        stdout = stdout_task.result()
        payload = json.loads(stdout)
        report = ValidationReport.model_validate(payload["report"])
        mermaid = payload.get("mermaid", "")
    except ValidationTimeoutError:
        raise
    except Exception:
        report, mermaid = _fail("error", "500")
        return report, mermaid
    finally:
        await _release_validation_slot()

    duration_ms = int((time.perf_counter() - started) * 1000)
    if report.parse_errors:
        usage.job_finished(request_id, outcome="error", status="422", duration_ms=duration_ms)
    else:
        usage.job_finished(request_id, outcome="ok", status="200", duration_ms=duration_ms)
    return report, mermaid


app = FastAPI(
    title="askwol",
    description=(
        "Validate OWL ontologies: namespace resolution, external term "
        "definitions (existence in remote vocabularies), internal term "
        "definitions (own-namespace terms are defined), label "
        "and comment documentation (SHACL), ontology metadata (SHACL), "
        "open licence conformance (Open Definition), language-tag "
        "consistency, unused prefix declarations, owl:imports "
        "resolution, IRI strategy consistency (hash vs slash), IRI scheme "
        "consistency (http vs https), term naming and inventory, domain and "
        "range declarations, recognised datatypes, non-ontology terms, and "
        "lightweight OWL RL reasoner checks (ontology consistency, "
        "inconsistent individuals, and unsatisfiable classes)."
    ),
    version="0.1.0",
    root_path=ROOT_PATH,
)


@app.middleware("http")
async def _add_openapi_robots_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == app.openapi_url:
        response.headers["X-Robots-Tag"] = "noindex"
    return response


# Test-only hook: when set, run_isolated_validation calls this directly
# in-process instead of spawning a worker subprocess, bypassing all
# isolation machinery. Namespace/import resolution normally happens inside
# a separate process, which can no longer be stubbed via an in-process cache
# shared with the test - the test suite uses this hook instead, so report-
# content tests keep working exactly as before. Left unset (None) in
# production; askwol.pipeline.run_full_validation is called directly.
_TEST_INPROCESS_PIPELINE = None


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
    the max, then the max itself (every displayed count is >= 1)."""
    ticks = {1, max_value}
    power = 10
    while power < max_value:
        ticks.add(power)
        power *= 10
    return sorted(ticks)


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


def _render_stats_page(data: dict[str, object]) -> str:
    total_events = int(data.get("total_events") or 0)
    unique_visitors = int(data.get("unique_visitors") or 0)
    avg_duration = data.get("avg_duration_ms")
    days = int(data.get("days") or 30)
    token = data.get("token") or None

    by_day = list(data.get("by_day") or [])
    by_status = list(data.get("by_status") or [])
    top_sources = list(data.get("top_sources") or [])
    all_events = list(data.get("all_events") or [])

    page = int(data.get("page") or 1)
    page_size = int(data.get("page_size") or 25)
    total_entries = int(data.get("total_entries") or 0)

    status_page = int(data.get("status_page") or 1)
    status_page_size = int(data.get("status_page_size") or 25)
    status_total = int(data.get("status_total") or 0)

    source_page = int(data.get("source_page") or 1)
    source_page_size = int(data.get("source_page_size") or 25)
    source_total = int(data.get("source_total") or 0)

    max_day = max((int(row["n"]) for row in by_day), default=0)
    max_status = int(data.get("status_max") or 0)
    max_source = int(data.get("source_max") or 0)

    day_html = _render_day_chart(by_day, max_day)

    status_rows = []
    for row in by_status:
        count = int(row["n"])
        status_rows.append(
            "<tr>"
            f"<td>{_status_badge(row['status'])}</td>"
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
            f"<td class=\"source\">{_source_link(row['source'])}</td>"
            f"<td class=\"num\">{_format_int(count)}</td>"
            f"<td><span class=\"mini-bar\"><span style=\"width:{_stats_bar(count, max_source)}\"></span></span></td>"
            "</tr>"
        )
    source_html = "".join(source_rows) or '<tr><td colspan="3" class="empty-cell">No sources yet.</td></tr>'

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
            f"<td>{escape(_format_duration(row.get('duration_ms')))}</td>"
            f"<td class=\"source\">{_source_link(row['source'])}</td>"
            "</tr>"
        )
    all_html = "".join(all_rows) or '<tr><td colspan="6" class="empty-cell">No database entries yet.</td></tr>'

    events_pagination = _render_pagination(
        page=page, page_size=page_size, total=total_entries, shown=len(all_events),
        param="page", other_pages={"source_page": source_page, "status_page": status_page},
        token=token, anchor="all-events", prev_label="&larr; Newer", next_label="Older &rarr;",
        first_label="&laquo; Newest", last_label="Oldest &raquo;",
    )
    source_pagination = _render_pagination(
        page=source_page, page_size=source_page_size, total=source_total, shown=len(top_sources),
        param="source_page", other_pages={"page": page, "status_page": status_page},
        token=token, anchor="top-sources", compact=True,
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
    .ranked-table .status-col {{ width: 100px; }}
    .ranked-table .num {{ width: 78px; }}
    .ranked-table .share-col {{ width: 70px; }}
    .hint {{ color: var(--muted); font-size: 0.9em; }}
    .status-badge {{ display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; font-weight: 700; font-size: 0.85em; white-space: nowrap; }}
    .status-ok {{ background: #e3f3e9; color: #1f7a4d; }}
    .status-warn {{ background: #fdf0dc; color: #9a5b12; }}
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
            <span class="brand"><span class="brand-mark" aria-hidden="true">🦉</span> Ask Wol usage</span>
            <a href="./">Home</a>
            <a href="guide">Publishing guide</a>
            <a href="docs">API docs</a>
        </div>
        <div class="hero">
            <span class="kicker">Internal dashboard</span>
            <h1>Ask Wol usage dashboard</h1>
            <p class="lede">Read-only validation activity for the last {days} days.</p>
        </div>
        <div class="grid">
            <section class="card summary" aria-label="Usage summary">
                <div class="metric"><div class="label">Events</div><div class="value">{_format_int(total_events)}</div></div>
                <div class="metric"><div class="label">Unique visitors</div><div class="value">{_format_int(unique_visitors)}</div></div>
                <div class="metric"><div class="label">Average duration</div><div class="value">{escape(_format_duration(int(avg_duration) if avg_duration is not None else None))}</div></div>
            </section>

            <section class="card panel" style="grid-column: span 12;">
                <h2>Events by day</h2>
                {day_html}
            </section>

            <section class="card panel" id="all-events" style="grid-column: span 12;">
                <h2>All events</h2>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Timestamp</th><th>Visitor</th><th>Kind</th><th>Status</th><th>Duration</th><th>Source</th></tr></thead>
                        <tbody>{all_html}</tbody>
                    </table>
                </div>
                {events_pagination}
            </section>

            <section class="card panel" id="top-sources" style="grid-column: span 6;">
                <h2>Top sources <span class="hint">(all time)</span></h2>
                <div class="table-wrap">
                    <table class="ranked-table">
                        <thead><tr><th>Source</th><th class="num">Events</th><th class="share-col">Share</th></tr></thead>
                        <tbody>{source_html}</tbody>
                    </table>
                </div>
                {source_pagination}
            </section>

            <section class="card panel" id="by-status" style="grid-column: span 6;">
                <h2>By status <span class="hint">(all time)</span></h2>
                <div class="table-wrap">
                    <table class="ranked-table">
                        <thead><tr><th class="status-col">Status</th><th>Notes</th><th class="num">Events</th><th class="share-col">Share</th></tr></thead>
                        <tbody>{status_html}</tbody>
                    </table>
                </div>
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
async def stats_page(
    request: Request,
    token: str | None = None,
    page: int = 1,
    source_page: int = 1,
    status_page: int = 1,
):
    """Internal usage dashboard. Requires ASKWOL_STATS_TOKEN env var to match `?token=`."""
    expected = usage.stats_token()
    if not expected:
        return HTMLResponse(
            "<p>stats disabled - set ASKWOL_STATS_TOKEN to enable the usage dashboard.</p>",
            status_code=503,
        )
    if token != expected and not _is_local_request(request):
        return HTMLResponse("<p>unauthorised</p>", status_code=401)

    page = max(1, page)
    source_page = max(1, source_page)
    status_page = max(1, status_page)
    data = usage.stats(
        days=30,
        source_page=source_page,
        source_page_size=AGG_PAGE_SIZE,
        status_page=status_page,
        status_page_size=AGG_PAGE_SIZE,
    )
    data["total_entries"] = usage.events_count()
    data["all_events"] = usage.all_events(limit=EVENTS_PAGE_SIZE, offset=(page - 1) * EVENTS_PAGE_SIZE)
    data["page"] = page
    data["page_size"] = EVENTS_PAGE_SIZE
    data["token"] = token
    return HTMLResponse(_render_stats_page(data))


@app.get("/api/stats", include_in_schema=False)
async def stats_endpoint(
    request: Request,
    token: str | None = None,
    page: int = 1,
    source_page: int = 1,
    status_page: int = 1,
):
    """Internal usage data. Requires ASKWOL_STATS_TOKEN env var to match `?token=`."""
    expected = usage.stats_token()
    if not expected:
        return JSONResponse(
            {"error": "stats disabled - set ASKWOL_STATS_TOKEN to enable"},
            status_code=503,
        )
    if token != expected and not _is_local_request(request):
        return JSONResponse({"error": "unauthorised"}, status_code=401)
    page = max(1, page)
    source_page = max(1, source_page)
    status_page = max(1, status_page)
    payload = usage.stats(
        days=30,
        source_page=source_page,
        source_page_size=AGG_PAGE_SIZE,
        status_page=status_page,
        status_page_size=AGG_PAGE_SIZE,
    )
    payload["total_entries"] = usage.events_count()
    payload["page"] = page
    payload["page_size"] = EVENTS_PAGE_SIZE
    payload["all_events"] = usage.all_events(limit=EVENTS_PAGE_SIZE, offset=(page - 1) * EVENTS_PAGE_SIZE)
    return JSONResponse(payload)


@app.get("/guide", response_class=HTMLResponse, include_in_schema=False)
async def guide():
    return HTMLResponse(_apply_prefix(GUIDE_HTML))

@app.get("/validate", include_in_schema=False)
async def validate_get(request: Request, url: str | None = None):
    """Bookmarkable/shareable form of URL-based validation. `POST /validate`
    redirects here (Post/Redirect/Get) when given a URL, so the address bar
    ends up on a link that reproduces the same result for anyone it's shared
    with. Bare GETs with no `url` (e.g. an old bookmark) just go to the form."""
    if not url or not url.strip():
        return RedirectResponse(url="./", status_code=303)

    source = url.strip()
    started = time.perf_counter()
    client_ip = _client_ip(request)

    if _rate_limited(client_ip):
        response = HTMLResponse(
            "<p>Too many requests. Please wait a minute and try again.</p>",
            status_code=429,
        )
    else:
        response = await _validate_url(source)

    usage.record(
        "validate",
        source=source,
        status=str(response.status_code),
        duration_ms=int((time.perf_counter() - started) * 1000),
        ip=client_ip,
    )
    # Shared links must always re-validate rather than serve a stale copy,
    # and shouldn't accumulate in search engines as if they were content pages.
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@app.post("/validate", include_in_schema=False)
async def validate(
    request: Request,
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
):
    """Validate an uploaded file directly, or (Post/Redirect/Get) redirect a
    submitted URL to its own GET /validate?url=... link - see validate_get."""
    if url and url.strip():
        query = urlencode({"url": url.strip()})
        return RedirectResponse(url=f"validate?{query}", status_code=303)

    started = time.perf_counter()
    client_ip = _client_ip(request)
    source: str | None = None
    kind = "validate"

    if _rate_limited(client_ip):
        source = "(rate limited)"
        response = HTMLResponse(
            "<p>Too many requests. Please wait a minute and try again.</p>",
            status_code=429,
        )
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


# Recognised ontology file extensions. Used only as a narrow escape hatch for
# generic or absent Content-Type responses (see _validate_url below) - never
# as the primary signal for what counts as RDF.
RDF_FILE_EXTENSIONS = frozenset({".ttl", ".rdf", ".owl", ".rdfs", ".jsonld", ".nt", ".n3", ".xml"})



async def _validate_url(url: str) -> HTMLResponse:
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        return HTMLResponse("<p>Only http and https URLs are supported.</p>", status_code=400)

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
                # raw.githubusercontent.com) serve Turtle or RDF as text/plain, so we
                # fall back to the URL path extension instead of assuming N-Triples.
                "text/n3": ".n3",
            }.get(ctype)

            # This is direct user input ("validate this URL as my ontology"), so be
            # strict about what counts as RDF: trust a recognised media type above,
            # or a generic or absent Content-Type whose URL path ends in a known
            # ontology file extension (the raw.githubusercontent.com case). Anything
            # else is rejected outright rather than optimistically parsed - some
            # servers redirect namespace URIs to catalogue/metadata endpoints that
            # return non-standard content types (e.g. "text/anot+turtle") which are
            # syntactically valid RDF but aren't the ontology itself.
            path_suffix = Path(parsed_url.path).suffix
            trusted_by_extension = (
                ctype in ("text/plain", "") and path_suffix.lower() in RDF_FILE_EXTENSIONS
            )
            if ctype_suffix is None and not trusted_by_extension:
                if ctype in ("text/html", "application/xhtml+xml"):
                    return HTMLResponse(
                        f"<p>The URL <code>{escape(url)}</code> returned an HTML page "
                        f"(<code>{escape(ctype)}</code>) instead of RDF. The server does not "
                        f"support content negotiation for this namespace. Try a direct link "
                        f"to the ontology file (e.g. <code>.ttl</code> or <code>.rdf</code>).</p>",
                        status_code=415,
                    )
                return HTMLResponse(
                    f"<p>The URL <code>{escape(url)}</code> returned "
                    f"<code>{escape(ctype or '(no content-type)')}</code>, which isn't a "
                    f"recognised RDF format. Try a direct link to the ontology file "
                    f"(e.g. <code>.ttl</code> or <code>.rdf</code>).</p>",
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
            final_url = str(resp.url)
    except httpx.HTTPError as exc:
        return HTMLResponse(f"<p>Could not fetch URL: {escape(str(exc))}</p>", status_code=422)

    suffix = ctype_suffix or path_suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    return await _run_validation(tmp_path, url, base_uri=final_url)


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

async def _run_validation(tmp_path: Path, source_name: str, base_uri: str | None = None) -> HTMLResponse:
    try:
        try:
            report, mermaid = await run_isolated_validation(
                tmp_path, source_name, kind="validate", base_uri=base_uri,
            )
        except ValidationBusyError:
            return HTMLResponse(_apply_prefix(_owl_message_html(_OWL_BUSY_MESSAGE)), status_code=503)
        except ValidationTimeoutError:
            return HTMLResponse(_apply_prefix(_owl_message_html(_OWL_TIMEOUT_MESSAGE)), status_code=504)
    finally:
        tmp_path.unlink(missing_ok=True)

    status_code = 422 if report.parse_errors else 200
    return HTMLResponse(_apply_prefix(render_report(report, mermaid)), status_code=status_code)


@app.post(
    "/api/validate",
    response_model=ValidationReport,
    summary="Validate an ontology",
    description=render_checks_api_description(),
    tags=["validation"],
    responses={
        422: {"description": "Parse error  -  the file could not be parsed as RDF"},
        429: {"description": "Too many requests from this client"},
        503: {"description": "Too many concurrent validations, try again shortly"},
        504: {"description": "This ontology took too long to validate"},
    },
)
async def validate_api(
    request: Request,
    file: UploadFile = File(..., description="OWL ontology file (Turtle, RDF/XML, JSON-LD, N-Triples, or N3)"),
):
    """Upload an OWL ontology and get a full validation report as JSON.

    See the route description for the full list of checks (single-sourced
    from askwol.templates.CHECKS). Uses the same isolated validation runner
    as the HTML /validate route.
    """
    started = time.perf_counter()
    client_ip = _client_ip(request)
    source = file.filename or "upload"

    if _rate_limited(client_ip):
        response = JSONResponse(
            content={"detail": "Too many requests. Please wait a minute and try again."},
            status_code=429,
        )
    else:
        try:
            content = await _read_upload_capped(file)
        except UploadTooLargeError as exc:
            response = JSONResponse(content={"detail": str(exc)}, status_code=413)
        else:
            suffix = Path(file.filename or "ontology.ttl").suffix or ".ttl"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            try:
                try:
                    report, _mermaid = await run_isolated_validation(tmp_path, source, kind="validate_api")
                    status_code = 422 if report.parse_errors else 200
                    response = JSONResponse(content=report.model_dump(mode="json"), status_code=status_code)
                except ValidationBusyError:
                    response = JSONResponse(content={"detail": _OWL_BUSY_MESSAGE}, status_code=503)
                except ValidationTimeoutError:
                    response = JSONResponse(content={"detail": _OWL_TIMEOUT_MESSAGE}, status_code=504)
            finally:
                tmp_path.unlink(missing_ok=True)

    usage.record(
        "validate_api", source=source, status=str(response.status_code),
        duration_ms=int((time.perf_counter() - started) * 1000), ip=client_ip,
    )
    return response

