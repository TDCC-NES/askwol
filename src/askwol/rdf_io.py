"""Parse RDF with a scoped loader for JSON-LD's secondary documents."""

from __future__ import annotations

import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

from rdflib import Dataset, Graph
from rdflib.plugins.parsers.jsonld import Parser as JsonLDParser
from rdflib.plugins.shared.jsonld.context import Context
from rdflib.util import guess_format

from askwol.network import MAX_CONTEXT_BYTES, fetch_document

MAX_CONTEXTS = 32


class _ContextLoader:
    def __init__(self, allow_network: bool):
        self.allow_network = allow_network
        self.documents: dict[str, dict] = {}
        self.final_urls: dict[str, str] = {}

    def load(self, url: str) -> dict:
        if url in self.documents:
            return self.documents[url]
        if not self.allow_network:
            raise ValueError("Remote JSON-LD contexts are disabled in offline mode")
        if urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("JSON-LD contexts must use public HTTP(S) URLs")
        if len(self.documents) >= MAX_CONTEXTS:
            raise ValueError(f"JSON-LD exceeds the {MAX_CONTEXTS}-context limit")
        content, final_url, _content_type = fetch_document(
            url, accept="application/ld+json, application/json", max_bytes=MAX_CONTEXT_BYTES,
        )
        document = json.loads(content)
        if not isinstance(document, dict) or "@context" not in document:
            raise ValueError("Remote JSON-LD document has no @context")
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
            raise ValueError("Recursive JSON-LD context inclusion")
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
        if isinstance(source.get("@import"), str):
            source = {**source, "@import": urljoin(source_url or self.base or "", source["@import"])}
        return super()._read_source(source, source_url, referenced_contexts)

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


def parse_rdf_bytes(
    graph: Graph, content: bytes, *, format: str, base_uri: str | None = None,
    allow_network: bool = True,
) -> Graph:
    if format in ("json-ld", "application/ld+json"):
        context = _SafeContext(_ContextLoader(allow_network), base=base_uri or graph.absolutize(""))
        dataset = _JsonLDDataset(store=graph.store)
        dataset.default_graph = graph
        _SafeJsonLDParser().parse(json.loads(content), context, dataset)
    else:
        graph.parse(BytesIO(content), format=format, publicID=base_uri)
    return graph


def load_rdf_source(graph: Graph, source: str | Path, *, base_uri: str | None, allow_network: bool) -> None:
    source_text = str(source)
    scheme = urlsplit(source_text).scheme
    if scheme in ("http", "https"):
        if not allow_network:
            raise ValueError("Remote ontology sources are disabled in offline mode")
        content, final_url, content_type = fetch_document(
            source_text, accept="text/turtle, application/rdf+xml, application/ld+json",
        )
        format = guess_format(urlsplit(final_url).path) or content_type.split(";", 1)[0] or "turtle"
        base_uri = base_uri or final_url
    else:
        path = Path(url2pathname(urlsplit(source_text).path)) if scheme == "file" else Path(source)
        content = path.read_bytes()
        format = guess_format(path.name) or "turtle"
        base_uri = base_uri or path.resolve().as_uri()
    parse_rdf_bytes(graph, content, format=format, base_uri=base_uri, allow_network=allow_network)
