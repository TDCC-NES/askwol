"""Shared outbound-request policy for RDF documents and JSON-LD contexts."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import httpx

from askwol.input_utils import InputError

DEFAULT_TIMEOUT = 30.0
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_CONTEXT_BYTES = 1024 * 1024


class SSRFBlockedError(httpx.HTTPError):
    """Raised when a document target is not a public HTTP(S) address."""


def _is_unsafe_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    )


def _check_addresses(request: httpx.Request, infos) -> None:
    if not infos or any(_is_unsafe_ip(info[4][0]) for info in infos):
        raise SSRFBlockedError(f"Blocked request to '{request.url.host}': private/internal addresses are not allowed")


def _check_url(request: httpx.Request) -> None:
    if request.url.scheme not in ("http", "https") or not request.url.host:
        raise SSRFBlockedError("Only public HTTP(S) document URLs are allowed")


async def block_private_network_requests(request: httpx.Request) -> None:
    """Validate every HTTPX request, including each redirect hop."""
    _check_url(request)
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.run_in_executor(None, socket.getaddrinfo, request.url.host, None),
            timeout=5.0,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise SSRFBlockedError(f"Could not safely resolve '{request.url.host}'") from exc
    _check_addresses(request, infos)


def block_private_network_request(request: httpx.Request) -> None:
    """Synchronous equivalent for the synchronous RDF parser API."""
    _check_url(request)
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        infos = executor.submit(socket.getaddrinfo, request.url.host, None).result(timeout=5.0)
    except (OSError, FutureTimeoutError) as exc:
        raise SSRFBlockedError(f"Could not safely resolve '{request.url.host}'") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    _check_addresses(request, infos)


def fetch_document(
    url: str, *, accept: str, max_bytes: int = MAX_DOCUMENT_BYTES,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> tuple[bytes, str, str]:
    """Fetch bounded content without allowing private redirects or local files."""
    with httpx.Client(
        timeout=timeout, follow_redirects=True, max_redirects=10,
        event_hooks={"request": [block_private_network_request]},
    ) as client, client.stream("GET", url, headers={"Accept": accept}) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_bytes():
            if len(content) + len(chunk) > max_bytes:
                raise InputError("resource_limit", f"RDF document exceeds the {max_bytes:,}-byte limit. Try a smaller file.")
            content.extend(chunk)
        return bytes(content), str(response.url), response.headers.get("content-type", "")
