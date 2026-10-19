"""Parse RDF with a scoped loader for JSON-LD's secondary documents."""

from __future__ import annotations

import codecs
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

from rdflib import Dataset, Graph
from rdflib.plugins.parsers.jsonld import Parser as JsonLDParser
from rdflib.plugins.parsers.ntriples import NTGraphSink, W3CNTriplesParser
from rdflib.plugins.shared.jsonld.context import Context

from askwol.input_utils import (
    GUIDE_URL,
    InputError,
    github_raw_url,
    reject_html_content,
    select_rdf_format,
    validate_base_uri,
)
from askwol.network import DEFAULT_TIMEOUT, MAX_CONTEXT_BYTES, fetch_document
from askwol.parse_diagnostics import annotate_parse_error

MAX_CONTEXTS = 32


class _ContextLoader:
    def __init__(self, allow_network: bool, timeout: float | None = DEFAULT_TIMEOUT):
        self.allow_network = allow_network
        self.timeout = timeout
        self.documents: dict[str, dict] = {}
        self.final_urls: dict[str, str] = {}

    def load(self, url: str) -> dict:
        if url in self.documents:
            return self.documents[url]
        if not self.allow_network:
            raise InputError("offline_network_disabled", "Remote JSON-LD contexts are disabled in offline mode")
        if urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("JSON-LD contexts must use public HTTP(S) URLs")
        if len(self.documents) >= MAX_CONTEXTS:
            raise InputError("resource_limit", f"JSON-LD exceeds the {MAX_CONTEXTS}-context limit")
        timeout_options = {"timeout": self.timeout} if self.timeout != DEFAULT_TIMEOUT else {}
        content, final_url, content_type = fetch_document(
            url, accept="application/ld+json, application/json", max_bytes=MAX_CONTEXT_BYTES,
            **timeout_options,
        )
        select_rdf_format(final_url, content_type=content_type, format="json-ld")
        reject_html_content(content)
        try:
            document = json.loads(content)
            if not isinstance(document, dict) or "@context" not in document:
                raise ValueError("Remote JSON-LD document has no @context")
        except (ValueError, UnicodeError) as exc:
            raise annotate_parse_error(exc, "json-ld", source=final_url)
        self.documents[url] = document
        self.final_urls[url] = final_url
        return document


class _SafeContext(Context):
    def __init__(self, loader: _ContextLoader, **kwargs):
        self._loader = loader
        super().__init__(**kwargs)

    def _fetch_context(self, source, base, referenced_contexts):
        url = urljoin(base or self.doc_base or "", source)
        if url in referenced_contexts:
            error = ValueError("Recursive JSON-LD context inclusion")
            raise annotate_parse_error(error, "json-ld", source=self._loader.final_urls.get(url, url))
        referenced_contexts.add(url)
        return deepcopy(self._loader.load(url))

    def _prep_sources(self, base, inputs, sources, referenced_contexts, in_source_url=None):
        for source in inputs:
            if isinstance(source, str):
                url = urljoin(base or self.doc_base or "", source)
                document = self._fetch_context(source, base, referenced_contexts)
                final_url = self._loader.final_urls[url]
                self._prep_sources(final_url, [document], sources, referenced_contexts, final_url)
            else:
                super()._prep_sources(base, [source], sources, referenced_contexts, in_source_url)

    def _read_source(self, source, source_url=None, referenced_contexts=None):
        try:
            if isinstance(source.get("@import"), str):
                source = {**source, "@import": urljoin(source_url or self.base or "", source["@import"])}
            return super()._read_source(source, source_url, referenced_contexts)
        except Exception as exc:
            # RDFLib merges imported and local definitions before processing
            # them. Without a known origin, do not blame the parent context.
            origin = None if isinstance(source, dict) and isinstance(source.get("@import"), str) else source_url
            raise annotate_parse_error(exc, "json-ld", source=origin)

    def _subcontext(self, source, propagate):
        # RDFLib constructs Context directly here; keep the scoped loader in
        # term/type-scoped contexts instead of falling back to urllib.
        ctx = _SafeContext(self._loader, version=self.version)
        ctx.propagate = propagate
        ctx.parent = self
        ctx.language = self.language
        ctx.vocab = self.vocab
        ctx.base = self.base
        ctx.doc_base = self.doc_base
        ctx._alias = {key: aliases[:] for key, aliases in self._alias.items()}
        ctx.terms = self.terms.copy()
        ctx._lookup = self._lookup.copy()
        ctx._prefixes = self._prefixes.copy()
        ctx._context_cache = self._context_cache
        ctx.load(source)
        return ctx


class _SafeJsonLDParser(JsonLDParser):
    def _add_to_graph(self, dataset, graph, context, node, topcontext=False):
        # A null/empty nested context resets expansion state, but must retain
        # the document-loading policy as well.
        if isinstance(node, dict) and not topcontext and "@context" in node and not node["@context"]:
            context = _SafeContext(context._loader, base=context.doc_base)
            node = {key: value for key, value in node.items() if key != "@context"}
        return super()._add_to_graph(dataset, graph, context, node, topcontext)


class _JsonLDDataset(Dataset):
    # RDFLib's JSON-LD expansion still reads this legacy property. Keep its
    # alias local while using Dataset's supported default_graph interface.
    @property
    def default_context(self):
        return self.default_graph

    @default_context.setter
    def default_context(self, graph):
        self.default_graph = graph


class _LocatedNTriplesParser(W3CNTriplesParser):
    """Track logical line numbers while RDFLib parses N-Triples."""

    line_number = 0

    def readline(self):
        line = super().readline()
        if line is not None:
            self.line_number += 1
        return line


def parse_rdf_bytes(
    graph: Graph, content: bytes, *, format: str, base_uri: str | None = None,
    allow_network: bool = True, timeout: float | None = DEFAULT_TIMEOUT,
) -> Graph:
    format = select_rdf_format("", format=format)
    reject_html_content(content, format=format)
    if base_uri is not None:
        validate_base_uri(base_uri)
    nt_parser = None
    try:
        if format == "json-ld":
            context = _SafeContext(_ContextLoader(allow_network, timeout), base=base_uri or graph.absolutize(""))
            dataset = _JsonLDDataset(store=graph.store)
            dataset.default_graph = graph
            _SafeJsonLDParser().parse(json.loads(content), context, dataset)
        elif format == "nt":
            nt_parser = _LocatedNTriplesParser(NTGraphSink(graph))
            with codecs.getreader("utf-8")(BytesIO(content)) as stream:
                nt_parser.parse(stream)
        else:
            graph.parse(BytesIO(content), format=format, publicID=base_uri)
    except Exception as exc:
        # A bare <html> can also start valid Turtle. Classify it only after
        # parsing fails. JSON-LD context errors must retain their own source.
        if format != "json-ld":
            reject_html_content(content)
        raise annotate_parse_error(exc, format, line=nt_parser.line_number if nt_parser else None)
    return graph


def load_rdf_source(
    graph: Graph, source: str | Path, *, base_uri: str | None, allow_network: bool,
    format: str | None = None, timeout: float | None = DEFAULT_TIMEOUT,
) -> None:
    source_text = str(source)
    try:
        parsed_source = urlsplit(source_text)
        scheme = parsed_source.scheme
        if scheme in ("http", "https"):
            if not parsed_source.hostname or any(char.isspace() or ord(char) < 32 for char in source_text):
                raise ValueError("Missing or invalid host")
            _ = parsed_source.port
    except ValueError as exc:
        raise InputError("invalid_url", "The source URL is malformed. Check its address and try again.") from exc
    if base_uri is not None:
        validate_base_uri(base_uri)
    if scheme in ("http", "https"):
        if not allow_network:
            raise InputError("offline_network_disabled", "Remote ontology sources are disabled in offline mode")
        raw_url = github_raw_url(source_text)
        if raw_url:
            raise InputError(
                "github_file_viewer",
                "This GitHub URL opens an HTML file viewer. Ontology tools need raw RDF contents. "
                "On GitHub, select Raw and copy that URL, then submit or download the raw file.",
                suggested_url=raw_url, guide_url=GUIDE_URL,
            )
        timeout_options = {"timeout": timeout} if timeout != DEFAULT_TIMEOUT else {}
        content, final_url, content_type = fetch_document(
            source_text, accept="text/turtle, application/rdf+xml;q=0.9, application/ld+json;q=0.8, "
            "application/n-triples;q=0.7, text/n3;q=0.6, */*;q=0.1",
            **timeout_options,
        )
        format = select_rdf_format(final_url, content_type=content_type, format=format)
        base_uri = base_uri or final_url
    else:
        if scheme and scheme != "file" and "://" in source_text:
            raise InputError("invalid_url", "Remote ontology sources must use a public HTTP(S) URL.")
        path = Path(url2pathname(parsed_source.path)) if scheme == "file" else Path(source)
        content = path.read_bytes()
        format = select_rdf_format(str(path), format=format)
        base_uri = base_uri or path.resolve().as_uri()
    timeout_options = {"timeout": timeout} if timeout != DEFAULT_TIMEOUT else {}
    parse_rdf_bytes(graph, content, format=format, base_uri=base_uri, allow_network=allow_network, **timeout_options)
