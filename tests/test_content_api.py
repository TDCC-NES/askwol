"""Programmatic RDF input and compact reports share the existing pipeline."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from askwol import web
from askwol.checks import CHECKS
from askwol.pipeline import run_full_validation
from tests.test_client_disconnect import _Client

ONTOLOGY = "https://example.org/ontology"
OWL = "http://www.w3.org/2002/07/owl#"
JSON_LD = {
    "@context": {"owl": OWL},
    "@graph": [
        {"@id": ONTOLOGY, "@type": "owl:Ontology"},
        {"@id": ONTOLOGY + "#Person", "@type": "owl:Class"},
    ],
}
TURTLE = f"""@prefix owl: <{OWL}> .
<{ONTOLOGY}> a owl:Ontology .
<{ONTOLOGY}#Person> a owl:Class .
"""


@pytest.fixture
def client(monkeypatch):
    async def offline_validation(path, display_name, *, kind, base_uri=None):
        return await run_full_validation(
            path, display_name=display_name, base_uri=base_uri,
            skip_resolution=True, include_mermaid=False,
        )

    monkeypatch.setattr(web, "run_isolated_validation", offline_validation)
    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 0)
    monkeypatch.setattr(web, "_rate_limit_buckets", {})
    return TestClient(web.app)


def post_ontology(client, route, *, compact=False, content=TURTLE):
    params = {"compact": "true"} if compact else None
    if route == "/api/validate":
        return client.post(
            route, params=params,
            files={"file": ("ontology.ttl", content.encode("utf-8"), "text/turtle")},
        )
    return client.post(
        route, params=params, json={"format": "turtle", "content": content},
    )


@pytest.mark.parametrize("content", [JSON_LD, [JSON_LD]])
def test_json_ld_structured_content_matches_turtle(client, content):
    response = client.post(
        "/api/validate/content", json={"format": "json-ld", "content": content},
    )
    turtle = post_ontology(client, "/api/validate/content")

    assert response.status_code == turtle.status_code == 200
    report, reference = response.json(), turtle.json()
    assert report["parse_errors"] == []
    for section in ("ontology_metadata", "definition_docs", "term_inventory", "reasoner"):
        assert report[section] == reference[section]
    assert {entry["term"] for entry in report["term_inventory"]["entries"]} == {
        ONTOLOGY + "#Person",
    }


def test_content_base_iri_resolves_relative_terms(client):
    response = client.post("/api/validate/content", json={
        "format": "turtle",
        "content": f"@prefix owl: <{OWL}> . <> a owl:Ontology . <#Person> a owl:Class .",
        "base_uri": ONTOLOGY,
    })

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["iri_strategy"]["ontology_iri"] == ONTOLOGY
    assert {entry["term"] for entry in report["term_inventory"]["entries"]} == {
        ONTOLOGY + "#Person",
    }


@pytest.mark.parametrize("route", ["/api/validate", "/api/validate/content"])
def test_compact_report_preserves_findings_and_unchecked_scope(client, route):
    source = TURTLE + f"<{ONTOLOGY}> <{OWL}imports> <https://example.org/imported> ."
    full = post_ontology(client, route, content=source)
    compact = post_ontology(client, route, content=source, compact=True)

    assert full.status_code == compact.status_code == 200
    full_report, report = full.json(), compact.json()
    assert report["severity_summary"] == full_report["severity_summary"]
    assert "term_inventory" not in report
    assert "namespaces" not in report
    assert {check["check"] for check in report["checks"]} == {
        check["report_anchor"] for check in CHECKS
    }
    coverage = {check["check"]: check["status"] for check in report["checks"]}
    assert coverage["imports"] == coverage["namespaces"] == "skipped"
    assert report["reasoner"]["imports_followed"] is False
    assert report["reasoner"]["scoped_to_current_ontology"] is True
    assert report["reasoner"]["consistent"] is None
    findings = report["severity_summary"]["findings"]
    assert findings
    assert all(finding["guide_url"].startswith(
        "https://lod-4tu.tudelft.nl/askwol/guide#",
    ) for finding in findings)


@pytest.mark.parametrize("route", ["/api/validate", "/api/validate/content"])
def test_compact_parse_error_is_a_finding_with_no_guide_link(client, route):
    response = post_ontology(client, route, compact=True, content="not valid RDF <<<")

    assert response.status_code == 422
    report = response.json()
    summary = report["severity_summary"]
    assert summary["has_errors"] is True
    assert summary["errors"] > 0
    assert {finding["rule"] for finding in summary["findings"]} == {"parse.error"}
    assert all(finding["guide_url"] is None for finding in summary["findings"])
    assert all(check["status"] == "skipped" for check in report["checks"])
    assert report["reasoner"] is None


@pytest.mark.parametrize("payload", [
    {"content": TURTLE},
    {"format": "not-rdf", "content": TURTLE},
    {"format": "turtle", "content": JSON_LD},
    {"format": "json-ld", "content": 42},
    {"format": "turtle", "content": TURTLE, "base_uri": "relative/path"},
])
def test_invalid_content_request_has_request_errors(client, payload):
    response = client.post("/api/validate/content", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert "severity_summary" not in response.json()


@pytest.mark.parametrize("content", [b"{", b"\xff"])
def test_malformed_json_has_request_errors(client, content):
    response = client.post(
        "/api/validate/content", content=content,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_content_endpoint_requires_json_content_type(client):
    response = client.post("/api/validate/content", content=TURTLE)

    assert response.status_code == 415
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("route", ["/api/validate", "/api/validate/content"])
def test_size_limit_applies_before_rdf_or_json_parsing(client, monkeypatch, route):
    monkeypatch.setattr(web, "MAX_UPLOAD_SIZE", 64)
    if route == "/api/validate/content":
        # Invalid JSON still gets the size response, rather than a parse error.
        response = client.post(
            route, content=b"{" + b" " * 128,
            headers={"content-type": "application/json"},
        )
    else:
        response = client.post(route, files={"file": ("large.ttl", b" " * 128, "text/turtle")})

    assert response.status_code == 413
    assert isinstance(response.json()["detail"], str)


def test_both_api_routes_share_the_rate_limit(client, monkeypatch):
    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 1)
    assert post_ontology(client, "/api/validate").status_code == 200

    response = post_ontology(client, "/api/validate/content")
    assert response.status_code == 429
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize(("error", "status"), [
    (web.ValidationBusyError, 503),
    (web.ValidationTimeoutError, 504),
    (web.ValidationExecutionError, 500),
])
def test_content_worker_errors_are_typed_and_tempfiles_removed(client, monkeypatch, error, status):
    paths = []

    async def fail(path, display_name, *, kind, base_uri=None):
        assert Path(path).exists()
        paths.append(Path(path))
        raise error()

    monkeypatch.setattr(web, "run_isolated_validation", fail)
    response = post_ontology(client, "/api/validate/content")

    assert response.status_code == status
    assert isinstance(response.json()["detail"], str)
    assert paths and all(not path.exists() for path in paths)


@pytest.mark.parametrize(("disconnect", "expected_status"), [(False, 413), (True, 499)])
@pytest.mark.asyncio
async def test_incomplete_stream_never_starts_validation(client, monkeypatch, disconnect, expected_status):
    monkeypatch.setattr(web, "MAX_UPLOAD_SIZE", 64)
    recorded = []
    monkeypatch.setattr(web.usage, "record", lambda *args, **kwargs: recorded.append(kwargs))

    async def unexpected_validation(*args, **kwargs):
        pytest.fail("An incomplete or oversized request must not start validation")

    monkeypatch.setattr(web, "run_isolated_validation", unexpected_validation)
    connection = _Client("POST", "/api/validate/content")
    connection.headers.append((b"content-type", b"application/json"))
    messages = iter([
        {"type": "http.request", "body": b"{" + b" " * 31, "more_body": True},
        {"type": "http.disconnect"} if disconnect else {
            "type": "http.request", "body": b" " * 33, "more_body": True,
        },
    ])

    async def receive():
        return next(messages)

    await web.app(connection.scope(), receive, connection.send)

    assert connection.status == expected_status
    assert len(recorded) == (0 if disconnect else 1)


def test_openapi_describes_both_report_variants_and_request_errors(client):
    schema = client.get("/openapi.json").json()
    definitions = schema["components"]["schemas"]
    for route in ("/api/validate", "/api/validate/content"):
        operation = schema["paths"][route]["post"]
        assert any(parameter["name"] == "compact" for parameter in operation["parameters"])
        responses = operation["responses"]
        success = responses["200"]["content"]["application/json"]["schema"]["anyOf"]
        invalid = responses["422"]["content"]["application/json"]["schema"]["anyOf"]
        assert len(success) == 2
        assert {item["$ref"] for item in success} < {item["$ref"] for item in invalid}
        request_errors = next(item for item in invalid if item not in success)
        error_definition = definitions[request_errors["$ref"].rsplit("/", 1)[-1]]
        assert error_definition["properties"]["detail"]["type"] == "array"
        for status in ("413", "429", "500", "503", "504"):
            response_schema = responses[status]["content"]["application/json"]["schema"]
            error_definition = definitions[response_schema["$ref"].rsplit("/", 1)[-1]]
            assert error_definition["properties"]["detail"]["type"] == "string"

    operation = schema["paths"]["/api/validate/content"]["post"]
    request = operation["requestBody"]
    assert request["required"] is True
    body = request["content"]["application/json"]["schema"]
    assert set(body["required"]) == {"format", "content"}
    assert body["additionalProperties"] is False
    assert set(body["properties"]["format"]["enum"]) == {"json-ld", "turtle", "xml", "nt", "n3"}
    assert "415" in operation["responses"]
