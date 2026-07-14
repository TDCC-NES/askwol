"""End-to-end integration tests for the FastAPI app.

These tests drive the app through Starlette's `TestClient` and confirm that
every check is wired through `/api/validate` for the bundled `examples/sample.ttl`,
and that the simple HTML routes work without network access.

Namespace resolution is stubbed out by pre-populating the global ontology
cache, so the tests do not hit the network.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph

from askwol import web
from askwol.cache import OntologyCache

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.ttl"


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
