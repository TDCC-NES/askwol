"""Input policy is shared across file, URL, and explicit-content adapters."""

import pytest
from rdflib import Graph

from askwol.input_utils import (
    GUIDE_URL,
    InputError,
    github_raw_url,
    input_diagnostic,
    select_rdf_format,
    validate_base_uri,
)
from askwol.rdf_io import parse_rdf_bytes


@pytest.mark.parametrize("source,media_type,explicit,expected", [
    ("ontology.owl", "text/turtle", None, "turtle"),
    ("https://example.org/ontology.owl", "TEXT/TURTLE ; charset=utf-8", None, "turtle"),
    ("https://example.org/ontology", "application/x-turtle", None, "turtle"),
    ("https://example.org/ontology", "text/xml", None, "xml"),
    ("https://example.org/ontology", "application/json", None, "json-ld"),
    ("https://example.org/ontology%2Ettl", "text/plain", None, "turtle"),
    ("https://example.org/ontology;v1.ttl", "application/octet-stream", None, "turtle"),
    ("https://example.org/ontology.owl", "application/rdf+xml", "turtle", "turtle"),
    ("https://example.org/ontology", "application/unknown", "jsonld", "json-ld"),
    ("ontology.unknown", None, None, "turtle"),
    ("ontology.unknown", None, "application/rdf+xml", "xml"),
])
def test_format_selection_has_consistent_precedence(source, media_type, explicit, expected):
    assert select_rdf_format(source, content_type=media_type, format=explicit) == expected


@pytest.mark.parametrize("source,media_type,explicit,code", [
    ("https://example.org/ontology.ttl", "text/anot+turtle", None, "unsupported_media_type"),
    ("https://example.org/ontology", "text/plain", None, "unsupported_format"),
    ("ontology.ttl", None, "csv", "unsupported_format"),
    ("https://example.org/ontology.owl", "text/html", "xml", "html_instead_of_rdf"),
    ("ontology.owl", "application/xhtml+xml", None, "html_instead_of_rdf"),
    ("https://[invalid", None, None, "invalid_url"),
])
def test_format_errors_explain_how_to_correct_the_input(source, media_type, explicit, code):
    with pytest.raises(InputError) as captured:
        select_rdf_format(source, content_type=media_type, format=explicit)
    assert captured.value.code == code
    assert captured.value.message


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32"])
@pytest.mark.parametrize("html", [
    "<html><body>File viewer</body></html>",
    " \n<html><body>File viewer</body></html>",
    "<!DOCTYPE html><html><body>File viewer</body></html>",
    '<?xml version="1.0"?><!-- file viewer --><html xmlns="http://www.w3.org/1999/xhtml"/>',
    '<x:html xmlns:x="http://www.w3.org/1999/xhtml"/>',
])
def test_html_content_cannot_be_parsed_as_rdfxml(html, encoding):
    with pytest.raises(InputError) as captured:
        parse_rdf_bytes(Graph(), html.encode(encoding), format="xml")
    assert captured.value.code == "html_instead_of_rdf"
    assert "Raw" in captured.value.message
    assert captured.value.guide_url == GUIDE_URL


def test_html_literal_inside_rdf_is_not_an_html_document():
    content = b'@prefix ex: <https://example.org/> . ex:item ex:description "<html><body>Example</body></html>" .'
    assert len(parse_rdf_bytes(Graph(), content, format="turtle")) == 1


@pytest.mark.parametrize("format", ["turtle", "n3"])
def test_relative_subject_named_html_is_valid_rdf(format):
    content = b'<html> a <http://www.w3.org/2002/07/owl#Class> .'
    assert len(parse_rdf_bytes(Graph(), content, format=format, base_uri="https://example.org/")) == 1


def test_bare_html_document_still_has_informative_error_when_selected_as_turtle():
    with pytest.raises(InputError, match="HTML page"):
        parse_rdf_bytes(Graph(), b"<html><body>Viewer</body></html>", format="turtle")


def test_html_root_at_initial_inspection_boundary_is_rejected():
    content = b"<!--" + b" " * (65536 - 7) + b"--><html><body>Viewer</body></html>"
    with pytest.raises(InputError, match="HTML page"):
        parse_rdf_bytes(Graph(), content, format="xml")


def test_long_html_comment_does_not_hide_document_root():
    content = b"<!--" + b" " * 70000 + b"--><html><body>File viewer</body></html>"
    with pytest.raises(InputError, match="HTML page"):
        parse_rdf_bytes(Graph(), content, format="xml")


def test_rdfxml_typed_node_named_html_in_another_namespace_is_valid():
    content = b'<html xmlns="https://example.org/schema#" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" rdf:about="https://example.org/item"/>'
    assert len(parse_rdf_bytes(Graph(), content, format="xml")) == 1


@pytest.mark.parametrize("value", ["https://example.org/ontology#", "urn:example:ontology", "file:///tmp/ontology.ttl"])
def test_semantic_base_validation_does_not_restrict_absolute_iri_schemes(value):
    assert validate_base_uri(value) == value


@pytest.mark.parametrize("value", ["relative/base", "", "https://[bad", "https://example.org:bad/base", "https://example.org/a b", "https://example.org/a\n"])
def test_invalid_base_has_an_actionable_error(value):
    with pytest.raises(InputError) as captured:
        validate_base_uri(value)
    assert captured.value.code == "invalid_base_uri"


def test_github_suggestion_preserves_slash_refs_and_encoded_filenames():
    assert github_raw_url("https://github.com/owner/repo/blob/refs/heads/feature/new/ont%20ology.owl?plain=1#L2") == (
        "https://github.com/owner/repo/raw/refs/heads/feature/new/ont%20ology.owl"
    )
    assert github_raw_url("https://[bad") is None
    assert github_raw_url("https://github.com.evil.example/owner/repo/blob/main/ontology.owl") is None


def test_empty_parser_exception_still_has_an_actionable_diagnostic():
    result = input_diagnostic(ValueError(), "ontology.ttl")
    assert result["code"] == "invalid_rdf"
    assert result["message"]
    assert "input format" in result["message"]
