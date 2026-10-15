"""Isolated validation jobs, concurrency limits, and cancellation cleanup."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections import deque
from collections.abc import Awaitable
from pathlib import Path
from typing import TypeVar

from starlette.requests import Request

from askwol import progress, usage
from askwol.models import ValidationReport

logger = logging.getLogger(__name__)

# Isolated validation. Each job parses and checks the ontology in its own OS
# process (validate_worker.py), never inline in this event loop, so a slow
# or hung ontology can be killed outright without blocking /health or any
# other concurrent request. Both /validate and /api/validate call
# run_isolated_validation() below - the one place this is implemented.
VALIDATION_TIMEOUT = float(os.environ.get("ASKWOL_VALIDATION_TIMEOUT", "300"))
MAX_CONCURRENT_VALIDATIONS = int(os.environ.get("ASKWOL_MAX_CONCURRENT_VALIDATIONS", "2"))

# The command used to spawn the worker, as a plain module-level list rather
# than hardcoded inline, so tests can monkeypatch it to a small fake process
# to exercise timeout/kill/concurrency behaviour without a real slow ontology.
WORKER_CMD: list[str] = [sys.executable, "-m", "askwol.validate_worker"]

_validation_slots_lock = asyncio.Lock()
_validation_slots_in_use = 0

BUSY_MESSAGE = "Wol is busy validating other ontologies right now. Please try again in a few minutes."
TIMEOUT_MESSAGE = "This ontology took too long to validate. Please try a smaller file, or try again later."
ERROR_MESSAGE = "Something went wrong while validating this ontology. Please try again."


class ValidationBusyError(Exception):
    """Raised when the global concurrent-validation limit is reached."""


class ValidationTimeoutError(Exception):
    """Raised when a validation job exceeds VALIDATION_TIMEOUT."""


class ValidationExecutionError(Exception):
    """Raised when a worker cannot produce a valid validation result."""


class ClientDisconnectedError(Exception):
    """Raised when the client closes the connection while its request is still
    being worked on, so there is nobody left to send a response to."""


async def _try_acquire_validation_slot() -> bool:
    global _validation_slots_in_use
    async with _validation_slots_lock:
        if _validation_slots_in_use >= MAX_CONCURRENT_VALIDATIONS:
            return False
        _validation_slots_in_use += 1
        return True


async def _release_validation_slot() -> None:
    global _validation_slots_in_use
    async with _validation_slots_lock:
        _validation_slots_in_use = max(0, _validation_slots_in_use - 1)


async def _drain_phase_updates(request_id: str, stream: asyncio.StreamReader) -> str:
    """Read phase-update lines from the worker's stderr as it runs, logging
    each one so a job that never finishes still shows its last known phase."""
    diagnostics: deque[str] = deque(maxlen=20)
    async for raw_line in stream:
        try:
            data = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            diagnostics.append(raw_line.decode("utf-8", errors="replace").rstrip()[:1000])
            continue
        phase = data.get("phase") if isinstance(data, dict) else None
        if isinstance(phase, str) and phase:
            usage.job_phase(request_id, phase)
            progress.report(phase)
    return "\n".join(diagnostics)


async def _stop_process(proc: asyncio.subprocess.Process) -> None:
    """Stop a worker process: ask it to exit, kill it if it won't, and reap it."""
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:  # exited between the check and the signal
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def run_isolated_validation(
    tmp_path: Path,
    display_name: str,
    *,
    kind: str,
    base_uri: str | None = None,
) -> tuple[ValidationReport, str]:
    """Validate one ontology file in an isolated child process.

    Shared by /validate and /api/validate so both get identical protection:
    a global concurrency limit (raises ValidationBusyError past it) and a
    hard wall-clock timeout that kills the child process outright (raises
    ValidationTimeoutError). Any other unexpected failure is turned into a
    ValidationExecutionError, separate from invalid ontology input. Job start, phase, and outcome are logged
    via askwol.usage so a job that never finishes can still be identified.

    If the awaiting request is cancelled (its client disconnected), the child
    is stopped, the concurrency slot is freed, and the job is logged as
    "cancelled" before the cancellation propagates.
    """
    request_id = uuid.uuid4().hex[:12]
    usage.job_started(request_id, kind=kind, source=display_name)

    if not await _try_acquire_validation_slot():
        usage.job_finished(request_id, outcome="rejected", status="503", duration_ms=0)
        raise ValidationBusyError()

    started = time.perf_counter()
    # The worker only reports "parsing" once its imports are done; say so now
    # so the progress display doesn't linger on the previous step meanwhile.
    progress.report("parsing")

    proc: asyncio.subprocess.Process | None = None
    tasks: tuple[asyncio.Task, ...] = ()
    try:
        cmd = [*WORKER_CMD, str(tmp_path), "--display-name", display_name]
        if base_uri:
            cmd += ["--base-uri", base_uri]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None and proc.stderr is not None
        stdout_task = asyncio.create_task(proc.stdout.read())
        phase_task = asyncio.create_task(_drain_phase_updates(request_id, proc.stderr))
        wait_task = asyncio.create_task(proc.wait())
        tasks = (stdout_task, phase_task, wait_task)

        try:
            await asyncio.wait_for(asyncio.gather(stdout_task, phase_task, wait_task), timeout=VALIDATION_TIMEOUT)
        except asyncio.TimeoutError:
            await _stop_process(proc)
            for task in tasks:
                task.cancel()
            usage.job_finished(
                request_id, outcome="timeout", status="504",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise ValidationTimeoutError() from None

        if proc.returncode != 0:
            diagnostics = phase_task.result()
            detail = f":\n{diagnostics}" if diagnostics else ""
            raise RuntimeError(f"Validation worker exited with status {proc.returncode}{detail}")

        stdout = stdout_task.result()
        payload = json.loads(stdout)
        report = ValidationReport.model_validate(payload["report"])
        mermaid = payload.get("mermaid", "")
        if not isinstance(mermaid, str):
            raise TypeError("Validation worker returned an invalid diagram")
    except asyncio.CancelledError:
        # The client went away, so nobody is waiting for this result: stop the
        # worker instead of letting it run to completion.
        if proc is not None:
            await _stop_process(proc)
        for task in tasks:
            task.cancel()
        usage.job_finished(
            request_id, outcome="cancelled", status="499",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        raise
    except ValidationTimeoutError:
        raise
    except Exception as exc:
        if proc is not None and proc.returncode is None:
            await _stop_process(proc)
        for task in tasks:
            task.cancel()
        usage.job_finished(
            request_id, outcome="error", status="500",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        logger.exception("Validation worker failed (job %s)", request_id)
        raise ValidationExecutionError(ERROR_MESSAGE) from exc
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        await _release_validation_slot()

    duration_ms = int((time.perf_counter() - started) * 1000)
    if report.parse_errors:
        usage.job_finished(request_id, outcome="error", status="422", duration_ms=duration_ms)
    else:
        usage.job_finished(request_id, outcome="ok", status="200", duration_ms=duration_ms)
    return report, mermaid


# How often a running validation checks that its client is still connected.
DISCONNECT_POLL_SECONDS = 0.5

_T = TypeVar("_T")


async def unless_client_disconnects(request: Request, work: Awaitable[_T]) -> _T:
    """Await `work`, but stop it as soon as the client goes away.

    A plain Starlette handler keeps running after its client disconnects (the
    user pressed Stop or Reload, closed the tab, or an API client timed out),
    which burns CPU, holds one of the few concurrency slots and, for the
    browser, then counts a request nobody saw the result of. This races the
    work against a watcher that polls ``request.is_disconnected()``; if the
    client leaves first the work is cancelled - and given the chance to clean
    up, e.g. stop its worker process - and ClientDisconnectedError is raised.

    Only works if the ASGI server reports the disconnect and nothing in between
    (a BaseHTTPMiddleware, a proxy that doesn't pass the abort on) swallows it;
    otherwise this degrades to simply awaiting the work.
    """
    task = asyncio.ensure_future(work)
    stop_watching = asyncio.Event()

    async def _client_left() -> bool:
        try:
            while not stop_watching.is_set():
                if await request.is_disconnected():
                    return True
                try:
                    await asyncio.wait_for(stop_watching.wait(), timeout=DISCONNECT_POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
        except Exception:  # noqa: BLE001 - any failure to check means "can't tell"
            return False  # stop watching rather than cancel valid work
        return False

    watcher = asyncio.ensure_future(_client_left())
    try:
        await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            return task.result()
        if not watcher.result():
            return await task
        task.cancel()
        await asyncio.wait({task})  # let its cleanup (stopping the worker, freeing the slot) finish
        raise ClientDisconnectedError()
    finally:
        stop_watching.set()
        watcher.cancel()
        if not task.done():  # we were cancelled ourselves
            task.cancel()
        await asyncio.gather(task, watcher, return_exceptions=True)

