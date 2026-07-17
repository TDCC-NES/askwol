"""Resolve namespace URIs via HTTP and cache the resulting RDF graphs."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from io import BytesIO

import httpx
from rdflib import Graph

from askwol.cache import OntologyCache
from askwol.models import NamespaceCheck, Status
from askwol.term_validator import KNOWN_TERMS


class SSRFBlockedError(httpx.HTTPError):
    """Raised when a request target resolves to a private/internal address."""


def _is_unsafe_ip(ip_str: str) -> bool:
    """True if the IP is private, loopback, link-local, reserved, or otherwise non-public."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def block_private_network_requests(request: httpx.Request) -> None:
    """httpx request hook: reject requests whose host resolves to a private or
    internal address (SSRF guard). Namespace URIs and owl:imports targets come
    from untrusted ontology content, so they could point at cloud metadata
    endpoints or internal services. httpx invokes request hooks for every hop
    of a redirect chain, so this also covers redirects to internal hosts.
    """
    host = request.url.host
    if not host:
        return
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.run_in_executor(None, socket.getaddrinfo, host, None), timeout=5.0,
        )
    except (OSError, TimeoutError):
        return  # DNS failure/slow DNS - let the real request fail naturally
    for info in infos:
        ip_str = info[4][0]
        if _is_unsafe_ip(ip_str):
            raise SSRFBlockedError(
                f"Blocked request to '{host}' ({ip_str}): private/internal "
                f"addresses are not allowed"
            )


def _friendly_error(exc: httpx.HTTPError) -> str:
    """Turn a raw httpx exception into a short, user-friendly message."""
    if isinstance(exc, SSRFBlockedError):
        return str(exc)
    msg = str(exc)
    if "nodename nor servname" in msg or "Name or service not known" in msg:
        return "Server not found  -  the domain name could not be resolved"
    if "timed out" in msg.lower() or "TimeoutException" in type(exc).__name__:
        return "Connection timed out  -  the server did not respond in time"
    if "Connection refused" in msg:
        return "Connection refused  -  the server is not accepting connections"
    if "SSL" in msg or "certificate" in msg.lower():
        return "SSL/TLS error  -  could not establish a secure connection"
    if "Too many redirects" in msg:
        return "Too many redirects  -  the server kept redirecting"
    return f"Could not connect to the server ({type(exc).__name__})"


def _friendly_http_status(code: int) -> str:
    """Return a user-friendly description for an HTTP error status code."""
    descriptions = {
        400: "Bad request",
        401: "Authentication required",
        403: "Access denied",
        404: "Not found  -  the namespace URL does not exist on this server",
        405: "Method not allowed",
        406: "Server cannot provide RDF for this namespace",
        408: "Request timed out",
        410: "Gone  -  the resource has been permanently removed",
        429: "Too many requests  -  try again later",
        500: "Internal server error",
        502: "Bad gateway",
        503: "Service unavailable  -  the server may be down for maintenance",
        504: "Gateway timeout",
    }
    desc = descriptions.get(code, "Server error")
    return f"HTTP {code}  -  {desc}"


# Namespace URIs whose servers don't support content negotiation.
# Maps the namespace (without fragment) to a direct RDF download URL.
NAMESPACE_REDIRECTS: dict[str, str] = {
    "http://www.opengis.net/ont/geosparql#":
        "https://opengeospatial.github.io/ogc-geosparql/geosparql11/geo.ttl",
}

# Ordered list of Accept headers to try  -  most specific first
RDF_ACCEPT_HEADERS = [
    "text/turtle",
    "application/rdf+xml",
    "application/n-triples",
    "application/ld+json",
]

RDF_ACCEPT = ", ".join(
    f"{ct};q={1.0 - i * 0.1:.1f}" for i, ct in enumerate(RDF_ACCEPT_HEADERS)
)

DEFAULT_TIMEOUT = 30.0
MAX_CONCURRENT = 10

# Patterns to find RDF links in HTML responses
_LINK_RE = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]*type=["\']'
    r'(application/rdf\+xml|text/turtle|application/n-triples|application/ld\+json)'
    r'["\']',
    re.IGNORECASE,
)
_LINK_RE_REV = re.compile(
    r'<link[^>]+type=["\']'
    r'(application/rdf\+xml|text/turtle|application/n-triples|application/ld\+json)'
    r'["\'][^>]*href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
# Also look for <a> links to .ttl, .rdf, .owl, .nt, .jsonld files
_RDF_FILE_RE = re.compile(
    r'href=["\']([^"\']+\.(?:ttl|rdf|owl|nt|n3|jsonld))["\']',
    re.IGNORECASE,
)


async def resolve_namespace(
    prefix: str,
    uri: str,
    client: httpx.AsyncClient,
    cache: OntologyCache,
) -> NamespaceCheck:
    """Resolve a single namespace URI and try to parse its RDF content.

    Strategy:
    1. Request with RDF Accept headers
    2. If response is RDF, parse it
    3. If response is HTML, scan for <link> tags or .ttl/.rdf/.owl file links
    4. Try fetching each discovered RDF link
    """
    if cache.has(uri):
        cached_err = cache.get_error(uri)
        if cached_err:
            return NamespaceCheck(
                prefix=prefix, uri=uri, status=Status.FAIL, error=cached_err
            )
        return NamespaceCheck(
            prefix=prefix, uri=uri, status=Status.OK, is_valid_rdf=True
        )

    # If we have a known redirect URL, try it first
    redirect_url = NAMESPACE_REDIRECTS.get(uri)
    if redirect_url:
        try:
            rdr_resp = await client.get(redirect_url, follow_redirects=True)
            if rdr_resp.status_code < 400:
                g, is_valid_rdf = _try_parse_rdf(rdr_resp.content)
                if is_valid_rdf:
                    cache.put(uri, graph=g)
                    return NamespaceCheck(
                        prefix=prefix, uri=uri, status=Status.OK,
                        http_status=rdr_resp.status_code,
                        content_type=rdr_resp.headers.get("content-type", ""),
                        is_valid_rdf=True,
                    )
        except httpx.HTTPError:
            pass  # fall through to normal resolution

    try:
        resp = await client.get(
            uri,
            headers={"Accept": RDF_ACCEPT},
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        err = _friendly_error(exc)
        cache.put(uri, graph=None, error=err)
        return NamespaceCheck(prefix=prefix, uri=uri, status=Status.FAIL, error=err)

    ct = resp.headers.get("content-type", "")

    if resp.status_code >= 400:
        err = _friendly_http_status(resp.status_code)
        cache.put(uri, graph=None, error=err)
        return NamespaceCheck(
            prefix=prefix, uri=uri, status=Status.FAIL,
            http_status=resp.status_code, content_type=ct, error=err,
        )

    # Try to parse the response directly as RDF
    g, is_valid_rdf = _try_parse_rdf(resp.content)

    # If that didn't work, the response is probably HTML  -  look for RDF links
    if not is_valid_rdf and "html" in ct.lower():
        rdf_urls = _extract_rdf_links(resp.text, uri)
        for rdf_url in rdf_urls:
            try:
                rdf_resp = await client.get(rdf_url, follow_redirects=True)
                if rdf_resp.status_code < 400:
                    g, is_valid_rdf = _try_parse_rdf(rdf_resp.content)
                    if is_valid_rdf:
                        break
            except httpx.HTTPError:
                continue

    cache.put(uri, graph=g if is_valid_rdf else None)

    return NamespaceCheck(
        prefix=prefix, uri=uri,
        status=Status.OK if resp.status_code < 400 else Status.FAIL,
        http_status=resp.status_code, content_type=ct,
        is_valid_rdf=is_valid_rdf,
    )


def _try_parse_rdf(content: bytes) -> tuple[Graph, bool]:
    """Try parsing bytes as RDF in multiple formats. Returns (graph, success)."""
    g = Graph()
    rdflib_logger = logging.getLogger("rdflib")
    prev_level = rdflib_logger.level
    rdflib_logger.setLevel(logging.ERROR)
    try:
        for fmt in ("turtle", "xml", "json-ld", "nt"):
            try:
                g.parse(BytesIO(content), format=fmt)
                if len(g) > 0:
                    return g, True
            except Exception:
                g = Graph()  # reset on failure
                continue
    finally:
        rdflib_logger.setLevel(prev_level)
    return g, False


def _extract_rdf_links(html: str, base_url: str) -> list[str]:
    """Extract URLs to RDF files from an HTML page."""
    from urllib.parse import urljoin

    urls: list[str] = []
    seen: set[str] = set()

    # <link href="..." type="text/turtle">
    for match in _LINK_RE.finditer(html):
        url = urljoin(base_url, match.group(1))
        if url not in seen:
            urls.append(url)
            seen.add(url)

    # <link type="text/turtle" href="...">  (reversed attribute order)
    for match in _LINK_RE_REV.finditer(html):
        url = urljoin(base_url, match.group(2))
        if url not in seen:
            urls.append(url)
            seen.add(url)

    # <a href="something.ttl">
    for match in _RDF_FILE_RE.finditer(html):
        url = urljoin(base_url, match.group(1))
        if url not in seen:
            urls.append(url)
            seen.add(url)

    return urls


async def resolve_all_namespaces(
    namespaces: dict[str, str],
    cache: OntologyCache,
    timeout: float = DEFAULT_TIMEOUT,
    max_concurrent: int = MAX_CONCURRENT,
) -> list[NamespaceCheck]:
    """Resolve all namespace URIs concurrently."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _limited(prefix: str, uri: str, client: httpx.AsyncClient) -> NamespaceCheck:
        async with sem:
            return await resolve_namespace(prefix, uri, client, cache)

    results: list[NamespaceCheck] = []
    to_resolve: list[tuple[str, str]] = []
    known_idx: dict[int, NamespaceCheck] = {}

    for i, (prefix, uri) in enumerate(namespaces.items()):
        if uri in KNOWN_TERMS:
            known_idx[i] = NamespaceCheck(
                prefix=prefix, uri=uri, status=Status.OK,
                is_valid_rdf=False,
            )
        else:
            to_resolve.append((prefix, uri))

    async with httpx.AsyncClient(
        timeout=timeout, event_hooks={"request": [block_private_network_requests]},
    ) as client:
        tasks = [
            _limited(prefix, uri, client)
            for prefix, uri in to_resolve
        ]
        resolved = await asyncio.gather(*tasks)

    resolved_iter = iter(resolved)
    for i, (_prefix, _uri) in enumerate(namespaces.items()):
        if i in known_idx:
            results.append(known_idx[i])
        else:
            results.append(next(resolved_iter))

    return results
