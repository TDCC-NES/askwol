"""Blocking syntax errors retain reliable parser details across interfaces."""

import json
from io import BytesIO
from xml.sax import SAXParseException

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from rdflib import Graph
from rdflib.compare import isomorphic
from rdflib.exceptions import ParserError
from rdflib.plugins.parsers.notation3 import BadSyntax
from rdflib.plugins.shared.jsonld.errors import INVALID_CONTEXT_ENTRY, JSONLDException

from askwol import network, pipeline, validation_runner, web
from askwol.agent_api import compact_report
from askwol.parser import parse_ontology
from askwol.parse_diagnostics import parse_diagnostic
from askwol.rdf_io import parse_rdf_bytes

PREFIX = "@prefix ex: <https://example.org/> .\n"
MALFORMED_TURTLE = PREFIX + 'ex:s ex:p "café" .\nex:s ex:p .\nex:s ex:p .\n'


@pytest.mark.parametrize(("format", "content", "position", "exception"), [
    ("turtle", MALFORMED_TURTLE, (3, 10), BadSyntax),
    ("n3", PREFIX + 'ex:s ex:p """café\n雪""" .\nex:s ex:p .\n', (4, 10), BadSyntax),
    ("xml", '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
     '<rdf:Description rdf:about="https://example.org/A">\n</rdf:RDF>', (3, 3), SAXParseException),
    ("json-ld", '{\n  "@id": "https://example.org/é",\n  "@type":\n}', (4, 1), json.JSONDecodeError),
    ("nt", '<https://example.org/s> <https://example.org/p> "café" .\n# comment\n'
     '<https://example.org/s> <https://example.org/p> .\n', (3, None), ParserError),
])
async def test_supported_syntax_errors_stop_before_checks_and_keep_public_types(
    tmp_path, monkeypatch, format, content, position, exception,
):
    path = tmp_path / "temporary-upload.data"
    path.write_bytes(content.encode())

    def unexpected(*_args, **_kwargs):
        pytest.fail("Syntax failures must stop before checks or diagram generation")

    monkeypatch.setattr(pipeline, "build_mermaid", unexpected)
    monkeypatch.setattr(pipeline, "check_lang_tags", unexpected)
    phases = []
    report, diagram = await pipeline.run_full_validation(
        path, display_name="ontology.data", format=format, skip_resolution=True, phase=phases.append,
    )

    error = report.input_error
    assert error.code == "invalid_rdf"
    assert error.format == format
    assert (error.line, error.column) == position
    assert error.source is None
    assert error.detail and "\\x" not in error.detail
    assert "input format" in error.guidance
    assert "further" in error.guidance.lower()
    assert error.guide_url.endswith("#rdf-syntax")
    assert report.file == "ontology.data"
    assert str(path) not in error.model_dump_json()
    assert report.parse_errors == [error.message]
    assert phases == ["parsing"]
    assert diagram == "" and report.term_inventory is None and report.reasoner is None
    compact = compact_report(report)
    assert compact.input_error == error
    assert all(check.status == "skipped" for check in compact.checks)

    # Both public entry points must still expose RDFLib's original exception type.
    with pytest.raises(exception):
        parse_ontology(path, format=format, allow_network=False)
    with pytest.raises(exception):
        parse_rdf_bytes(Graph(), content.encode(), format=format, allow_network=False)


async def test_turtle_backtracking_uses_the_character_offset_not_parser_line_counter(tmp_path):
    path = tmp_path / "ontology.ttl"
    path.write_text(PREFIX + "ex:s ex:p [\n")
    report, _diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    # RDFLib's line counter has moved past '[', the actual stopping position.
    assert (report.input_error.line, report.input_error.column) == (2, 11)


async def test_unfinished_turtle_has_no_guessed_location(tmp_path):
    path = tmp_path / "ontology.ttl"
    path.write_text(PREFIX + "ex:s ex:p (")
    report, diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    error = report.input_error
    assert error.code == "invalid_rdf" and error.format == "turtle"
    assert error.line is None and error.column is None
    assert error.message and error.guidance
    assert "string index out of range" not in error.model_dump_json()
    assert diagram == ""


@respx.mock
async def test_malformed_remote_context_identifies_its_final_url(tmp_path, monkeypatch):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *_args:
                        [(2, 1, 6, "", ("93.184.216.34", 0))])
    monkeypatch.setattr("rdflib.parser._urlopen", lambda *_args: pytest.fail("unguarded request"))
    context = "https://example.org/context"
    final = "https://example.org/v2/context.jsonld"
    respx.get(context).mock(return_value=httpx.Response(302, headers={"location": final}))
    respx.get(final).mock(return_value=httpx.Response(
        200, text='{\n  "@context":\n}', headers={"content-type": "application/ld+json"},
    ))
    path = tmp_path / "ontology.jsonld"
    path.write_text(json.dumps({"@context": context, "@id": "https://example.org/ontology"}))

    report, _diagram = await pipeline.run_full_validation(path)
    error = report.input_error
    assert error.code == "invalid_rdf" and error.format == "json-ld"
    assert error.source == final
    assert (error.line, error.column) == (3, 1)
    assert report.file == str(path)
    with pytest.raises(json.JSONDecodeError):
        parse_ontology(path)


def test_content_api_preserves_syntax_diagnostic_without_worker(client):
    full = client.post("/api/validate/content", json={"format": "turtle", "content": MALFORMED_TURTLE})
    compact = client.post("/api/validate/content?compact=true", json={
        "format": "turtle", "content": MALFORMED_TURTLE,
    })
    assert full.status_code == compact.status_code == 422
    error = full.json()["input_error"]
    assert compact.json()["input_error"] == error
    assert (error["line"], error["column"]) == (3, 10)
    assert error["detail"] and error["guidance"]


@pytest.fixture
def client(monkeypatch):
    async def offline_validation(path, display_name, *, kind, base_uri=None):
        return await pipeline.run_full_validation(
            path, display_name=display_name, base_uri=base_uri, skip_resolution=True,
        )

    monkeypatch.setattr(web, "run_isolated_validation", offline_validation)
    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 0)
    return TestClient(web.app)


async def test_upload_api_preserves_diagnostics_through_real_worker(monkeypatch):
    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 0)
    monkeypatch.setattr(validation_runner, "_validation_slots_in_use", 0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://test") as client:
        responses = []
        for compact in (False, True):
            responses.append(await client.post(
                "/api/validate", params={"compact": str(compact).lower()},
                files={"file": ("user-ontology.ttl", MALFORMED_TURTLE.encode(), "text/turtle")},
            ))
    assert [response.status_code for response in responses] == [422, 422]
    full, compact = [response.json() for response in responses]
    assert compact["input_error"] == full["input_error"]
    error = full["input_error"]
    assert (error["line"], error["column"]) == (3, 10)
    assert error["format"] == "turtle" and error["source"] is None
    assert error["detail"] and error["guidance"]
    assert full["file"] == compact["file"] == "user-ontology.ttl"
    assert all(check["status"] == "skipped" for check in compact["checks"])
    assert validation_runner._validation_slots_in_use == 0


@pytest.mark.parametrize(("exception", "code"), [
    (httpx.ConnectError("Connection refused"), "network_error"),
    (httpx.ReadTimeout("Timed out"), "fetch_timeout"),
])
async def test_retrieval_failures_do_not_acquire_syntax_locations(monkeypatch, exception, code):
    def fail(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr(pipeline, "parse_ontology", fail)
    report, _diagram = await pipeline.run_full_validation("https://example.org/ontology.ttl")
    assert report.input_error.code == code
    assert report.input_error.line is None and report.input_error.column is None
    assert report.input_error.guide_url is None


async def test_html_keeps_its_existing_diagnostic_and_help_link(tmp_path):
    path = tmp_path / "ontology.owl"
    path.write_text("<html><body>File viewer</body></html>")
    report, _diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    assert report.input_error.code == "html_instead_of_rdf"
    assert report.input_error.guide_url.endswith("#server-config")
    assert report.input_error.line is None and report.input_error.column is None


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"], ids=["LF", "CR", "CRLF"])
async def test_ntriples_adapter_preserves_graph_and_counts_long_lines(tmp_path, newline):
    # The literal spans several RDFLib read buffers; blank labels must retain identity.
    content = newline.join([
        "# Ontology terms",
        "",
        '_:shared <https://example.org/label> "' + "é雪" * 4096 + '" .',
        "_:shared <https://example.org/next> _:other .",
        '_:other <https://example.org/label> "Child" .',
    ]).encode()
    native = Graph().parse(BytesIO(content), format="nt")
    actual = parse_rdf_bytes(Graph(), content, format="nt", allow_network=False)
    assert len(actual) == 3 and isomorphic(actual, native)

    path = tmp_path / "ontology.nt"
    path.write_bytes(content + newline.encode() + b"<https://example.org/s> <https://example.org/p> .")
    report, _diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    assert report.input_error.code == "invalid_rdf"
    assert report.input_error.line == 6 and report.input_error.column is None


async def test_utf16_rdfxml_uses_xml_parser_coordinates(tmp_path):
    path = tmp_path / "ontology.rdf"
    path.write_bytes(('<?xml version="1.0" encoding="UTF-16"?>\n'
                      '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
                      '<rdf:Description rdf:about="https://example.org/é">\n'
                      '</rdf:RDF>').encode("utf-16"))
    report, _diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    error = report.input_error
    assert error.code == "invalid_rdf" and error.format == "xml"
    assert (error.line, error.column) == (4, 3)
    assert error.detail and error.source is None


async def test_inline_jsonld_context_processing_error_has_no_textual_location(tmp_path):
    path = tmp_path / "ontology.jsonld"
    path.write_text(json.dumps({"@context": 123, "@id": "https://example.org/ontology"}))
    report, _diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    error = report.input_error
    assert error.code == "invalid_rdf" and error.format == "json-ld"
    assert error.message and error.source is None
    assert error.line is None and error.column is None


@respx.mock
async def test_remote_jsonld_context_processing_error_retains_final_source(tmp_path, monkeypatch):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *_args:
                        [(2, 1, 6, "", ("93.184.216.34", 0))])
    context = "https://example.org/context"
    final = "https://example.org/v2/context.jsonld"
    respx.get(context).mock(return_value=httpx.Response(302, headers={"location": final}))
    respx.get(final).mock(return_value=httpx.Response(
        200, json={"@context": {"term": {"@id": {}}}},
        headers={"content-type": "application/ld+json"},
    ))
    path = tmp_path / "ontology.jsonld"
    path.write_text(json.dumps({"@context": context, "@id": "https://example.org/ontology"}))
    report, _diagram = await pipeline.run_full_validation(path)
    error = report.input_error
    assert error.code == "invalid_rdf" and error.format == "json-ld"
    assert error.message and error.source == final
    assert error.line is None and error.column is None


async def test_json_syntax_with_cr_only_newlines_uses_character_position(tmp_path):
    path = tmp_path / "ontology.jsonld"
    path.write_bytes(b'{\r  "@id": "https://example.org/ontology",\r  "@type":\r}')
    report, _diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    assert report.input_error.code == "invalid_rdf"
    assert (report.input_error.line, report.input_error.column) == (4, 1)


async def test_ntriples_decode_failure_does_not_use_buffered_parser_line(tmp_path):
    path = tmp_path / "ontology.nt"
    path.write_bytes(b'<https://example.org/s> <https://example.org/p> "Term" .\n' * 100 + b'\xff')
    report, _diagram = await pipeline.run_full_validation(path, skip_resolution=True)
    error = report.input_error
    assert error.code == "invalid_rdf" and error.format == "nt"
    assert error.line is None and error.column is None
    assert "encoding" in error.detail
    with pytest.raises(UnicodeDecodeError):
        parse_ontology(path, allow_network=False)


@respx.mock
async def test_jsonld_singleton_errors_do_not_retain_another_documents_source(tmp_path, monkeypatch):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *_args:
                        [(2, 1, 6, "", ("93.184.216.34", 0))])
    path = tmp_path / "ontology.jsonld"
    for index in range(2):
        context = f"https://example.org/context-{index}"
        final = f"https://example.org/v2/context-{index}.jsonld"
        respx.get(context).mock(return_value=httpx.Response(302, headers={"location": final}))
        respx.get(final).mock(return_value=httpx.Response(
            200, json={"@context": {"@import": 42}}, headers={"content-type": "application/ld+json"},
        ))
        path.write_text(json.dumps({"@context": context, "@id": "https://example.org/ontology"}))
        with pytest.raises(JSONLDException) as captured:
            parse_ontology(path)
        assert captured.value is not INVALID_CONTEXT_ENTRY
        assert parse_diagnostic(captured.value)["source"] == final
        assert parse_diagnostic(INVALID_CONTEXT_ENTRY) == {}
        report, _diagram = await pipeline.run_full_validation(path)
        assert report.input_error.source == final
        assert report.input_error.line is None and report.input_error.column is None


@respx.mock
async def test_imported_jsonld_processing_failure_does_not_blame_parent_context(tmp_path, monkeypatch):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *_args:
                        [(2, 1, 6, "", ("93.184.216.34", 0))])
    parent = "https://example.org/context"
    parent_final = "https://example.org/v2/context.jsonld"
    imported = "https://example.org/v2/terms.jsonld"
    respx.get(parent).mock(return_value=httpx.Response(302, headers={"location": parent_final}))
    respx.get(parent_final).mock(return_value=httpx.Response(
        200, json={"@context": {"@import": "terms.jsonld", "local": "https://example.org/local"}},
        headers={"content-type": "application/ld+json"},
    ))
    respx.get(imported).mock(return_value=httpx.Response(
        200, json={"@context": {"bad": {"@id": {}}}}, headers={"content-type": "application/ld+json"},
    ))
    path = tmp_path / "ontology.jsonld"
    path.write_text(json.dumps({"@context": parent, "@id": "https://example.org/ontology"}))
    report, _diagram = await pipeline.run_full_validation(path)
    error = report.input_error
    assert error.code == "invalid_rdf" and error.format == "json-ld"
    assert error.source in (None, imported)
    assert error.line is None and error.column is None
