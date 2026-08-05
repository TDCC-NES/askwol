"""Isolated validation worker, run as ``python -m askwol.validate_worker``.

Spawned as a fresh OS process per validation job by the web app (see
``web.py``'s ``run_isolated_validation``), so a slow or hung validation can
be killed outright without affecting any other concurrent request. Prints
one JSON result object to stdout when done; emits one JSON phase-update line
per pipeline stage to stderr as it progresses, so the parent process can log
what a job was doing even if it never finishes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from askwol.pipeline import run_full_validation


def _emit_phase(phase: str) -> None:
    sys.stderr.write(json.dumps({"phase": phase}) + "\n")
    sys.stderr.flush()


async def _run(args: argparse.Namespace) -> dict:
    report, mermaid = await run_full_validation(
        args.file,
        display_name=args.display_name,
        base_uri=args.base_uri,
        skip_resolution=args.skip_resolution,
        phase=_emit_phase,
    )
    return {"report": report.model_dump(mode="json"), "mermaid": mermaid}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one isolated ontology validation.")
    parser.add_argument("file", help="Path to the ontology file to validate.")
    parser.add_argument("--display-name", default=None, help="Name shown in the report (e.g. original URL or filename).")
    parser.add_argument("--base-uri", default=None, help="Published URI, for resolving relative IRIs.")
    parser.add_argument("--skip-resolution", action="store_true", help="Skip namespace/import HTTP resolution.")
    args = parser.parse_args()

    result = asyncio.run(_run(args))
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
