"""Regression tests for isolated, timed-out, and rate-limited validation.

These exercise web.run_isolated_validation's real subprocess path (not the
in-process test hook used by test_api_integration.py), so a hanging
validation is simulated with a tiny fake worker command instead of a real
slow ontology - deterministic and fast, but still a genuine child process
that must be spawned, awaited, and killed exactly like the real worker.
"""

from __future__ import annotations

import asyncio
import sys

import httpx
import pytest
from httpx import ASGITransport

from askwol import web

# A minimal, valid, and fully offline ontology: no declared prefixes with
# subject-position terms and no owl:imports, so parsing and "resolution"
# both complete instantly with zero network calls.
MINIMAL_TTL = (
    b"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    b"<http://example.org/test-ontology-minimal> a owl:Ontology .\n"
)

# Ignores whatever arguments run_isolated_validation appends (the temp file
# path, --display-name, --base-uri) and just hangs, so it stands in for a
# validation that never finishes.
_SLEEP_FOREVER_CMD = [sys.executable, "-c", "import time; time.sleep(9999)"]


@pytest.fixture(autouse=True)
def _clean_isolation_state(monkeypatch):
    """Every test here manipulates module-level isolation state directly;
    reset it before and after so tests can't leak into each other."""
    web._validation_slots_in_use = 0
    monkeypatch.setattr(web, "_TEST_INPROCESS_PIPELINE", None)
    yield
    web._validation_slots_in_use = 0


async def _post_file(client: httpx.AsyncClient, path: str, content: bytes = MINIMAL_TTL):
    return await client.post(path, files={"file": ("x.ttl", content, "text/turtle")})


@pytest.mark.asyncio
async def test_hanging_validation_returns_504(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 1.0)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        r = await _post_file(client, "/validate")

    assert r.status_code == 504
    assert "too long" in r.text


@pytest.mark.asyncio
async def test_api_hanging_validation_returns_504(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 1.0)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        r = await _post_file(client, "/api/validate")

    assert r.status_code == 504
    assert "detail" in r.json()


@pytest.mark.asyncio
async def test_health_and_normal_pages_stay_responsive_during_a_hang(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 2.0)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        hang_task = asyncio.create_task(_post_file(client, "/validate"))
        await asyncio.sleep(0.3)  # let the hang actually start and occupy its slot

        health = await asyncio.wait_for(client.get("/health"), timeout=2)
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        home = await asyncio.wait_for(client.get("/"), timeout=2)
        assert home.status_code == 200

        # Let the real timeout resolve the hang cleanly (kills the child,
        # releases the slot) instead of cancelling it out from under it.
        hang_response = await hang_task
        assert hang_response.status_code == 504


@pytest.mark.asyncio
async def test_excess_concurrent_validations_return_503_immediately(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 2.0)
    monkeypatch.setattr(web, "MAX_CONCURRENT_VALIDATIONS", 1)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        first_task = asyncio.create_task(_post_file(client, "/validate"))
        await asyncio.sleep(0.3)  # let the first request occupy the only slot

        started = asyncio.get_event_loop().time()
        second = await _post_file(client, "/validate")
        elapsed = asyncio.get_event_loop().time() - started

        assert second.status_code == 503
        assert "Wol is busy" in second.text
        assert elapsed < 1.0, "excess job should be rejected immediately, not queued"

        first_response = await first_task
        assert first_response.status_code == 504


@pytest.mark.asyncio
async def test_child_process_is_terminated_after_timeout(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 1.0)

    real_create_subprocess_exec = asyncio.create_subprocess_exec
    spawned: list[asyncio.subprocess.Process] = []

    async def _capture(*args, **kwargs):
        proc = await real_create_subprocess_exec(*args, **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(web.asyncio, "create_subprocess_exec", _capture)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        r = await _post_file(client, "/validate")

    assert r.status_code == 504
    assert len(spawned) == 1
    assert spawned[0].returncode is not None, "the hung child process should have been killed and reaped"


@pytest.mark.asyncio
async def test_temp_file_removed_after_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 1.0)

    created: list = []
    import tempfile as tempfile_module

    real_named_temp_file = tempfile_module.NamedTemporaryFile

    def _capture(*args, **kwargs):
        tmp = real_named_temp_file(*args, **kwargs)
        created.append(tmp.name)
        return tmp

    monkeypatch.setattr(web.tempfile, "NamedTemporaryFile", _capture)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        r = await _post_file(client, "/validate")

    assert r.status_code == 504
    assert len(created) == 1
    from pathlib import Path
    assert not Path(created[0]).exists()


@pytest.mark.asyncio
async def test_next_validation_still_works_after_a_timeout(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 1.0)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        timed_out = await _post_file(client, "/validate")
        assert timed_out.status_code == 504

        # Restore the real worker; the isolation machinery (concurrency
        # slot, subprocess spawning) must not be left in a broken state.
        monkeypatch.setattr(web, "WORKER_CMD", [sys.executable, "-m", "askwol.validate_worker"])
        monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 300.0)

        ok = await _post_file(client, "/validate")
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_html_and_api_validation_use_the_same_runner(monkeypatch):
    calls: list[str] = []

    async def fake_runner(tmp_path, display_name, *, kind, base_uri=None):
        calls.append(kind)
        from askwol.models import ValidationReport
        return ValidationReport(file=display_name), ""

    monkeypatch.setattr(web, "run_isolated_validation", fake_runner)

    async with httpx.AsyncClient(transport=ASGITransport(app=web.app), base_url="http://test") as client:
        html_response = await _post_file(client, "/validate")
        api_response = await _post_file(client, "/api/validate")

    assert html_response.status_code == 200
    assert api_response.status_code == 200
    assert calls == ["validate", "validate_api"]
