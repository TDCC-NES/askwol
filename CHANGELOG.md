# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-05-29

Initial public release.

- CLI (`askwol check`) with rich, markdown, and JSON output.
- Web UI (FastAPI) with class diagram, validation reports, and API at `/api/validate`.
- Namespace resolution with HTML-fallback link scanning.
- Term existence validation against remote vocabularies.
- SHACL-based metadata and definition documentation checks.
- OWL RL reasoner sanity check.
- Language-tag consistency check.
- Privacy-friendly, zero-dependency usage tracking with optional `/stats` endpoint.
- Docker and `docker compose` deployment with optional dev hot-reload override.
