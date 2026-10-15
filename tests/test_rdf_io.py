"""Secondary JSON-LD documents obey the same outbound policy as ontologies."""

import json

import httpx
import pytest
import respx
from rdflib import RDF, RDFS, Graph, Literal, URIRef

from askwol import network, rdf_io
from askwol.input_utils import InputError
from askwol.parser import parse_ontology
from askwol.pipeline import run_full_validation
from askwol.resolver import _try_parse_rdf


@pytest.fixture(autouse=True)
def controlled_dns(monkeypatch):
    def lookup(host, *_args):
        ip = "127.0.0.1" if host in ("localhost", "127.0.0.1") else "93.184.216.34"
        return [(2, 1, 6, "", (ip, 0))]
    monkeypatch.setattr(network.socket, "getaddrinfo", lookup)
    monkeypatch.setattr("rdflib.parser._urlopen", lambda *_args: pytest.fail("unguarded urllib request"))


def write_jsonld(tmp_path, document):
    path = tmp_path / "ontology.jsonld"
    path.write_text(json.dumps(document))
    return path


@pytest.mark.parametrize("location", ["http://127.0.0.1/context", "file:///private/context.jsonld"])
@pytest.mark.parametrize("nested", [False, True])
def test_jsonld_contexts_cannot_load_private_or_file_locations(tmp_path, location, nested):
    node = {"@context": location, "@id": "https://example.org/Term", "label": "Term"}
    if nested:
        node = {
            "@context": {"child": "https://example.org/child"},
            "@id": "https://example.org/root",
            "child": {"@context": None, "https://example.org/child": node},
        }
    path = write_jsonld(tmp_path, node)
    with pytest.raises((ValueError, network.SSRFBlockedError), match="public HTTP|private/internal"):
        parse_ontology(path)


def test_resolver_jsonld_context_cannot_bypass_httpx_guard():
    content = json.dumps({"@context": "http://127.0.0.1/context", "@id": "https://example.org/Term"}).encode()
    _graph, valid = _try_parse_rdf(content, base_uri="https://example.org/ontology.jsonld")
    assert valid is False


def test_jsonld_cannot_import_a_private_context(tmp_path):
    path = write_jsonld(tmp_path, {"@context": {"@import": "http://127.0.0.1/context"}})
    with pytest.raises(network.SSRFBlockedError, match="private/internal"):
        parse_ontology(path)


def test_jsonld_cannot_read_an_existing_local_context(tmp_path):
    context = tmp_path / "context.jsonld"
    context.write_text(json.dumps({"@context": {"label": str(RDFS.label)}}))
    path = write_jsonld(tmp_path, {
        "@context": context.as_uri(), "@id": "https://example.org/Term", "label": "Term",
    })
    with pytest.raises(ValueError, match="public HTTP"):
        parse_ontology(path)


@respx.mock
def test_public_context_redirects_and_relative_nested_contexts_work(tmp_path):
    respx.get("https://example.org/context").mock(return_value=httpx.Response(
        302, headers={"location": "/v2/context.json"},
    ))
    respx.get("https://example.org/v2/context.json").mock(return_value=httpx.Response(
        200, json={"@context": ["terms.json", {"label": str(RDFS.label)}]},
    ))
    nested = respx.get("https://example.org/v2/terms.json").mock(return_value=httpx.Response(
        200, json={"@context": {"ex": "https://example.org/"}},
    ))
    path = write_jsonld(tmp_path, {
        "@context": "https://example.org/context", "@id": "ex:Term", "@type": "ex:Class", "label": "Term",
    })
    graph = parse_ontology(path).graph
    assert (URIRef("https://example.org/Term"), RDF.type, URIRef("https://example.org/Class")) in graph
    assert str(graph.value(URIRef("https://example.org/Term"), RDFS.label)) == "Term"
    assert nested.call_count == 1


@respx.mock
def test_public_context_cannot_redirect_to_private_address(tmp_path):
    respx.get("https://example.org/context").mock(return_value=httpx.Response(
        302, headers={"location": "http://127.0.0.1/context"},
    ))
    path = write_jsonld(tmp_path, {"@context": "https://example.org/context"})
    with pytest.raises(network.SSRFBlockedError, match="private/internal"):
        parse_ontology(path)


@respx.mock
def test_scoped_context_uses_guarded_loader(tmp_path):
    respx.get("https://example.org/context").mock(return_value=httpx.Response(
        200, json={"@context": {"label": str(RDFS.label)}},
    ))
    path = write_jsonld(tmp_path, {
        "@context": {"child": {"@id": "https://example.org/child", "@context": "https://example.org/context"}},
        "@id": "https://example.org/root", "child": {"@id": "https://example.org/Term", "label": "Term"},
    })
    graph = parse_ontology(path).graph
    assert str(graph.value(URIRef("https://example.org/Term"), RDFS.label)) == "Term"


@respx.mock
def test_remote_context_size_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(rdf_io, "MAX_CONTEXT_BYTES", 16)
    respx.get("https://example.org/context").mock(return_value=httpx.Response(
        200, json={"@context": {"label": str(RDFS.label)}},
    ))
    path = write_jsonld(tmp_path, {"@context": "https://example.org/context"})
    with pytest.raises(ValueError, match="byte limit"):
        parse_ontology(path)


@respx.mock
def test_recursive_remote_contexts_are_rejected(tmp_path):
    respx.get("https://example.org/context").mock(return_value=httpx.Response(
        200, json={"@context": "https://example.org/context"},
    ))
    path = write_jsonld(tmp_path, {"@context": "https://example.org/context"})
    with pytest.raises(ValueError, match="Recursive"):
        parse_ontology(path)


@respx.mock
def test_remote_context_count_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(rdf_io, "MAX_CONTEXTS", 2)
    for index in range(2):
        respx.get(f"https://example.org/context/{index}").mock(return_value=httpx.Response(
            200, json={"@context": f"https://example.org/context/{index + 1}"},
        ))
    path = write_jsonld(tmp_path, {"@context": "https://example.org/context/0"})
    with pytest.raises(ValueError, match="context limit"):
        parse_ontology(path)


async def test_offline_pipeline_rejects_remote_context_but_accepts_inline(tmp_path):
    remote = write_jsonld(tmp_path, {"@context": "https://example.org/context"})
    report, _diagram = await run_full_validation(remote, skip_resolution=True, include_mermaid=False)
    assert report.parse_errors and "offline" in report.parse_errors[0]
    inline = write_jsonld(tmp_path, {
        "@context": {"ex": "https://example.org/", "owl": "http://www.w3.org/2002/07/owl#"},
        "@id": "ex:ontology", "@type": "owl:Ontology",
    })
    report, _diagram = await run_full_validation(inline, skip_resolution=True, include_mermaid=False)
    assert report.parse_errors == []


def test_jsonld_keeps_default_and_named_graphs_separate(tmp_path):
    value = URIRef("https://example.org/value")
    default_term = URIRef("https://example.org/default")
    named_term = URIRef("https://example.org/inside")
    path = write_jsonld(tmp_path, [
        {"@id": str(default_term), str(value): "Default graph"},
        {"@id": "https://example.org/named", "@graph": [
            {"@id": str(named_term), str(value): "Named graph"},
        ]},
    ])
    graph = parse_ontology(path, allow_network=False).graph
    assert set(graph) == {(default_term, value, Literal("Default graph"))}
    named = Graph(store=graph.store, identifier=URIRef("https://example.org/named"))
    assert set(named) == {(named_term, value, Literal("Named graph"))}


@pytest.mark.parametrize("content_type", ["TEXT/TURTLE ; charset=utf-8", "application/x-turtle"])
@respx.mock
def test_remote_mime_type_takes_precedence_over_misleading_suffix(content_type):
    url = "https://example.org/ontology.owl"
    respx.get(url).mock(return_value=httpx.Response(
        200, content=b'<https://example.org/A> a <http://www.w3.org/2002/07/owl#Class> .',
        headers={"content-type": content_type},
    ))
    assert len(parse_ontology(url).graph) == 1


@pytest.mark.parametrize("content_type", ["text/html", "text/plain"])
@respx.mock
def test_remote_html_is_rejected_even_with_owl_filename(content_type):
    url = "https://example.org/ontology.owl"
    respx.get(url).mock(return_value=httpx.Response(
        200, content=b'<html><body>File viewer</body></html>', headers={"content-type": content_type},
    ))
    with pytest.raises(InputError) as captured:
        parse_ontology(url)
    assert captured.value.code == "html_instead_of_rdf"


@respx.mock
def test_python_github_viewer_url_explains_raw_link_without_fetching():
    url = "https://github.com/example/ontology/blob/feature/new/ontology.owl"
    with pytest.raises(InputError) as captured:
        parse_ontology(url)
    assert captured.value.code == "github_file_viewer"
    assert captured.value.suggested_url == "https://github.com/example/ontology/raw/feature/new/ontology.owl"
    assert not respx.calls


@pytest.mark.parametrize("timeout", [1.25, None])
@respx.mock
def test_source_and_secondary_context_fetch_use_requested_timeout(timeout):
    ontology = "https://example.org/ontology.jsonld"
    context = "https://example.org/context.jsonld"
    timeouts = []

    def response(request):
        timeouts.append(request.extensions["timeout"])
        document = {"@context": context, "@id": "https://example.org/Thing", "label": "Thing"}
        if str(request.url) == context:
            document = {"@context": {"label": str(RDFS.label)}}
        return httpx.Response(200, json=document, headers={"content-type": "application/ld+json"})

    respx.get(ontology).mock(side_effect=response)
    respx.get(context).mock(side_effect=response)
    graph = parse_ontology(ontology, timeout=timeout).graph
    assert len(graph) == 1
    assert timeouts == [httpx.Timeout(timeout).as_dict()] * 2


@respx.mock
def test_context_serving_html_gets_input_diagnostic_before_json_parsing(tmp_path):
    context = "https://example.org/context.jsonld"
    respx.get(context).mock(return_value=httpx.Response(
        200, text='<html><body>Context viewer</body></html>', headers={"content-type": "text/html"},
    ))
    path = write_jsonld(tmp_path, {"@context": context, "@id": "https://example.org/Thing"})
    with pytest.raises(InputError) as captured:
        parse_ontology(path)
    assert captured.value.code == "html_instead_of_rdf"


def test_parser_rejects_malformed_url_before_fetching():
    with pytest.raises(InputError) as captured:
        parse_ontology("https://[bad")
    assert captured.value.code == "invalid_url"
