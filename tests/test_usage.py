"""Tests for askwol.usage: event recording, filtering, and stats aggregation.

The autouse fixture in conftest.py already points usage._DB_PATH at a fresh
temp file per test, so these can call usage.record() freely.
"""

import sqlite3
from contextlib import closing

import pytest

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


@pytest.fixture
def tracked_connections(monkeypatch):
    connections = []
    connect = usage._connect

    def tracked_connect():
        conn = connect()
        connections.append(conn)
        return conn

    monkeypatch.setattr(usage, "_connect", tracked_connect)
    yield connections
    for conn in connections:
        conn.close()


def test_usage_closes_connections_after_events_jobs_and_progress(tracked_connections):
    usage.record("validate", source="test.ttl", status="200")
    assert usage.events_count() == 1
    assert len(usage.all_events()) == 1
    assert usage.stats()["total_events"] == 1
    assert usage.distinct_sources() == [{"source": "test.ttl", "n": 1}]
    assert usage.distinct_statuses() == [{"status": "200", "n": 1}]

    usage.job_started("request", kind="validate", source="test.ttl")
    usage.job_phase("request", "checks")
    usage.stuck_jobs()
    usage.job_finished("request", outcome="ok", status="200", duration_ms=1)

    usage.progress_put("key", "owner", "[]", "parsing", 1.0)
    usage.progress_set_phase("key", "owner", "checks", 2.0)
    assert usage.progress_get("key")["phase"] == "checks"
    usage.progress_finish("key", "owner", 3.0)
    usage.progress_prune(finished_before=2.0, updated_before=1.0)
    usage.progress_drop("key", "owner")

    assert tracked_connections
    for conn in tracked_connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            conn.execute("SELECT 1")


def test_record_rolls_back_and_closes_connection_after_failed_write(tracked_connections):
    usage._init()
    with closing(usage._connect()) as conn, conn:
        conn.execute(
            "CREATE TRIGGER reject_event AFTER INSERT ON events "
            "BEGIN SELECT RAISE(FAIL, 'reject event'); END"
        )

    usage.record("validate", source="rejected.ttl")

    assert usage.events_count() == 0
    for conn in tracked_connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            conn.execute("SELECT 1")
