"""Live step progress of running validations, for the browser's progress bar.

A validation is one long HTTP request that ends in the report page itself, so
the browser cannot learn about progress from that response. Instead the form
page keeps running while the request is pending and polls
``GET /validate/progress`` for the current step.

Jobs are looked up by (client IP, source name) rather than by a token: a token
would have to travel through the POST -> 303 -> GET redirect and end up in the
shareable result URL (or in a cookie, which askwol avoids). The cost is that
two people behind one IP validating the very same source at the same moment
share a progress display, which is harmless.

State is in memory and per process, like the rate limiter. It is best-effort:
if a job is missing, the page simply falls back to a plain busy indicator.
"""

from __future__ import annotations

import contextlib
import contextvars
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

# The steps the pipeline reports, in order (see pipeline.run_full_validation).
# A URL submission has an extra first step: fetching the ontology.
_PIPELINE_STEPS = ("parsing", "checks", "reasoner", "namespaces")
UPLOAD_FLOW = _PIPELINE_STEPS
URL_FLOW = ("fetching", *_PIPELINE_STEPS)

LABELS = {
    "fetching": "Fetching the ontology",
    "parsing": "Reading and parsing the ontology",
    "checks": "Running the ontology checks",
    "reasoner": "Running the reasoner checks",
    "namespaces": "Checking namespaces, imports and external terms",
}

# A finished job stays visible briefly so a poll that lands while the report
# is still being sent reads "finishing" instead of "no such job".
FINISHED_TTL_SECONDS = 5.0
MAX_JOBS = 1000
MAX_SOURCE_LENGTH = 2048


@dataclass(eq=False)
class Job:
    key: tuple[str, str]
    steps: tuple[str, ...]
    phase: str | None
    finished_at: float | None = None


_lock = threading.Lock()
_latest: dict[tuple[str, str], Job] = {}

# The job the current request is working on. A ContextVar (not a parameter) so
# run_isolated_validation and its phase-reader task can report progress without
# their signatures knowing about it.
current: contextvars.ContextVar[Job | None] = contextvars.ContextVar("askwol_progress_job", default=None)


def _key(client_ip: str | None, source: str | None) -> tuple[str, str] | None:
    source = (source or "").strip()[:MAX_SOURCE_LENGTH]
    if not client_ip or not source:
        return None
    return client_ip, source


def _prune(now: float) -> None:
    expired = [k for k, j in _latest.items() if j.finished_at is not None and now - j.finished_at > FINISHED_TTL_SECONDS]
    for k in expired:
        del _latest[k]
    while len(_latest) > MAX_JOBS:
        del _latest[next(iter(_latest))]


@contextlib.contextmanager
def track(client_ip: str | None, source: str | None, *, steps: tuple[str, ...]) -> Iterator[Job | None]:
    """Track one validation request for its whole lifetime. Yields None (and
    tracks nothing) when there is no client IP or source to look it up by."""
    key = _key(client_ip, source)
    if key is None:
        yield None
        return
    job = Job(key=key, steps=steps, phase=steps[0])
    with _lock:
        _prune(time.monotonic())
        _latest[key] = job
    token = current.set(job)
    try:
        yield job
    except BaseException:
        # Cancelled, abandoned or failed: no report is on its way. Drop the job
        # instead of leaving a "finishing" entry that a quick re-submit of the
        # same source would pick up.
        with _lock:
            if _latest.get(key) is job:
                del _latest[key]
        raise
    finally:
        current.reset(token)
        job.finished_at = time.monotonic()


def report(phase: str) -> None:
    """Report that the current request's job entered `phase`. Phases outside
    the job's steps (such as the worker's final "done") are ignored."""
    job = current.get()
    if job is not None and phase in job.steps:
        job.phase = phase


def snapshot(client_ip: str | None, source: str | None) -> dict[str, object]:
    """What the browser's poll gets back for its (IP, source) job."""
    key = _key(client_ip, source)
    with _lock:
        _prune(time.monotonic())
        job = _latest.get(key) if key else None
    if job is None:
        return {"state": "waiting"}
    steps = len(job.steps)
    if job.finished_at is not None:
        return {"state": "finishing", "steps": steps}
    step = job.steps.index(job.phase) + 1 if job.phase in job.steps else 1
    return {
        "state": "running",
        "step": step,
        "steps": steps,
        "label": LABELS.get(job.steps[step - 1], ""),
    }
