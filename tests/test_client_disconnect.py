"""Tests for stopping work that nobody is waiting for any more.

When a client disconnects mid-validation (Stop, Reload, a closed tab, an API
client timing out) the work is cancelled, its worker process stopped, its
concurrency slot freed, and no usage event is recorded.

httpx's ASGI transport can't drop a connection mid-request, so the end-to-end
tests drive the full ASGI app (middleware included) with a tiny hand-rolled
client whose connection they can cut on demand.
"""

from __future__ import annotations

import asyncio
import sys

import httpx
import pytest
from starlette.middleware.base import BaseHTTPMiddleware

from askwol import usage, web

MINIMAL_TTL = (
    b"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    b"<http://example.org/test-ontology-minimal> a owl:Ontology .\n"
)

_SLEEP_FOREVER_CMD = [sys.executable, "-c", "import time; time.sleep(9999)"]

# Takes a little while, then returns a valid (empty) result, so a client that
# stays connected for the whole time must still be served normally.
_SLOW_THEN_OK_CMD = [
    sys.executable,
    "-c",
    (
        "import json, sys, time; time.sleep(0.6); "
        "sys.stdout.write(json.dumps({'report': {'file': 'x.ttl'}, 'mermaid': ''}))"
    ),
]


@pytest.fixture(autouse=True)
def _fast_polling_and_clean_state(monkeypatch):
    monkeypatch.setattr(web, "DISCONNECT_POLL_SECONDS", 0.05)
    monkeypatch.setattr(web, "_TEST_INPROCESS_PIPELINE", None)
    # These tests send many requests from one address; keep them out of the
    # rate-limit budget that other test modules share.
    monkeypatch.setattr(web, "_rate_limit_buckets", {})
    web._validation_slots_in_use = 0
    yield
    web._validation_slots_in_use = 0


@pytest.fixture
def spawned(monkeypatch) -> list[asyncio.subprocess.Process]:
    """Every worker process the app starts, so tests can check it was stopped."""
    procs: list[asyncio.subprocess.Process] = []
    real = asyncio.create_subprocess_exec

    async def _capture(*args, **kwargs):
        proc = await real(*args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(web.asyncio, "create_subprocess_exec", _capture)
    return procs


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "timed out waiting for condition"
        await asyncio.sleep(0.02)


def _job_outcomes() -> list[str]:
    usage._init()
    with usage._connect() as conn:
        return [row["outcome"] for row in conn.execute("SELECT outcome FROM validation_jobs ORDER BY started_at")]


class _Client:
    """A minimal ASGI client whose connection can be cut with disconnect.set()."""

    def __init__(self, method: str, path: str, *, query: str = "", files: dict | None = None) -> None:
        body = b""
        headers = [(b"host", b"test")]
        if files:
            request = httpx.Request(method, f"http://test{path}", files=files)
            body = request.read()
            headers = [(k.lower(), v) for k, v in request.headers.raw]
        self.method, self.path, self.query, self.body, self.headers = method, path, query, body, headers
        self.disconnect = asyncio.Event()
        self.sent: list[dict] = []
        self._body_delivered = False

    @classmethod
    def upload(cls, path: str) -> _Client:
        return cls("POST", path, files={"file": ("x.ttl", MINIMAL_TTL, "text/turtle")})

    def scope(self) -> dict:
        return {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": self.method,
            "scheme": "http", "path": self.path, "raw_path": self.path.encode(),
            "query_string": self.query.encode(), "root_path": "", "headers": self.headers,
            "client": ("127.0.0.1", 50000), "server": ("test", 80),
        }

    async def receive(self) -> dict:
        if not self._body_delivered:
            self._body_delivered = True
            return {"type": "http.request", "body": self.body, "more_body": False}
        await self.disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(self, message: dict) -> None:
        self.sent.append(message)

    @property
    def status(self) -> int | None:
        return next((m["status"] for m in self.sent if m["type"] == "http.response.start"), None)

    def start(self) -> asyncio.Task:
        return asyncio.create_task(web.app(self.scope(), self.receive, self.send))


# --- the helper -------------------------------------------------------------


class _FakeRequest:
    def __init__(self) -> None:
        self.gone = False
        self.broken = False

    async def is_disconnected(self) -> bool:
        if self.broken:
            raise RuntimeError("cannot tell")
        return self.gone


@pytest.mark.asyncio
async def test_work_result_is_returned_while_the_client_stays():
    async def work():
        await asyncio.sleep(0.2)  # several polls
        return "report"

    assert await web._unless_client_disconnects(_FakeRequest(), work()) == "report"


@pytest.mark.asyncio
async def test_work_is_cancelled_and_cleaned_up_when_the_client_leaves():
    request = _FakeRequest()
    started = asyncio.Event()
    cleaned_up: list[bool] = []

    async def work():
        try:
            started.set()
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            await asyncio.sleep(0.1)  # cleanup that takes a moment, e.g. stopping a worker
            cleaned_up.append(True)
            raise

    waiting = asyncio.create_task(web._unless_client_disconnects(request, work()))
    await started.wait()
    request.gone = True
    with pytest.raises(web.ClientDisconnectedError):
        await asyncio.wait_for(waiting, timeout=5)
    assert cleaned_up == [True], "the helper must let the work finish cleaning up before returning"


@pytest.mark.asyncio
async def test_errors_from_the_work_propagate_unchanged():
    async def work():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await web._unless_client_disconnects(_FakeRequest(), work())


@pytest.mark.asyncio
async def test_a_broken_disconnect_check_does_not_cancel_valid_work():
    request = _FakeRequest()
    request.broken = True

    async def work():
        await asyncio.sleep(0.2)
        return "report"

    assert await web._unless_client_disconnects(request, work()) == "report"


@pytest.mark.asyncio
async def test_cancelling_the_request_cancels_the_work():
    started = asyncio.Event()
    cancelled: list[bool] = []

    async def work():
        try:
            started.set()
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    waiting = asyncio.create_task(web._unless_client_disconnects(_FakeRequest(), work()))
    await started.wait()
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await _wait_until(lambda: cancelled)


# --- the worker process -----------------------------------------------------


@pytest.mark.asyncio
async def test_cancelled_validation_stops_its_worker_and_frees_its_slot(monkeypatch, tmp_path, spawned):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    ontology = tmp_path / "x.ttl"
    ontology.write_bytes(MINIMAL_TTL)

    task = asyncio.create_task(web.run_isolated_validation(ontology, "x.ttl", kind="validate"))
    await _wait_until(lambda: spawned)
    assert web._validation_slots_in_use == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert spawned[0].returncode is not None, "the worker must be stopped, not left running"
    assert web._validation_slots_in_use == 0
    assert _job_outcomes() == ["cancelled"]


# --- end to end, through the whole app --------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/validate", "/api/validate"])
async def test_disconnect_stops_an_upload_validation_and_records_nothing(monkeypatch, spawned, path):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "VALIDATION_TIMEOUT", 60.0)  # a hang would trip the wait_for below instead
    client = _Client.upload(path)

    running = client.start()
    await _wait_until(lambda: spawned)
    client.disconnect.set()
    await asyncio.wait_for(running, timeout=5)

    assert client.status == 499
    assert spawned[0].returncode is not None
    assert web._validation_slots_in_use == 0
    assert usage.events_count() == 0
    assert _job_outcomes() == ["cancelled"]


@pytest.mark.asyncio
async def test_disconnect_stops_a_url_validation_and_records_nothing(monkeypatch):
    started = asyncio.Event()
    cancelled: list[bool] = []

    async def slow_fetch(url):
        try:
            started.set()
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    monkeypatch.setattr(web, "_validate_url", slow_fetch)
    client = _Client("GET", "/validate", query="url=http%3A%2F%2Fexample.org%2Fo.ttl")

    running = client.start()
    await asyncio.wait_for(started.wait(), timeout=5)
    client.disconnect.set()
    await asyncio.wait_for(running, timeout=5)

    assert client.status == 499
    assert cancelled == [True]
    assert usage.events_count() == 0


@pytest.mark.asyncio
async def test_a_client_that_stays_connected_is_served_and_counted(monkeypatch):
    monkeypatch.setattr(web, "WORKER_CMD", _SLOW_THEN_OK_CMD)
    client = _Client.upload("/validate")

    await asyncio.wait_for(client.start(), timeout=10)

    assert client.status == 200
    assert usage.events_count() == 1
    assert _job_outcomes() == ["ok"]


@pytest.mark.asyncio
async def test_a_cancelled_validation_does_not_leave_the_next_one_waiting_for_a_slot(monkeypatch, spawned):
    monkeypatch.setattr(web, "WORKER_CMD", _SLEEP_FOREVER_CMD)
    monkeypatch.setattr(web, "MAX_CONCURRENT_VALIDATIONS", 1)

    first = _Client.upload("/validate")
    first_running = first.start()
    await _wait_until(lambda: spawned)
    first.disconnect.set()
    await asyncio.wait_for(first_running, timeout=5)

    second = _Client.upload("/validate")
    second_running = second.start()
    await _wait_until(lambda: len(spawned) == 2)  # got a slot instead of an immediate 503
    second.disconnect.set()
    await asyncio.wait_for(second_running, timeout=5)

    assert _job_outcomes() == ["cancelled", "cancelled"]


def test_no_base_http_middleware_hides_disconnects_from_the_routes():
    """BaseHTTPMiddleware (what @app.middleware("http") creates) stops
    request.is_disconnected() from ever seeing the client leave, which would
    silently turn all of the above off."""
    assert not [m for m in web.app.user_middleware if m.cls is BaseHTTPMiddleware]
