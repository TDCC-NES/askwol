"""Shared pytest fixtures for the whole test suite."""

import pytest

from askwol import usage


@pytest.fixture(autouse=True)
def _isolated_usage_db(monkeypatch, tmp_path):
    """Every test that hits /validate, /api/validate, /stats, or /api/stats
    exercises askwol.usage's real read/write path, which defaults to the
    real data/usage.db (ASKWOL_USAGE_DB isn't set during test runs, and
    usage.py reads it once at import time, before any fixture can act).
    Without this, running the suite writes real rows into the production
    database (confirmed: synthetic "x.ttl" uploads with 504/503 statuses
    from the timeout/concurrency tests leaking into the live dashboard).
    Point every test at a fresh temp file instead of disabling tracking
    outright, since some tests assert on usage.stats()'s real aggregated
    output. `_initialised`/`_ip_secret` are reset too so usage._init() runs
    its CREATE TABLE/secret-generation logic again for the new path."""
    monkeypatch.setattr(usage, "_DB_PATH", tmp_path / "usage.db")
    monkeypatch.setattr(usage, "_initialised", False)
    monkeypatch.setattr(usage, "_ip_secret", None)
