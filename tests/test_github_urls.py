"""GitHub viewer links require an explained, explicit switch to the raw file."""

from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from askwol import usage, web
from askwol.network import SSRFBlockedError
from askwol.pipeline import run_full_validation

BLOB = "https://github.com/example/ontology/blob/main/schema/ontology.ttl"
RAW = "https://github.com/example/ontology/raw/main/schema/ontology.ttl"
FINAL = "https://raw.githubusercontent.com/example/ontology/main/schema/ontology.ttl"
TURTLE = b"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<> a owl:Ontology; owl:imports <imports/other.ttl> .
<#Thing> a owl:Class; rdfs:label "A thing"@en .
"""


class _Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def by_id(self, element_id):
        return next(attrs for _tag, attrs in self.elements if attrs.get("id") == element_id)


def _choose_raw_file(client, entered=BLOB):
    guidance = client.post("/validate", data={"url": entered})
    assert guidance.status_code == 415
    displayed_raw_url = _Elements(guidance.text).by_id("github-raw-url")["href"]
    return client.post("/validate", data={"url": displayed_raw_url})


@pytest.fixture
def validation_client(monkeypatch):
    """Exercise real parsing/checks without worker startup or secondary HTTP."""
    validations = []
    outgoing = []

    async def request_hook(request):
        outgoing.append(str(request.url))

    async def inprocess(path, display_name, *, kind, base_uri=None):
        report, mermaid = await run_full_validation(
            path, display_name=display_name, base_uri=base_uri,
            skip_resolution=True, include_mermaid=False,
        )
        validations.append(SimpleNamespace(
            report=report, display_name=display_name, base_uri=base_uri, kind=kind,
        ))
        return report, mermaid

    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 0)
    monkeypatch.setattr(web, "ROOT_PATH", "")
    monkeypatch.setattr(web, "block_private_network_requests", request_hook)
    monkeypatch.setattr(web, "run_isolated_validation", inprocess)
    with TestClient(web.app) as client:
        yield SimpleNamespace(client=client, validations=validations, outgoing=outgoing)


@pytest.mark.parametrize("tail", [
    "master/ontology.owl",
    "main/schema/ontology.ttl",
    "v1.2.3/schema/ontology.rdf",
    "4eee6f24179586482af80589b26b63137b4385a7/ontology.owl",
    "feature/new-schema/schema/ontology.ttl",
    "refs/heads/feature/new-schema/schema/ontology.ttl",
    "refs/tags/v1.2.3/schema/ontology.ttl",
    "stable%2F5.2.x/schema/ont%20ology%23%3F%C3%A9.ttl",
    "main/schema/ontology;version%2E1.ttl",
])
def test_github_raw_url_preserves_complete_encoded_ref_and_path(tail):
    url = f"https://github.com/Example/Ontology/blob/{tail}?plain=1#L12-L15"
    assert web._github_raw_url(url) == f"https://github.com/Example/Ontology/raw/{tail}"


@pytest.mark.parametrize("url", [
    "https://github.com.evil.example/example/ontology/blob/main/ontology.owl",
    "https://evilgithub.com/example/ontology/blob/main/ontology.owl",
    "https://github.com@evil.example/example/ontology/blob/main/ontology.owl",
    "https://user@github.com/example/ontology/blob/main/ontology.owl",
    "https://user:password@github.com/example/ontology/blob/main/ontology.owl",
    "https://github.com:443/example/ontology/blob/main/ontology.owl",
    "https://github.com:8443/example/ontology/blob/main/ontology.owl",
    "https://gist.github.com/example/ontology/blob/main/ontology.owl",
    "https://raw.githubusercontent.com/example/ontology/main/ontology.owl",
    "https://github.com/example/ontology/tree/main/ontology.owl",
    "https://github.com/example/ontology/raw/main/ontology.owl",
    "https://github.com/example/ontology/blob/main",
    "https://github.com/example/ontology/blob/main/",
    "https://github.com/example/ontology/blob//ontology.owl",
    "https://github.com//ontology/blob/main/ontology.owl",
    "https://github.com/example//blob/main/ontology.owl",
    "file://github.com/example/ontology/blob/main/ontology.owl",
])
def test_github_raw_url_does_not_rewrite_other_hosts_or_nonfile_links(url):
    assert web._github_raw_url(url) is None


@pytest.mark.parametrize("prefix", ["", "/askwol"])
@respx.mock
def test_viewer_submission_explains_correction_without_fetching(validation_client, monkeypatch, prefix):
    monkeypatch.setattr(web, "ROOT_PATH", prefix)
    entered = BLOB + '?plain=1&view="source"#L12'
    response = validation_client.client.post("/validate", data={"url": entered})

    assert [r.status_code for r in response.history] == [303]
    assert response.status_code == 415
    assert not respx.calls
    assert validation_client.outgoing == []
    assert validation_client.validations == []
    elements = _Elements(response.text)
    original_input = elements.by_id("url-input")
    assert original_input["value"] == entered
    assert "readonly" not in original_input
    assert "disabled" not in original_input
    assert [
        attrs for tag, attrs in elements.elements
        if tag == "input" and attrs.get("type") == "url"
    ] == [original_input]
    raw_link = elements.by_id("github-raw-url")
    assert raw_link["href"] == RAW
    assert "hidden" not in raw_link
    element_ids = {attrs.get("id") for _tag, attrs in elements.elements}
    assert "github-raw-details" not in element_ids
    assert "validate-raw-file" not in element_ids
    assert elements.by_id("validate-form")["action"] == (prefix + "/validate" if prefix else "validate")
    submit_buttons = [
        attrs for tag, attrs in elements.elements
        if tag == "button" and attrs.get("type") == "submit"
    ]
    assert submit_buttons
    assert all(attrs.get("name") != "raw" for attrs in submit_buttons)
    assert not any(
        tag == "input" and attrs.get("name") == "raw"
        for tag, attrs in elements.elements
    )
    assert elements.by_id("copy-raw-url")["type"] == "button"
    assert elements.by_id("copy-raw-status")["role"] == "status"
    assert "clipboard.writeText" in response.text
    assert "HTML file viewer" in response.text
    assert "raw file contents" in response.text
    plain_text = "".join(elements.text)
    assert "paste it into the Ontology URL box below" in plain_text
    assert "Ask Wol" in plain_text
    assert "You entered:" not in response.text
    guide_url = prefix + "/guide#server-config" if prefix else "guide#server-config"
    assert f'href="{guide_url}"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex"


@pytest.mark.parametrize("declared_base", [None, "https://example.org/published/ontology"])
@pytest.mark.parametrize("filename", ["ontology.ttl", "ontology%2Ettl", "ontology;version.1.ttl"])
@respx.mock
def test_manually_submitted_raw_url_follows_guarded_redirect_and_parses_correct_base(
    validation_client, declared_base, filename,
):
    blob = BLOB.rsplit("/", 1)[0] + "/" + filename
    raw = RAW.rsplit("/", 1)[0] + "/" + filename
    final = FINAL.rsplit("/", 1)[0] + "/" + filename.replace("%2E", ".")
    respx.get(raw).mock(return_value=httpx.Response(302, headers={"location": final}))
    body = TURTLE
    if declared_base:
        body = f"@base <{declared_base}> .\n".encode() + body
    respx.get(final).mock(return_value=httpx.Response(
        200, content=body, headers={"content-type": "text/plain; charset=utf-8"},
    ))
    entered = blob + "?plain=1#L12"
    response = _choose_raw_file(validation_client.client, entered)

    assert response.status_code == 200, response.text
    assert parse_qs(response.url.query.decode()) == {"url": [raw]}
    assert validation_client.outgoing == [raw, final]
    assert len(validation_client.validations) == 1
    validation = validation_client.validations[0]
    assert validation.base_uri == final
    assert validation.display_name == raw
    assert validation.report.parse_errors == []
    semantic_base = declared_base or final
    assert validation.report.imports.checks[0].iri == urljoin(semantic_base, "imports/other.ttl")
    assert semantic_base + "#Thing" in {
        entry.term for entry in validation.report.term_inventory.entries
    }
    links = [attrs.get("href") for tag, attrs in _Elements(response.text).elements if tag == "a"]
    assert raw in links
    events = usage.all_events(source=raw)
    assert len(events) == 1
    assert events[0]["source"] == raw
    assert events[0]["status"] == "200"


@respx.mock
def test_raw_response_still_rejects_html(validation_client):
    respx.get(RAW).mock(return_value=httpx.Response(
        200, text="<html><body>File viewer</body></html>", headers={"content-type": "text/html"},
    ))
    response = _choose_raw_file(validation_client.client)

    assert response.status_code == 415
    assert "HTML page" in response.text
    assert validation_client.validations == []


@respx.mock
def test_raw_response_still_has_to_parse_as_rdf(validation_client):
    respx.get(RAW).mock(return_value=httpx.Response(
        200, text="this is not valid turtle <<<", headers={"content-type": "text/plain"},
    ))
    response = _choose_raw_file(validation_client.client)

    assert response.status_code == 422
    assert validation_client.validations[0].report.parse_errors
    assert "Parse error:" in response.text


@respx.mock
def test_missing_raw_file_does_not_fall_back_to_another_ref(validation_client):
    respx.get(RAW).mock(return_value=httpx.Response(404))
    response = _choose_raw_file(validation_client.client)

    assert response.status_code == 422
    assert [str(call.request.url) for call in respx.calls] == [RAW]
    assert validation_client.validations == []


@respx.mock
def test_ordinary_url_on_other_host_is_validated_unchanged(validation_client):
    url = "https://example.org/owner/repo/blob/main/ontology.ttl"
    respx.get(url).mock(return_value=httpx.Response(
        200, content=TURTLE, headers={"content-type": "text/turtle"},
    ))
    response = validation_client.client.post("/validate", data={"url": url})

    assert response.status_code == 200, response.text
    assert validation_client.outgoing == [url]
    assert validation_client.validations[0].display_name == url
    assert validation_client.validations[0].base_uri == url
    assert usage.all_events()[0]["source"] == url


@respx.mock
def test_raw_query_parameter_cannot_bypass_manual_correction(validation_client):
    response = validation_client.client.get("/validate", params={"url": BLOB, "raw": "true"})

    assert response.status_code == 415
    assert not respx.calls
    assert validation_client.outgoing == []
    assert validation_client.validations == []
    assert _Elements(response.text).by_id("url-input")["value"] == BLOB
    assert usage.all_events()[0]["source"] == BLOB


@respx.mock
def test_raw_redirect_cannot_bypass_request_safety_hook(validation_client, monkeypatch):
    private_url = "http://127.0.0.1/internal/ontology.ttl"
    checked = []

    async def reject_private_redirect(request):
        checked.append(str(request.url))
        if request.url.host == "127.0.0.1":
            raise SSRFBlockedError("Blocked private redirect")

    monkeypatch.setattr(web, "block_private_network_requests", reject_private_redirect)
    respx.get(RAW).mock(return_value=httpx.Response(302, headers={"location": private_url}))
    response = _choose_raw_file(validation_client.client)

    assert response.status_code == 422
    assert checked == [RAW, private_url]
    assert "Blocked private redirect" in response.text
    assert [str(call.request.url) for call in respx.calls] == [RAW]
    assert validation_client.validations == []
