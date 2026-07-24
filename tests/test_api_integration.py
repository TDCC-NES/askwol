"""End-to-end integration tests for the FastAPI app.

These tests drive the app through Starlette's `TestClient` and confirm that
every check is wired through `/api/validate` for the bundled `html/ontologies/sample.ttl`,
and that the simple HTML routes work without network access.

Namespace resolution is stubbed out by pre-populating the global ontology
cache, so the tests do not hit the network.
"""

from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from rdflib import Graph

from askwol import web
from askwol.cache import OntologyCache

SAMPLE = Path(__file__).resolve().parent.parent / "html" / "ontologies" / "sample.ttl"


async def _noop_request_hook(request):
    """Stand-in for resolver.block_private_network_requests in URL-fetch tests:
    the SSRF guard does a real DNS lookup, which the content-type gating tests
    below don't need and shouldn't depend on."""


@pytest.fixture
def client(monkeypatch):
    # Isolate the cache and prevent network calls for resolved namespaces
    # by pre-populating an empty graph for every namespace the sample uses.
    cache = OntologyCache()
    monkeypatch.setattr(web, "_global_cache", cache)

    for ns_uri in [
        "https://w3id.org/test/",
        "http://www.w3.org/2002/07/owl#",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://www.w3.org/2000/01/rdf-schema#",
        "http://www.w3.org/2001/XMLSchema#",
    ]:
        cache.put(ns_uri, Graph())

    return TestClient(web.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_guide_renders(client):
    r = client.get("/guide")
    assert r.status_code == 200
    assert "<html" in r.text.lower()


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()


def test_api_validate_returns_all_check_sections(client):
    with SAMPLE.open("rb") as fh:
        r = client.post(
            "/api/validate",
            files={"file": ("sample.ttl", fh, "text/turtle")},
        )
    assert r.status_code == 200, r.text
    data = r.json()

    # Every check shows up in the JSON payload.
    for field in [
        "file",
        "namespaces",
        "unused_prefixes",
        "lang_tags",
        "ontology_metadata",
        "definition_docs",
        "imports",
        "iri_strategy",
        "iri_scheme",
        "reasoner",
        "non_ontology_terms",
    ]:
        assert field in data, f"missing field: {field}"

    assert data["file"] == "sample.ttl"
    assert data["parse_errors"] == []
    # The sample is single-scheme (https://w3id.org/test/) so iri_scheme is OK.
    assert data["iri_scheme"]["status"] in ("ok", "skip")
    # Sample uses hash-style terms only? It actually uses slash:
    # <https://w3id.org/test/> with :MyClass -> https://w3id.org/test/MyClass.
    assert data["iri_strategy"]["status"] in ("ok", "warn", "skip")


def test_api_validate_excludes_own_namespace_from_term_validation(client):
    """The ontology's own namespace stays in the namespace-resolution list (2.1)
    but its terms are not run through external term validation (2.3): they're
    already covered by the internal term inventory."""
    with SAMPLE.open("rb") as fh:
        r = client.post(
            "/api/validate",
            files={"file": ("sample.ttl", fh, "text/turtle")},
        )
    assert r.status_code == 200, r.text
    data = r.json()

    own_ns = next(ns for ns in data["namespaces"] if ns["uri"].startswith("https://lod-4tu.tudelft.nl/dataset"))
    assert own_ns["terms"] == []


def test_api_validate_parse_error_returns_422(client):
    r = client.post(
        "/api/validate",
        files={"file": ("bad.ttl", b"this is not valid turtle <<<", "text/turtle")},
    )
    assert r.status_code == 422
    data = r.json()
    assert data["parse_errors"], "expected parse_errors to be populated"


def test_html_validate_renders_report(client):
    with SAMPLE.open("rb") as fh:
        r = client.post(
            "/validate",
            files={"file": ("sample.ttl", fh, "text/turtle")},
        )
    assert r.status_code == 200
    body = r.text
    # All check section anchors should be present in the HTML report.
    for anchor in [
        "ontology-metadata",
        "imports",
        "iri-strategy",
        "iri-scheme",
        "namespaces",
        "external-terms",
        "internal-terms",
        "term-inventory",
        "domains-ranges",
        "datatypes",
        "labels",
        "comments",
        "language-tags",
        "reasoner",
        "unused-prefixes",
    ]:
        assert f'id="{anchor}"' in body, f"missing section anchor: {anchor}"


def test_html_validate_requires_file_or_url(client):
    r = client.post("/validate")
    assert r.status_code == 400


@respx.mock
def test_html_validate_url_rejects_html_response(client, monkeypatch):
    monkeypatch.setattr(web, "block_private_network_requests", _noop_request_hook)
    respx.get("https://example.org/").mock(
        return_value=httpx.Response(
            200, content=b"<html><body>hi</body></html>", headers={"content-type": "text/html"}
        )
    )
    r = client.post("/validate", data={"url": "https://example.org/"})
    assert r.status_code == 415
    assert "HTML page" in r.text


@respx.mock
def test_html_validate_url_rejects_unrecognized_content_type(client, monkeypatch):
    """A server can redirect a namespace URI to a catalog/metadata endpoint that
    returns a non-standard content type which still happens to be syntactically
    valid RDF (e.g. OGC's Prez backend serving "text/anot+turtle" for
    http://www.opengis.net/ont/geosparql). This isn't the ontology itself, so
    it must be rejected rather than silently parsed as if it were."""
    monkeypatch.setattr(web, "block_private_network_requests", _noop_request_hook)
    respx.get("http://example.org/ont/geosparql").mock(
        return_value=httpx.Response(
            200,
            content=b'@prefix ex: <http://example.org/> .\nex:a ex:b "not the real ontology" .',
            headers={"content-type": "text/anot+turtle"},
        )
    )
    r = client.post("/validate", data={"url": "http://example.org/ont/geosparql"})
    assert r.status_code == 415
    assert "text/anot+turtle" in r.text


@respx.mock
def test_html_validate_url_rejects_text_plain_without_recognized_extension(client, monkeypatch):
    monkeypatch.setattr(web, "block_private_network_requests", _noop_request_hook)
    respx.get("http://example.org/ont/geosparql").mock(
        return_value=httpx.Response(
            200, content=b"@prefix ex: <http://example.org/> .", headers={"content-type": "text/plain"}
        )
    )
    r = client.post("/validate", data={"url": "http://example.org/ont/geosparql"})
    assert r.status_code == 415


@respx.mock
def test_html_validate_url_accepts_text_plain_with_recognized_extension(client, monkeypatch):
    """raw.githubusercontent.com-style hosts serve RDF as generic text/plain; the
    URL's own file extension is still trusted in that specific case."""
    monkeypatch.setattr(web, "block_private_network_requests", _noop_request_hook)
    # SAMPLE declares owl:imports <http://www.w3.org/ns/dcat> and its own
    # namespace (the ":" prefix) also goes through namespace resolution;
    # pre-cache both so check_imports/resolve_all_namespaces don't need a
    # real network fetch.
    web._global_cache.put("http://www.w3.org/ns/dcat", Graph())
    web._global_cache.put("https://lod-4tu.tudelft.nl/dataset#", Graph())
    respx.get("https://raw.githubusercontent.com/example/sample.ttl").mock(
        return_value=httpx.Response(200, content=SAMPLE.read_bytes(), headers={"content-type": "text/plain"})
    )
    r = client.post("/validate", data={"url": "https://raw.githubusercontent.com/example/sample.ttl"})
    assert r.status_code == 200, r.text


def test_api_validate_rate_limited(monkeypatch, client):
    monkeypatch.setattr(web, "_rate_limit_buckets", {})
    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 1)

    with SAMPLE.open("rb") as fh:
        first = client.post("/api/validate", files={"file": ("sample.ttl", fh, "text/turtle")})
    assert first.status_code == 200, first.text

    with SAMPLE.open("rb") as fh:
        second = client.post("/api/validate", files={"file": ("sample.ttl", fh, "text/turtle")})
    assert second.status_code == 429
    assert "detail" in second.json()


def test_usage_dashboard_requires_token(monkeypatch, client):
    monkeypatch.setenv("ASKWOL_STATS_TOKEN", "secret-token")

    unauthorized = client.get("/stats")
    assert unauthorized.status_code == 401

    response = client.get("/stats", params={"token": "secret-token"})
    assert response.status_code == 200
    assert "Usage" in response.text
    assert "All events" in response.text


def test_usage_dashboard_allows_localhost_without_token(monkeypatch, client):
    monkeypatch.setenv("ASKWOL_STATS_TOKEN", "secret-token")
    monkeypatch.setattr(web, "_is_local_request", lambda request: True)

    response = client.get("/stats")
    assert response.status_code == 200
    assert "Usage" in response.text


def test_usage_api_returns_json(monkeypatch, client):
    monkeypatch.setenv("ASKWOL_STATS_TOKEN", "secret-token")

    response = client.get("/api/stats", params={"token": "secret-token"})
    assert response.status_code == 200
    payload = response.json()
    assert "total_events" in payload
    assert "all_events" in payload
    assert "page" in payload
