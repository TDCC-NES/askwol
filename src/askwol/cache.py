"""In-memory cache for fetched remote ontology graphs."""

from __future__ import annotations

import time
from dataclasses import dataclass

from rdflib import Graph


@dataclass
class _CacheEntry:
    graph: Graph | None
    fetched_at: float
    error: str | None = None


class OntologyCache:
    """Simple in-memory cache for remote ontology graphs.

    Entries expire after `ttl` seconds (default: 1 hour).
    """

    def __init__(self, ttl: float = 3600.0) -> None:
        self._ttl = ttl
        self._store: dict[str, _CacheEntry] = {}

    def get(self, uri: str) -> Graph | None:
        """Return cached graph for URI, or None if missing/expired."""
        entry = self._store.get(uri)
        if entry is None:
            return None
        if time.monotonic() - entry.fetched_at > self._ttl:
            del self._store[uri]
            return None
        return entry.graph

    def get_error(self, uri: str) -> str | None:
        """Return cached error for a URI that failed to fetch."""
        entry = self._store.get(uri)
        if entry is None:
            return None
        if time.monotonic() - entry.fetched_at > self._ttl:
            del self._store[uri]
            return None
        return entry.error

    def has(self, uri: str) -> bool:
        """Check if URI is cached (and not expired)."""
        entry = self._store.get(uri)
        if entry is None:
            return False
        if time.monotonic() - entry.fetched_at > self._ttl:
            del self._store[uri]
            return False
        return True

    def put(self, uri: str, graph: Graph | None, error: str | None = None) -> None:
        """Cache a graph (or error) for a namespace URI."""
        self._store[uri] = _CacheEntry(
            graph=graph,
            fetched_at=time.monotonic(),
            error=error,
        )

    def clear(self) -> None:
        self._store.clear()
