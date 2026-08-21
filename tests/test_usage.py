"""Tests for askwol.usage: event recording, filtering, and stats aggregation.

The autouse fixture in conftest.py already points usage._DB_PATH at a fresh
temp file per test, so these can call usage.record() freely.
"""

from askwol import usage


def _seed():
    usage.record("validate", source="https://example.org/a.ttl", status="200", duration_ms=100, ip="1.1.1.1")
    usage.record("validate", source="https://example.org/a.ttl", status="422", duration_ms=50, ip="1.1.1.1")
    usage.record("validate", source="https://example.org/b.ttl", status="200", duration_ms=200, ip="2.2.2.2")
    usage.record("validate_upload", source="upload.ttl", status="200", duration_ms=150, ip="3.3.3.3")
    usage.record("validate_api", source="api.ttl", status="200", duration_ms=150, ip="4.4.4.4")
    usage.record("validate", source="https://example.org/c.ttl", status=None, duration_ms=10, ip="5.5.5.5")


def test_events_count_and_all_events_no_filter():
    _seed()
    assert usage.events_count() == 6
    assert len(usage.all_events(limit=10)) == 6


def test_source_filter():
    _seed()
    assert usage.events_count(source="https://example.org/a.ttl") == 2
    rows = usage.all_events(limit=10, source="https://example.org/a.ttl")
    assert len(rows) == 2
    assert all(r["source"] == "https://example.org/a.ttl" for r in rows)


def test_status_filter():
    _seed()
    assert usage.events_count(status="200") == 4
    rows = usage.all_events(limit=10, status="200")
    assert all(r["status"] == "200" for r in rows)


def test_status_none_filter_matches_null_status():
    """The "(none)" sentinel must match a real NULL status column, not the
    literal string "(none)" (which never appears in the data)."""
    _seed()
    assert usage.events_count(status=usage.STATUS_NONE) == 1
    rows = usage.all_events(limit=10, status=usage.STATUS_NONE)
    assert len(rows) == 1
    assert rows[0]["status"] is None


def test_source_and_status_filter_combined():
    _seed()
    assert usage.events_count(source="https://example.org/a.ttl", status="200") == 1
    assert usage.events_count(source="https://example.org/a.ttl", status="422") == 1


def test_stats_splits_sources_by_kind():
    _seed()
    data = usage.stats(days=30)
    url_sources = {row["source"] for row in data["url_sources"]}
    upload_sources = {row["source"] for row in data["upload_sources"]}

    assert url_sources == {"https://example.org/a.ttl", "https://example.org/b.ttl", "https://example.org/c.ttl"}
    assert upload_sources == {"upload.ttl", "api.ttl"}
    assert data["url_source_total"] == 3
    assert data["upload_source_total"] == 2


def test_distinct_sources_and_statuses():
    _seed()
    sources = {row["source"] for row in usage.distinct_sources()}
    assert sources == {
        "https://example.org/a.ttl", "https://example.org/b.ttl", "https://example.org/c.ttl",
        "upload.ttl", "api.ttl",
    }

    statuses = {row["status"]: row["n"] for row in usage.distinct_statuses()}
    assert statuses["200"] == 4
    assert statuses["422"] == 1
    assert statuses[usage.STATUS_NONE] == 1
