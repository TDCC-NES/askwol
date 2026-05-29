# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-05-29

Initial public release.

- CLI (`askwol check`) with rich, markdown, and JSON output.
- Web UI (FastAPI) with class diagram, validation reports, and API at `/api/validate`.
- Ten automated checks, each linked to a matching section in the built-in modeling guide at `/guide`:
  - Ontology metadata (SHACL: title, description, creator, license IRI, version required; created/modified/publisher recommended).
  - Imports completeness (external vocabularies used in triples must be declared in `owl:imports`; core W3C vocabularies excluded).
  - IRI strategy (hash vs slash consistency for the ontology's own defined terms).
  - IRI scheme (each host must be referenced under a single `http://` or `https://`, not both).
  - Namespace resolution with HTML-fallback link scanning.
  - Term existence validation against remote vocabularies.
  - Definition documentation (SHACL: every internal class/property carries both `rdfs:label` and `rdfs:comment`).
  - Language-tag consistency across labels and definitions.
  - OWL RL reasoner sanity check covering three facets: ontology consistency, inconsistent named individuals (e.g. typed in two `owl:disjointWith` classes), and unsatisfiable classes (definitions equivalent to `owl:Nothing`).
  - Unused-prefix detection.
- Import-time `assert` that keeps the report's `CHECKS` registry and the guide's `GUIDE_SECTIONS` aligned.
- 79 tests covering each check on good and bad inputs, HTML rendering, FastAPI routes via `TestClient`, and a pinned end-to-end smoke test on `tests/fixtures/broken.ttl`.
- Privacy-friendly, zero-dependency usage tracking with optional `/stats` endpoint.
- Docker and `docker compose` deployment with optional dev hot-reload override.
