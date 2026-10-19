"""Shared input formats and actionable diagnostics for every entry point."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from askwol.parse_diagnostics import FORMAT_LABELS, SYNTAX_GUIDANCE, SYNTAX_GUIDE_URL, parse_diagnostic

GUIDE_URL = "https://lod-4tu.tudelft.nl/askwol/guide#server-config"
RDF_FORMAT_SUFFIXES = {
    "turtle": ".ttl", "xml": ".rdf", "json-ld": ".jsonld", "nt": ".nt", "n3": ".n3",
}
RDF_MEDIA_TYPES = {
    "text/turtle": "turtle",
    "application/x-turtle": "turtle",
    "application/rdf+xml": "xml",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/ld+json": "json-ld",
    "application/json": "json-ld",
    "application/n-triples": "nt",
    "text/n3": "n3",
    "application/n3": "n3",
}
_FORMAT_ALIASES = {
    **{name: name for name in RDF_FORMAT_SUFFIXES},
    **RDF_MEDIA_TYPES,
    "ttl": "turtle", "rdf": "xml", "owl": "xml", "rdfxml": "xml", "rdf/xml": "xml",
    "jsonld": "json-ld", "n-triples": "nt", "ntriples": "nt",
}
_SUFFIX_FORMATS = {
    ".ttl": "turtle", ".rdf": "xml", ".owl": "xml", ".rdfs": "xml", ".xml": "xml",
    ".jsonld": "json-ld", ".json": "json-ld", ".nt": "nt", ".n3": "n3",
}
_GENERIC_MEDIA_TYPES = {"", "text/plain", "application/octet-stream"}
_HTML_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}


class InputError(ValueError):
    """An input problem with an explanation suitable for people and API clients."""

    def __init__(
        self, code: str, message: str, *, suggested_url: str | None = None,
        guide_url: str | None = None,
    ) -> None:
        message = message.strip() or "The ontology input could not be read or parsed. Check its contents and input format."
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggested_url = suggested_url
        self.guide_url = guide_url


def github_raw_url(url: str) -> str | None:
    """Suggest GitHub's raw route without guessing where a ref ends."""
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "github.com":
        return None
    parts = parsed.path.split("/", 4)
    if (
        len(parts) != 5 or not parts[1] or not parts[2] or parts[3] != "blob"
        or "/" not in parts[4] or parts[4].startswith("/") or parts[4].endswith("/")
    ):
        return None
    return f"https://github.com/{parts[1]}/{parts[2]}/raw/{parts[4]}"


def html_input_error(source: str = "") -> InputError:
    return InputError(
        "html_instead_of_rdf",
        "The input contains an HTML page instead of raw RDF. Ontology tools need the file contents, "
        "not a file viewer or documentation page. On GitHub, select Raw and copy that URL; "
        "then download or submit the raw RDF file.",
        suggested_url=github_raw_url(source), guide_url=GUIDE_URL,
    )


def select_rdf_format(
    source: str, *, content_type: str | None = None, format: str | None = None,
) -> str:
    """Choose explicit syntax, then a known MIME type, then a decoded suffix.

    Local files retain the historical Turtle fallback. Remote responses need
    a recognized syntax signal, and an explicitly HTML response is never RDF.
    """
    try:
        parsed = urlsplit(source)
    except ValueError as exc:
        raise InputError("invalid_url", "The source URL is malformed. Check its address and try again.") from exc
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type in _HTML_MEDIA_TYPES:
        raise html_input_error(source)
    if format is not None:
        selected = _FORMAT_ALIASES.get(format.strip().lower())
        if selected is None:
            raise InputError(
                "unsupported_format",
                "Unsupported RDF format. Choose turtle, xml (RDF/XML), json-ld, nt, or n3.",
                guide_url=GUIDE_URL,
            )
        return selected
    if media_type in RDF_MEDIA_TYPES:
        return RDF_MEDIA_TYPES[media_type]
    remote = parsed.scheme in ("http", "https")
    if remote and media_type not in _GENERIC_MEDIA_TYPES:
        raise InputError(
            "unsupported_media_type",
            f"The URL returned {media_type!r}, which does not identify a supported RDF syntax. "
            "Use a direct RDF file URL or select its input format explicitly.",
            guide_url=GUIDE_URL,
        )
    path = parsed.path if parsed.scheme else source
    selected = _SUFFIX_FORMATS.get(Path(unquote(path)).suffix.lower())
    if selected:
        return selected
    if remote:
        raise InputError(
            "unsupported_format",
            "The URL does not identify an RDF syntax through its content type or filename. "
            "Use a direct RDF file URL or select its input format explicitly.",
            guide_url=GUIDE_URL,
        )
    return "turtle"


def validate_base_uri(value: str) -> str:
    """Validate a semantic base IRI without retrieving it."""
    try:
        parsed = urlsplit(value)
        valid = (
            bool(parsed.scheme)
            and (parsed.scheme not in {"http", "https"} or bool(parsed.hostname))
            and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        )
        _ = parsed.port  # Accessing the property validates malformed/out-of-range ports.
    except ValueError:
        valid = False
    if not valid:
        raise InputError(
            "invalid_base_uri", "base_uri must be an absolute IRI without whitespace or control characters.",
            guide_url=GUIDE_URL,
        )
    return value


def reject_html_content(content: bytes, *, format: str | None = None) -> None:
    """Reject an HTML document root, without inspecting RDF literal contents.

    Inspect only the document prolog/root and never expand XML entities. The
    encoding signatures also cover UTF-16/32 documents before RDFLib parses.
    """
    prefix = content[:65536]
    if prefix.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encoding = "utf-32"
    elif prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    elif prefix.startswith(b"\x00\x00\x00"):
        encoding = "utf-32-be"
    elif prefix[1:4] == b"\x00\x00\x00":
        encoding = "utf-32-le"
    elif prefix.startswith(b"\x00"):
        encoding = "utf-16-be"
    elif prefix[1:2] == b"\x00":
        encoding = "utf-16-le"
    else:
        encoding = "utf-8-sig"
    text = prefix.decode(encoding, errors="replace").lstrip("\ufeff \t\r\n")
    # A large leading comment/whitespace must not hide an HTML root beyond the
    # initial inspection window. Decode more only for that unusual prolog.
    if (not text or text.startswith(("<?", "<!--"))) and len(content) > len(prefix):
        prefix = content
        text = content.decode(encoding, errors="replace").lstrip("\ufeff \t\r\n")
    while text.startswith(("<?", "<!--")):
        end_marker = "?>" if text.startswith("<?") else "-->"
        end = text.find(end_marker)
        if end < 0:
            return
        text = text[end + len(end_marker):].lstrip()
    if re.match(r"<!doctype\s+html(?:\s|>)", text, re.IGNORECASE):
        raise html_input_error()
    root = re.match(r"<(?P<prefix>[A-Za-z_][\w.-]*:)?html(?=[\s/>])(?P<attrs>[^>]*)>", text, re.IGNORECASE)
    if root is None:
        return
    # In Turtle/N3, <html> can be a legitimate relative subject IRI. Let
    # those parsers decide first; failed parsing is checked again below.
    if format in {"turtle", "n3", "nt"} and root.group(0).lower() == "<html>":
        return
    prefix_name = (root.group("prefix") or "").rstrip(":")
    namespace_attribute = f"xmlns:{prefix_name}" if prefix_name else "xmlns"
    namespace = re.search(rf"\b{re.escape(namespace_attribute)}\s*=\s*(['\"])(.*?)\1", root.group("attrs"))
    if (not prefix_name and namespace is None) or (
        namespace is not None and namespace.group(2) == "http://www.w3.org/1999/xhtml"
    ):
        raise html_input_error()


def input_diagnostic(exc: Exception, source: str | Path) -> dict:
    """Normalize failures at the pipeline boundary; public parsers keep types."""
    from askwol.network import SSRFBlockedError

    detail = str(exc).strip() or type(exc).__name__
    if isinstance(exc, InputError):
        error = exc
    elif isinstance(exc, httpx.TimeoutException):
        error = InputError("fetch_timeout", "Fetching the ontology or a remote JSON-LD context timed out. Try again or increase the HTTP timeout.")
    elif isinstance(exc, SSRFBlockedError):
        error = InputError("blocked_url", detail)
    elif isinstance(exc, httpx.HTTPStatusError):
        error = InputError("http_error", f"The server returned HTTP {exc.response.status_code}. Check that the URL points to an accessible raw RDF file.")
    elif isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol)):
        error = InputError("invalid_url", "The source URL is invalid or uses an unsupported protocol. Use a public HTTP(S) URL.")
    elif isinstance(exc, httpx.HTTPError):
        error = InputError("network_error", f"Could not retrieve the ontology or a remote JSON-LD context: {detail}")
    elif isinstance(exc, OSError):
        error = InputError("io_error", f"Could not read the ontology file: {detail}")
    else:
        parsed = parse_diagnostic(exc)
        format_label = FORMAT_LABELS.get(parsed.get("format"), "RDF")
        error = InputError(
            "invalid_rdf", f"Could not parse the input as {format_label}.",
            guide_url=SYNTAX_GUIDE_URL,
        )
    result = {
        "code": error.code, "message": error.message,
        "suggested_url": error.suggested_url or github_raw_url(str(source)), "guide_url": error.guide_url,
    }
    if error.code == "invalid_rdf":
        result.update(parse_diagnostic(exc))
        result["guidance"] = SYNTAX_GUIDANCE
    return result
