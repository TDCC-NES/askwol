"""FastAPI web application for the askwol ontology checker."""

from __future__ import annotations

import ipaddress
import os
import tempfile
import threading
import time
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit

import httpx
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from starlette.datastructures import MutableHeaders
from starlette.requests import ClientDisconnect
from starlette.staticfiles import StaticFiles

from askwol import progress, usage
from askwol.agent_api import (
    ApiError,
    ApiValidationError,
    CompactValidationReport,
    OntologyContent,
    compact_report,
)
from askwol.branding import STATIC_DIR
from askwol.checks import render_checks_api_description
from askwol.models import ValidationReport
from askwol.report_html import render_report
from askwol.resolver import block_private_network_requests
from askwol.stats_web import create_stats_router
from askwol.templates import GUIDE_HTML, UPLOAD_HTML
from askwol.validation_runner import (
    BUSY_MESSAGE,
    ERROR_MESSAGE,
    TIMEOUT_MESSAGE,
    ClientDisconnectedError,
    ValidationBusyError,
    ValidationExecutionError,
    ValidationTimeoutError,
    run_isolated_validation,
)
from askwol.validation_runner import (
    unless_client_disconnects as _unless_client_disconnects,
)
from askwol.web_utils import apply_prefix

# ASKWOL_ROOT_PATH is the reverse-proxy sub-path prefix (e.g. /askwol); empty
# for a root deployment.
ROOT_PATH = os.environ.get("ASKWOL_ROOT_PATH", "").rstrip("/")

# Generous cap for ontology uploads - real Turtle, RDF/XML, or JSON-LD files
# are almost always a few MB at most. Bounds memory and disk use against
# oversized or abusive uploads.
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

# Shared per-IP throttle for validation, since each request can
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


def _owl_message_html(message: str) -> str:
    """Render a validation failure message."""
    return (
        '<div style="text-align:center;padding:48px 20px;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;\">"
        f'<p style="font-size:1.15rem;color:#3d6a4a;margin:18px 0 0;font-weight:600;">{escape(message)}</p>'
        "</div>"
    )


app = FastAPI(
    title="askwol",
    description=(
        "Validate OWL ontologies: namespace resolution, external term "
        "definitions (existence in remote vocabularies), internal term "
        "definitions (own-namespace terms are defined), label "
        "and comment documentation (SHACL), ontology metadata (SHACL), "
        "ontology-header licence recognition, language-tag "
        "consistency, unused prefix declarations, owl:imports "
        "resolution, IRI strategy consistency (hash vs slash), IRI scheme "
        "consistency (http vs https), term naming and inventory, domain and "
        "range declarations, recognised datatypes, non-ontology terms, and "
        "selected OWL RL/RDF checks for contradictory class memberships of named individuals "
        "and unsatisfiable internal classes. Imports are excluded from reasoning."
    ),
    version="0.2.0",
    root_path=ROOT_PATH,
)


class _NoindexOpenapiMiddleware:
    """Adds ``X-Robots-Tag: noindex`` to the OpenAPI JSON.

    A plain ASGI middleware on purpose, not ``@app.middleware("http")``:
    Starlette's BaseHTTPMiddleware hides the client's disconnect from
    ``request.is_disconnected()``, which the validation routes rely on to stop
    work that nobody is waiting for any more (see _unless_client_disconnects).
    """

    def __init__(self, asgi_app):
        self.app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        if path != app.openapi_url:
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Robots-Tag"] = "noindex"
            await send(message)

        await self.app(scope, receive, send_with_header)


app.add_middleware(_NoindexOpenapiMiddleware)


class _CachedStaticFiles(StaticFiles):
    """Static files that browsers may keep for a week; the brand images rarely change."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=604800"
        return response


app.mount("/static", _CachedStaticFiles(directory=STATIC_DIR), name="static")
app.include_router(create_stats_router(lambda: ROOT_PATH))


def _apply_prefix(html: str) -> str:
    return apply_prefix(html, ROOT_PATH)


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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    return HTMLResponse(_apply_prefix(UPLOAD_HTML))


@app.get("/health", summary="Health check", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/guide", response_class=HTMLResponse, include_in_schema=False)
async def guide():
    return HTMLResponse(_apply_prefix(GUIDE_HTML))


def _abandoned_response() -> Response:
    """Stand-in for the response of a request whose client has gone (499 is
    nginx's "client closed request"). There is nobody to deliver it to, and the
    request is deliberately not recorded as usage: the user never saw a result."""
    return Response(status_code=499)


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
        try:
            with progress.track(client_ip, source, steps=progress.URL_FLOW):
                response = await _unless_client_disconnects(request, _validate_url(source))
        except ClientDisconnectedError:
            return _abandoned_response()

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
        try:
            with progress.track(client_ip, source, steps=progress.UPLOAD_FLOW):
                response = await _unless_client_disconnects(request, _validate_upload(file))
        except ClientDisconnectedError:
            return _abandoned_response()
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


@app.get("/validate/progress", include_in_schema=False)
async def validate_progress(request: Request, source: str = ""):
    """Current step of the caller's own running validation of `source`, polled
    by the form page while its /validate request is pending. Deliberately not
    rate limited (a poll per second per waiting user) and read-only: it only
    looks up this client's job in memory."""
    return JSONResponse(
        progress.snapshot(_client_ip(request), source),
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


# Recognised ontology file extensions. Used only as a narrow escape hatch for
# generic or absent Content-Type responses (see _validate_url below) - never
# as the primary signal for what counts as RDF.
RDF_FILE_EXTENSIONS = frozenset({".ttl", ".rdf", ".owl", ".rdfs", ".jsonld", ".nt", ".n3", ".xml"})


def _github_raw_url(url: str) -> str | None:
    """Let GitHub resolve the unchanged ref/path, including slash-containing refs."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "github.com":
        return None
    parts = parsed.path.split("/", 4)
    if (
        len(parts) != 5 or not parts[1] or not parts[2] or parts[3] != "blob"
        or "/" not in parts[4] or parts[4].startswith("/") or parts[4].endswith("/")
    ):
        return None
    # The /raw/ route uses the same ref/path as /blob/. Strip viewer query
    # parameters and line fragments, without decoding the file path.
    return f"https://github.com/{parts[1]}/{parts[2]}/raw/{parts[4]}"


def _github_url_guidance(url: str, raw_url: str) -> HTMLResponse:
    """Explain the correction in the existing, editable URL form."""
    notice = (
        '<div class="github-guidance" role="note" aria-labelledby="github-url-title">'
        '<h2 id="github-url-title">Use GitHub\u2019s raw file</h2>'
        '<p>This GitHub link opens an HTML file viewer. Ontology tools need the raw '
        'file contents.</p>'
        f'<p><a id="github-raw-url" href="{escape(raw_url)}" target="_blank" rel="noopener"><code>{escape(raw_url)}</code></a></p>'
        '<button type="button" class="chip" id="copy-raw-url">Copy raw URL</button>'
        ' <span id="copy-raw-status" class="input-help" role="status"></span>'
        '<p>Copy this raw URL, paste it into the <strong>Ontology URL</strong> box below, '
        'then click <strong>Ask Wol</strong>. '
        '<a href="guide#server-config">Learn more about ontology URLs</a>.</p>'
        '</div>'
    )
    html = UPLOAD_HTML.replace('<!-- github-url-guidance -->', notice).replace(
        'id="url-input" name="url"', f'id="url-input" name="url" value="{escape(url)}"',
    )
    html = html.replace('</body>', '''<script>
document.getElementById('copy-raw-url').addEventListener('click', async function() {
  const link = document.getElementById('github-raw-url');
  const status = document.getElementById('copy-raw-status');
  try {
    await navigator.clipboard.writeText(link.textContent);
    status.textContent = 'Raw URL copied';
  } catch {
    status.textContent = 'Copy unavailable. Select and copy the raw URL above.';
  }
});
</script></body>''')
    return HTMLResponse(_apply_prefix(html), status_code=415)


async def _validate_url(url: str) -> HTMLResponse:
    raw_url = _github_raw_url(url)
    if raw_url:
        return _github_url_guidance(url, raw_url)
    parsed_url = urlsplit(url)
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
            path_suffix = Path(unquote(parsed_url.path)).suffix
            trusted_by_extension = (
                ctype in ("text/plain", "") and path_suffix.lower() in RDF_FILE_EXTENSIONS
            )
            if ctype_suffix is None and not trusted_by_extension:
                if ctype in ("text/html", "application/xhtml+xml"):
                    return HTMLResponse(
                        f"<p>The URL <code>{escape(url)}</code> returned an HTML page "
                        f"(<code>{escape(ctype)}</code>) instead of RDF. Try a direct link "
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
            return HTMLResponse(_apply_prefix(_owl_message_html(BUSY_MESSAGE)), status_code=503)
        except ValidationTimeoutError:
            return HTMLResponse(_apply_prefix(_owl_message_html(TIMEOUT_MESSAGE)), status_code=504)
        except ValidationExecutionError:
            return HTMLResponse(_owl_message_html(ERROR_MESSAGE), status_code=500)
    finally:
        tmp_path.unlink(missing_ok=True)

    status_code = 422 if report.parse_errors else 200
    return HTMLResponse(_apply_prefix(render_report(report, mermaid)), status_code=status_code)


_API_REPORT = ValidationReport | CompactValidationReport
_API_RESPONSES = {
    200: {"description": "Validation completed; inspect findings and check coverage"},
    422: {
        "model": _API_REPORT | ApiValidationError,
        "description": "RDF parse-error report, or invalid request with a detail list",
    },
    413: {"model": ApiError, "description": "Ontology file or JSON request exceeds the 20 MB size limit"},
    429: {"model": ApiError, "description": "Too many requests from this client"},
    503: {"model": ApiError, "description": "Too many concurrent validations; retry later"},
    504: {"model": ApiError, "description": "Validation exceeded its time limit"},
    500: {"model": ApiError, "description": "The validation worker failed"},
}
_COMPACT_QUERY = Query(
    False, description="Return findings, counts and execution coverage without detailed term inventories.",
)
_RATE_LIMIT_MESSAGE = "Too many requests. Please wait a minute and try again."


async def _api_validation_response(
    request: Request, content: bytes, source: str, suffix: str,
    *, compact: bool, base_uri: str | None = None,
) -> Response:
    """Both API inputs share isolation, cleanup and report selection."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        try:
            report, _mermaid = await _unless_client_disconnects(
                request, run_isolated_validation(tmp_path, source, kind="validate_api", base_uri=base_uri),
            )
            result = compact_report(report) if compact else report
            return JSONResponse(result.model_dump(mode="json"), status_code=422 if report.parse_errors else 200)
        except ValidationBusyError:
            return JSONResponse({"detail": BUSY_MESSAGE}, status_code=503)
        except ValidationTimeoutError:
            return JSONResponse({"detail": TIMEOUT_MESSAGE}, status_code=504)
        except ValidationExecutionError:
            return JSONResponse({"detail": ERROR_MESSAGE}, status_code=500)
        except ClientDisconnectedError:
            return _abandoned_response()
    finally:
        tmp_path.unlink(missing_ok=True)


def _record_api_response(response: Response, source: str, started: float, client_ip: str | None) -> Response:
    if response.status_code != 499:
        usage.record(
            "validate_api", source=source, status=str(response.status_code),
            duration_ms=int((time.perf_counter() - started) * 1000), ip=client_ip,
        )
    return response


@app.post(
    "/api/validate",
    response_model=_API_REPORT,
    summary="Validate an ontology file",
    description=render_checks_api_description(),
    tags=["validation"],
    responses={**_API_RESPONSES, 400: {"model": ApiError, "description": "Malformed multipart upload"}},
)
async def validate_api(
    request: Request,
    file: UploadFile = File(..., description="OWL ontology file (Turtle, RDF/XML, JSON-LD, N-Triples, or N3)"),
    compact: bool = _COMPACT_QUERY,
):
    """Validate a file through the same isolated runner as the HTML tool."""
    started = time.perf_counter()
    client_ip = _client_ip(request)
    source = file.filename or "upload"
    if _rate_limited(client_ip):
        response = JSONResponse({"detail": _RATE_LIMIT_MESSAGE}, status_code=429)
    else:
        try:
            content = await _read_upload_capped(file)
        except UploadTooLargeError as exc:
            response = JSONResponse({"detail": str(exc)}, status_code=413)
        else:
            suffix = Path(file.filename or "ontology.ttl").suffix or ".ttl"
            response = await _api_validation_response(request, content, source, suffix, compact=compact)
    return _record_api_response(response, source, started, client_ip)


async def _read_content_capped(request: Request) -> bytes:
    """Bound the complete JSON envelope before decoding or parsing it."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise UploadTooLargeError(f"Request exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB size limit")
        chunks.append(chunk)
    return b"".join(chunks)


@app.post(
    "/api/validate/content",
    response_model=_API_REPORT,
    summary="Validate ontology content in a JSON request",
    description=(
        "Send JSON-LD directly as the `content` object or array, or send RDF source text "
        "with an explicit `format`. Optional `base_uri` resolves relative IRIs. "
        "The complete JSON request is limited to 20 MB.\n\n" + render_checks_api_description()
    ),
    tags=["validation"],
    responses={**_API_RESPONSES, 415: {"model": ApiError, "description": "Content-Type must be application/json"}},
    # Read the body ourselves so the limit applies before JSON parsing. The
    # request schema still comes from the same model used to validate it.
    openapi_extra={"requestBody": {
        "required": True,
        "content": {"application/json": {"schema": OntologyContent.model_json_schema()}},
    }},
)
async def validate_content_api(request: Request, compact: bool = _COMPACT_QUERY):
    """Accept generated RDF without requiring an agent to create a file."""
    started = time.perf_counter()
    client_ip = _client_ip(request)
    source = "ontology"
    if _rate_limited(client_ip):
        response = JSONResponse({"detail": _RATE_LIMIT_MESSAGE}, status_code=429)
    elif request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        response = JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
    else:
        try:
            body = await _read_content_capped(request)
            ontology = OntologyContent.model_validate_json(body)
        except ClientDisconnect:
            return _abandoned_response()
        except UploadTooLargeError as exc:
            response = JSONResponse({"detail": str(exc)}, status_code=413)
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_context=False, include_input=False)
            for error in errors:
                error["loc"] = ["body", *error["loc"]]
            response = JSONResponse({"detail": errors}, status_code=422)
        else:
            source += ontology.suffix
            response = await _api_validation_response(
                request, ontology.as_bytes(), source, ontology.suffix,
                compact=compact, base_uri=ontology.base_uri,
            )
    return _record_api_response(response, source, started, client_ip)

