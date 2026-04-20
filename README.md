# askwol 🦉

**askwol** gives your [OWL](https://www.w3.org/OWL/) ontology an instant health check: a visual class diagram, namespace verification, term validation, and a clean-up report.

> The W3C originally planned to call their Web Ontology Language **WOL**. Tim Finin [proposed rearranging it to **OWL**](http://lists.w3.org/Archives/Public/www-webont-wg/2001Dec/0169.html) because *"owls are associated with wisdom."* Scrambling three letters is of course exactly what [Owl](https://en.wikipedia.org/wiki/Owl_(Winnie-the-Pooh)) from Milne's *Winnie-the-Pooh* is famous for  -  he spells his own name **"WOL"**: *"wise though he was in many ways, able to read and write and spell his own name WOL, yet somehow went all to pieces over delicate words like MEASLES and BUTTEREDTOAST"* (Ch. 4, 1926).

<p align="center">
  <a href="https://commons.wikimedia.org/wiki/File:Winnie-the-Pooh_67.png">
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Winnie-the-Pooh_67.png/250px-Winnie-the-Pooh_67.png" alt="Owl by E.H. Shepard (1926, public domain)" width="180">
  </a>
</p>

## What do you get?

1. **Ontology diagram**  -  an interactive class diagram showing classes, properties, and inheritance hierarchy (web UI). Zoom, pan, and explore.
2. **Namespace resolution**  -  fetches each namespace URI, checks HTTP status, tries to parse as RDF (Turtle, RDF/XML, JSON-LD, N-Triples). Falls back to scanning HTML pages for RDF links.
3. **Term validation**  -  verifies that terms defined in your ontology (classes, properties, individuals) actually exist in the remote vocabularies they reference. Catches typos like `owl:MadeUpClass`.
4. **Unused prefixes**  -  flags `@prefix` declarations that are never used in any triple.
5. **Language tag consistency**  -  checks whether human-readable labels and definitions use language tags consistently across the ontology.

## Quick start

```bash
git clone <repo-url>
cd askwol
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"   # Python 3.10+
```

### Start the web server

```bash
PYTHONPATH=src .venv/bin/uvicorn askwol.web:app --reload --port 8000
```

Then open:

- http://127.0.0.1:8000/ for the upload form
- http://127.0.0.1:8000/docs for the API docs

## Usage

```bash
# Rich terminal output
askwol check ontology.ttl

# Markdown / JSON report
askwol check ontology.ttl --format markdown -o report.md
askwol check ontology.ttl --format json

# Options
askwol check ontology.ttl --timeout 60        # default: 30s
askwol check ontology.ttl --skip-resolution   # parse only
```

Exit codes: `0` all pass, `1` issues found.

### Web UI

```bash
PYTHONPATH=src .venv/bin/uvicorn askwol.web:app --reload --port 8000
```

Endpoints: `GET /` (upload form), `POST /validate` (HTML report), `POST /api/validate` (JSON), `GET /guide` (modeling guide), `GET /health`, `GET /docs` (Swagger / OpenAPI).

### Python API

```python
import asyncio
from askwol.parser import parse_ontology
from askwol.cache import OntologyCache
from askwol.resolver import resolve_all_namespaces
from askwol.term_validator import validate_terms

parsed = parse_ontology("ontology.ttl")
cache = OntologyCache()
checks = asyncio.run(resolve_all_namespaces(parsed.namespaces, cache))

for prefix, uri in parsed.namespaces.items():
    for r in validate_terms(prefix, uri, parsed.terms_by_namespace.get(prefix, set()), cache):
        print(f"{r.prefix}:{r.local_name} -> {r.status}")
```

## Supported formats

Turtle (`.ttl`), RDF/XML (`.rdf`, `.owl`), JSON-LD (`.jsonld`), N-Triples (`.nt`), N3 (`.n3`)

## Project structure

```
src/askwol/
├── cli.py           # Click CLI
├── web.py           # FastAPI web app
├── parser.py        # rdflib ontology parsing
├── resolver.py      # async HTTP namespace resolution
├── term_validator.py
├── cache.py         # in-memory ontology cache
├── models.py        # Pydantic models
└── report.py        # output formatting
```

## Tests

```bash
pytest tests/ -v
```

## Roadmap

- [ ] Scan for SKOS concepts, should be defined separately 
- [ ] Test with more ontologies


## License

MIT
