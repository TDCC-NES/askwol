"""Input mistakes and explicit syntax/base choices behave consistently."""

import json
from html.parser import HTMLParser

import httpx
import pytest
import respx
from click.testing import CliRunner
from fastapi.testclient import TestClient

from askwol import cli, network, web
from askwol.parser import parse_ontology
from askwol.pipeline import run_full_validation

BASE = "https://example.org/ontology"
TURTLE = b"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
<> a owl:Ontology . <#Person> a owl:Class .
"""
HTML = b"<!DOCTYPE html><html><head><title>Viewer</title></head><body>File</body></html>"


@pytest.fixture
def client(monkeypatch):
    async def offline_validation(path, display_name, *, kind, base_uri=None):
        return await run_full_validation(
            path, display_name=display_name, base_uri=base_uri,
            skip_resolution=True, include_mermaid=False,
        )

    async def request_hook(request):
        pass

    monkeypatch.setattr(web, "run_isolated_validation", offline_validation)
    monkeypatch.setattr(web, "block_private_network_requests", request_hook)
    monkeypatch.setattr(network, "block_private_network_request", lambda request: None)
    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 0)
    return TestClient(web.app)


@pytest.mark.parametrize("route", ["/api/validate", "/api/validate/content"])
@pytest.mark.parametrize("compact", [False, True])
def test_html_disguised_as_rdf_is_actionable_in_both_api_reports(client, route, compact):
    kwargs = {"params": {"compact": str(compact).lower()}}
    if route.endswith("/content"):
        kwargs["json"] = {"format": "xml", "content": HTML.decode()}
    else:
        kwargs["files"] = {"file": ("ontology.owl", HTML, "application/rdf+xml")}
    response = client.post(route, **kwargs)

    assert response.status_code == 422, response.text
    report = response.json()
    assert report["input_error"]["code"] == "html_instead_of_rdf"
    assert "Raw" in report["input_error"]["message"]
    assert report["input_error"]["guide_url"].endswith("#server-config")
    assert report["input_error"]["line"] is None
    assert report["input_error"]["column"] is None
    assert report["severity_summary"]["has_errors"] is True
    if compact:
        assert all(check["status"] == "skipped" for check in report["checks"])
    else:
        assert report["parse_errors"] == [report["input_error"]["message"]]
        assert report["term_inventory"] is None


def test_web_upload_explains_html_instead_of_showing_passed_checks(client):
    response = client.post("/validate", files={"file": ("ontology.owl", HTML, "application/rdf+xml")})
    assert response.status_code == 422
    assert "HTML page" in response.text
    assert "Ontology checks were not run" in response.text
    assert 'id="unused-prefixes"' not in response.text


@pytest.mark.parametrize("compact", [False, True])
def test_upload_content_type_and_explicit_syntax_override_misleading_suffix(client, compact):
    for content_type, fields in [("text/turtle", {}), ("application/rdf+xml", {"format": "turtle"})]:
        response = client.post(
            "/api/validate", params={"compact": str(compact).lower()},
            files={"file": ("ontology.owl", TURTLE, content_type)},
            data={"base_uri": BASE, **fields},
        )
        assert response.status_code == 200, response.text
        assert response.json()["input_error"] is None
        assert response.json()["input_warnings"] == []
        if not compact:
            assert response.json()["term_inventory"]["entries"][0]["term"] == BASE + "#Person"


def test_upload_relative_identifiers_have_explicit_base_or_source_guidance(client):
    without_base = client.post("/api/validate", files={"file": ("ontology.ttl", TURTLE, "text/turtle")})
    assert without_base.status_code == 200
    assert without_base.json()["input_warnings"]
    assert without_base.json()["term_inventory"]["entries"][0]["term"].startswith("file:")
    compact = client.post(
        "/api/validate?compact=true", files={"file": ("ontology.ttl", TURTLE, "text/turtle")},
    )
    assert compact.json()["input_warnings"] == without_base.json()["input_warnings"]

    html = client.post(
        "/validate", files={"file": ("ontology.data", TURTLE, "application/octet-stream")},
        data={"base_uri": BASE, "format": "turtle"},
    )
    assert html.status_code == 200, html.text
    assert BASE + "#Person" in html.text
    assert "Some RDF identifiers use file://" not in html.text


@pytest.mark.parametrize("field, value, code", [
    ("base_uri", "relative/path", "invalid_base_uri"),
    ("format", "not-rdf", "unsupported_format"),
])
def test_upload_invalid_settings_return_structured_errors(client, field, value, code):
    response = client.post(
        "/api/validate?compact=true", files={"file": ("ontology.ttl", TURTLE, "text/turtle")},
        data={field: value},
    )
    assert response.status_code == 422
    assert response.json()["input_error"]["code"] == code
    assert all(check["status"] == "skipped" for check in response.json()["checks"])


def test_api_url_misuse_explains_supported_inputs(client):
    for route in ("/api/validate", "/api/validate/content"):
        response = client.post(route, json={"url": "https://github.com/ex/onto/blob/main/onto.owl"})
        assert response.status_code == 422
        messages = " ".join(error["msg"] for error in response.json()["detail"])
        assert "does not download source URLs" in messages
        assert "Raw" in messages


def test_api_url_in_file_field_explains_raw_upload(client):
    response = client.post("/api/validate", data={"file": "https://github.com/ex/onto/blob/main/onto.owl"})
    assert response.status_code == 422
    assert "does not download source URLs" in response.json()["detail"][0]["msg"]


@pytest.mark.parametrize("url", ["https://[broken/ontology.ttl", "https://example.org:bad/ontology.ttl", "https://example.org/\x00"])
def test_malformed_web_urls_are_explained_without_server_errors(client, url):
    response = client.post("/validate", data={"url": url})
    assert response.status_code == 400
    assert "Invalid ontology URL" in response.text
    assert "Ontology checks were not run" in response.text


@respx.mock
def test_redirect_format_and_base_match_web_and_python(client):
    source = "https://example.org/download"
    final = "https://example.org/schema/ontology.ttl"
    respx.get(source).mock(return_value=httpx.Response(302, headers={"location": final}))
    respx.get(final).mock(return_value=httpx.Response(200, content=TURTLE, headers={"content-type": "text/plain"}))
    response = client.post("/validate", data={"url": source})
    parsed = parse_ontology(source)

    assert response.status_code == 200, response.text
    assert final + "#Person" in response.text
    assert any(str(subject) == final + "#Person" for subject in parsed.graph.subjects())


@respx.mock
def test_web_url_rejects_html_with_generic_content_type(client):
    source = "https://example.org/ontology.owl"
    respx.get(source).mock(return_value=httpx.Response(200, content=HTML, headers={"content-type": "text/plain"}))
    response = client.post("/validate", data={"url": source})
    assert response.status_code == 422
    assert "HTML page" in response.text
    assert "Ontology checks were not run" in response.text


@pytest.mark.parametrize("output_format", ["text", "markdown", "json"])
def test_cli_html_diagnostic_is_informative_in_every_output(tmp_path, output_format):
    path = tmp_path / "viewer.owl"
    path.write_bytes(HTML)
    result = CliRunner().invoke(cli.main, ["check", str(path), "--skip-resolution", "--format", output_format])
    assert result.exit_code == 1, result.output
    if output_format == "json":
        assert json.loads(result.stdout)["input_error"]["code"] == "html_instead_of_rdf"
    else:
        assert "HTML page" in result.stdout
        assert "Ontology checks were not run" in result.stdout
        assert "Unused prefixes" not in result.stdout


def test_cli_explicit_input_format_and_base_are_applied(tmp_path):
    path = tmp_path / "ontology.owl"
    path.write_bytes(TURTLE)
    result = CliRunner().invoke(cli.main, [
        "check", str(path), "--skip-resolution", "--input-format", "turtle",
        "--base-uri", BASE, "--format", "json",
    ])
    report = json.loads(result.stdout)
    assert report["input_error"] is None
    assert report["input_warnings"] == []
    assert report["term_inventory"]["entries"][0]["term"] == BASE + "#Person"


def test_cli_url_argument_teaches_raw_download_instead_of_missing_path():
    result = CliRunner().invoke(cli.main, ["check", "https://github.com/ex/onto/blob/main/ontology.owl"])
    assert result.exit_code == 2
    assert "local file" in result.stderr
    assert "Download the raw ontology file" in result.stderr
    assert "https://github.com/ex/onto/raw/main/ontology.owl" in result.stderr


def test_cli_unexpected_failure_has_readable_error(tmp_path, monkeypatch):
    path = tmp_path / "ontology.ttl"
    path.write_bytes(TURTLE)

    async def fail(*args, **kwargs):
        raise RuntimeError("Check failed unexpectedly")

    monkeypatch.setattr(cli, "run_full_validation", fail)
    result = CliRunner().invoke(cli.main, ["check", str(path)])
    assert result.exit_code == 1
    assert "Validation could not complete. Check failed unexpectedly" in result.stderr
    assert not isinstance(result.exception, RuntimeError)


def test_upload_settings_start_collapsed_and_disabled(client):
    class Controls(HTMLParser):
        def __init__(self, html):
            super().__init__()
            self.elements = []
            self.feed(html)

        def handle_starttag(self, tag, attrs):
            self.elements.append((tag, dict(attrs)))

    elements = Controls(client.get("/").text).elements
    settings = next(attrs for tag, attrs in elements if tag == "details" and attrs.get("class") == "input-settings")
    assert "open" not in settings
    for field in ("base_uri", "format"):
        control = next(attrs for _tag, attrs in elements if attrs.get("name") == field)
        assert "disabled" in control
