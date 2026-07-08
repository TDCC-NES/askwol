"""Tests for the Mermaid class-diagram generation.

Regression guard for overlapping namespaces (e.g. ``.../food#`` sitting under
``.../food/`` under ``.../``). ``_shorten`` used to pick the first match, so a
term like ``.../food#Grape`` shortened to ``_ns4:food#Grape``. The stray ``#``
then leaked into the Mermaid node ID and broke parsing on machines where
rdflib happened to order the namespaces that way.
"""

import re

from rdflib import Graph, Namespace, RDFS

from askwol.mermaid_diagram import _mermaid_id, _shorten, build_mermaid

# A Mermaid classDiagram node ID may only contain word characters.
_SAFE_ID = re.compile(r"^[0-9A-Za-z_]+$")


def test_shorten_prefers_longest_namespace():
    # Overlapping namespaces: the most specific (longest) one must win so the
    # local part never contains a leftover '#'.
    namespaces = {
        "_ns4": "http://example.org/onto/",
        "food": "http://example.org/onto/food#",
    }
    assert _shorten("http://example.org/onto/food#Grape", namespaces) == "food:Grape"


def test_mermaid_id_sanitizes_special_characters():
    assert _mermaid_id("food:Grape") == "food_Grape"
    assert _mermaid_id("food#Grape") == "food_Grape"
    assert _mermaid_id("a:b-c.d e") == "a_b_c_d_e"
    assert _SAFE_ID.match(_mermaid_id("weird/id{with}chars"))


def test_diagram_node_ids_are_safe_with_overlapping_namespaces():
    # End-to-end guard on a tiny in-memory graph: no '#' may leak into any
    # Mermaid node ID even when namespaces overlap.
    food = Namespace("http://example.org/onto/food#")
    g = Graph()
    g.add((food.Grape, RDFS.subClassOf, food.PlantPart))

    namespaces = {
        "_ns4": "http://example.org/onto/",
        "food": "http://example.org/onto/food#",
    }
    mermaid = build_mermaid(g, namespaces)

    assert "#" not in mermaid
    ids = re.findall(r'^\s*class\s+(\S+)\["', mermaid, re.MULTILINE)
    assert ids, "expected the diagram to declare class nodes"
    for node_id in ids:
        assert _SAFE_ID.match(node_id), f"unsafe Mermaid node ID: {node_id!r}"
    assert 'class food_Grape["food:Grape"]' in mermaid
