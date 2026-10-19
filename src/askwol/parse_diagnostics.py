"""Capture parser details while preserving public exception types."""

from __future__ import annotations

import json
import re
from xml.sax import SAXParseException

from rdflib.exceptions import ParserError
from rdflib.plugins.parsers.notation3 import BadSyntax
from rdflib.plugins.shared.jsonld.errors import JSONLDException

FORMAT_LABELS = {
    "turtle": "Turtle", "xml": "RDF/XML", "json-ld": "JSON-LD",
    "nt": "N-Triples", "n3": "N3",
}
SYNTAX_GUIDE_URL = "https://lod-4tu.tudelft.nl/askwol/guide#rdf-syntax"
SYNTAX_GUIDANCE = (
    "Check that the input format matches the contents. Fix the reported error "
    "and try again; further syntax errors may appear."
)
_ATTRIBUTE = "_askwol_parse_diagnostic"
_MAX_DETAIL = 400
_NEWLINE = re.compile(r"\r\n|\r|\n")


def parse_diagnostic(exc: Exception) -> dict:
    return getattr(exc, _ATTRIBUTE, {})


def _position(text: str, offset: int) -> tuple[int, int]:
    line = sum(1 for _ in _NEWLINE.finditer(text, 0, offset)) + 1
    column = offset - max(text.rfind("\n", 0, offset), text.rfind("\r", 0, offset))
    return line, column


def annotate_parse_error(
    exc: Exception, format: str, *, source: str | None = None,
    line: int | None = None,
) -> Exception:
    """Keep the innermost document's details; outer catches must not replace them.

    Locations are one-based character positions. RDFLib's Turtle line counter
    can overcount after backtracking, so use its decoded source and offset.
    """
    if parse_diagnostic(exc):
        return exc
    if isinstance(exc, JSONLDException):
        # RDFLib reuses singleton JSON-LD errors. Never attach per-file data
        # to those shared instances, including when jobs run in parallel.
        exc = type(exc)(*exc.args)
    detail = None
    column = None
    if isinstance(exc, BadSyntax):
        detail = exc._why
        text = exc._str.decode("utf-8")
        offset = exc._i
        if 0 <= offset <= len(text):
            line, column = _position(text, offset)
    elif isinstance(exc, json.JSONDecodeError):
        detail = exc.msg
        line, column = _position(exc.doc, exc.pos)
    elif isinstance(exc, SAXParseException):
        detail = exc.getMessage()
        line = exc.getLineNumber()
        column = exc.getColumnNumber() + 1
    elif isinstance(exc, UnicodeError):
        detail = "The input could not be decoded. Check the file encoding."
        line = None
    elif isinstance(exc, (IndexError, AssertionError, AttributeError, TypeError, KeyError)):
        # These RDFLib failures have neither a useful reason nor a location.
        line = None
    else:
        detail = str(exc).strip() or "The parser could not read this document."
        if format == "xml" and isinstance(exc, ParserError):
            # RDF/XML grammar errors use the SAX locator in this exact form.
            match = re.match(r"^(?:None|<unknown>):([1-9][0-9]*):([0-9]+):\s*(.*)$", detail, re.DOTALL)
            if match:
                line, column = int(match[1]), int(match[2]) + 1
                detail = match[3]
        if format == "nt" and isinstance(exc, ParserError) and exc.__context__:
            # The outer N-Triples exception keeps only the unconsumed fragment.
            detail = str(exc.__context__).strip() or detail
    detail = " ".join(detail.split()) if detail else None
    if detail and len(detail) > _MAX_DETAIL:
        detail = detail[:_MAX_DETAIL - 1] + "…"
    data = {
        "format": format, "detail": detail, "source": source,
        "line": line if line is not None and line > 0 else None,
        "column": column if line is not None and line > 0 and column is not None and column > 0 else None,
    }
    try:
        setattr(exc, _ATTRIBUTE, data)
    except (AttributeError, TypeError):
        # An unusual parser exception must still reach its original caller.
        pass
    return exc
