"""FastAPI web application for the ontology checker."""

from __future__ import annotations

import tempfile
import time
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from rdflib import RDF, RDFS, OWL, Graph, URIRef

from askwol.cache import OntologyCache
from askwol.definition_docs import check_definition_documentation
from askwol.lang_tags import check_lang_tags
from askwol.metadata_validator import validate_ontology_metadata
from askwol.reasoner_checks import run_reasoner_checks
from askwol.models import NamespaceReport, Status, UnusedPrefix, ValidationReport
from askwol.parser import parse_ontology
from askwol.resolver import resolve_all_namespaces
from askwol.term_validator import validate_terms
from askwol import usage

app = FastAPI(
    title="askwol",
    description="Validate namespace resolution and term existence in OWL ontologies.",
    version="0.1.0",
)

# Global cache  -  persists across requests so repeated uploads don't re-fetch
_global_cache = OntologyCache()

UPLOAD_HTML = """<!DOCTYPE html>
<html>
<head><title>Ask Wol</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x1F989;</text></svg>">
<style>
  :root { --accent: #4a7c59; --accent-dark: #3d6a4a; --border: #e5e7eb; --muted: #6b7280; --bg-soft: #f9fafb; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; max-width: 720px; margin: 50px auto; padding: 0 20px; color: #1f2937; line-height: 1.6; }
  h1 { margin: 0.4em 0 0.1em; font-weight: 700; font-size: 2.4em; letter-spacing: -0.02em; display: flex; align-items: center; gap: 0.35em; }
  h1 .owl { font-size: 1.4em; line-height: 1; }
  h2 { color: #374151; margin-top: 1.8em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; font-weight: 600; }
  code { background: #f3f4f6; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
  a { color: var(--accent); }
  .topnav { margin-bottom: 1.2em; font-size: 0.95em; color: #4b5563; background: var(--bg-soft); border: 1px solid var(--border); border-radius: 8px; padding: 0.6em 0.9em; }

  /* Card form */
  .card { margin: 1.2em 0; padding: 1.5em; background: #fff; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.03); }

  /* Tabs */
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 1.2em; }
  .tab { padding: 0.55em 1.1em; font-size: 0.95em; cursor: pointer; background: none; border: none; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; font-weight: 500; }
  .tab:hover { color: #1f2937; }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  /* Inputs */
  label { display: block; font-size: 0.85em; color: var(--muted); margin-bottom: 0.35em; font-weight: 500; text-transform: uppercase; letter-spacing: 0.02em; }
  input[type=url], input[type=file] { width: 100%; padding: 0.6em 0.75em; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.95em; font-family: inherit; background: #fff; }
  input[type=url]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(74,124,89,0.15); }
  input[type=file] { padding: 0.5em; }

  /* Examples */
  .examples-label { font-size: 0.8em; color: var(--muted); margin: 1em 0 0.4em; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.4em; }
  .chip { padding: 0.3em 0.85em; font-size: 0.85em; background: #f3f4f6; color: #374151; border: 1px solid var(--border); border-radius: 999px; cursor: pointer; transition: all 0.15s; font-family: inherit; }
  .chip:hover { background: #eef3ef; color: var(--accent-dark); border-color: #cfdcd2; }

  /* Submit */
  .actions { margin-top: 1.4em; }
  button.submit { padding: 0.65em 1.8em; font-size: 1em; cursor: pointer; background: var(--accent); color: white; border: none; border-radius: 6px; font-weight: 500; font-family: inherit; transition: background 0.15s; }
  button.submit:hover { background: var(--accent-dark); }

  .about { margin-top: 2.5em; padding-top: 1.5em; border-top: 1px solid var(--border); color: #4b5563; font-size: 0.95em; }
  .about .wol-link { float: right; display: block; margin: 0 0 1em 1.5em; }
  .about img { width: 140px; border-radius: 6px; display: block; cursor: pointer; }
  .footer { margin-top: 2em; font-size: 0.85em; color: #9ca3af; text-align: center; }
</style>
</head>
<body>
  <p class="topnav">
    <strong>Navigation:</strong>
    <a href="/">Home</a> &middot;
    <a href="/guide">Modeling guide</a> &middot;
    <a href="/docs">API docs</a>
  </p>
  <h1><span class="owl" aria-hidden="true">&#x1F989;</span> Ask Wol</h1>
  <p>Your friendly owl for instant <a href="https://www.w3.org/OWL/">OWL</a>
  ontology reviews: a visual class diagram, namespace and term checks,
  metadata and documentation review, and a clean-up report.</p>

  <form class="card" action="/validate" method="post" enctype="multipart/form-data">
    <div class="tabs" role="tablist">
      <button type="button" class="tab active" data-tab="url" role="tab">From URL</button>
      <button type="button" class="tab" data-tab="file" role="tab">Upload file</button>
    </div>

    <div id="panel-url" class="tab-panel active">
      <label for="url-input">Ontology URL</label>
      <input type="url" id="url-input" name="url" placeholder="https://example.org/ontology.ttl" value="http://xmlns.com/foaf/spec/index.rdf">
      <div class="examples-label">Or try a well-known ontology</div>
      <div class="chips">
        <button type="button" class="chip" data-url="http://xmlns.com/foaf/spec/index.rdf">FOAF</button>
        <button type="button" class="chip" data-url="http://purl.org/dc/terms/">Dublin Core</button>
        <button type="button" class="chip" data-url="https://www.w3.org/ns/prov.ttl">PROV-O</button>
        <button type="button" class="chip" data-url="https://www.w3.org/2006/time">Time</button>
        <button type="button" class="chip" data-url="https://opengeospatial.github.io/ogc-geosparql/geosparql11/geo.ttl">GeoSPARQL</button>
      </div>
    </div>

    <div id="panel-file" class="tab-panel">
      <label for="file-input">Ontology file</label>
      <input type="file" id="file-input" name="file" accept=".ttl,.rdf,.owl,.jsonld,.nt,.n3">
      <div class="examples-label" style="margin-top:0.8em">Accepts Turtle, RDF/XML, JSON-LD, N-Triples, or N3.</div>
    </div>

    <div class="actions">
      <button type="submit" class="submit">Ask Wol</button>
    </div>
  </form>
  <script>
    // Tab switching: also clears the inactive panel's value so server gets only one input
    const urlInput = document.getElementById('url-input');
    const fileInput = document.getElementById('file-input');
    document.querySelectorAll('.tab').forEach(function(tab) {
      tab.addEventListener('click', function() {
        const target = tab.dataset.tab;
        document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + target));
        // Disable the inactive input so it isn't submitted
        if (target === 'url') { fileInput.disabled = true; urlInput.disabled = false; }
        else { urlInput.disabled = true; fileInput.disabled = false; }
      });
    });
    document.querySelectorAll('.chip').forEach(function(btn) {
      btn.addEventListener('click', function() {
        urlInput.value = btn.dataset.url;
        urlInput.focus();
      });
    });
  </script>

  <h2>What do you get?</h2>
  <ol>
    <li><strong>Ontology diagram</strong>  -  an interactive class
    diagram showing your classes, properties, and inheritance hierarchy.
    Zoom, pan, and explore.</li>
    <li><strong>Namespace resolution</strong>  -  fetches each namespace
    URI, checks HTTP status, tries to parse as RDF. Falls back to scanning
    HTML for RDF links.</li>
    <li><strong>Term validation</strong>  -  verifies that terms defined
    in your ontology (classes, properties, individuals) actually exist in
    the remote vocabularies they reference. Only terms that appear as
    <em>subjects</em> are checked  -  these are the concepts your
    ontology defines, not the vocabulary it references. Catches typos like
    <code>owl:MadeUpClass</code>.</li>
    <li><strong>Ontology metadata</strong>  -  evaluates SHACL
    shapes for the ontology itself: title, description, creator,
    license, version, and other key metadata.</li>
    <li><strong>Definition documentation</strong>  -  checks that
    your internally defined classes and properties have both
    <code>rdfs:label</code> and <code>rdfs:comment</code>.</li>
    <li><strong>Reasoner checks</strong>  -  checks the current ontology
    for logical consistency and unsatisfiable classes. Imports are not
    followed for this check.</li>
    <li><strong>Unused prefixes</strong>  -  flags
    <code>@prefix</code> declarations that are never used in any triple.
    Keeps your ontology tidy.</li>
    <li><strong>Language tag consistency</strong>  -  checks that
    language-tagged properties like <code>rdfs:label</code> and
    <code>skos:definition</code> use the same set of languages on every
    subject. Catches missing translations and bare strings.</li>
  </ol>

  <div class="about">
    <a class="wol-link" href="https://commons.wikimedia.org/wiki/File:Winnie-the-Pooh_67.png" target="_blank" rel="noopener" title="Open the image on Wikimedia Commons">
      <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Winnie-the-Pooh_67.png/250px-Winnie-the-Pooh_67.png"
           alt="Owl by E.H. Shepard (1926)">
    </a>
    <h2 style="margin-top:0; border:none; padding:0;">Why &ldquo;askwol&rdquo;?</h2>
    <p>
      The W3C originally called their language <strong>WOL</strong>. Tim Finin
      <a href="http://lists.w3.org/Archives/Public/www-webont-wg/2001Dec/0169.html">proposed
      rearranging it to <strong>OWL</strong></a> because <em>&ldquo;owls are
      associated with wisdom.&rdquo;</em> Scrambling three letters is of course
      what <a href="https://en.wikipedia.org/wiki/Owl_(Winnie-the-Pooh)">Owl</a>
      from Milne&rsquo;s <em>Winnie-the-Pooh</em> is famous for  -  he spells
      his own name <strong>WOL</strong>.
    </p>
    <h2 style="border:none; padding:0; margin-top:1.2em;">Built by TDCC-NES Ontology Engineers</h2>
    <p>
      <i>askwol</i> is developed and maintained by the
      <a href="https://tdcc.nl/nes-ontology-engineers/">TDCC-NES Ontology Engineers</a>:
      <strong>Kathrin F&uuml;llenbach</strong> and <strong>Dani Metilli</strong>.
      For questions, collaboration, or support, contact us at
      <a href="mailto:nes@tdcc.nl">nes@tdcc.nl</a>.
    </p>
    <p>
      Our work is fully funded by <a href="https://www.openscience.nl/en/">Open Science NL</a>.
      We support ontology selection and reuse, co-development,
      implementation, knowledge graph design, and training.
    </p>
  </div>

  <p class="footer">
    <strong>External links:</strong>
    <a href="https://tdcc.nl/nes-ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot;
    <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot;
    <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a>
  </p>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    return UPLOAD_HTML


@app.get("/health", summary="Health check", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/stats", include_in_schema=False)
async def stats_endpoint(token: str | None = None):
    """Internal usage dashboard. Requires ASKWOL_STATS_TOKEN env var to match `?token=`."""
    expected = usage.stats_token()
    if not expected:
        return JSONResponse(
            {"error": "stats disabled - set ASKWOL_STATS_TOKEN to enable"},
            status_code=503,
        )
    if token != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(usage.stats(days=30))


GUIDE_HTML = """<!DOCTYPE html>
<html>
<head><title>Ask Wol - Modeling Guide</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x1F989;</text></svg>">
<style>
  body { font-family: system-ui, sans-serif; max-width: 720px; margin: 50px auto; padding: 0 20px; color: #333; line-height: 1.7; }
  h1 { margin-bottom: 0.2em; }
  h2 { color: #555; margin-top: 2em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }
  h3 { color: #666; margin-top: 1.5em; }
  a { color: #4a7c59; }
  code { background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
  pre { background: #f7f7f7; padding: 1em; border-radius: 6px; overflow-x: auto; font-size: 0.88em; line-height: 1.5; }
  .tip { background: #f0f7f2; border-left: 4px solid #4a7c59; padding: 0.8em 1em; margin: 1em 0; border-radius: 0 6px 6px 0; }
  .warn { background: #fef9f0; border-left: 4px solid #d4a017; padding: 0.8em 1em; margin: 1em 0; border-radius: 0 6px 6px 0; }
  .footer { margin-top: 2.5em; font-size: 0.85em; color: #aaa; text-align: center; }
  .topnav { margin-bottom: 1em; font-size: 0.95em; color: #555; background: #f7f7f7; border: 1px solid #eee; border-radius: 8px; padding: 0.6em 0.9em; }
  .toc { background: #f9f9f9; padding: 1em 1.5em; border-radius: 8px; margin: 1.5em 0; }
  .toc ol { margin: 0.3em 0 0 0; padding-left: 1.5em; }
  .toc li { margin: 0.2em 0; }
</style>
</head>
<body>
  <p class="topnav">
    <strong>Navigation:</strong>
    <a href="/">Home</a> &middot;
    <a href="/guide">Modeling guide</a> &middot;
    <a href="/docs">API docs</a>
  </p>
  <h1>&#x1F989; How to Model a Good Ontology</h1>
  <p>A practical checklist for building OWL ontologies that are
  interoperable, resolvable, and maintainable. These are the things
  <a href="/">askwol</a> checks, and why they matter.</p>

  <div class="toc">
    <strong>Contents</strong>
    <ol>
      <li><a href="#define-terms">Define your terms</a></li>
      <li><a href="#resolvable">Make terms resolvable</a></li>
      <li><a href="#iri-strategy">Choose an IRI strategy</a></li>
      <li><a href="#https-http">Use https or http  -  but be consistent</a></li>
      <li><a href="#labels">Give concepts human-readable labels</a></li>
      <li><a href="#reuse">Reuse standard vocabularies</a></li>
      <li><a href="#imports">Declare imports explicitly</a></li>
      <li><a href="#prefixes">Keep your prefixes clean</a></li>
      <li><a href="#lang-tags">Use language tags consistently</a></li>
      <li><a href="#metadata">Give the ontology itself good metadata</a></li>
      <li><a href="#validate">Validate early and often</a></li>
    </ol>
  </div>

  <h2 id="define-terms">1. Define your terms</h2>
  <p>Every class, property, and individual in your ontology should have an
  explicit declaration. Don&rsquo;t just <em>use</em> a term  - 
  <em>define</em> it.</p>
  <pre>&lt;#Person&gt; a owl:Class ;
    rdfs:label "Person"@en ;
    rdfs:comment "A human being."@en .</pre>
  <div class="warn">If you reference <code>ex:Persom</code> but
  never define it, that&rsquo;s probably a typo. askwol catches these.</div>
  <div class="tip">askwol only validates terms that appear as
  <strong>subjects</strong> in your triples  -  these are the concepts
  your ontology <em>defines</em>. Terms used only as predicates or objects
  (like <code>rdfs:label</code> or <code>owl:Class</code>) are assumed to
  be well-known vocabulary and are not checked.</div>
  <div class="tip">askwol also uses SHACL to check whether each
  <em>internally defined</em> class and property has both an
  <code>rdfs:label</code> and an <code>rdfs:comment</code>. Reused external
  vocabulary terms are ignored. Missing items are shown in a table on the
  results page.</div>

  <h2 id="resolvable">2. Make terms resolvable</h2>
  <p>Every namespace URI should return something useful when fetched with HTTP.
  Ideally it returns RDF (content-negotiated), so tools can discover term
  definitions automatically.</p>
  <div class="tip"><strong>Good:</strong>
  <code>http://xmlns.com/foaf/0.1/</code> returns RDF when asked with
  <code>Accept: application/rdf+xml</code>.</div>
  <div class="warn"><strong>Bad:</strong> A namespace that returns
  404 or a generic HTML page with no RDF link.</div>
  <p>If you host your own ontology, configure your server to support
  <a href="https://www.w3.org/TR/swbp-vocab-pub/">content negotiation</a>
   -  serve RDF to machines and HTML to browsers.</p>

  <h2 id="iri-strategy">3. Choose an IRI strategy</h2>
  <p>Pick a consistent pattern for your term IRIs and stick with it.</p>
  <h3>Hash vs. slash</h3>
  <p>This is one of the oldest debates in semantic web engineering.
  The <a href="https://www.w3.org/TR/cooluris/">W3C &ldquo;Cool URIs for the
  Semantic Web&rdquo;</a> note (2008, with significant input from
  Tim Berners-Lee) describes both as valid approaches:</p>

  <p><strong>Hash URIs</strong>  -  <code>http://example.org/ont#Person</code></p>
  <ul>
    <li>The fragment (<code>#Person</code>) is <strong>stripped before the HTTP
    request</strong> is sent. The server never sees it  -  it returns the
    entire document at <code>http://example.org/ont</code>.</li>
    <li>All terms come back in a single request. Efficient, zero server
    configuration  -  just upload one RDF file.</li>
    <li>Downside: a client asking about <code>#PersonX</code> gets
    <em>every</em> term in the vocabulary. Fine for 50&nbsp;terms, painful
    for 50&thinsp;000.</li>
  </ul>

  <p><strong>Slash URIs</strong>  -  <code>http://example.org/ont/Person</code></p>
  <ul>
    <li>Each term is a first-class HTTP resource with its own URL.</li>
    <li>The server can return a targeted description (via a
    <code>303&nbsp;See&nbsp;Other</code> redirect to the describing document),
    as defined by the W3C TAG&rsquo;s
    <a href="http://lists.w3.org/Archives/Public/www-tag/2005Jun/0039.html">httpRange-14
    resolution</a> (2005).</li>
    <li>More flexible: each term can have its own HTML page, RDF description,
    and versioning. Better for large or growing vocabularies.</li>
    <li>Downside: requires server-side redirect rules and content
    negotiation.</li>
  </ul>

  <h3>What does Tim Berners-Lee say?</h3>
  <p>TBL&rsquo;s <a href="https://www.w3.org/Provider/Style/URI">&ldquo;Cool
  URIs don&rsquo;t change&rdquo;</a> (1998) focuses on one overriding
  principle: <strong>the URI you pick today must still work in 20&nbsp;years</strong>.
  Whether it contains a <code>#</code> or a <code>/</code> matters less than
  whether you can commit to keeping it alive.</p>
  <p>The Cool URIs for the Semantic Web note concludes:</p>
  <blockquote style="border-left:3px solid #ccc;padding-left:1em;color:#555;margin:1em 0;">
  &ldquo;Hash URIs should be preferred for rather <strong>small and stable</strong>
  sets of resources that evolve together. The ideal case are RDF Schema
  vocabularies and OWL ontologies. [&hellip;] 303&nbsp;URIs may also be
  used for [large] data sets, making neater-looking URIs.&rdquo;
  </blockquote>

  <h3>Who uses what?</h3>
  <table style="width:100%;border-collapse:collapse;font-size:0.9em;margin:0.5em 0 1em;">
    <tr style="border-bottom:2px solid #ddd;text-align:left;">
      <th style="padding:0.4em 0.6em;">Vocabulary</th>
      <th style="padding:0.4em 0.6em;">Pattern</th>
      <th style="padding:0.4em 0.6em;">Example</th></tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:0.3em 0.6em;">OWL</td>
      <td style="padding:0.3em 0.6em;">Hash</td>
      <td style="padding:0.3em 0.6em;"><code>owl:Class</code> = <code>http://&hellip;/owl#Class</code></td></tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:0.3em 0.6em;">RDF Schema</td>
      <td style="padding:0.3em 0.6em;">Hash</td>
      <td style="padding:0.3em 0.6em;"><code>rdfs:label</code> = <code>http://&hellip;/rdf-schema#label</code></td></tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:0.3em 0.6em;">FOAF</td>
      <td style="padding:0.3em 0.6em;">Slash (trailing)</td>
      <td style="padding:0.3em 0.6em;"><code>foaf:name</code> = <code>http://xmlns.com/foaf/0.1/name</code></td></tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:0.3em 0.6em;">Schema.org</td>
      <td style="padding:0.3em 0.6em;">Slash</td>
      <td style="padding:0.3em 0.6em;"><code>schema:Person</code> = <code>https://schema.org/Person</code></td></tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:0.3em 0.6em;">Dublin Core</td>
      <td style="padding:0.3em 0.6em;">Slash</td>
      <td style="padding:0.3em 0.6em;"><code>dct:title</code> = <code>http://purl.org/dc/terms/title</code></td></tr>
    <tr>
      <td style="padding:0.3em 0.6em;">DBpedia</td>
      <td style="padding:0.3em 0.6em;">Slash</td>
      <td style="padding:0.3em 0.6em;"><code>http://dbpedia.org/ontology/Person</code></td></tr>
  </table>

  <h3>Is preferring slash valid?</h3>
  <p><strong>Yes.</strong> Slash URIs are the mainstream choice for new
  vocabularies. Hash URIs are great for tiny, self-contained ontologies,
  but slash URIs give you more flexibility as things grow: individual term
  pages, per-term content negotiation, and the option to serve lightweight
  responses. Most major Linked Data projects (DBpedia, Wikidata,
  Schema.org, Dublin Core) use slash.</p>
  <div class="tip">If in doubt, go with slash  -  it scales.
  Use hash only when you know the vocabulary is small and will stay
  that way. Either way, <strong>pick one per namespace</strong> and
  don&rsquo;t mix them.</div>

  <h3>Persistent identifiers</h3>
  <p>Use a domain you control, or a persistent ID service like
  <a href="https://w3id.org/">w3id.org</a> or
  <a href="https://purl.org/">purl.org</a>,
  so your IRIs survive domain changes.</p>

  <h2 id="https-http">4. Use https or http  -  but be consistent</h2>
  <p><code>http://example.org/ont/Person</code> and
  <code>https://example.org/ont/Person</code> are
  <strong>different IRIs</strong> as far as RDF is concerned. Mixing
  schemes silently breaks <code>owl:sameAs</code>, SPARQL joins, and
  every tool that does string comparison on URIs.</p>

  <h3>The legacy problem</h3>
  <p>Most foundational vocabularies were minted before HTTPS was ubiquitous.
  OWL, RDFS, FOAF, Dublin Core, SKOS and PROV-O all use
  <code>http://</code>. Changing them would break billions of existing
  triples, so they stay on <code>http</code>.</p>
  <div class="warn"><strong>Do not</strong> &ldquo;fix&rdquo;
  <code>http://xmlns.com/foaf/0.1/name</code> to <code>https://</code>.
  You would be creating a <em>different</em> IRI that matches nothing in
  other people&rsquo;s data.</div>

  <h3>For your own ontology</h3>
  <ul>
    <li>New vocabularies: <strong><code>https://</code> is fine and recommended.</strong>
    Schema.org switched to <code>https</code> as its canonical scheme.</li>
    <li>Match what the vocabulary owner publishes. If their namespace is
    <code>http://</code>, use <code>http://</code>.</li>
    <li>Make sure your server redirects one scheme to the other
    (e.g.&nbsp;<code>http &rarr; https</code>), so both resolve, but always
    use the canonical form in your RDF.</li>
  </ul>
  <div class="tip"><strong>Rule of thumb:</strong> copy-paste the
  namespace IRI from the vocabulary&rsquo;s own ontology file. Don&rsquo;t
  retype it, don&rsquo;t &ldquo;upgrade&rdquo; the scheme.</div>

  <h2 id="labels">5. Give concepts human-readable labels</h2>
  <p>Every class and property should have at least:</p>
  <ul>
    <li><code>rdfs:label</code>  -  a short human-readable name</li>
    <li><code>rdfs:comment</code>  -  a brief description</li>
  </ul>
  <pre>&lt;#hasMother&gt; a owl:ObjectProperty ;
    rdfs:label "has mother"@en ;
    rdfs:comment "Relates a person to their biological mother."@en ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range &lt;#Person&gt; .</pre>
  <div class="tip">Use language tags (<code>@en</code>, <code>@de</code>)
  to support multilingual ontologies. Consider
  <code>skos:prefLabel</code> and <code>skos:altLabel</code> for richer
  labeling.</div>

  <h2 id="reuse">6. Reuse standard vocabularies</h2>
  <p>Don&rsquo;t reinvent the wheel. Before defining a new term, check if
  an established vocabulary already covers it:</p>
  <ul>
    <li><a href="https://schema.org/">schema.org</a>  -  broad web vocabulary</li>
    <li><a href="http://xmlns.com/foaf/0.1/">FOAF</a>  -  people and social networks</li>
    <li><a href="http://purl.org/dc/terms/">Dublin Core</a>  -  metadata (title, creator, date)</li>
    <li><a href="https://www.w3.org/2004/02/skos/core">SKOS</a>  -  concept schemes and thesauri</li>
    <li><a href="https://www.w3.org/ns/prov#">PROV-O</a>  -  provenance</li>
  </ul>
  <div class="warn">When reusing a term, use the <em>exact</em>
  IRI from the source vocabulary. A typo like <code>foaf:nme</code> instead
  of <code>foaf:name</code> silently breaks interoperability.</div>

  <h2 id="imports">7. Declare imports explicitly</h2>
  <p>If your ontology depends on another, say so with
  <code>owl:imports</code>:</p>
  <pre>&lt;http://example.org/my-ontology&gt; a owl:Ontology ;
    owl:imports &lt;http://xmlns.com/foaf/0.1/&gt; .</pre>
  <p>This tells reasoners and tools to load the imported ontology too.
  Without it, tools may not know where your external terms come from.</p>

  <h2 id="prefixes">8. Keep your prefixes clean</h2>
  <p>Only declare prefixes you actually use. Leftover
  <code>@prefix</code> declarations clutter the file and confuse
  readers  -  they suggest a dependency that doesn&rsquo;t exist.</p>
  <pre>@prefix dct: &lt;http://purl.org/dc/terms/&gt; .   -- used below
@prefix geo: &lt;http://www.opengis.net/ont/geosparql#&gt; .  -- unused, remove it</pre>
  <div class="tip">askwol flags every prefix that is declared
  but never appears in a triple, so you can clean them up.</div>

  <h2 id="lang-tags">9. Use language tags consistently</h2>
  <p>If your ontology includes human-readable labels and descriptions,
  use <a href="https://www.rfc-editor.org/rfc/bcp47">BCP 47 language tags</a>
  (<code>@en</code>, <code>@nl</code>, <code>@de</code>, &hellip;) on every
  literal that carries natural-language text.</p>
  <pre>:TestTrench a owl:Class ;
    rdfs:label "test trench"@en ,
               "proefsleuf"@nl ;
    skos:definition "A physical excavation &hellip;"@en ,
                    "Een fysieke opgraving &hellip;"@nl .</pre>
  <h3>Consistency rules</h3>
  <ul>
    <li><strong>No bare strings next to tagged ones.</strong> If
    <code>rdfs:label</code> uses <code>@en</code> on most subjects but one
    subject has a plain <code>"My label"</code> without a tag, that&rsquo;s
    inconsistent.</li>
    <li><strong>Same language set everywhere.</strong> If you provide
    <code>@en</code> and <code>@nl</code> labels on most classes, every
    class should have both. A missing <code>@nl</code> on one subject
    is probably an oversight.</li>
  </ul>
  <div class="warn">SPARQL filters like
  <code>FILTER(LANG(?label) = "en")</code> return nothing for untagged
  literals  -  your data becomes invisible.</div>
  <div class="tip">askwol checks
  <code>rdfs:label</code>, <code>rdfs:comment</code>,
  <code>skos:prefLabel</code>, <code>skos:definition</code>, and other
  standard annotation properties for tag consistency.</div>

  <h2 id="metadata">10. Give the ontology itself good metadata</h2>
  <p>Your ontology is itself a published research object. It should say
  what it is, who made it, which version it is, and under which license
  it can be reused.</p>
  <p>askwol evaluates SHACL shapes for the ontology header and checks these properties:</p>
  <ul>
    <li><strong>Required:</strong> <code>rdf:type owl:Ontology</code>,
    <code>dcterms:title</code> (or <code>rdfs:label</code>),
    <code>dcterms:description</code> (or <code>rdfs:comment</code>),
    <code>dcterms:creator</code>, <code>dcterms:license</code>, and
    <code>owl:versionInfo</code> or <code>owl:versionIRI</code>.</li>
    <li><strong>Recommended:</strong> <code>dcterms:created</code>
    (or <code>dcterms:issued</code>), <code>dcterms:modified</code>,
    and <code>dcterms:publisher</code>.</li>
  </ul>
  <pre>&lt;https://example.org/my-ontology&gt; a owl:Ontology ;
    dcterms:title "My Ontology"@en ;
    dcterms:description "What this ontology is about."@en ;
    dcterms:creator "Example Team" ;
    dcterms:license &lt;https://creativecommons.org/licenses/by/4.0/&gt; ;
    dcterms:created "2026-04-20"^^xsd:date ;
    dcterms:publisher "Example Institute" ;
    owl:versionInfo "1.0" .</pre>
  <div class="tip">Fill these in once and both humans and machines
  can understand the provenance and reuse conditions of your ontology.</div>

  <h3 id="versioning">Versioning</h3>
  <p>Version information is part of good ontology metadata. Use
  <code>owl:versionIRI</code> and/or <code>owl:versionInfo</code> to track
  changes over time:</p>
  <pre>&lt;http://example.org/my-ontology&gt; a owl:Ontology ;
    owl:versionIRI &lt;http://example.org/my-ontology/2.0&gt; ;
    owl:versionInfo "2.0" .</pre>
  <p>This lets consumers pin to a specific version and detect breaking changes.</p>

  <h2 id="validate">11. Validate early and often</h2>
  <p>Run <a href="/">askwol</a> on your ontology during development, not just
  before release. You get:</p>
  <ul>
    <li>An interactive <strong>class diagram</strong> of your ontology</li>
    <li>Broken namespace URIs (servers down, domains expired)</li>
    <li>Typos in term names (<code>owl:Clss</code> instead of <code>owl:Class</code>)</li>
    <li>Namespaces that don&rsquo;t serve RDF</li>
    <li>Terms that don&rsquo;t exist in the remote vocabulary</li>
    <li>Unused <code>@prefix</code> declarations</li>
    <li>Inconsistent language tags</li>
    <li>Missing <code>rdfs:label</code> or <code>rdfs:comment</code> on your own classes and properties</li>
    <li>Logical contradictions and unsatisfiable classes in the current ontology (without following imports)</li>
    <li>Missing ontology metadata (title, creator, license, version, and more)</li>
  </ul>
  <div class="tip">askwol also runs lightweight reasoner checks on the
  <em>current ontology only</em>. It does <strong>not</strong> follow
  <code>owl:imports</code> here, and it does not need dummy instances to spot
  obvious contradictions and unsatisfiable classes.</div>
  <div class="tip">Integrate validation into your CI pipeline:
  <code>askwol check my-ontology.ttl</code></div>

  <p class="footer">
    <strong>External links:</strong>
    <a href="https://tdcc.nl/nes-ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot;
    <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot;
    <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a>
  </p>
</body>
</html>"""


@app.get("/guide", response_class=HTMLResponse, include_in_schema=False)
async def guide():
    return GUIDE_HTML


@app.post("/validate", include_in_schema=False)
async def validate(
    request: Request,
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
):
    """Validate an ontology from file upload or URL."""
    started = time.perf_counter()
    client_ip = request.client.host if request.client else None
    source: str | None = None
    kind = "validate"

    if url and url.strip():
        source = url.strip()
        response = await _validate_url(source)
    elif file and file.filename:
        source = file.filename
        kind = "validate_upload"
        response = await _validate_upload(file)
    else:
        response = HTMLResponse("<p>Please provide a file or URL.</p>", status_code=400)

    usage.record(
        kind,
        source=source,
        status=str(response.status_code),
        duration_ms=int((time.perf_counter() - started) * 1000),
        ip=client_ip,
    )
    return response


async def _validate_url(url: str) -> HTMLResponse:
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        return HTMLResponse("<p>Only http/https URLs are supported.</p>", status_code=400)

    # Ask the server for RDF via content negotiation. Many namespace URIs
    # return HTML by default and only serve RDF when explicitly asked.
    accept_header = (
        "text/turtle, application/rdf+xml;q=0.9, application/ld+json;q=0.8, "
        "application/n-triples;q=0.7, text/n3;q=0.6, */*;q=0.1"
    )

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers={"Accept": accept_header})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return HTMLResponse(f"<p>Could not fetch URL: {escape(str(exc))}</p>", status_code=422)

    # Pick a suffix from the Content-Type so the parser can sniff the format.
    # Fall back to the URL path, then to .ttl.
    ctype = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    ctype_suffix = {
        "text/turtle": ".ttl",
        "application/x-turtle": ".ttl",
        "application/rdf+xml": ".rdf",
        "application/xml": ".rdf",
        "text/xml": ".rdf",
        "application/ld+json": ".jsonld",
        "application/json": ".jsonld",
        "application/n-triples": ".nt",
        "text/plain": ".nt",
        "text/n3": ".n3",
    }.get(ctype)

    if ctype in ("text/html", "application/xhtml+xml"):
        return HTMLResponse(
            f"<p>The URL <code>{escape(url)}</code> returned an HTML page "
            f"(<code>{escape(ctype)}</code>) instead of RDF. The server does not "
            f"support content negotiation for this namespace. Try a direct link "
            f"to the ontology file (e.g. <code>.ttl</code> or <code>.rdf</code>).</p>",
            status_code=415,
        )

    suffix = ctype_suffix or Path(parsed_url.path).suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = Path(tmp.name)

    return await _run_validation(tmp_path, url)


async def _validate_upload(file: UploadFile) -> HTMLResponse:
    content = await file.read()
    suffix = Path(file.filename or "ontology.ttl").suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    return await _run_validation(tmp_path, file.filename or "upload")


def _shorten(uri: str, namespaces: dict[str, str]) -> str:
    """Shorten a URI to prefix:local using the ontology's own prefixes."""
    uri_str = str(uri)
    for pfx, ns_uri in namespaces.items():
        if uri_str.startswith(ns_uri):
            local = uri_str[len(ns_uri):]
            if local:
                return f"{pfx}:{local}" if pfx else local
    # Fallback: use fragment or last path segment
    if "#" in uri_str:
        return uri_str.rsplit("#", 1)[-1]
    if "/" in uri_str:
        return uri_str.rsplit("/", 1)[-1]
    return uri_str


def _mermaid_id(label: str) -> str:
    """Make a label safe for use as a Mermaid node ID."""
    return label.replace(":", "_").replace("\u2236", "_").replace("-", "_").replace(".", "_").replace(" ", "_")


# U+2236 RATIO looks identical to a colon but doesn't trigger Mermaid's parser
_RATIO = "\u2236"


def _mermaid_text(label: str) -> str:
    """Make label safe for Mermaid edge/attribute text (replace : with RATIO)."""
    return label.replace(":", _RATIO)


def _build_mermaid(graph: Graph, namespaces: dict[str, str]) -> str:
    """Extract classes, properties, and relationships from the graph into a Mermaid class diagram."""
    lines = ["classDiagram"]

    # Collect classes
    classes: set[str] = set()
    for s, _, _ in graph.triples((None, RDF.type, OWL.Class)):
        if isinstance(s, URIRef):
            classes.add(str(s))
    for s, _, _ in graph.triples((None, RDF.type, RDFS.Class)):
        if isinstance(s, URIRef):
            classes.add(str(s))

    # Collect properties with domain/range
    properties: list[tuple[str, str | None, str | None, str]] = []  # (name, domain, range, kind)
    seen_props: set[str] = set()
    for pred_type, kind in [(OWL.ObjectProperty, "obj"), (OWL.DatatypeProperty, "data")]:
        for s, _, _ in graph.triples((None, RDF.type, pred_type)):
            if not isinstance(s, URIRef):
                continue
            prop_name = _shorten(str(s), namespaces)
            domains = [str(o) for _, _, o in graph.triples((s, RDFS.domain, None)) if isinstance(o, URIRef)]
            ranges = [str(o) for _, _, o in graph.triples((s, RDFS.range, None)) if isinstance(o, URIRef)]
            domain = domains[0] if domains else None
            rng = ranges[0] if ranges else None
            properties.append((prop_name, domain, rng, kind))
            seen_props.add(str(s))
            # Ensure domain/range classes appear even if not explicitly typed
            if domain:
                classes.add(domain)
            if rng and kind == "obj":
                classes.add(rng)

    # Also pick up plain rdf:Property (used by Dublin Core, schema.org, etc.)
    # — infer kind from the range URI (xsd:* or rdfs:Literal => data, else obj).
    xsd_ns = "http://www.w3.org/2001/XMLSchema#"
    rdfs_literal = "http://www.w3.org/2000/01/rdf-schema#Literal"
    for s, _, _ in graph.triples((None, RDF.type, RDF.Property)):
        if not isinstance(s, URIRef) or str(s) in seen_props:
            continue
        prop_name = _shorten(str(s), namespaces)
        domains = [str(o) for _, _, o in graph.triples((s, RDFS.domain, None)) if isinstance(o, URIRef)]
        ranges = [str(o) for _, _, o in graph.triples((s, RDFS.range, None)) if isinstance(o, URIRef)]
        domain = domains[0] if domains else None
        rng = ranges[0] if ranges else None
        if rng and (rng.startswith(xsd_ns) or rng == rdfs_literal):
            kind = "data"
        elif rng:
            kind = "obj"
        else:
            kind = "data"  # no range => assume literal/annotation
        properties.append((prop_name, domain, rng, kind))
        if domain:
            classes.add(domain)
        if rng and kind == "obj":
            classes.add(rng)

    # Collect subClassOf
    subclass_rels: list[tuple[str, str]] = []
    for s, _, o in graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            classes.add(str(s))
            classes.add(str(o))
            subclass_rels.append((str(s), str(o)))

    if not classes:
        return ""

    # Filter out well-known vocabulary classes (owl:, rdf:, rdfs:, xsd:)
    skip_ns = {
        "http://www.w3.org/2002/07/owl#",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://www.w3.org/2000/01/rdf-schema#",
        "http://www.w3.org/2001/XMLSchema#",
    }
    classes = {c for c in classes if not any(c.startswith(ns) for ns in skip_ns)}

    if not classes:
        return ""

    # Emit class nodes  -  quoted labels handle real colons fine
    for cls_uri in sorted(classes):
        label = _shorten(cls_uri, namespaces)
        mid = _mermaid_id(label)
        lines.append(f'    class {mid}["{label}"]')

    # Emit subClassOf (inheritance)
    for child, parent in subclass_rels:
        c_label = _shorten(child, namespaces)
        p_label = _shorten(parent, namespaces)
        if any(str(child).startswith(ns) for ns in skip_ns) or any(str(parent).startswith(ns) for ns in skip_ns):
            continue
        lines.append(f"    {_mermaid_id(p_label)} <|-- {_mermaid_id(c_label)}")

    # Emit object properties as associations
    for prop_name, domain, rng, kind in properties:
        if kind == "obj" and domain and rng:
            if any(domain.startswith(ns) for ns in skip_ns) or any(rng.startswith(ns) for ns in skip_ns):
                continue
            d_label = _shorten(domain, namespaces)
            r_label = _shorten(rng, namespaces)
            lines.append(f'    {_mermaid_id(d_label)} --> {_mermaid_id(r_label)} : {_mermaid_text(prop_name)}')
        elif kind == "data" and domain:
            if any(domain.startswith(ns) for ns in skip_ns):
                continue
            d_label = _shorten(domain, namespaces)
            rng_label = _mermaid_text(_shorten(rng, namespaces)) if rng else "Literal"
            d_mid = _mermaid_id(d_label)
            lines.append(f"    {d_mid} : {_mermaid_text(prop_name)} {rng_label}")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


async def _run_validation(tmp_path: Path, source_name: str) -> HTMLResponse:
    report = ValidationReport(file=source_name)
    cache = _global_cache
    mermaid = ""

    try:
        parsed = parse_ontology(tmp_path)
    except Exception as exc:
        report.parse_errors.append(str(exc))
        return HTMLResponse(_render_report(report, mermaid), status_code=422)
    finally:
        tmp_path.unlink(missing_ok=True)

    mermaid = _build_mermaid(parsed.graph, parsed.namespaces)

    # Detect unused prefixes
    used_prefixes = set(parsed.namespaces.keys())
    for pfx, uri in parsed.declared_prefixes.items():
        if pfx not in used_prefixes:
            report.unused_prefixes.append(UnusedPrefix(prefix=pfx, uri=uri))

    # Language tag consistency
    report.lang_tags = check_lang_tags(parsed.graph, parsed.namespaces)

    # Ontology metadata completeness
    report.ontology_metadata = validate_ontology_metadata(parsed.graph)

    # Internal definition documentation
    report.definition_docs = check_definition_documentation(parsed.graph)

    # Reasoner checks (current ontology only; imports are not followed)
    report.reasoner = run_reasoner_checks(parsed.graph)

    # Only resolve and report namespaces that have subject-position terms
    active_ns = {pfx: uri for pfx, uri in parsed.namespaces.items()
                 if parsed.terms_by_namespace.get(pfx)}

    ns_checks = await resolve_all_namespaces(active_ns, cache)
    ns_check_map = {c.uri: c for c in ns_checks}

    for prefix, uri in active_ns.items():
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())
        term_checks = validate_terms(prefix, uri, local_names, cache)

        report.namespaces.append(
            NamespaceReport(
                prefix=prefix,
                uri=uri,
                resolution=ns_check,
                terms=term_checks,
            )
        )

    return HTMLResponse(_render_report(report, mermaid))


@app.post(
    "/api/validate",
    response_model=ValidationReport,
    summary="Validate an ontology",
    tags=["validation"],
    responses={
        422: {"description": "Parse error  -  the file could not be parsed as RDF"},
    },
)
async def validate_api(
    file: UploadFile = File(..., description="OWL ontology file (Turtle, RDF/XML, JSON-LD, N-Triples, or N3)"),
):
    """Upload an OWL ontology and get a full validation report.

    Checks namespace resolution, term existence in remote vocabularies,
    flags unused prefix declarations, and evaluates ontology metadata
    SHACL shapes. Only terms that appear as subjects are validated.
    """
    content = await file.read()
    suffix = Path(file.filename or "ontology.ttl").suffix or ".ttl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    report = ValidationReport(file=file.filename or "upload")
    cache = _global_cache
    try:
        parsed = parse_ontology(tmp_path)
    except Exception as exc:
        report.parse_errors.append(str(exc))
        return JSONResponse(content=report.model_dump(mode="json"), status_code=422)
    finally:
        tmp_path.unlink(missing_ok=True)

    ns_checks = await resolve_all_namespaces(
        {pfx: uri for pfx, uri in parsed.namespaces.items()
         if parsed.terms_by_namespace.get(pfx)},
        cache,
    )
    ns_check_map = {c.uri: c for c in ns_checks}
    for prefix, uri in parsed.namespaces.items():
        if not parsed.terms_by_namespace.get(prefix):
            continue
        ns_check = ns_check_map[uri]
        local_names = parsed.terms_by_namespace.get(prefix, set())
        term_checks = validate_terms(prefix, uri, local_names, cache)
        report.namespaces.append(
            NamespaceReport(prefix=prefix, uri=uri, resolution=ns_check, terms=term_checks)
        )

    used_prefixes = set(parsed.namespaces.keys())
    for pfx, uri in parsed.declared_prefixes.items():
        if pfx not in used_prefixes:
            report.unused_prefixes.append(UnusedPrefix(prefix=pfx, uri=uri))

    report.lang_tags = check_lang_tags(parsed.graph, parsed.namespaces)
    report.ontology_metadata = validate_ontology_metadata(parsed.graph)
    report.definition_docs = check_definition_documentation(parsed.graph)
    report.reasoner = run_reasoner_checks(parsed.graph)

    return report.model_dump(mode="json")


def _render_report(report: ValidationReport, mermaid: str = "") -> str:
    source = escape(report.file)
    parts = [
        "<!DOCTYPE html><html><head><title>Ask Wol - results</title>",
        '<link rel="icon" href="data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><text y=\'.9em\' font-size=\'90\'>&#x1F989;</text></svg>">',
        "<style>",
        "  body { font-family: system-ui, sans-serif; max-width: 780px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.5; }",
        "  h1 { margin-bottom: 0.2em; }",
        "  h2 { color: #555; margin-top: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }",
        "  h3 { color: #666; margin-top: 1.2em; margin-bottom: 0.3em; font-size: 1em; }",
        "  a { color: #4a7c59; }",
        "  code { background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }",
        "  .summary { background: #f9f9f9; border: 1px solid #ddd; border-radius: 8px; padding: 1.2em 1.5em; margin: 1.2em 0; }",
        "  .summary td { padding: 0.45em 1.2em 0.45em 0; font-size: 1.05em; vertical-align: middle; }",
        "  .ns { margin-top: 1.5em; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }",
        "  .ns-header { background: #f5f5f5; padding: 0.6em 1em; font-weight: bold; border-bottom: 1px solid #ddd; }",
        "  .ns-body { padding: 0.5em 1em; }",
        "  table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }",
        "  th, td { text-align: left; padding: 0.3em 0.8em; border-bottom: 1px solid #f0f0f0; font-size: 0.9em; }",
        "  th { color: #666; font-weight: 600; }",
        "  .back { margin-top: 2em; }",
        "  .error { color: #c00; background: #fff0f0; padding: 0.8em; border-radius: 6px; }",
        "  .diagram { margin: 1.5em 0; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1em; background: #fafafa; position: relative; }",
        "  .diagram-viewport { width: 100%; height: 500px; overflow: hidden; border: 1px solid #eee; border-radius: 4px; background: #fff; }",
        "  .diagram-controls { display: flex; gap: 0.4em; margin-top: 0.5em; }",
        "  .diagram-controls button { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 0.3em 0.7em; cursor: pointer; font-size: 0.85em; }",
        "  .diagram-controls button:hover { background: #e8e8e8; }",
        "  .diagram h2 { margin: 0 0 0.5em 0; font-size: 1.1em; color: #555; }",
        "  .topnav { margin-bottom: 1em; font-size: 0.95em; color: #555; background: #f7f7f7; border: 1px solid #eee; border-radius: 8px; padding: 0.6em 0.9em; }",
        "  .section { background: #f9f9f9; border: 1px solid #eee; border-radius: 8px; padding: 0.8em 1.2em; margin: 1em 0; }",
        "  .section h2 { margin: 0 0 0.2em 0; font-size: 1.1em; color: #444; border: none; padding: 0; }",
        "  .section .subtitle { font-size: 0.9em; color: #666; margin: 0.35em 0; }",
        "  .warn-box { background: #fef9f0; border: 1px solid #e8d5a3; border-radius: 8px; padding: 0.8em 1.2em; margin: 1em 0; }",
        "  .footer { margin-top: 2em; font-size: 0.85em; color: #aaa; text-align: center; }",
        "</style>",
        "</head><body>",
        '<p class="topnav"><strong>Navigation:</strong> <a href="/">Home</a> &middot; <a href="/guide">Modeling guide</a> &middot; <a href="/docs">API docs</a></p>',
        f'<h1>Results for <code>{source}</code></h1>',
    ]

    if report.parse_errors:
        for err in report.parse_errors:
            parts.append(f'<div class="error"><strong>Parse error:</strong> {escape(err)}</div>')
        parts.append('</body></html>')
        return "\n".join(parts)

    def _status_mark(status: Status) -> str:
        return {
            'ok': '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>',
            'fail': '<span style="color:#c62828;font-size:1.3em;line-height:1">&#x2717;</span>',
            'warn': '<span style="color:#e6a700;font-size:1.3em;line-height:1">&#x26A0;</span>',
            'skip': '<span style="color:#888;font-size:1.3em;line-height:1">&#x2014;</span>',
        }[status.value]

    # Summary stats (computed now, rendered after diagram)
    total_ns = len(report.namespaces)
    ok_ns = sum(1 for ns in report.namespaces if ns.resolution.status == Status.OK)
    total_terms = sum(len(ns.terms) for ns in report.namespaces)
    ok_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.OK)
    fail_terms = sum(1 for ns in report.namespaces for t in ns.terms if t.status == Status.FAIL)

    # Ontology diagram (Mermaid)  -  shown first
    if mermaid:
        parts.append('<div class="diagram">')
        parts.append("<h2>Ontology diagram</h2>")
        parts.append('<div id="diagram-viewport" class="diagram-viewport">')
        parts.append(f'<pre class="mermaid">\n{mermaid}\n</pre>')
        parts.append('</div>')
        # Hidden copy of the Mermaid source so JS can copy / export it even
        # after Mermaid has replaced the <pre> with the rendered SVG.
        parts.append(f'<textarea id="mermaid-src" style="display:none">{escape(mermaid)}</textarea>')
        parts.append('<div class="diagram-controls">')
        parts.append('<button onclick="pzIn&amp;&amp;pzIn()">+ Zoom in</button>')
        parts.append('<button onclick="pzOut&amp;&amp;pzOut()">&minus; Zoom out</button>')
        parts.append('<button onclick="pzReset&amp;&amp;pzReset()">Reset view</button>')
        parts.append('<button onclick="copyMermaid&amp;&amp;copyMermaid(this)">Copy Mermaid</button>')
        parts.append('<button onclick="downloadSVG&amp;&amp;downloadSVG()">Download SVG</button>')
        parts.append('<button onclick="downloadPNG&amp;&amp;downloadPNG()">Download PNG</button>')
        parts.append('<span style="font-size:0.8em;color:#999;margin-left:0.5em;">Ctrl+scroll to zoom, drag to pan</span>')
        parts.append('</div>')
        parts.append("</div>")

    # Summary  -  right before the detail cards
    _ok = '<span style="color:#2e7d32;font-size:1.1em;line-height:1;vertical-align:middle">&#x2713;</span>'
    _fail = '<span style="color:#c62828;font-size:1.1em;line-height:1;vertical-align:middle">&#x2717;</span>'
    _warn = '<span style="color:#e6a700;font-size:1.1em;line-height:1;vertical-align:middle">&#x26A0;</span>'
    ns_mark = _ok if ok_ns == total_ns else _fail
    term_mark = _ok if fail_terms == 0 else _fail
    parts.append('<div class="summary"><table>')
    parts.append(f'<tr><td>{ns_mark} <strong>Namespaces</strong></td><td>{ok_ns}/{total_ns} resolved</td></tr>')
    parts.append(f'<tr><td>{term_mark} <strong>Terms</strong></td><td>{ok_terms} confirmed, {fail_terms} failed, {total_terms - ok_terms - fail_terms} skipped</td></tr>')
    meta = report.ontology_metadata
    if meta and meta.total_checks:
        meta_mark = _ok if not meta.failed_checks and not meta.warning_checks else (_warn if not meta.failed_checks else _fail)
        if meta.failed_checks or meta.warning_checks:
            bits = [f'{meta.passed_checks}/{meta.total_checks} OK']
            if meta.failed_checks:
                bits.append(f'{meta.failed_checks} required missing')
            if meta.warning_checks:
                bits.append(f'{meta.warning_checks} recommended missing')
            parts.append(f'<tr><td>{meta_mark} <strong>Ontology metadata</strong></td><td>{", ".join(bits)}</td></tr>')
        else:
            parts.append(f'<tr><td>{meta_mark} <strong>Ontology metadata</strong></td><td>{meta.total_checks}/{meta.total_checks} OK</td></tr>')
    docs = report.definition_docs
    if docs and docs.total_definitions:
        docs_mark = _ok if not docs.issues else _fail
        if docs.issues:
            parts.append(f'<tr><td>{docs_mark} <strong>Definition docs</strong></td><td>{docs.documented_definitions}/{docs.total_definitions} complete, {len(docs.issues)} missing label/comment</td></tr>')
        else:
            parts.append(f'<tr><td>{docs_mark} <strong>Definition docs</strong></td><td>{docs.total_definitions}/{docs.total_definitions} complete</td></tr>')
    reasoner = report.reasoner
    if reasoner:
        reas_ok = reasoner.consistent and not reasoner.unsatisfiable_classes
        reas_mark = _ok if reas_ok else _fail
        if reas_ok:
            parts.append(f'<tr><td>{reas_mark} <strong>Reasoner checks</strong></td><td>consistent</td></tr>')
        else:
            parts.append(f'<tr><td>{reas_mark} <strong>Reasoner checks</strong></td><td>{len(reasoner.inconsistent_individuals)} inconsistency issue(s), {len(reasoner.unsatisfiable_classes)} unsatisfiable class(es)</td></tr>')
    lt = report.lang_tags
    if lt and lt.languages_used:
        lang_str = ", ".join(lt.languages_used)
        issue_count = len(lt.issues)
        lang_mark = _ok if not issue_count else _warn
        if issue_count:
            parts.append(f'<tr><td>{lang_mark} <strong>Language tags</strong></td><td>{lang_str} &ndash; {issue_count} issue{"s" if issue_count != 1 else ""}</td></tr>')
        else:
            parts.append(f'<tr><td>{lang_mark} <strong>Language tags</strong></td><td>{lang_str} &ndash; consistent</td></tr>')
    parts.append("</table></div>")

    # Tip: link to the modeling guide
    parts.append('<p style="font-size:0.9em;color:#666;margin:0.5em 0 1em;">Not sure what a check means? See the <a href="/guide">modeling guide</a> for explanations and best practices.</p>')

    # Per-namespace details  -  split into "interesting" and "standard OK"
    STANDARD_NS = {
        "http://www.w3.org/2002/07/owl#",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://www.w3.org/2000/01/rdf-schema#",
        "http://www.w3.org/2001/XMLSchema#",
        "http://www.w3.org/XML/1998/namespace",
        "http://www.w3.org/2004/02/skos/core#",
        "http://www.w3.org/ns/prov#",
        "http://purl.org/dc/terms/",
        "http://purl.org/dc/elements/1.1/",
        "http://xmlns.com/foaf/0.1/",
        "https://schema.org/",
        "http://schema.org/",
        "http://www.w3.org/ns/shacl#",
        "http://www.w3.org/2006/time#",
        "http://www.w3.org/ns/dcat#",
        "http://www.opengis.net/ont/geosparql#",
    }

    def _ns_has_issues(ns: NamespaceReport) -> bool:
        if ns.resolution.status != Status.OK:
            return True
        return any(t.status == Status.FAIL for t in ns.terms)

    prominent = [ns for ns in report.namespaces if _ns_has_issues(ns) or ns.uri not in STANDARD_NS]
    standard_ok = sorted(
        [ns for ns in report.namespaces if not _ns_has_issues(ns) and ns.uri in STANDARD_NS],
        key=lambda ns: ns.prefix.lower(),
    )

    def _render_ns_card(ns: NamespaceReport) -> None:
        mark = _status_mark(ns.resolution.status)
        prefix = escape(ns.prefix) or "<em>(default)</em>"
        uri = escape(ns.uri)
        parts.append(f'<div class="ns"><div class="ns-header">{mark} {prefix}: &lt;{uri}&gt;</div>')
        parts.append('<div class="ns-body">')

        res = ns.resolution
        if res.http_status:
            parts.append(f"<p>HTTP {res.http_status}")
            if res.content_type:
                parts.append(f" &middot; {escape(res.content_type)}")
            if res.is_valid_rdf is not None:
                parts.append(f" &middot; {'valid' if res.is_valid_rdf else 'invalid'} RDF")
            parts.append("</p>")
        if res.error:
            parts.append(f"<p style='color:#c00'>{escape(res.error)}</p>")

        if ns.terms:
            t_ok = sum(1 for t in ns.terms if t.status == Status.OK)
            t_fail = sum(1 for t in ns.terms if t.status == Status.FAIL)
            t_skip = sum(1 for t in ns.terms if t.status == Status.SKIP)
            summary_parts = []
            if t_ok:
                summary_parts.append(f"{t_ok} confirmed")
            if t_fail:
                summary_parts.append(f"{t_fail} not found")
            if t_skip:
                summary_parts.append(f"{t_skip} skipped")
            parts.append(f'<p style="font-size:0.9em;color:#666;">{" &middot; ".join(summary_parts)}</p>')

            has_issues = t_fail > 0 or t_skip > 0
            if has_issues:
                issue_terms = [t for t in ns.terms if t.status != Status.OK]
                unique_errors = set(t.error for t in issue_terms if t.error)

                if len(unique_errors) == 1:
                    shared_err = next(iter(unique_errors))
                    if shared_err != res.error:
                        parts.append(f'<p style="color:#c00;font-size:0.9em;">{escape(shared_err)}</p>')
                    term_links = ", ".join(
                        f'<a href="{escape(t.term_uri)}" target="_blank" rel="noopener"><code>{escape(t.local_name)}</code></a>'
                        for t in issue_terms
                    )
                    parts.append(f'<p style="font-size:0.85em;">{term_links}</p>')
                else:
                    parts.append("<table><tr><th>Term</th><th>Status</th><th>Detail</th></tr>")
                    for t in issue_terms:
                        t_iri = escape(t.term_uri)
                        t_name = escape(t.local_name)
                        t_err = escape(t.error) if t.error else ""
                        t_mark = _status_mark(t.status)
                        parts.append(f'<tr><td><a href="{t_iri}" target="_blank" rel="noopener"><code>{t_name}</code></a></td><td>{t_mark}</td><td>{t_err}</td></tr>')
                    parts.append("</table>")

            ok_terms_list = [t for t in ns.terms if t.status == Status.OK]
            if ok_terms_list:
                if has_issues:
                    parts.append('<p style="font-size:0.9em;color:#666;margin-top:0.8em;">Confirmed:</p>')
                parts.append("<table><tr><th>Term</th></tr>")
                for t in ok_terms_list:
                    t_iri = escape(t.term_uri)
                    t_name = escape(t.local_name)
                    parts.append(f'<tr><td><a href="{t_iri}" target="_blank" rel="noopener"><code>{t_name}</code></a></td></tr>')
                parts.append("</table>")
        else:
            parts.append("<p><em>No terms used from this namespace.</em></p>")

        parts.append("</div></div>")

    if prominent:
        parts.append('<h2>Namespace IRI checks</h2>')
        failed_ns = [ns for ns in prominent if ns.resolution.status == Status.FAIL]
        warn_ns = [ns for ns in prominent if ns.resolution.status == Status.WARN]
        ok_ns_list = [ns for ns in prominent if ns.resolution.status == Status.OK]

        if failed_ns:
            http_404 = [ns for ns in failed_ns if ns.resolution.http_status == 404]
            http_other = [ns for ns in failed_ns if ns.resolution.http_status and ns.resolution.http_status != 404]
            conn_err = [ns for ns in failed_ns if not ns.resolution.http_status]

            if http_404:
                parts.append(f'<h3>404 Not Found ({len(http_404)})</h3>')
                for ns in http_404:
                    _render_ns_card(ns)
            if http_other:
                for ns in http_other:
                    parts.append(f'<h3>HTTP {ns.resolution.http_status}</h3>')
                    _render_ns_card(ns)
            if conn_err:
                parts.append(f'<h3>Connection errors ({len(conn_err)})</h3>')
                for ns in conn_err:
                    _render_ns_card(ns)

        if warn_ns:
            parts.append(f'<h3>Warnings ({len(warn_ns)})</h3>')
            for ns in warn_ns:
                _render_ns_card(ns)

        if ok_ns_list:
            parts.append(f'<h3>Resolved OK ({len(ok_ns_list)})</h3>')
            for ns in ok_ns_list:
                _render_ns_card(ns)

    if standard_ok:
        total_std_terms = sum(len(ns.terms) for ns in standard_ok)
        parts.append(f'<details style="margin-top:1.5em;"><summary style="cursor:pointer;padding:0.6em 0;font-weight:bold;color:#555;">')
        parts.append(f'{len(standard_ok)} standard vocabularies OK ({total_std_terms} terms verified)</summary>')
        for ns in standard_ok:
            _render_ns_card(ns)
        parts.append("</details>")

    # Ontology metadata summary
    meta = report.ontology_metadata
    if meta and meta.checks:
        missing_required = [c for c in meta.checks if c.status == Status.FAIL]
        missing_recommended = [c for c in meta.checks if c.status == Status.WARN]
        parts.append('<section class="section">')
        parts.append('<h2>Ontology metadata</h2>')
        parts.append('<p class="subtitle">Checked against SHACL shapes for the ontology header.</p>')
        summary_bits = [f"{meta.passed_checks} present"]
        if missing_required:
            summary_bits.append(f"{len(missing_required)} required missing")
        if missing_recommended:
            summary_bits.append(f"{len(missing_recommended)} recommended missing")
        parts.append(f'<p class="subtitle">{" &middot; ".join(summary_bits)}</p>')
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show metadata checks ({meta.total_checks})</summary>')
        parts.append('<table><tr><th>Property</th><th>Level</th><th>Status</th></tr>')
        for check in meta.checks:
            mark = _status_mark(check.status)
            if check.status == Status.OK:
                status_label = '<span style="color:#2e7d32">ok</span>'
            elif check.status == Status.WARN:
                status_label = '<span style="color:#e6a700">warning</span>'
            else:
                status_label = '<span style="color:#c62828">missing</span>'
            parts.append(
                f'<tr><td><code>{escape(check.property)}</code></td><td>{escape(check.severity)}</td><td>{mark} {status_label}</td></tr>'
            )
        parts.append('</table></details>')
        parts.append('</section>')

    # Internal definition documentation summary
    docs = report.definition_docs
    if docs and docs.total_definitions:
        incomplete = docs.total_definitions - docs.documented_definitions
        parts.append('<section class="section">')
        parts.append('<h2>Definition documentation</h2>')
        parts.append('<p class="subtitle">Internal classes and properties only. Reused external vocabulary terms are ignored.</p>')
        parts.append(f'<p class="subtitle">{docs.documented_definitions} complete &middot; {incomplete} incomplete</p>')
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show documentation checks ({docs.total_definitions})</summary>')
        parts.append('<table><tr><th>Term</th><th>Type</th><th>Label</th><th>Comment</th></tr>')
        for check in sorted(docs.checks, key=lambda c: (c.status == Status.OK, c.display_name.lower())):
            term = escape(check.display_name)
            term_uri = escape(check.term)
            label_status = '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>' if check.has_label else '<span style="color:#c62828;font-size:1.3em;line-height:1">&#x2717;</span>'
            comment_status = '<span style="color:#2e7d32;font-size:1.3em;line-height:1">&#x2713;</span>' if check.has_comment else '<span style="color:#c62828;font-size:1.3em;line-height:1">&#x2717;</span>'
            parts.append(
                f'<tr><td><a href="{term_uri}" target="_blank" rel="noopener"><code>{term}</code></a></td><td>{escape(check.term_type)}</td><td>{label_status}</td><td>{comment_status}</td></tr>'
            )
        parts.append('</table></details>')
        parts.append('</section>')

    # Reasoner checks
    reasoner = report.reasoner
    if reasoner and reasoner.checks:
        parts.append('<section class="section">')
        parts.append('<h2>Reasoner checks</h2>')
        parts.append('<p class="subtitle">Current ontology only &ndash; owl:imports are not followed for this check.</p>')
        parts.append(f'<details><summary style="cursor:pointer;font-weight:600;">Show reasoner checks ({len(reasoner.checks)})</summary>')
        parts.append('<table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>')
        for check in reasoner.checks:
            mark = _status_mark(check.status)
            if check.status == Status.OK:
                status_label = '<span style="color:#2e7d32">ok</span>'
            elif check.status == Status.WARN:
                status_label = '<span style="color:#e6a700">warning</span>'
            else:
                status_label = '<span style="color:#c62828">fail</span>'
            parts.append(f'<tr><td>{escape(check.label)}</td><td>{mark} {status_label}</td><td>{escape(check.message or "")}</td></tr>')
        parts.append('</table></details>')
        parts.append('</section>')

    # Unused prefixes warning
    if report.unused_prefixes:
        parts.append('<h2>Unused prefixes</h2>')
        parts.append('<div class="warn-box">')
        parts.append(f'<strong>{len(report.unused_prefixes)} declared but never used in any triple:</strong>')
        parts.append('<ul style="margin:0.3em 0 0;padding-left:1.5em;">')
        for up in report.unused_prefixes:
            pfx = escape(up.prefix) or "<em>(default)</em>"
            uri = escape(up.uri)
            parts.append(f"<li><code>{pfx}:</code> &lt;{uri}&gt;</li>")
        parts.append("</ul></div>")

    # Language tag consistency
    lt = report.lang_tags
    if lt and lt.issues:
        n_issues = len(lt.issues)
        n_missing_tag = sum(1 for i in lt.issues if i.issue_type == "missing_tag")
        n_missing_lang = sum(1 for i in lt.issues if i.issue_type == "missing_language")
        summary_bits = []
        if n_missing_tag:
            summary_bits.append(f"{n_missing_tag} untagged")
        if n_missing_lang:
            summary_bits.append(f"{n_missing_lang} missing translation{'s' if n_missing_lang != 1 else ''}")
        summary_text = " &middot; ".join(summary_bits) if summary_bits else ""

        parts.append('<h2>Language tag consistency</h2>')
        parts.append('<details class="warn-box">')
        parts.append(f'<summary style="cursor:pointer;font-weight:bold;">{n_issues} consistency issue{"s" if n_issues != 1 else ""}'
                     f'{f" ({summary_text})" if summary_text else ""}</summary>')

        # Build a quick lookup from property name to its summary
        prop_summary_map = {ps.property: ps for ps in (lt.property_summaries or [])}

        # Group issues by property for cleaner display
        by_prop: dict[str, list] = {}
        for issue in lt.issues:
            by_prop.setdefault(issue.property, []).append(issue)

        for prop, issues in sorted(by_prop.items()):
            ps = prop_summary_map.get(prop)
            parts.append(f'<p style="margin:0.8em 0 0.2em;font-weight:600;font-size:0.95em;"><code>{escape(prop)}</code></p>')

            # Explain WHY these languages are expected
            if ps:
                langs_str = ", ".join(f"<code>{escape(l)}</code>" for l in ps.languages)
                parts.append(f'<p style="font-size:0.85em;color:#666;margin:0.2em 0;">'
                             f'{ps.consistent_subjects} of {ps.total_subjects} subjects use {langs_str} correctly')
                if ps.examples:
                    examples_str = ", ".join(f"<code>{escape(e)}</code>" for e in ps.examples)
                    parts.append(f' (e.g. {examples_str})')
                parts.append('</p>')

            parts.append('<table><tr><th>Subject</th><th>Issue</th><th>Has</th><th>Expected</th></tr>')
            for issue in issues:
                has = ", ".join(issue.languages_found) if issue.languages_found else "<em>none</em>"
                expected = ", ".join(issue.languages_expected)
                parts.append(f'<tr><td><code>{escape(issue.subject)}</code></td>'
                             f'<td>{escape(issue.detail)}</td>'
                             f'<td>{has}</td><td>{expected}</td></tr>')
            parts.append('</table>')
        parts.append("</details>")

    parts.append('<p class="footer"><strong>External links:</strong> <a href="https://tdcc.nl/nes-ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot; <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot; <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a></p>')
    if mermaid:
        parts.append("""<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
const vp = document.getElementById('diagram-viewport');
function showError(msg) {
  if (vp) vp.innerHTML = '<div style="padding:1em;color:#c00;font-family:monospace;font-size:0.85em;white-space:pre-wrap;">Diagram error: ' + msg + '</div>';
  console.error('[askwol diagram]', msg);
}
try {
  mermaid.initialize({startOnLoad:false,theme:"neutral",securityLevel:"loose"});
  await mermaid.run();
} catch (e) {
  showError(String(e && e.message || e));
}
const svg = vp && vp.querySelector('svg');
if (!svg) {
  showError('Mermaid did not produce an SVG. Check the Mermaid source via the "Copy Mermaid" button.');
} else {
  // Read Mermaid's own viewBox (it always sets one)
  const vb = svg.viewBox.baseVal;
  let origX = vb.x, origY = vb.y, origW = vb.width, origH = vb.height;
  if (origW === 0 || origH === 0) {
    // Fallback if somehow no viewBox
    const bbox = svg.getBBox();
    origX = bbox.x - 20; origY = bbox.y - 20;
    origW = bbox.width + 40; origH = bbox.height + 40;
  }
  // Remember pristine values for export (before aspect-ratio padding)
  const pristineX = origX, pristineY = origY, pristineW = origW, pristineH = origH;

  // Fill the container  -  disable preserveAspectRatio so viewBox maps 1:1
  svg.removeAttribute('style');
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.style.display = 'block';

  // Adjust viewBox to match container aspect ratio so mapping is 1:1
  const cW = vp.clientWidth, cH = vp.clientHeight;
  const cAR = cW / cH, sAR = origW / origH;
  if (cAR > sAR) {
    // Container wider: expand viewBox width
    const nw = origH * cAR;
    origX -= (nw - origW) / 2; origW = nw;
  } else {
    // Container taller: expand viewBox height
    const nh = origW / cAR;
    origY -= (nh - origH) / 2; origH = nh;
  }

  let curX = origX, curY = origY, curW = origW, curH = origH;
  function setVB() { svg.setAttribute('viewBox', `${curX} ${curY} ${curW} ${curH}`); }
  setVB();

  // Zoom: shrink/grow viewBox around mouse
  let dragging = false, lastMX, lastMY;
  vp.addEventListener('wheel', (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const rect = vp.getBoundingClientRect();
    const fx = (e.clientX - rect.left) / rect.width;
    const fy = (e.clientY - rect.top) / rect.height;
    const f = e.deltaY > 0 ? 1.15 : 1/1.15;
    const nw = curW * f, nh = curH * f;
    curX += (curW - nw) * fx;
    curY += (curH - nh) * fy;
    curW = nw; curH = nh;
    setVB();
  }, {passive: false});

  // Pan: drag to shift viewBox
  vp.addEventListener('mousedown', (e) => {
    dragging = true; lastMX = e.clientX; lastMY = e.clientY;
    vp.style.cursor = 'grabbing';
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const rect = vp.getBoundingClientRect();
    curX -= (e.clientX - lastMX) / rect.width * curW;
    curY -= (e.clientY - lastMY) / rect.height * curH;
    lastMX = e.clientX; lastMY = e.clientY;
    setVB();
  });
  window.addEventListener('mouseup', () => { dragging = false; vp.style.cursor = 'grab'; });
  vp.style.cursor = 'grab';

  // Button handlers
  const zf = 1.3;
  window.pzIn = () => { const nw=curW/zf, nh=curH/zf; curX+=(curW-nw)/2; curY+=(curH-nh)/2; curW=nw; curH=nh; setVB(); };
  window.pzOut = () => { const nw=curW*zf, nh=curH*zf; curX+=(curW-nw)/2; curY+=(curH-nh)/2; curW=nw; curH=nh; setVB(); };
  window.pzReset = () => { curX=origX; curY=origY; curW=origW; curH=origH; setVB(); };

  // Build a clean, exportable SVG (original size, preserved aspect ratio)
  function buildExportSVG() {
    const clone = svg.cloneNode(true);
    clone.setAttribute('viewBox', `${pristineX} ${pristineY} ${pristineW} ${pristineH}`);
    clone.setAttribute('width', String(pristineW));
    clone.setAttribute('height', String(pristineH));
    clone.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
    return '<?xml version="1.0" encoding="UTF-8"?>\\n' + new XMLSerializer().serializeToString(clone);
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.copyMermaid = async (btn) => {
    const src = document.getElementById('mermaid-src').value;
    try {
      await navigator.clipboard.writeText(src);
      const old = btn.textContent; btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = old; }, 1500);
    } catch (e) {
      alert('Could not copy: ' + e);
    }
  };

  window.downloadSVG = () => {
    const blob = new Blob([buildExportSVG()], {type: 'image/svg+xml'});
    triggerDownload(blob, 'ontology-diagram.svg');
  };

  window.downloadPNG = () => {
    const svgStr = buildExportSVG();
    // Use a data URL (works more reliably than blob: across browsers)
    const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgStr);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const scale = 2;
      const w = Math.max(1, Math.round(pristineW * scale));
      const h = Math.max(1, Math.round(pristineH * scale));
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      try {
        canvas.toBlob((blob) => {
          if (blob) triggerDownload(blob, 'ontology-diagram.png');
          else alert('PNG conversion failed (empty blob).');
        }, 'image/png');
      } catch (e) {
        alert('Could not export PNG: ' + e.message + '\\nTry the SVG download instead.');
      }
    };
    img.onerror = () => alert('Could not render PNG. Try downloading the SVG instead.');
    img.src = dataUrl;
  };
}
</script>""")
    parts.append("</body></html>")
    return "\n".join(parts)
