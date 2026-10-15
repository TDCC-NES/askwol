"""Dashboard authorization and shared HTML/JSON query behavior."""

import pytest
from fastapi.testclient import TestClient

from askwol import usage, web


@pytest.mark.parametrize("path", ["/stats", "/api/stats"])
def test_stats_token_cannot_be_bypassed_by_host_or_proxy_headers(monkeypatch, path):
    monkeypatch.setenv("ASKWOL_STATS_TOKEN", "test-secret")
    for peer in ("8.8.8.8", "127.0.0.1"):
        with TestClient(web.app, client=(peer, 12345)) as client:
            for headers in (
                {"Host": "localhost"},
                {"Host": "127.0.0.1", "X-Forwarded-For": "127.0.0.1"},
                {"Host": "localhost", "Forwarded": "for=127.0.0.1"},
            ):
                assert client.get(path, headers=headers).status_code == 401
            assert client.get(path, params={"token": "wrong-☃"}).status_code == 401
            assert client.get(path, params={"token": "test-secret"}).status_code == 200


@pytest.mark.parametrize("path", ["/stats", "/api/stats"])
def test_stats_stay_disabled_without_configured_token(monkeypatch, path):
    monkeypatch.delenv("ASKWOL_STATS_TOKEN", raising=False)
    with TestClient(web.app) as client:
        assert client.get(path, params={"token": "anything"}).status_code == 503


def test_stats_html_and_json_apply_the_same_filters_and_page_bounds(monkeypatch):
    monkeypatch.setenv("ASKWOL_STATS_TOKEN", "test-secret")
    usage.record("validate", source="a.ttl", status="200", duration_ms=100)
    usage.record("validate_upload", source="b.ttl", status="422", duration_ms=200)
    params = {"token": "test-secret", "source": "a.ttl", "status": "200", "page": -1}
    with TestClient(web.app) as client:
        data = client.get("/api/stats", params=params).json()
        html = client.get("/stats", params=params)
    assert data["page"] == 1
    assert data["total_entries"] == 1
    assert [row["source"] for row in data["all_events"]] == ["a.ttl"]
    assert html.status_code == 200
    assert "Showing 1&ndash;1 of 1" in html.text

