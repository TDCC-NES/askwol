# askwol 🦉

Check OWL ontologies during modelling and before publication. Get a report on namespaces, terms, metadata, documentation, and selected logical issues, plus an interactive class diagram in the web app.

[![Licence: MIT](https://img.shields.io/badge/Licence-MIT-blue.svg)](https://github.com/TDCC-NES/askwol/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/askwol)](https://pypi.org/project/askwol/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/TDCC-NES/askwol/actions/workflows/tests.yml/badge.svg)](https://github.com/TDCC-NES/askwol/actions/workflows/tests.yml)

**[Try online](https://lod-4tu.tudelft.nl/askwol/)** · **[Publishing guide](https://lod-4tu.tudelft.nl/askwol/guide)**

<p align="center">
  <img src="https://raw.githubusercontent.com/TDCC-NES/askwol/main/docs/screenshot.png" alt="askwol web UI screenshot" width="720">
</p>

Supported formats: Turtle (`.ttl`), RDF/XML (`.rdf`, `.owl`), JSON-LD (`.jsonld`), N-Triples (`.nt`), and N3 (`.n3`). See the [full list of checks](https://lod-4tu.tudelft.nl/askwol/#what-do-you-get); each report section links to the matching guide entry.

Findings count individual issues, not checks:

| Severity | Meaning |
| --- | --- |
| **Error** | A detected logical issue or violation of selected OWL restrictions. |
| **Warning** | A likely mistake or interoperability problem. |
| **Recommendation** | A publishing convention, such as metadata, licensing, or documentation. |

Reasoning uses the submitted document without imports. Passing these checks does not establish overall consistency or complete OWL conformance.

## Install

Python **3.10+** is required. For the CLI only, install with [pipx](https://pipx.pypa.io/stable/):

```bash
pipx install askwol
```

For local development, the web app, and the Python API (macOS/Linux):

```bash
git clone https://github.com/TDCC-NES/askwol.git
cd askwol
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Run locally

Run from the repository folder containing `pyproject.toml`, using the virtual environment above:

```bash
ASKWOL_ROOT_PATH= PYTHONPATH=src .venv/bin/python -m uvicorn \
  askwol.web:app --reload --reload-dir src --port 8000
```

Open the [checker](http://127.0.0.1:8000/), [guide](http://127.0.0.1:8000/guide), or [API docs](http://127.0.0.1:8000/docs). Python changes reload automatically; refresh the browser to see them. Stop with **Ctrl+C**.

## CLI

```bash
askwol check ontology.ttl
askwol check ontology.ttl --format json
askwol check ontology.ttl --format markdown -o report.md
askwol check ontology.ttl --skip-resolution
```

For a source install, use `.venv/bin/askwol` instead of `askwol`.

- `--timeout 60` sets the HTTP timeout in seconds (default: `30`).
- `--skip-resolution` skips namespace and import HTTP requests; local checks and reasoning still run.
- Exit code `0` means no errors; `1` means errors were found. Warnings and recommendations do not change the exit code.

## API

Upload a file to the running app for a JSON report:

```bash
curl -F "file=@ontology.ttl" http://127.0.0.1:8000/api/validate
```

JSON includes `severity_summary` with finding counts and `has_errors`. Per-check `status` values (`ok`, `warn`, `fail`, `skip`) describe outcomes, not severity. `/health` reports service availability.

To run the same checks from Python:

```python
import asyncio
from askwol.pipeline import run_full_validation

report, _ = asyncio.run(run_full_validation("ontology.ttl", include_mermaid=False))
print(report.model_dump_json(indent=2))
```

## Docker

From the repository root, build and start the app, or rebuild after changes:

```bash
docker compose up -d --build --force-recreate
```

The app is available at http://127.0.0.1:8000/. Logs: `docker compose logs -f askwol`. Stop: `docker compose down`.

For automatic reloading during development:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up --build
```

Keep that development override off production servers. The supplied production configuration uses **one web worker**, binds to `127.0.0.1:8000`, and persists usage data in `./data/`.

On a server, clone the repository, run the start command above, and put an HTTPS reverse proxy in front of it. For example, with Caddy:

```caddy
askwol.example.com {
    encode zstd gzip
    request_body { max_size 25MB }
    reverse_proxy 127.0.0.1:8000
}
```

For updates, run `git pull`, then repeat the build/start command.

### Serving under a sub-path

For a deployment at `/askwol/`, put this in the repository's `.env` file:

```dotenv
ASKWOL_ROOT_PATH=/askwol
```

The reverse proxy must strip the prefix before forwarding. With Caddy:

```caddy
server.example.com {
    handle_path /askwol/* {
        reverse_proxy 127.0.0.1:8000
    }
}
```

## Configuration

Native Python runs read environment variables, not `.env` files. Docker Compose forwards `ASKWOL_ROOT_PATH` and `ASKWOL_STATS_TOKEN` from `.env`; add other overrides under the service's `environment` in a Compose override file. Restart native runs or recreate Compose containers after changing settings.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ASKWOL_RATE_LIMIT` | `20` | Validation requests per client IP per minute, per worker; `0` disables. |
| `ASKWOL_VALIDATION_TIMEOUT` | `300` | Maximum seconds per web job. |
| `ASKWOL_MAX_CONCURRENT_VALIDATIONS` | `2` | Concurrent web jobs per worker. |
| `ASKWOL_MAX_TRIPLES` | `500000` | Maximum triples per ontology. |
| `ASKWOL_MAX_NAMESPACES` | `500` | Maximum declared prefixes per ontology. |
| `ASKWOL_MAX_IMPORTS` | `200` | Maximum declared imports per ontology. |
| `ASKWOL_USAGE_DB` | `data/usage.db` | Usage database path; Docker uses `/data/usage.db`. |
| `ASKWOL_USAGE_DISABLED` | unset | Set to `1` to disable usage tracking. |
| `ASKWOL_STATS_TOKEN` | unset | Enables access to usage statistics. |

Web uploads are capped at **20 MB**. Requests to private/internal network addresses are blocked. Web jobs run in isolated subprocesses: timeouts return `504`, and excess concurrent requests return `503`. Set the proxy timeout above the job timeout and enforce a proxy upload limit. The CLI shares the ontology size caps, but runs without the web job timeout or concurrency limit.

A client disconnect cancels its job when the reverse proxy forwards the disconnect. Cancelled requests do not count as usage.

### Usage tracking

A local SQLite database records timestamps, source URLs or filenames, HTTP statuses, durations, and IP hashes salted with a per-database secret. No cookies or third-party tracking services are used.

Set `ASKWOL_STATS_TOKEN` to a long random value (generate one with `openssl rand -hex 32`) and apply it as described above. `/stats` is the HTML dashboard; `/api/stats` returns JSON. Pass `?token=YOUR_TOKEN` to authenticate; local requests can omit it once a token is configured. Totals and daily counts cover all recorded activity; average duration uses the last 30 days.

## Tests

After the source installation above, run from the repository root:

```bash
.venv/bin/python -m pytest tests/ -q
```

For manual checks, upload [`sample.ttl`](https://github.com/TDCC-NES/askwol/blob/main/html/ontologies/sample.ttl) or [`broken.ttl`](https://github.com/TDCC-NES/askwol/blob/main/html/ontologies/broken.ttl) through the local app. Contribution guidelines: [CONTRIBUTING.md](https://github.com/TDCC-NES/askwol/blob/main/CONTRIBUTING.md).

## Why askwol?

The name plays on OWL and [“Wol,” Owl's misspelled name](https://lists.w3.org/Archives/Public/www-webont-wg/2002Sep/0301.html) in *Winnie-the-Pooh*: ask Owl for a second opinion on your ontology. Wollie, to friends.

## Licence

[MIT](https://github.com/TDCC-NES/askwol/blob/main/LICENSE).
