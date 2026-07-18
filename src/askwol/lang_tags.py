"""Analyse language tag consistency across an RDF graph."""

from __future__ import annotations

from collections import defaultdict

from rdflib import BNode, Graph, Literal, URIRef

from askwol.deprecation import is_deprecated
from askwol.models import LangTagIssue, LangTagPropertySummary, LangTagReport, Status

# Annotation properties where language tags are expected
LABEL_PROPERTIES = {
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://www.w3.org/2004/02/skos/core#prefLabel",
    "http://www.w3.org/2004/02/skos/core#altLabel",
    "http://www.w3.org/2004/02/skos/core#hiddenLabel",
    "http://www.w3.org/2004/02/skos/core#definition",
    "http://www.w3.org/2004/02/skos/core#note",
    "http://www.w3.org/2004/02/skos/core#scopeNote",
    "http://www.w3.org/2004/02/skos/core#example",
    "http://www.w3.org/2004/02/skos/core#historyNote",
    "http://www.w3.org/2004/02/skos/core#editorialNote",
    "http://www.w3.org/2004/02/skos/core#changeNote",
    "http://purl.org/dc/terms/title",
    "http://purl.org/dc/terms/description",
    "http://purl.org/dc/elements/1.1/title",
    "http://purl.org/dc/elements/1.1/description",
}


def _shorten(uri: str, ns_map: dict[str, str]) -> str:
    """Shorten a URI to prefix:local using the graph's namespace map."""
    for pfx, ns_uri in ns_map.items():
        if uri == ns_uri:
            return f"<{uri}>"
        if uri.startswith(ns_uri):
            local = uri[len(ns_uri):]
            if local:
                return f"{pfx}:{local}" if pfx else local
    if "#" in uri:
        return uri.rsplit("#", 1)[-1]
    if "/" in uri:
        seg = uri.rsplit("/", 1)[-1]
        return seg if seg else f"<{uri}>"
    return uri


def check_lang_tags(graph: Graph, ns_map: dict[str, str]) -> LangTagReport:
    """Check language tag consistency for annotation properties.

    Rules:
    - If a property uses language tags on *any* subject, every subject
      using that property should also use language tags (no bare strings).
    - All subjects should use the same set of languages for each property.
    """
    # property URI -> subject (URI string or bnode id) -> set of language tags
    prop_data: dict[str, dict[str, set[str | None]]] = defaultdict(lambda: defaultdict(set))
    bnode_subjects: set[str] = set()
    # memoize deprecation lookups; a deprecated term is exempt from this check
    deprecated_cache: dict[URIRef, bool] = {}

    for s, p, o in graph:
        if not isinstance(p, URIRef) or not isinstance(o, Literal):
            continue
        p_str = str(p)
        if p_str not in LABEL_PROPERTIES:
            continue
        if isinstance(s, URIRef):
            if s not in deprecated_cache:
                deprecated_cache[s] = is_deprecated(graph, s)
            if deprecated_cache[s]:
                continue
        s_str = str(s)
        if isinstance(s, BNode):
            bnode_subjects.add(s_str)
        lang = o.language  # None when untagged
        prop_data[p_str][s_str].add(lang)

    if not prop_data:
        return LangTagReport()

    all_langs: set[str] = set()
    issues: list[LangTagIssue] = []
    property_summaries: list[LangTagPropertySummary] = []

    for prop_uri, subjects in sorted(prop_data.items()):
        # Collect all language tags used for this property across all subjects
        prop_langs: set[str] = set()
        has_tagged = False
        for langs in subjects.values():
            for lang in langs:
                if lang is not None:
                    prop_langs.add(lang)
                    has_tagged = True

        if not has_tagged:
            # No language tags on this property at all  -  skip
            continue

        all_langs |= prop_langs
        expected = sorted(prop_langs)
        prop_short = _shorten(prop_uri, ns_map)

        # Track which subjects are fully consistent (have all expected langs, no bare strings)
        consistent: list[str] = []
        for subj_uri, subj_langs in sorted(subjects.items()):
            is_bnode = subj_uri in bnode_subjects
            subj_short = "(blank node)" if is_bnode else _shorten(subj_uri, ns_map)
            actual_langs = {l for l in subj_langs if l is not None}

            if actual_langs == prop_langs and None not in subj_langs:
                if not is_bnode:
                    consistent.append(subj_short)
                continue

            # Check 1: untagged literal when tags are expected
            if None in subj_langs:
                issues.append(LangTagIssue(
                    subject=subj_short,
                    property=prop_short,
                    issue_type="missing_tag",
                    languages_found=sorted(actual_langs),
                    languages_expected=expected,
                    detail="Has untagged value  -  add a language tag",
                    is_blank_node=is_bnode,
                ))

            # Check 2: missing languages
            missing = prop_langs - actual_langs
            if missing and None not in subj_langs:
                # Only report missing languages when the subject already
                # uses tags (otherwise the "missing_tag" issue covers it)
                issues.append(LangTagIssue(
                    subject=subj_short,
                    property=prop_short,
                    issue_type="missing_language",
                    languages_found=sorted(actual_langs),
                    languages_expected=expected,
                    detail=f"Missing: {', '.join(sorted(missing))}",
                    is_blank_node=is_bnode,
                ))

        property_summaries.append(LangTagPropertySummary(
            property=prop_short,
            languages=expected,
            total_subjects=len(subjects),
            consistent_subjects=len(consistent),
            examples=consistent[:3],  # up to 3 examples of correct usage
        ))

    return LangTagReport(
        properties_checked=len(prop_data),
        languages_used=sorted(all_langs),
        property_summaries=property_summaries,
        issues=issues,
        # Labels/comments are used, but either inconsistently (issues) or not
        # tagged at all (no languages_used) - both are worth flagging. Fully
        # consistent tagging is OK; no labels/comments to check at all keeps
        # the default SKIP.
        status=Status.WARN if (issues or not all_langs) else Status.OK,
    )
