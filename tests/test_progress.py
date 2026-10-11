"""Tests for the live step progress shown while a validation runs.

The registry is exercised directly, then end to end through the real
subprocess path with a tiny fake worker that reports phases on stderr with
pauses in between, so a concurrent poll can watch the steps go by.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap

import httpx
import pytest
from fastapi.responses import HTMLResponse
from httpx import ASGITransport

from askwol import progress, web
from askwol.models import ValidationReport

IP = "203.0.113.7"

MINIMAL_TTL = (
    b"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    b"<http://example.org/test-ontology-minimal> a owl:Ontology .\n"
)

# Reports every phase the real worker does, 0.4 s apart, then a valid result.
_PHASED_WORKER = [
    sys.executable,
    "-c",
    textwrap.dedent(
        """
        import json, sys, time
        for phase in ("parsing", "checks", "reasoner", "namespaces", "done"):
            sys.stderr.write(json.dumps({"phase": phase}) + "\\n")
            sys.stderr.flush()
            time.sleep(0.4)
        sys.stdout.write(json.dumps({"report": {"file": "x.ttl"}, "mermaid": ""}))
        """
    ),
]


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    progress._latest.clear()
    web._validation_slots_in_use = 0
    monkeypatch.setattr(web, "_TEST_INPROCESS_PIPELINE", None)
    # Keep this module's requests out of the rate-limit budget other modules share.
    monkeypatch.setattr(web, "_rate_limit_buckets", {})
    yield
    progress._latest.clear()
    web._validation_slots_in_use = 0


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test")


# --- the registry -----------------------------------------------------------


def test_track_registers_a_running_job_at_its_first_step():
    with progress.track(IP, "a.ttl", steps=progress.UPLOAD_FLOW):
        snap = progress.snapshot(IP, "a.ttl")
    assert snap == {"state": "running", "step": 1, "steps": 4, "label": progress.LABELS["parsing"]}


def test_url_submissions_have_an_extra_fetching_step():
    with progress.track(IP, "http://example.org/o.ttl", steps=progress.URL_FLOW):
        snap = progress.snapshot(IP, "http://example.org/o.ttl")
    assert snap["step"] == 1
    assert snap["steps"] == 5
    assert snap["label"] == progress.LABELS["fetching"]


def test_report_advances_the_job_and_ignores_unknown_phases():
    with progress.track(IP, "a.ttl", steps=progress.URL_FLOW):
        progress.report("parsing")
        assert progress.snapshot(IP, "a.ttl")["step"] == 2
        progress.report("namespaces")
        assert progress.snapshot(IP, "a.ttl")["step"] == 5
        for ignored in ("done", "no-such-phase"):
            progress.report(ignored)
            assert progress.snapshot(IP, "a.ttl")["step"] == 5


def test_report_outside_a_tracked_request_does_nothing():
    progress.report("checks")


def test_finished_job_reads_as_finishing_and_then_expires(monkeypatch):
    with progress.track(IP, "a.ttl", steps=progress.UPLOAD_FLOW):
        pass
    assert progress.snapshot(IP, "a.ttl") == {"state": "finishing", "steps": 4}

    monkeypatch.setattr(progress, "FINISHED_TTL_SECONDS", -1)
    assert progress.snapshot(IP, "a.ttl") == {"state": "waiting"}


def test_a_job_that_ends_in_an_exception_leaves_no_trace():
    """A cancelled or failed request has no report on its way, so a quick
    re-submit of the same source must not see a stale "finishing" entry."""
    for exc in (RuntimeError("boom"), asyncio.CancelledError()):
        with pytest.raises(type(exc)), progress.track(IP, "a.ttl", steps=progress.UPLOAD_FLOW):
            raise exc
        assert progress.snapshot(IP, "a.ttl") == {"state": "waiting"}


def test_jobs_are_looked_up_by_client_and_source():
    with progress.track(IP, "a.ttl", steps=progress.UPLOAD_FLOW):
        assert progress.snapshot("198.51.100.1", "a.ttl") == {"state": "waiting"}
        assert progress.snapshot(IP, "b.ttl") == {"state": "waiting"}
        assert progress.snapshot(IP, "  a.ttl  ")["state"] == "running"


def test_nothing_is_tracked_without_a_client_ip_or_source():
    with progress.track(None, "a.ttl", steps=progress.UPLOAD_FLOW) as job:
        assert job is None
    with progress.track(IP, "   ", steps=progress.UPLOAD_FLOW) as job:
        assert job is None
    assert progress.snapshot(None, "a.ttl") == {"state": "waiting"}
    assert progress.snapshot(IP, "") == {"state": "waiting"}


def test_registry_is_bounded(monkeypatch):
    monkeypatch.setattr(progress, "MAX_JOBS", 3)
    for i in range(6):
        with progress.track(IP, f"{i}.ttl", steps=progress.UPLOAD_FLOW):
            pass
    progress.snapshot(IP, "0.ttl")
    assert len(progress._latest) <= 3


@pytest.mark.asyncio
async def test_a_newer_request_for_the_same_source_is_not_clobbered_by_an_older_one_finishing():
    async def request(hold: float) -> None:
        with progress.track(IP, "a.ttl", steps=progress.UPLOAD_FLOW):
            await asyncio.sleep(hold)

    older = asyncio.create_task(request(0.2))
    await asyncio.sleep(0.05)
    newer = asyncio.create_task(request(0.6))
    await older
    assert progress.snapshot(IP, "a.ttl")["state"] == "running"
    await newer


# --- the endpoint and the wiring --------------------------------------------


@pytest.mark.asyncio
async def test_progress_endpoint_reports_waiting_for_an_unknown_job_and_is_not_cacheable():
    async with _client() as client:
        r = await client.get("/validate/progress", params={"source": "nothing.ttl"})
    assert r.status_code == 200
    assert r.json() == {"state": "waiting"}
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex"


@pytest.mark.asyncio
async def test_progress_endpoint_is_not_rate_limited(monkeypatch):
    monkeypatch.setattr(web, "_rate_limit_buckets", {})
    monkeypatch.setattr(web, "RATE_LIMIT_MAX_REQUESTS", 1)
    async with _client() as client:
        statuses = [(await client.get("/validate/progress", params={"source": "a.ttl"})).status_code for _ in range(5)]
    assert statuses == [200] * 5


@pytest.mark.asyncio
async def test_progress_follows_a_real_worker_through_its_steps(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _PHASED_WORKER)
    seen: list[dict] = []

    async with _client() as client:
        validation = asyncio.create_task(
            client.post("/validate", files={"file": ("x.ttl", MINIMAL_TTL, "text/turtle")})
        )
        while not validation.done():
            r = await client.get("/validate/progress", params={"source": "x.ttl"})
            seen.append(r.json())
            await asyncio.sleep(0.1)
        response = await validation
        after = (await client.get("/validate/progress", params={"source": "x.ttl"})).json()

    assert response.status_code == 200
    running = [s for s in seen if s["state"] == "running"]
    steps = [s["step"] for s in running]
    assert steps == sorted(steps), "steps must only move forward"
    assert {1, 2, 3, 4} <= set(steps)
    assert {s["steps"] for s in running} == {4}
    assert all(s["label"] for s in running)
    # Once the work is done the response is still on its way to the browser.
    assert after == {"state": "finishing", "steps": 4}


@pytest.mark.asyncio
async def test_progress_is_scoped_to_the_caller(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _PHASED_WORKER)

    async with _client() as client:
        validation = asyncio.create_task(
            client.post("/validate", files={"file": ("x.ttl", MINIMAL_TTL, "text/turtle")})
        )
        await asyncio.sleep(0.5)
        mine = (await client.get("/validate/progress", params={"source": "x.ttl"})).json()
        # Behind the proxy the client address comes from X-Forwarded-For.
        someone_else = (
            await client.get(
                "/validate/progress",
                params={"source": "x.ttl"},
                headers={"x-forwarded-for": "198.51.100.9"},
            )
        ).json()
        await validation

    assert mine["state"] == "running"
    assert someone_else == {"state": "waiting"}


@pytest.mark.asyncio
async def test_each_entry_point_tracks_the_right_flow(monkeypatch):
    tracked: dict[str, tuple[str, ...] | None] = {}

    async def fake_validate_url(url):
        job = progress.current.get()
        tracked["url"] = job.steps if job else None
        return HTMLResponse("ok")

    async def fake_validate_upload(file):
        job = progress.current.get()
        tracked["upload"] = job.steps if job else None
        return HTMLResponse("ok")

    async def fake_runner(tmp_path, display_name, *, kind, base_uri=None):
        job = progress.current.get()
        tracked["api"] = job.steps if job else None
        return ValidationReport(file=display_name), ""

    monkeypatch.setattr(web, "_validate_url", fake_validate_url)
    monkeypatch.setattr(web, "_validate_upload", fake_validate_upload)
    monkeypatch.setattr(web, "run_isolated_validation", fake_runner)

    async with _client() as client:
        await client.get("/validate", params={"url": "http://example.org/o.ttl"})
        await client.post("/validate", files={"file": ("x.ttl", MINIMAL_TTL, "text/turtle")})
        await client.post("/api/validate", files={"file": ("x.ttl", MINIMAL_TTL, "text/turtle")})

    assert tracked["url"] == progress.URL_FLOW
    assert tracked["upload"] == progress.UPLOAD_FLOW
    assert tracked["api"] is None, "the JSON API has no progress display"
