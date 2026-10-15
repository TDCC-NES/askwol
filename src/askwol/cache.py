"""In-memory cache for fetched remote ontology graphs."""

from __future__ import annotations

import time
from dataclasses import dataclass

from rdflib import Graph

from askwol.models import NamespaceCheck, Status


@dataclass
class _CacheEntry:
    graph: Graph | None
    fetched_at: float
    error: str | None = None
    resolution: NamespaceCheck | None = None


class OntologyCache:
    """Simple in-memory cache for remote ontology graphs.

    Entries expire after `ttl` seconds (default: 1 hour).
    """

    def __init__(self, ttl: float = 3600.0) -> None:
        self._ttl = ttl
        self._store: dict[str, _CacheEntry] = {}

    def _get_entry(self, uri: str) -> _CacheEntry | None:
        entry = self._store.get(uri)
        if entry is None:
            return None
        if time.monotonic() - entry.fetched_at > self._ttl:
            del self._store[uri]
            return None
        return entry

    def get(self, uri: str) -> Graph | None:
        """Return cached graph for URI, or None if missing/expired."""
        entry = self._get_entry(uri)
        return entry.graph if entry is not None else None

    def get_error(self, uri: str) -> str | None:
        """Return cached error for a URI that failed to fetch."""
        entry = self._get_entry(uri)
        return entry.error if entry is not None else None

    def get_resolution(self, uri: str, prefix: str) -> NamespaceCheck | None:
        """Return a fresh result, preserving retrieval details on cache hits."""
        entry = self._get_entry(uri)
        if entry is None:
            return None
        if entry.resolution is not None:
            return entry.resolution.model_copy(update={"prefix": prefix, "uri": uri})
        return NamespaceCheck(
            prefix=prefix, uri=uri, status=Status.FAIL if entry.error else Status.OK,
            is_valid_rdf=entry.graph is not None, error=entry.error,
        )

    def has(self, uri: str) -> bool:
        """Check if URI is cached (and not expired)."""
        return self._get_entry(uri) is not None

    def put(
        self, uri: str, graph: Graph | None, error: str | None = None,
        *, resolution: NamespaceCheck | None = None,
    ) -> None:
        """Cache a graph (or error) for a namespace URI."""
        self._store[uri] = _CacheEntry(
            graph=graph,
            fetched_at=time.monotonic(),
            error=error if error is not None else resolution.error if resolution is not None else None,
            resolution=resolution.model_copy() if resolution is not None else None,
        )

    def clear(self) -> None:
        self._store.clear()
