"""HTML templates for askwol: home page and publishing guide.

Single source of truth for the static UI markup. The `GUIDE_SECTIONS` list
drives both the table of contents and the body of the publishing guide so the
two cannot drift apart. The `report_html` module imports `GUIDE_SECTIONS`
and enforces (via assert) that its `CHECKS` registry uses the same anchors
in the same order.
"""

from __future__ import annotations


UPLOAD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask Wol: OWL ontology reviewer</title>
<meta name="description" content="askwol is a free, open-source OWL ontology reviewer. Get an instant class diagram plus namespace, term, metadata, documentation, IRI, language-tag, and reasoner checks for your RDF or OWL ontology.">
<meta name="keywords" content="OWL, ontology, RDF, Semantic Web, ontology validator, ontology review, SHACL, linked data, knowledge graph, Turtle, JSON-LD">
<meta name="author" content="TDCC-NES Ontology Engineers">
<meta name="robots" content="index, follow">
<meta name="theme-color" content="#4a7c59">
<meta property="og:type" content="website">
<meta property="og:site_name" content="askwol">
<meta property="og:title" content="Ask Wol: OWL ontology reviewer">
<meta property="og:description" content="Instant OWL ontology review: class diagram, namespace and term checks, metadata and documentation review, and a clean-up report.">
<meta property="og:image" content="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Winnie-the-Pooh_67.png/250px-Winnie-the-Pooh_67.png">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Ask Wol: OWL ontology reviewer">
<meta name="twitter:description" content="Instant OWL ontology review: class diagram, namespace and term checks, metadata and documentation review, and a clean-up report.">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "askwol",
  "description": "A free, open-source OWL ontology reviewer: class diagram, namespace and term checks, metadata and documentation review, and a clean-up report.",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Any",
  "url": "https://github.com/TDCC-NES/askwol",
  "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
  "author": {"@type": "Organization", "name": "TDCC-NES Ontology Engineers", "url": "https://tdcc.nl/nes-ontology-engineers/"},
  "license": "https://github.com/TDCC-NES/askwol/blob/main/LICENSE"
}
</script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x1F989;</text></svg>">
<style>
  :root { --accent: #4a7c59; --accent-dark: #3d6a4a; --border: #e5e7eb; --muted: #6b7280; --bg-soft: #f9fafb; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; max-width: 720px; margin: 50px auto; padding: 0 20px; color: #1f2937; line-height: 1.6; }
  h1 { margin: 0.4em 0 0.1em; font-weight: 700; font-size: 2.4em; letter-spacing: -0.02em; display: flex; align-items: center; gap: 0.35em; }
  h1 .owl { font-size: 1.4em; line-height: 1; }
  h2 { color: #374151; margin-top: 1.8em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; font-weight: 600; }
  .cluster-h { color: var(--accent-dark); font-size: 1.15em; font-weight: 700; margin: 1.5em 0 0.3em; }
  .checks-list { margin: 0.2em 0 0.8em; padding-left: 1.4em; }
  .checks-list li { margin: 0.4em 0; }
  .checks-list .num { color: var(--accent-dark); font-weight: 700; }
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
    <a href="./">Home</a> &middot;
    <a href="guide">Publishing guide</a> &middot;
    <a href="docs">API docs</a>
  </p>
  <h1><span class="owl" aria-hidden="true">&#x1F989;</span> Ask Wol</h1>
  <p>Your friendly owl for instant <a href="https://www.w3.org/OWL/">OWL</a>
  ontology reviews: a visual class diagram, namespace and term checks,
  metadata and documentation review, and a clean-up report.</p>

  <form class="card" action="validate" method="post" enctype="multipart/form-data">
    <div class="tabs" role="tablist">
      <button type="button" class="tab active" data-tab="url" role="tab">From URL</button>
      <button type="button" class="tab" data-tab="file" role="tab">Upload file</button>
    </div>

    <div id="panel-url" class="tab-panel active">
      <label for="url-input">Ontology URL</label>
      <input type="url" id="url-input" name="url" placeholder="https://example.org/ontology.ttl" required>
      <div class="examples-label">Or try a well-known ontology</div>
      <div class="chips">
        <button type="button" class="chip" data-url="http://xmlns.com/foaf/spec/index.rdf">FOAF</button>
        <button type="button" class="chip" data-url="https://www.w3.org/ns/prov.ttl">PROV-O</button>
        <button type="button" class="chip" data-url="https://www.w3.org/2006/time">Time</button>
        <button type="button" class="chip" data-url="https://opengeospatial.github.io/ogc-geosparql/geosparql11/geo.ttl">GeoSPARQL</button>
        <button type="button" class="chip" data-url="https://www.w3.org/TR/owl-guide/wine.rdf">Wine</button>
        <button type="button" class="chip" data-url="https://lod-4tu.tudelft.nl/ontologies/sample.ttl">sample ontology</button>
      </div>
    </div>

    <div id="panel-file" class="tab-panel">
      <label for="file-input">Ontology file</label>
      <input type="file" id="file-input" name="file" accept=".ttl,.rdf,.owl,.jsonld,.nt,.n3" required disabled>
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
  <p>An interactive <strong>class diagram</strong> of your ontology, plus one
  HTML report (or JSON via the API) with a section per check. The checks are
  grouped into five areas, and each links to the matching entry in the
  <a href="guide">publishing guide</a>:</p>

  <h3 class="cluster-h">1. Ontology basics</h3>
  <ul class="checks-list">
    <li><span class="num">1.1</span> <strong>Ontology metadata</strong>: a
    SHACL check on the ontology header. Title, description, creator, license
    IRI, and version are required; created/modified dates and publisher are
    recommended.</li>
    <li><span class="num">1.2</span> <strong>Imports</strong>: external
    vocabularies actually used in your ontology must be declared with
    <code>owl:imports</code>. Core W3C vocabularies (RDF, RDFS, OWL, XSD) are
    excluded.</li>
    <li><span class="num">1.3</span> <strong>IRI strategy</strong>: your
    ontology&rsquo;s own defined terms should consistently use either hash
    (<code>#Term</code>) or slash (<code>/Term</code>), not both.</li>
    <li><span class="num">1.4</span> <strong>IRI scheme</strong>: each host
    should be referenced under a single URI scheme.
    <code>http://example.org/X</code> and <code>https://example.org/X</code>
    are different IRIs.</li>
  </ul>

  <h3 class="cluster-h">2. Namespaces &amp; reuse</h3>
  <ul class="checks-list">
    <li><span class="num">2.1</span> <strong>Namespaces</strong>: fetches each
    declared namespace URI, checks HTTP status, and tries to parse it as RDF
    (Turtle, RDF/XML, JSON-LD, N-Triples). Falls back to scanning HTML pages
    for RDF links.</li>
    <li><span class="num">2.2</span> <strong>Unused prefixes</strong>: flags
    <code>@prefix</code> declarations that are never used in any triple.</li>
    <li><span class="num">2.3</span> <strong>External term definitions</strong>:
    verifies that terms your ontology reuses from an external vocabulary are
    actually defined there. Catches typos like <code>owl:MadeUpClass</code> and
    made-up reuse of established prefixes.</li>
  </ul>

  <h3 class="cluster-h">3. Term structure</h3>
  <ul class="checks-list">
    <li><span class="num">3.1</span> <strong>Internal term definitions</strong>:
    flags terms in your own namespace that are referenced but never defined,
    usually a typo or a forgotten declaration.</li>
    <li><span class="num">3.2</span> <strong>Term inventory &amp; naming</strong>:
    categorizes every term you define (class, object or datatype property,
    datatype, individual) and checks capitalization: classes start uppercase,
    properties start lowercase.</li>
    <li><span class="num">3.3</span> <strong>Domains &amp; ranges</strong>:
    object and datatype properties should declare a domain and a range. Object
    properties range over classes; datatype properties over datatypes.</li>
    <li><span class="num">3.4</span> <strong>Datatypes</strong>: datatypes used
    as ranges or literal types should be recognized (XSD built-ins,
    <code>rdfs:Literal</code>, <code>rdf:langString</code>, or a datatype you
    declare with <code>rdfs:Datatype</code>).</li>
    <li><span class="num">3.5</span> <strong>Non-ontology terms</strong>: an OWL
    ontology defines schema. Individuals, <code>skos:Concept</code> instances,
    and other instance data belong in a separate data resource or concept
    scheme.</li>
  </ul>

  <h3 class="cluster-h">4. Term documentation</h3>
  <ul class="checks-list">
    <li><span class="num">4.1</span> <strong>Labels</strong>: a SHACL check that
    every internally defined class and property carries an
    <code>rdfs:label</code>. Reused external terms are ignored.</li>
    <li><span class="num">4.2</span> <strong>Comments</strong>: a SHACL check
    that every internally defined class and property carries an
    <code>rdfs:comment</code>. Reused external terms are ignored.</li>
    <li><span class="num">4.3</span> <strong>Language tag consistency</strong>:
    language-tagged properties like <code>rdfs:label</code>,
    <code>rdfs:comment</code>, <code>skos:prefLabel</code>, and
    <code>skos:definition</code> should use the same set of languages across
    subjects. Catches missing translations and bare strings.</li>
  </ul>

  <h3 class="cluster-h">5. Logic</h3>
  <ul class="checks-list">
    <li><span class="num">5.1</span> <strong>Reasoner checks</strong>:
    lightweight OWL RL reasoning on the current ontology (imports are not
    followed), reported as three facets: <em>ontology consistency</em>,
    <em>inconsistent individuals</em>, and <em>unsatisfiable classes</em>.</li>
  </ul>

  <p><strong>What you don&rsquo;t get:</strong> askwol checks syntax and
  structure, but not content or meaning, which is what ontologies are all
  about.</p>

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
      from Milne&rsquo;s <em>Winnie-the-Pooh</em> is famous for. He spells
      his own name <strong>WOL</strong>, as Dave de Roure
      <a href="https://lists.w3.org/Archives/Public/www-webont-wg/2002Sep/0301.html">first
      pointed out</a> to the working group.
    </p>
    <h2 style="border:none; padding:0; margin-top:1.2em;">About</h2>
    <p>
      <i>askwol</i> is developed and maintained by the
      <a href="https://tdcc.nl/nes-ontology-engineers/">TDCC-NES Ontology Engineers</a>
      (<strong>Kathrin F&uuml;llenbach</strong> and <strong>Dani Metilli</strong>), funded by
      <a href="https://www.openscience.nl/en/">Open Science NL</a>. We help with ontology
      selection and reuse, co-development, knowledge graph design, and training.
    </p>
    <p>
      <i>askwol</i> is free and open source under the
      <a href="https://github.com/TDCC-NES/askwol/blob/main/LICENSE">MIT licence</a>.
      Found a bug or have an idea? Open an issue on
      <a href="https://github.com/TDCC-NES/askwol">GitHub</a> or reach us at
      <a href="mailto:nes@tdcc.nl">nes@tdcc.nl</a>.
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

# Single source of truth for the publishing guide. The order of this list IS
# the order of both the table of contents and the page body, so the two
# cannot drift apart. Sections in group="check" are linked from the
# validation report; their order and anchors must match CHECKS below.
# Sections in group="practice" are additional best practices with no
# automated check.
#
# Check-group sections are grouped into clusters via their "category" key.
# CHECK_CATEGORIES gives the cluster order and display labels, and is shared
# with report_html so the guide, the overview, and the results agree.
CHECK_CATEGORIES: list[dict[str, str]] = [
    {"key": "basics", "label": "Ontology basics"},
    {"key": "reuse", "label": "Namespaces &amp; reuse"},
    {"key": "structure", "label": "Term structure"},
    {"key": "docs", "label": "Term documentation"},
    {"key": "logic", "label": "Logic"},
]

GUIDE_SECTIONS: list[dict[str, str]] = [
    {
        "group": "check",
        "category": "basics",
        "anchor": "metadata",
        "title": "Give the ontology itself good metadata",
        "toc_label": "Ontology metadata",
        "body": """\
  <p>Your ontology is itself a published research object. It should say
  what it is, who made it, which version it is, and under which license
  it can be reused.</p>
  <p>askwol evaluates <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/ontology_metadata.ttl" target="_blank" rel="noopener">SHACL shapes for the ontology header</a> and checks these properties:</p>
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
""",
    },
    {
        "group": "check",
        "category": "basics",
        "anchor": "imports",
        "title": "Declare imports for vocabularies you use",
        "toc_label": "Imports",
        "body": """\
  <p>If your ontology uses terms from another vocabulary, declare it with
  <code>owl:imports</code> in the ontology header:</p>
  <pre>&lt;https://example.org/my-ontology&gt; a owl:Ontology ;
    owl:imports &lt;http://xmlns.com/foaf/0.1/&gt; ,
                &lt;http://www.w3.org/2004/02/skos/core&gt; .</pre>
  <p>This tells reasoners and tools where your external terms are defined
  and lets them load the imported ontology when needed.</p>
  <p>askwol flags any external namespace whose terms appear as subjects in
  your ontology but which is not listed in <code>owl:imports</code>. Core
  vocabularies (<code>rdf</code>, <code>rdfs</code>, <code>owl</code>,
  <code>xsd</code>) and your ontology&rsquo;s own namespace are excluded.</p>
  <div class="tip">If you only use a vocabulary for annotation properties
  (like <code>dcterms:title</code>), importing it is still good practice
  because it documents the dependency.</div>
""",
    },
    {
        "group": "check",
        "category": "basics",
        "anchor": "iri-strategy",
        "title": "Pick one IRI strategy (hash or slash) and stick to it",
        "toc_label": "IRI strategy",
        "body": """\
  <p><strong>What askwol checks:</strong> every term defined inside your
  ontology&rsquo;s own namespace is classified as either <em>hash style</em>
  (<code>http://example.org/ont#Person</code>) or <em>slash style</em>
  (<code>http://example.org/ont/Person</code>). The check
  <strong>passes</strong> when all defined terms use the same pattern and
  <strong>warns</strong> when you mix both within one ontology. The
  Imports section already verifies that you have declared an
  <code>owl:Ontology</code>; this check uses that IRI as the root.</p>
  <div class="tip">Mixing hash and slash in the same vocabulary is almost
  always accidental. It breaks naive prefix-based namespace splitting and
  confuses consumers about whether <code>Person</code> is the same term
  as <code>#Person</code>.</div>

  <h3>Hash vs. slash, in plain terms</h3>
  <p>Both patterns are valid (the W3C
  <a href="https://www.w3.org/TR/cooluris/">&ldquo;Cool URIs for the
  Semantic Web&rdquo;</a> note describes both); they differ in how the
  identifier behaves over HTTP and how the vocabulary scales.</p>

  <p><strong>Hash URIs</strong> &middot; <code>http://example.org/ont<strong>#</strong>Person</code></p>
  <ul>
    <li>The fragment (<code>#Person</code>) is <strong>stripped before the HTTP
    request</strong> is sent. The server never sees it; it returns the
    entire document at <code>http://example.org/ont</code>.</li>
    <li>All terms come back in a single request. Efficient, zero server
    configuration; just upload one RDF file.</li>
    <li>Downside: a client asking about one term gets <em>every</em>
    term in the vocabulary. Fine for 50&nbsp;terms, painful for 50&thinsp;000.</li>
  </ul>

  <p><strong>Slash URIs</strong> &middot; <code>http://example.org/ont<strong>/</strong>Person</code></p>
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

  <h3>Recommendation</h3>
  <p>If in doubt, <strong>go with slash</strong>. It scales. Use hash
  only when you know the vocabulary is small and will stay that way.
  The Cool URIs note concludes:</p>
  <blockquote style="border-left:3px solid #ccc;padding-left:1em;color:#555;margin:1em 0;">
  &ldquo;Hash URIs should be preferred for rather <strong>small and stable</strong>
  sets of resources that evolve together. The ideal case are RDF Schema
  vocabularies and OWL ontologies. [&hellip;] 303&nbsp;URIs may also be
  used for [large] data sets, making neater-looking URIs.&rdquo;
  </blockquote>
  <p>Either way, <strong>pick one per ontology</strong> and don&rsquo;t mix them.</p>

  <h3>Persistent identifiers</h3>
  <p>Use a domain you control, or a persistent ID service like
  <a href="https://w3id.org/">w3id.org</a> or
  <a href="https://purl.org/">purl.org</a>,
  so your IRIs survive domain changes.</p>
""",
    },
    {
        "group": "check",
        "category": "basics",
        "anchor": "https-http",
        "title": "Use http or https, but be consistent per host",
        "toc_label": "IRI scheme (http vs https)",
        "body": """\
  <p><strong>What askwol checks:</strong> every IRI used in the ontology
  (in subject, predicate, or object position, plus every bound namespace)
  is grouped by host. The check <strong>passes</strong> when each host
  appears under exactly one URI scheme and <strong>warns</strong> when the
  same host is referenced under both <code>http://</code> and
  <code>https://</code>. The report lists the conflicting hosts with
  examples of each scheme so you can pick one canonical form and migrate
  the others.</p>

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
""",
    },
    {
        "group": "check",
        "category": "reuse",
        "anchor": "resolvable",
        "title": "Make namespaces resolvable",
        "toc_label": "Namespaces",
        "body": """\
  <p>A <strong>namespace</strong> is the URI that a prefix expands to. In
  <code>@prefix foaf: &lt;http://xmlns.com/foaf/0.1/&gt;</code> the prefix is
  <code>foaf</code> and the namespace is
  <code>http://xmlns.com/foaf/0.1/</code>. This check looks at those namespace
  URIs; the short prefix aliases themselves are covered by
  <a href="#prefixes">Unused prefixes</a> below.</p>
  <p>Every namespace URI should return something useful when fetched with HTTP.
  Ideally it returns RDF (content-negotiated), so tools can discover term
  definitions automatically.</p>
  <div class="tip"><strong>Good:</strong>
  <code>http://xmlns.com/foaf/0.1/</code> returns RDF when asked with
  <code>Accept: application/rdf+xml</code>.</div>
  <div class="warn"><strong>Bad:</strong> A namespace that returns
  404 or a generic HTML page with no RDF link.</div>
  <p>If you host your own ontology, configure your server to support
  <a href="https://www.w3.org/TR/swbp-vocab-pub/">content negotiation</a>,
  serving RDF to machines and HTML to browsers.</p>
""",
    },
    {
        "group": "check",
        "category": "reuse",
        "anchor": "prefixes",
        "title": "Keep your prefixes clean",
        "toc_label": "Unused prefixes",
        "body": """\
  <p>Each <code>@prefix</code> line binds a short prefix to a
  <a href="#resolvable">namespace</a> URI. This check is about the prefix
  side: only declare prefixes you actually use. Leftover
  <code>@prefix</code> declarations clutter the file and confuse
  readers; they suggest a dependency that doesn&rsquo;t exist.</p>
  <pre>@prefix dct: &lt;http://purl.org/dc/terms/&gt; .   # used below
@prefix geo: &lt;http://www.opengis.net/ont/geosparql#&gt; .  # unused, remove it</pre>
  <div class="tip">askwol flags every prefix that is declared
  but never appears in a triple, so you can clean them up.</div>
""",
    },
    {
        "group": "check",
        "category": "reuse",
        "anchor": "external-terms",
        "title": "External term definitions",
        "toc_label": "External term definitions",
        "body": """\
  <p>Don&rsquo;t reinvent the wheel. Before defining a new term, check if
  an established vocabulary already covers it:</p>
  <ul>
    <li><a href="https://schema.org/">schema.org</a>: broad web vocabulary</li>
    <li><a href="http://xmlns.com/foaf/0.1/">FOAF</a>: people and social networks</li>
    <li><a href="http://purl.org/dc/terms/">Dublin Core</a>: metadata (title, creator, date)</li>
    <li><a href="https://www.w3.org/2004/02/skos/core">SKOS</a>: concept schemes and thesauri</li>
    <li><a href="https://www.w3.org/ns/prov#">PROV-O</a>: provenance</li>
  </ul>
  <div class="warn">When reusing a term, use the <em>exact</em>
  IRI from the source vocabulary. A typo like <code>foaf:nme</code> instead
  of <code>foaf:name</code> silently breaks interoperability.</div>
  <div class="tip">askwol looks up every term you reuse from an external
  vocabulary and reports the ones that are not actually defined there. This
  catches typos like <code>foaf:nme</code> and made-up reuse of established
  prefixes. Terms from your own namespace are checked separately (see
  <a href="#internal-terms">Internal term definitions</a>).</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "internal-terms",
        "title": "Internal term definitions",
        "toc_label": "Internal term definitions",
        "body": """\
  <p>Every term you use from your <em>own</em> namespace should also be
  defined there. Don&rsquo;t just <em>use</em> a term; <em>define</em> it.</p>
  <pre>&lt;#Person&gt; a owl:Class ;
    rdfs:label "Person"@en ;
    rdfs:comment "A human being."@en .</pre>
  <div class="warn">If you reference <code>ex:Persom</code> but
  never define it, that&rsquo;s probably a typo. askwol catches these.</div>
  <div class="tip">askwol treats a term as <strong>defined</strong> when it
  appears as the <strong>subject</strong> of at least one triple, and as
  <strong>referenced</strong> when it appears as a predicate or object. A term
  in your own namespace that is referenced but never defined is flagged.
  External vocabulary terms are covered by the
  <a href="#external-terms">External term definitions</a> check instead.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "term-inventory",
        "title": "Categorize your terms and name them consistently",
        "toc_label": "Term inventory &amp; naming",
        "body": """\
  <p>Every term you define falls into a category: a <strong>class</strong>, an
  <strong>object property</strong>, a <strong>datatype property</strong>, an
  <strong>annotation property</strong>, a <strong>datatype</strong>, or a
  <strong>named individual</strong>. askwol lists each internal term with the
  category it detected, so you can spot a term that was never typed
  (<code>rdf:type</code> missing) or typed as the wrong kind of thing.</p>
  <pre>&lt;#Person&gt;   a owl:Class .
&lt;#hasParent&gt; a owl:ObjectProperty .
&lt;#birthDate&gt; a owl:DatatypeProperty .</pre>
  <h3>Naming conventions</h3>
  <ul>
    <li><strong>Classes start with an uppercase letter</strong> and are usually
    nouns: <code>Person</code>, <code>Dataset</code>, <code>Organization</code>.</li>
    <li><strong>Properties start with a lowercase letter</strong>:
    <code>hasParent</code>, <code>birthDate</code>, <code>title</code>.</li>
  </ul>
  <div class="tip">Object properties read best as verb phrases. A
  <code>has</code> or <code>is</code> prefix, or an <code>of</code>/<code>by</code>
  form, gives a single unambiguous reading: <code>hasWife</code>,
  <code>wifeOf</code>, <code>lovedBy</code>. This is a readability convention,
  not something askwol enforces; askwol only checks the leading upper/lower case.</div>
  <div class="warn">Mixing conventions (a lowercase class like
  <code>person</code>, or an uppercase property like <code>HasName</code>)
  makes an ontology harder to read and to reuse.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "domains-ranges",
        "title": "Give properties a domain and a range",
        "toc_label": "Domains &amp; ranges",
        "body": """\
  <p>An <code>rdfs:domain</code> says what kind of subject a property applies
  to; an <code>rdfs:range</code> says what kind of value it takes. Declaring
  both makes a property self-documenting and lets tools reason about it.</p>
  <pre>&lt;#hasParent&gt; a owl:ObjectProperty ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range  &lt;#Person&gt; .        # a class

&lt;#birthDate&gt; a owl:DatatypeProperty ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range  xsd:date .        # a datatype</pre>
  <ul>
    <li>An <strong>object property</strong> should range over a
    <strong>class</strong>. A range that is a datatype means it should probably
    be a datatype property.</li>
    <li>A <strong>datatype property</strong> should range over a
    <strong>datatype</strong>. A range that is a class means it should probably
    be an object property.</li>
    <li>A <strong>domain</strong> should be a class for either kind.</li>
  </ul>
  <div class="warn">In OWL, a domain or range is not a constraint that rejects
  bad data; it <em>licenses inference</em>. Stating
  <code>rdfs:domain :Person</code> on <code>:birthDate</code> tells a reasoner
  that anything with a <code>:birthDate</code> is a <code>:Person</code>. Pick
  domains and ranges that are actually true of every use.</div>
  <div class="tip">askwol reads <code>rdfs:domain</code> and
  <code>rdfs:range</code> directly on each property; it does not follow domains
  or ranges inherited from a super-property.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "datatypes",
        "title": "Use recognized datatypes",
        "toc_label": "Datatypes",
        "body": """\
  <p>Datatype property ranges and typed literals should use a datatype that
  tools understand: an <a href="https://www.w3.org/TR/xmlschema11-2/">XSD</a>
  built-in (<code>xsd:string</code>, <code>xsd:integer</code>,
  <code>xsd:date</code>, <code>xsd:boolean</code>, &hellip;),
  <code>rdfs:Literal</code>, <code>rdf:langString</code>, or a custom datatype
  you declare with <code>rdfs:Datatype</code>.</p>
  <pre>&lt;#age&gt; rdfs:range xsd:nonNegativeInteger .
&lt;#born&gt; rdfs:range xsd:date .
"42"^^xsd:integer</pre>
  <div class="warn">A misspelled datatype (<code>xsd:stirng</code>,
  <code>xsd:dateTiem</code>) is silently treated as a brand-new, unknown
  datatype. Filters and validators that expect the real datatype then skip your
  values. askwol lists every datatype it sees and flags the ones it does not
  recognize.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "non-ontology-terms",
        "title": "Keep the ontology to schema, not instance data",
        "toc_label": "Non-ontology terms",
        "body": """\
  <p>An OWL ontology is the <em>schema</em>: it defines classes, properties,
  and datatypes (the terminology). Individual <strong>instances</strong> and
  subject-matter <strong>concepts</strong> (the members of a controlled
  vocabulary or thesaurus) are instance data; they belong in a separate data
  resource or a <a href="https://www.w3.org/TR/skos-primer/">SKOS</a> concept
  scheme, not inside the ontology itself.</p>
  <pre>&lt;#Dataset&gt; a owl:Class .            # schema, belongs here
&lt;#biology&gt; a skos:Concept .         # concept, belongs in a SKOS scheme
&lt;#dataset-001&gt; a &lt;#Dataset&gt; .       # instance, belongs in a data file</pre>
  <div class="tip">askwol works from a <strong>whitelist</strong>: a term in your
  own namespace is fine when it is typed as a class, a property, or a datatype
  (or is the ontology header). Anything else that carries a type but no schema
  type (a <code>skos:Concept</code>, a named individual, stray instance data) is
  flagged so you can move it out. External terms are ignored. Keeping the
  schema and the data apart lets each evolve, and be reused, independently.</div>
""",
    },
    {
        "group": "check",
        "category": "docs",
        "anchor": "labels",
        "title": "Labels",
        "toc_label": "Labels",
        "body": """\
  <p>Every class and property you define should carry a human-readable
  <code>rdfs:label</code>: a short name a person can read.</p>
  <pre>&lt;#hasMother&gt; a owl:ObjectProperty ;
    rdfs:label "has mother"@en ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range &lt;#Person&gt; .</pre>
  <div class="tip">Use language tags (<code>@en</code>, <code>@de</code>)
  to support multilingual ontologies. Consider
  <code>skos:prefLabel</code> and <code>skos:altLabel</code> for richer
  labeling.</div>
  <div class="tip">askwol uses <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/definition_documentation.ttl" target="_blank" rel="noopener">SHACL shapes</a> to check that each
  <em>internally defined</em> class and property has an
  <code>rdfs:label</code>. Reused external vocabulary terms are ignored.</div>
""",
    },
    {
        "group": "check",
        "category": "docs",
        "anchor": "comments",
        "title": "Comments",
        "toc_label": "Comments",
        "body": """\
  <p>Every class and property you define should also carry an
  <code>rdfs:comment</code>: a brief description of what it means.</p>
  <pre>&lt;#hasMother&gt; a owl:ObjectProperty ;
    rdfs:label "has mother"@en ;
    rdfs:comment "Relates a person to their biological mother."@en ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range &lt;#Person&gt; .</pre>
  <div class="tip">A good comment states the intended meaning and, where
  helpful, how the term should (and should not) be used.</div>
  <div class="tip">askwol uses <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/definition_documentation.ttl" target="_blank" rel="noopener">SHACL shapes</a> to check that each
  <em>internally defined</em> class and property has an
  <code>rdfs:comment</code>. Reused external vocabulary terms are ignored.</div>
""",
    },
    {
        "group": "check",
        "category": "docs",
        "anchor": "lang-tags",
        "title": "Use language tags consistently",
        "toc_label": "Language tag consistency",
        "body": """\
  <p>If your ontology includes human-readable labels and descriptions,
  use <a href="https://www.rfc-editor.org/rfc/bcp47">BCP 47 language tags</a>
  (<code>@en</code>, <code>@nl</code>, <code>@de</code>, &hellip;) on every
  literal that carries natural-language text.</p>
  <pre>:Person a owl:Class ;
    rdfs:label "person"@en ,
               "persoon"@nl ;
    skos:definition "A human being."@en ,
                    "Een menselijk wezen."@nl .</pre>
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
  literals; your data becomes invisible.</div>
  <div class="tip">askwol checks
  <code>rdfs:label</code>, <code>rdfs:comment</code>,
  <code>skos:prefLabel</code>, <code>skos:definition</code>, and other
  standard annotation properties for tag consistency.</div>
""",
    },
    {
        "group": "check",
        "category": "logic",
        "anchor": "reasoner",
        "title": "Check logical consistency",
        "toc_label": "Reasoner checks",
        "body": """\
  <p>OWL is a logical language. A reasoner can derive consequences from your
  axioms and detect contradictions you didn&rsquo;t intend. askwol reports
  these as three separate facets in the
  <a href="/#reasoner">Reasoner checks</a> section of the report:</p>
  <ul>
    <li><strong>Ontology consistency</strong>: the ontology as a whole
    has a possible model. This is the overall pass/fail verdict; it fails
    when at least one individual is inconsistent.</li>
    <li><strong>Inconsistent individuals</strong>: specific named
    individuals that violate a class restriction (e.g. a <code>Person</code>
    with two values for a functional property, or membership in two
    <code>owl:disjointWith</code> classes). Each offending individual is
    listed by IRI so you can locate the contradiction.</li>
    <li><strong>Unsatisfiable classes</strong>: no class definition is
    logically empty. A class is unsatisfiable when its definition forces it
    to be equivalent to <code>owl:Nothing</code> (e.g. via disjoint
    superclasses). The class is syntactically valid but can never have
    instances.</li>
  </ul>
  <div class="tip">askwol runs a lightweight OWL RL reasoner on the
  <strong>current ontology only</strong>; it does <em>not</em> follow
  <code>owl:imports</code>. This catches the obvious self-contained
  contradictions without the cost of loading every imported vocabulary. For
  deeper checks (against imports, with HermiT or Pellet), use a desktop
  tool like Prot&eacute;g&eacute;.</div>
""",
    },
    {
        "group": "practice",
        "anchor": "validate",
        "title": "Validate early and often",
        "toc_label": "Validate early and often",
        "body": """\
  <p>Run <a href="./">askwol</a> on your ontology during development, not just
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
""",
    },
    {
        "group": "practice",
        "anchor": "server-config",
        "title": "Serve it right: content negotiation",
        "toc_label": "Server configuration",
        "body": """\
  <p>Once published, your ontology&rsquo;s IRI should <em>resolve</em>: a client
  that dereferences it must get the RDF back. Two server-side settings make
  that work.</p>
  <ul>
    <li><strong>Correct content type.</strong> Serve Turtle as
    <code>text/turtle</code>, RDF/XML as <code>application/rdf+xml</code>,
    JSON-LD as <code>application/ld+json</code>. A file served as
    <code>text/plain</code> or <code>application/octet-stream</code> will not be
    recognised as RDF.</li>
    <li><strong>Content negotiation.</strong> Honour the client&rsquo;s
    <code>Accept</code> header: return RDF to tools that ask for it, and an
    HTML documentation page to browsers. A common pattern is one term IRI
    (<code>https://example.org/onto#Term</code>) that redirects
    (<code>303 See Other</code>) to either the <code>.ttl</code> or an HTML view
    depending on <code>Accept</code>.</li>
  </ul>
  <div class="tip">Keep the <strong>namespace IRI</strong> and the
  <strong>document URL</strong> consistent: if terms live under
  <code>https://example.org/onto#</code>, dereferencing
  <code>https://example.org/onto</code> should return the ontology (directly or
  via redirect).</div>
  <div class="warn">Static file servers often default to <code>text/plain</code>
  for <code>.ttl</code>. Set the MIME type explicitly in your web server or
  reverse proxy, otherwise namespace resolution (including askwol&rsquo;s) fails.</div>
""",
    },
]


# Hierarchical section numbers. Check sections are numbered "cluster.position"
# (1.1, 1.2, 2.1, ...) using their category; practice sections carry no number.
# The TOC and the body headings both use these, so the two always match.
def _compute_guide_numbers() -> dict[str, str]:
    cat_index = {c["key"]: i + 1 for i, c in enumerate(CHECK_CATEGORIES)}
    counters: dict[str, int] = {}
    labels: dict[str, str] = {}
    for s in GUIDE_SECTIONS:
        if s["group"] == "check":
            cat = s["category"]
            counters[cat] = counters.get(cat, 0) + 1
            labels[s["anchor"]] = f"{cat_index[cat]}.{counters[cat]}"
        else:
            labels[s["anchor"]] = ""
    return labels


_GUIDE_NUMBERS = _compute_guide_numbers()
# Cluster number (1..5) per category key, shown on the cluster band.
_CLUSTER_NUMBERS = {c["key"]: i + 1 for i, c in enumerate(CHECK_CATEGORIES)}


def _render_guide_toc() -> str:
    """Render the publishing-guide TOC from GUIDE_SECTIONS.

    The TOC has two groups: automated checks (linked from the report) and
    additional best practices. Within the checks group the entries are further
    split into the clusters defined by CHECK_CATEGORIES, each under its own
    sub-heading. Check entries are numbered "cluster.position" and use the exact
    same text as the matching body heading, so the TOC cannot drift from the body.
    """
    def _entry(s: dict) -> str:
        n = _GUIDE_NUMBERS[s["anchor"]]
        prefix = f"{n} " if n else ""
        return f'      <li><a href="#{s["anchor"]}">{prefix}{s["toc_label"]}</a></li>'

    lines: list[str] = [
        '    <span class="group-label">Checks askwol runs (same order as the report)</span>'
    ]
    for cat in CHECK_CATEGORIES:
        cat_sections = [
            s for s in GUIDE_SECTIONS
            if s["group"] == "check" and s.get("category") == cat["key"]
        ]
        if not cat_sections:
            continue
        cnum = _CLUSTER_NUMBERS[cat["key"]]
        lines.append(f'    <span class="cluster-label">{cnum}. {cat["label"]}</span>')
        lines.append("    <ul>")
        lines.extend(_entry(s) for s in cat_sections)
        lines.append("    </ul>")

    practice = [s for s in GUIDE_SECTIONS if s["group"] == "practice"]
    lines.append('    <span class="group-label">Additional best practices (no automated check)</span>')
    lines.append("    <ul>")
    lines.extend(_entry(s) for s in practice)
    lines.append("    </ul>")

    return "\n".join(lines)


def _render_guide_body() -> str:
    """Render the publishing-guide H2 sections from GUIDE_SECTIONS, in order.

    The heading text matches the TOC entry exactly (number + label). A cluster
    band is emitted before the first check section of each category. Where a
    section has a distinct one-line takeaway, it is shown as a subtitle under
    the heading.
    """
    blocks = []
    seen_categories: set[str] = set()
    emitted_practice_band = False
    for s in GUIDE_SECTIONS:
        if s["group"] == "check":
            cat = s.get("category")
            if cat and cat not in seen_categories:
                seen_categories.add(cat)
                label = next((c["label"] for c in CHECK_CATEGORIES if c["key"] == cat), "")
                if label:
                    cnum = _CLUSTER_NUMBERS[cat]
                    blocks.append(f'  <h2 class="cluster-band" id="cluster-{cat}">{cnum}. {label}</h2>')
        elif s["group"] == "practice" and not emitted_practice_band:
            emitted_practice_band = True
            blocks.append('  <h2 class="cluster-band" id="cluster-practice">Additional best practices</h2>')
        n = _GUIDE_NUMBERS[s["anchor"]]
        num = f"{n} " if n else ""
        heading = f'  <h3 class="check-heading" id="{s["anchor"]}">{num}{s["toc_label"]}</h3>'
        if s["title"] and s["title"] != s["toc_label"]:
            heading += f'\n  <p class="section-lead">{s["title"]}</p>'
        blocks.append(f'{heading}\n{s["body"]}')
    return "\n".join(blocks)


GUIDE_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask Wol: OWL publishing guide</title>
<meta name="description" content="A practical guide to publishing OWL ontologies: IRI strategy, http vs https, resolvable namespaces, external and internal term definitions, labels and comments, language tags, reasoner checks, and prefix hygiene.">
<meta name="keywords" content="OWL, ontology, RDF, Semantic Web, publishing guide, IRI strategy, SHACL, namespaces, language tags, OWL reasoner, best practices">
<meta name="author" content="TDCC-NES Ontology Engineers">
<meta name="robots" content="index, follow">
<meta name="theme-color" content="#4a7c59">
<meta property="og:type" content="article">
<meta property="og:site_name" content="askwol">
<meta property="og:title" content="Ask Wol: OWL publishing guide">
<meta property="og:description" content="A practical guide to publishing OWL ontologies: IRI strategy, resolvable namespaces, vocabulary reuse, documentation, language tags, and reasoner checks.">
<meta property="og:image" content="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Winnie-the-Pooh_67.png/250px-Winnie-the-Pooh_67.png">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Ask Wol: OWL publishing guide">
<meta name="twitter:description" content="A practical guide to publishing OWL ontologies: IRI strategy, resolvable namespaces, vocabulary reuse, documentation, language tags, and reasoner checks.">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "TechArticle",
  "headline": "OWL ontology publishing guide",
  "description": "A practical guide to publishing OWL ontologies: IRI strategy, http vs https, resolvable namespaces, external and internal term definitions, labels and comments, language tags, reasoner checks, and prefix hygiene.",
  "author": {{"@type": "Organization", "name": "TDCC-NES Ontology Engineers", "url": "https://tdcc.nl/nes-ontology-engineers/"}},
  "publisher": {{"@type": "Organization", "name": "TDCC-NES Ontology Engineers"}},
  "isPartOf": {{"@type": "WebApplication", "name": "askwol"}}
}}
</script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x1F989;</text></svg>">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 50px auto; padding: 0 20px; color: #333; line-height: 1.7; }}
  h1 {{ margin: 0.4em 0 0.1em; font-weight: 700; font-size: 2.4em; letter-spacing: -0.02em; display: flex; align-items: center; gap: 0.35em; }}
  h1 .owl {{ font-size: 1.4em; line-height: 1; }}
  h2 {{ color: #555; margin-top: 2em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }}
  h3 {{ color: #666; margin-top: 1.5em; }}
  .cluster-band {{ color: #4a7c59; font-size: 1.7em; font-weight: 700; margin: 2.6em 0 0.5em; padding-bottom: 0.2em; border-bottom: 2px solid #cfe0d5; letter-spacing: -0.01em; }}
  .check-heading {{ color: #333; font-size: 1.25em; font-weight: 600; margin-top: 1.8em; border: none; padding: 0; }}
  .section-lead {{ color: #555; font-size: 1.05em; margin: 0.4em 0 1.1em; }}
  a {{ color: #4a7c59; }}
  code {{ background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }}
  pre {{ background: #f7f7f7; padding: 1em; border-radius: 6px; overflow-x: auto; font-size: 0.88em; line-height: 1.5; }}
  .tip {{ background: #f0f7f2; border-left: 4px solid #4a7c59; padding: 0.8em 1em; margin: 1em 0; border-radius: 0 6px 6px 0; }}
  .warn {{ background: #fef9f0; border-left: 4px solid #d4a017; padding: 0.8em 1em; margin: 1em 0; border-radius: 0 6px 6px 0; }}
  .footer {{ margin-top: 2.5em; font-size: 0.85em; color: #aaa; text-align: center; }}
  .topnav {{ margin-bottom: 1em; font-size: 0.95em; color: #555; background: #f7f7f7; border: 1px solid #eee; border-radius: 8px; padding: 0.6em 0.9em; }}
  .toc {{ background: #f9f9f9; padding: 1em 1.5em; border-radius: 8px; margin: 1.5em 0; }}
  .toc ul {{ list-style: none; margin: 0.3em 0 0 0; padding-left: 0; }}
  .toc li {{ margin: 0.2em 0; }}
  .toc .group-label {{ display: block; margin-top: 0.8em; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.04em; color: #6b7280; font-weight: 600; }}
  .toc .group-label:first-child {{ margin-top: 0; }}
  .toc .cluster-label {{ display: block; margin: 0.7em 0 0.15em 0.2em; font-size: 0.98em; color: #4a7c59; font-weight: 700; }}
  .cluster-band {{ margin: 2.2em 0 0; font-size: 0.82em; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #4a7c59; }}
</style>
</head>
<body>
  <p class="topnav">
    <strong>Navigation:</strong>
    <a href="./">Home</a> &middot;
    <a href="guide">Publishing guide</a> &middot;
    <a href="docs">API docs</a>
  </p>
  <h1><span class="owl" aria-hidden="true">&#x1F989;</span> How to Publish an Ontology</h1>
  <p>A practical checklist for building OWL ontologies that are
  interoperable, resolvable, and maintainable. These are the things
  <a href="./">askwol</a> checks, and why they matter.</p>

  <div class="tip">Want a worked example? The
  <a href="https://lod-4tu.tudelft.nl/ontologies/sample.ttl" target="_blank" rel="noopener">askwol sample ontology</a>
  applies every convention below and passes all checks. Load it from the
  <a href="./">home page</a> (the <strong>sample ontology</strong> button) to see a clean report.</div>

  <div class="toc">
    <strong>Contents</strong>
{_render_guide_toc()}
  </div>

{_render_guide_body()}

  <p class="footer">
    <strong>External links:</strong>
    <a href="https://tdcc.nl/nes-ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot;
    <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot;
    <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a>
  </p>
</body>
</html>"""
