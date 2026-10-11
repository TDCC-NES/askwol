"""Wollie, the hand-drawn owl, replaces the previously hotlinked illustration.

The pages must not depend on a third-party image host, every image they
reference must really be served by the app, and the favicon must be on every
kind of page (the app's pages and a report rendered on its own).
"""

from __future__ import annotations

import re
import struct

import pytest
from fastapi.testclient import TestClient

from askwol import branding, web
from askwol.models import ValidationReport
from askwol.report_html import render_report


@pytest.fixture
def client():
    return TestClient(web.app)


def _png_size(data: bytes) -> tuple[int, int]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize("path", ["/", "/guide"])
def test_pages_do_not_hotlink_a_third_party_image_host(client, path):
    html = client.get(path).text.lower()
    assert "wikimedia" not in html
    assert "winnie-the-pooh_67" not in html


@pytest.mark.parametrize("path", ["/", "/guide"])
def test_every_static_asset_a_page_references_is_served(client, path):
    html = client.get(path).text
    names = set(re.findall(r'(?:src|href)="static/([^"]+)"', html))
    assert {"wollie-h1.png", "wollie-touch-180.png"} <= names
    for name in names:
        response = client.get(f"/static/{name}")
        assert response.status_code == 200, name
        assert response.headers["content-type"] == "image/png"
        assert "max-age" in response.headers["cache-control"]
        _png_size(response.content)


def test_home_page_shows_wollie_in_the_heading_and_the_about_section(client):
    html = client.get("/").text
    assert re.search(r'<h1>\s*<img class="logo" src="static/wollie-h1\.png" alt=""', html)
    assert 'class="wollie" src="static/wollie-about.png"' in html


def test_heading_keeps_its_descriptive_text_for_search_and_screen_readers(client):
    h1 = re.search(r"<h1>.*?</h1>", client.get("/").text, re.DOTALL).group(0)
    assert "Ask Wol" in h1
    assert "OWL Ontology Checker &amp; Reviewer" in h1


@pytest.mark.parametrize("path", ["/", "/guide"])
def test_social_card_image_is_wollie_at_a_usable_size(client, path):
    html = client.get(path).text
    url = re.search(r'<meta property="og:image" content="([^"]+)"', html).group(1)
    assert url.endswith("/askwol/static/wollie-og.png")
    name = url.rsplit("/", 1)[1]
    assert _png_size(client.get(f"/static/{name}").content) == (1200, 630)
    assert 'og:image:width" content="1200"' in html
    assert 'og:image:height" content="630"' in html


def test_favicon_is_embedded_on_every_kind_of_page(client, monkeypatch):
    monkeypatch.setenv("ASKWOL_STATS_TOKEN", "t")
    pages = {
        "home": client.get("/").text,
        "guide": client.get("/guide").text,
        "stats": client.get("/stats", params={"token": "t"}).text,
        "report": render_report(ValidationReport(file="x.ttl")),
    }
    for name, html in pages.items():
        assert branding.FAVICON_LINK in html, name
        assert "&#x1F989;" not in html.split("<body", 1)[0], f"{name}: old emoji favicon"


def test_static_urls_are_prefixed_behind_a_sub_path(client, monkeypatch):
    monkeypatch.setattr(web, "ROOT_PATH", "/askwol")
    html = client.get("/").text
    assert 'src="/askwol/static/wollie-h1.png"' in html
    assert 'href="/askwol/static/wollie-touch-180.png"' in html
    # the absolute social-card URL must not be rewritten
    assert 'content="https://lod-4tu.tudelft.nl/askwol/static/wollie-og.png"' in html


def test_static_route_cannot_read_files_outside_its_folder(client):
    assert client.get("/static/../web.py").status_code == 404
    assert client.get("/static/%2e%2e/web.py").status_code == 404
