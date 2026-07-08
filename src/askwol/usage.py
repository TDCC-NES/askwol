"""Lightweight, privacy-friendly usage tracking.

Records validation events to a local SQLite database. No cookies, no JS,
no third-party services. IPs are hashed with a per-database secret so
they cannot be recovered from the stored data.

Configuration via environment variables:
- ASKWOL_USAGE_DB: path to the SQLite file (default: ``data/usage.db``).
- ASKWOL_USAGE_DISABLED: set to ``1`` to disable tracking entirely.
- ASKWOL_STATS_TOKEN: required to access the ``/stats`` endpoint.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB_PATH = Path(os.environ.get("ASKWOL_USAGE_DB", "data/usage.db"))
_DISABLED = os.environ.get("ASKWOL_USAGE_DISABLED") == "1"
_lock = threading.Lock()
_initialised = False
_ip_secret: str | None = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    """Create tables and load (or generate) the IP-hash secret."""
    global _initialised, _ip_secret
    if _initialised:
        return
    with _lock:
        if _initialised:
            return
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts           TEXT    NOT NULL,
                    kind         TEXT    NOT NULL,
                    source       TEXT,
                    status       TEXT,
                    duration_ms  INTEGER,
                    ip_hash      TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
                CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);

                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'ip_secret'"
            ).fetchone()
            if row is None:
                _ip_secret = secrets.token_hex(32)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES ('ip_secret', ?)",
                    (_ip_secret,),
                )
            else:
                _ip_secret = row["value"]
        _initialised = True


def _hash_ip(ip: str | None) -> str | None:
    if not ip or _ip_secret is None:
        return None
    digest = hashlib.sha256(f"{_ip_secret}:{ip}".encode()).hexdigest()
    return digest[:16]


def record(
    kind: str,
    *,
    source: str | None = None,
    status: str | None = None,
    duration_ms: int | None = None,
    ip: str | None = None,
) -> None:
    """Insert a usage event. Silent on failure - tracking must never break the app."""
    if _DISABLED:
        return
    try:
        _init()
        with _connect() as conn:
            conn.execute(
                "INSERT INTO events(ts, kind, source, status, duration_ms, ip_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    kind,
                    source,
                    status,
                    duration_ms,
                    _hash_ip(ip),
                ),
            )
    except Exception:
        # Never let tracking errors propagate.
        pass


def stats(days: int = 30) -> dict[str, Any]:
    """Return aggregated counts for the dashboard."""
    if _DISABLED:
        return {"disabled": True}
    _init()
    with _connect() as conn:
        cutoff = f"-{int(days)} days"
        totals = conn.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT ip_hash) AS uniq "
            "FROM events WHERE ts >= datetime('now', ?)",
            (cutoff,),
        ).fetchone()

        by_day = conn.execute(
            "SELECT substr(ts, 1, 10) AS day, COUNT(*) AS n "
            "FROM events WHERE ts >= datetime('now', ?) "
            "GROUP BY day ORDER BY day DESC",
            (cutoff,),
        ).fetchall()

        by_status = conn.execute(
            "SELECT COALESCE(status, '(none)') AS status, COUNT(*) AS n "
            "FROM events WHERE ts >= datetime('now', ?) "
            "GROUP BY status ORDER BY n DESC",
            (cutoff,),
        ).fetchall()

        top_sources = conn.execute(
            "SELECT source, COUNT(*) AS n FROM events "
            "WHERE ts >= datetime('now', ?) AND source IS NOT NULL "
            "GROUP BY source ORDER BY n DESC LIMIT 25",
            (cutoff,),
        ).fetchall()

        avg_duration = conn.execute(
            "SELECT AVG(duration_ms) AS ms FROM events "
            "WHERE ts >= datetime('now', ?) AND duration_ms IS NOT NULL",
            (cutoff,),
        ).fetchone()

    return {
        "days": days,
        "total_events": totals["n"] or 0,
        "unique_visitors": totals["uniq"] or 0,
        "avg_duration_ms": int(avg_duration["ms"]) if avg_duration["ms"] else None,
        "by_day": [dict(r) for r in by_day],
        "by_status": [dict(r) for r in by_status],
        "top_sources": [dict(r) for r in top_sources],
    }


def stats_token() -> str | None:
    return os.environ.get("ASKWOL_STATS_TOKEN") or None
