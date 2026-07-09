"""FastAPI web application for the askwol ontology checker."""

from __future__ import annotations

import os
import tempfile
import time
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from askwol import usage
from askwol.cache import OntologyCache
from askwol.definition_docs import check_definition_documentation
from askwol.imports_check import check_imports
from askwol.iri_scheme import check_iri_scheme
from askwol.iri_strategy import check_iri_strategy
from askwol.lang_tags import check_lang_tags
from askwol.mermaid_diagram import build_mermaid
from askwol.metadata_validator import validate_ontology_metadata
from askwol.models import NamespaceReport, UnusedPrefix, ValidationReport
from askwol.parser import parse_ontology
from askwol.reasoner_checks import run_reasoner_checks
from askwol.report_html import render_report
from askwol.resolver import resolve_all_namespaces
from askwol.templates import GUIDE_HTML, UPLOAD_HTML
from askwol.term_validator import validate_terms

# ASKWOL_ROOT_PATH is the reverse-proxy sub-path prefix (e.g. /askwol); empty
# for a root deployment.
ROOT_PATH = os.environ.get("ASKWOL_ROOT_PATH", "").rstrip("/")

app = FastAPI(
    title="askwol",
    description=(
        "Validate OWL ontologies: namespace resolution, term existence in "
        "remote vocabularies, internal definition documentation (SHACL), "
        "ontology metadata (SHACL), language-tag consistency, unused "
        "prefix declarations, owl:imports completeness, IRI strategy "
        "consistency (hash vs slash), IRI scheme consistency (http vs "
        "https), and lightweight OWL RL reasoner checks (ontology "
        "consistency, inconsistent individuals, and unsatisfiable "
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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    return HTMLResponse(_apply_prefix(UPLOAD_HTML))


@app.get("/health", summary="Health check", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/stats", include_in_schema=False)
async def stats_endpoint(token: str | None = None):
    """Internal usage dashboard. Requires ASKWOL_STATS_TOKEN env var to match `?token=`."""
    expected = usage.stats_token()
    if not expected:
        return JSONResponse(
            {"error": "stats disabled - set ASKWOL_STATS_TOKEN to enable"},
            status_code=503,
        )
    if token != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(usage.stats(days=30))


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

    if url and url.strip():
        source = url.strip()
        response = await _validate_url(source)
    elif file and file.filename:
        source = file.filename
        kind = "validate_upload"
        response = await _validate_upload(file)
    else:
        response = HTMLResponse("<p>Please provide a file or URL.</p>", status_code=400)

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
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers={"Accept": accept_header})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return HTMLResponse(f"<p>Could not fetch URL: {escape(str(exc))}</p>", status_code=422)

    # Pick a suffix from the Content-Type so the parser can sniff the format.
    # Fall back to the URL path, then to .ttl.
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

    suffix = ctype_suffix or Path(parsed_url.path).suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = Path(tmp.name)

    return await _run_validation(tmp_path, url)


async def _validate_upload(file: UploadFile) -> HTMLResponse:
    content = await file.read()
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

    # Explicit owl:imports for external vocabularies actually used
    report.imports = check_imports(
        parsed.graph, parsed.namespaces, parsed.terms_by_namespace,
    )

    # IRI strategy (hash vs slash) for the ontology's own terms
    report.iri_strategy = check_iri_strategy(parsed.graph)

    # IRI scheme consistency (http vs https) per host
    report.iri_scheme = check_iri_scheme(parsed.graph, parsed.namespaces)

    # Reasoner checks (current ontology only; imports are not followed)
    report.reasoner = run_reasoner_checks(parsed.graph)

    # Only resolve and report namespaces that have subject-position terms
    active_ns = {pfx: uri for pfx, uri in parsed.namespaces.items()
                 if parsed.terms_by_namespace.get(pfx)}

    ns_checks = await resolve_all_namespaces(active_ns, cache)
    ns_check_map = {c.uri: c for c in ns_checks}

    for prefix, uri in active_ns.items():
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())
        term_checks = validate_terms(prefix, uri, local_names, cache)

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
    },
)
async def validate_api(
    file: UploadFile = File(..., description="OWL ontology file (Turtle, RDF/XML, JSON-LD, N-Triples, or N3)"),
):
    """Upload an OWL ontology and get a full validation report as JSON.

    The report includes:

    - **Namespaces** - each declared prefix is fetched over HTTP and parsed as RDF where possible.
    - **Terms** - every term used from a remote vocabulary is looked up in the resolved namespace.
    - **Definition documentation** - SHACL check that internally defined classes and properties carry `rdfs:label` and `rdfs:comment`. Reused external terms are ignored.
    - **Unused prefixes** - prefixes declared with `@prefix` but never used in a triple.
    - **Language-tag consistency** - labels and definitions (`rdfs:label`, `rdfs:comment`, `skos:prefLabel`, `skos:definition`, ...) should use the same language tags across subjects.
    - **Ontology metadata** - SHACL check on the ontology header (title, creator, license, version, ...).
    - **Imports** - external vocabularies actually used in the ontology should be declared with `owl:imports`.
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
    content = await file.read()
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

    ns_checks = await resolve_all_namespaces(
        {pfx: uri for pfx, uri in parsed.namespaces.items()
         if parsed.terms_by_namespace.get(pfx)},
        cache,
    )
    ns_check_map = {c.uri: c for c in ns_checks}
    for prefix, uri in parsed.namespaces.items():
        if not parsed.terms_by_namespace.get(prefix):
            continue
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())
        term_checks = validate_terms(prefix, uri, local_names, cache)
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
    report.imports = check_imports(
        parsed.graph, parsed.namespaces, parsed.terms_by_namespace,
    )
    report.iri_strategy = check_iri_strategy(parsed.graph)
    report.iri_scheme = check_iri_scheme(parsed.graph, parsed.namespaces)
    report.reasoner = run_reasoner_checks(parsed.graph)

    return report.model_dump(mode="json")

