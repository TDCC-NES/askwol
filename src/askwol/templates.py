"""HTML templates for askwol: home page and publishing guide.

The `GUIDE_SECTIONS` list drives both the table of contents and the guide
body. Its automated checks align with the independent `askwol.checks`
catalogue, which also supplies report numbering and API descriptions.
"""

from __future__ import annotations

import re
from datetime import date
from html import escape, unescape

from askwol.branding import PAGE_ICON_LINKS
from askwol.checks import (
    CHECK_CATEGORIES,
    CHECK_NUMBERS,
    CHECKS,
    CLUSTER_NUMBERS,
    GUIDE_CHECK_NUMBERS,
    render_checks_api_description,
)

__all__ = [
    "CHECKS",
    "CHECK_CATEGORIES",
    "CHECK_NUMBERS",
    "CLUSTER_NUMBERS",
    "GUIDE_HTML",
    "GUIDE_LAST_REVIEWED",
    "GUIDE_SECTIONS",
    "UPLOAD_HTML",
    "render_checks_api_description",
]


UPLOAD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Free Online OWL Ontology Checker | Ask Wol</title>
<link rel="canonical" href="https://lod-4tu.tudelft.nl/askwol/">
<meta name="description" content="Free online OWL ontology checks with Wollie. Upload a file or enter a URL for a class diagram and checks on namespaces, terms, metadata, and documentation.">
<meta name="keywords" content="OWL, ontology, RDF, Semantic Web, ontology validator, ontology review, SHACL, linked data, knowledge graph, Turtle, JSON-LD">
<meta name="author" content="TDCC-NES Ontology Engineers">
<meta name="robots" content="index, follow">
<meta name="theme-color" content="#4a7c59">
<meta property="og:type" content="website">
<meta property="og:site_name" content="askwol">
<meta property="og:title" content="Free Online OWL Ontology Checker | Ask Wol">
<meta property="og:description" content="Free online OWL ontology checks with Wollie. Upload a file or enter a URL for a class diagram and checks on namespaces, terms, metadata, and documentation.">
<meta property="og:image" content="https://lod-4tu.tudelft.nl/askwol/static/wollie-og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Wollie, a hand-drawn owl">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Free Online OWL Ontology Checker | Ask Wol">
<meta name="twitter:description" content="Free online OWL ontology checks with Wollie. Upload a file or enter a URL for a class diagram and checks on namespaces, terms, metadata, and documentation.">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "Ask Wol",
  "alternateName": "askwol",
  "description": "A free, open-source OWL ontology checker and reviewer: class diagram, namespace and term checks, metadata and documentation review, and a clean-up report.",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Any",
  "url": "https://lod-4tu.tudelft.nl/askwol/",
  "sameAs": [
    "https://github.com/TDCC-NES/askwol",
    "https://pypi.org/project/askwol/"
  ],
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "EUR"
  },
  "author": {
    "@type": "Organization",
    "name": "TDCC-NES Ontology Engineers",
    "url": "https://tdcc.nl/nes/ontology-engineers/"
  },
  "license": "https://github.com/TDCC-NES/askwol/blob/main/LICENSE"
}
</script>
<!--ICONS-->
<style>
  :root { --accent: #4a7c59; --accent-dark: #3d6a4a; --border: #e5e7eb; --muted: #6b7280; --bg-soft: #f9fafb; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; max-width: 720px; margin: 50px auto; padding: 0 20px; color: #1f2937; line-height: 1.6; }
  h1 { margin: 0.4em 0 0.1em; display: flex; align-items: center; gap: 0.9rem; font-size: 1rem; line-height: 1.2; }
  h1 .logo { height: 3.5rem; width: auto; flex: none; }
  h1 .brand { display: block; font-size: 2rem; font-weight: 600; letter-spacing: -0.01em; }
  h1 .tagline { display: block; margin-top: 0.2em; font-size: 1.05rem; font-weight: 400; color: var(--muted); }
  h1 .beta-badge { font-size: 0.4em; margin-left: 0.6em; }
  h2 { color: #374151; margin-top: 1.8em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; font-weight: 600; }
  .cluster-h { color: var(--accent-dark); font-size: 1.15em; font-weight: 700; margin: 1.5em 0 0.3em; }
  .checks-list { margin: 0.2em 0 0.8em; padding-left: 1.4em; }
  .checks-list li { margin: 0.4em 0; }
  .checks-list .num { color: var(--accent-dark); font-weight: 700; }
  code { background: #f3f4f6; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
  a { color: var(--accent); }
  .topnav { margin-bottom: 1.2em; font-size: 0.95em; color: #4b5563; background: var(--bg-soft); border: 1px solid var(--border); border-radius: 8px; padding: 0.6em 0.9em; }
  .beta-badge { display: inline-block; font-size: 0.5em; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: #8a6d1a; background: #fef3d7; border: 1px solid #e8d5a3; border-radius: 999px; padding: 0.2em 0.65em; vertical-align: middle; margin-left: 0.5em; }

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

  /* Busy state while a validation is running. The button uses aria-disabled
     (not disabled) so it keeps focus and full contrast; repeat submits are
     ignored in JS. */
  button.submit[aria-disabled="true"] { cursor: progress; }
  .is-busy .tabs, .is-busy .tab-panel { opacity: 0.55; }
  .working-status { margin: 0; font-size: 0.95em; color: #374151; }
  .is-busy .working { margin-top: 1.2em; padding: 0.9em 1em; background: var(--bg-soft); border: 1px solid var(--border); border-radius: 8px; }
  .is-busy .working-status { margin-bottom: 0.8em; }
  .progress { position: relative; height: 6px; overflow: hidden; background: #dfe8e2; border-radius: 999px; }
  .progress::before { content: ""; position: absolute; top: 0; bottom: 0; left: -35%; width: 35%; background: var(--accent); border-radius: 999px; animation: progress-slide 1.4s ease-in-out infinite; }
  @keyframes progress-slide { from { left: -35%; } to { left: 100%; } }
  @keyframes progress-pulse { 50% { opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) {
    .progress::before { left: 0; width: 100%; animation: progress-pulse 2s ease-in-out infinite; }
  }
  .working-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 0.6em; font-size: 0.85em; color: var(--muted); }
  .working-cancel { padding: 0; background: none; border: none; color: var(--accent); font: inherit; text-decoration: underline; cursor: pointer; }
  .working-cancel:hover { color: var(--accent-dark); }
  .working-hint { margin: 0.7em 0 0; font-size: 0.85em; color: var(--muted); }
  .working-hint:empty { display: none; }
  /* Step mode: one segment per pipeline step, the current one animated. */
  .progress--steps { display: flex; gap: 3px; height: 8px; overflow: visible; background: none; }
  .progress--steps::before { display: none; }
  .progress--steps > span { position: relative; flex: 1; overflow: hidden; background: #dfe8e2; border-radius: 999px; }
  .progress--steps > span.done { background: var(--accent); }
  .progress--steps > span.current::after { content: ""; position: absolute; top: 0; bottom: 0; left: -35%; width: 35%; background: var(--accent); border-radius: 999px; animation: progress-slide 1.4s ease-in-out infinite; }
  /* After the step rules above so it wins at equal specificity. */
  @media (prefers-reduced-motion: reduce) {
    .progress--steps > span.current::after { left: 0; width: 100%; animation: progress-pulse 2s ease-in-out infinite; }
  }

  .about { margin-top: 2.5em; padding-top: 1.5em; border-top: 1px solid var(--border); color: #4b5563; font-size: 0.95em; }
  .about .wollie { float: right; width: 140px; height: auto; margin: 0 0 1em 1.5em; }
  .footer { margin-top: 2em; font-size: 0.85em; color: #9ca3af; text-align: center; }
</style>
</head>
<body>
  <p class="topnav">
    <strong>Navigation:</strong>
    <a href="./">OWL ontology checker</a> &middot;
    <a href="guide">OWL ontology publishing guide</a> &middot;
    <a href="docs">API docs</a>
  </p>
<h1>
  <img class="logo" src="static/wollie-h1.png" alt="" width="43" height="56">
  <span><span class="brand">Ask Wol <span class="beta-badge">Beta</span></span> <span class="tagline">OWL Ontology Checker &amp; Reviewer</span></span>
</h1>
  <p>Your friendly owl (Wollie, to friends) for free online
  <a href="https://www.w3.org/OWL/">OWL</a> ontology checks
  during modelling and before publication.
  Enter a URL or upload a file to get a class diagram and a review report
  covering namespaces, terms, metadata, documentation, and selected logical issues.</p>
  <p>Preparing to publish? Follow the <a href="guide">OWL ontology publishing guide</a>.</p>

  <form class="card" id="validate-form" action="validate" method="post" enctype="multipart/form-data" data-progress-url="validate/progress">
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
        <button type="button" class="chip" data-url="https://raw.githubusercontent.com/opengeospatial/geosemantics-semantic-resources/refs/heads/main/resources/geosparql-swg/geosparql-1.1/ontologies/geo.ttl">GeoSPARQL</button>
        <button type="button" class="chip" data-url="https://www.w3.org/TR/owl-guide/wine.rdf">Wine</button>
        <button type="button" class="chip" data-url="https://cidoc-crm.org/rdfs/7.1.3/CIDOC_CRM_v7.1.3.rdfs">CIDOC CRM</button>
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

    <div class="working">
      <p class="working-status" id="working-status" role="status"></p>
      <div id="working-body" hidden>
        <div class="progress" id="working-bar" role="progressbar" aria-label="Checking your ontology"></div>
        <p class="working-hint" id="working-hint"></p>
        <div class="working-meta">
          <span id="working-elapsed" aria-hidden="true"></span>
          <button type="button" class="working-cancel" id="working-cancel">Cancel</button>
        </div>
      </div>
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
  <script>
    // Busy state for the validation form. A validation takes seconds to
    // minutes and the browser keeps showing this page until the report
    // arrives, so confirm the click was accepted, ignore repeat submits while
    // the request is in flight, and make sure the form is usable again if the
    // user cancels or comes back to this page.
    (function() {
      const form = document.getElementById('validate-form');
      const submitBtn = form.querySelector('button.submit');
      const statusEl = document.getElementById('working-status');
      const bodyEl = document.getElementById('working-body');
      const elapsedEl = document.getElementById('working-elapsed');
      const cancelBtn = document.getElementById('working-cancel');
      const barEl = document.getElementById('working-bar');
      const hintEl = document.getElementById('working-hint');
      const urlField = document.getElementById('url-input');
      const fileField = document.getElementById('file-input');
      const lockable = form.querySelectorAll('.tabs, .tab-panel');
      const idleLabel = submitBtn.textContent;

      // [seconds waited, expectation text]. Shown under the bar, or on the
      // live status line when there is no step information. The status line is
      // a live region, so text only changes at these thresholds and when the
      // step changes; the elapsed counter ticks silently.
      const MESSAGES = [
        [0, 'Wol is checking your ontology. Most checks finish within 30 seconds.'],
        [20, 'Still working. Large ontologies, or slow remote servers, can take a minute or more.'],
        [60, 'Still working. This one is taking longer than usual. Wol will stop and tell you if it takes too long.']
      ];

      let busy = false;
      let startedAt = 0;
      let timer = null;
      let pollTimer = null;
      let pollRun = 0;
      let source = '';
      let steps = null;  // latest step info from the server, or null if none yet

      function setText(el, text) { if (el.textContent !== text) el.textContent = text; }

      function expectation() {
        const secs = Math.floor((Date.now() - startedAt) / 1000);
        let text = MESSAGES[0][1];
        MESSAGES.forEach(function(m) { if (secs >= m[0]) text = m[1]; });
        return text;
      }

      function tick() {
        elapsedEl.textContent = Math.floor((Date.now() - startedAt) / 1000) + ' s';
        if (steps) setText(hintEl, expectation()); else setText(statusEl, expectation());
      }

      // The server reports which pipeline step the job is in; show one
      // segment per step (completed steps filled, current one animated)
      // rather than a percentage, since the steps take very uneven time.
      function renderSteps() {
        barEl.classList.add('progress--steps');
        if (barEl.children.length !== steps.total) {
          barEl.textContent = '';
          for (let i = 0; i < steps.total; i++) barEl.appendChild(document.createElement('span'));
        }
        const done = steps.finishing ? steps.total : steps.step - 1;
        Array.prototype.forEach.call(barEl.children, function(seg, i) {
          seg.className = i < done ? 'done' : (i === done ? 'current' : '');
        });
        const text = steps.finishing
          ? 'Almost done: preparing your report'
          : 'Step ' + steps.step + ' of ' + steps.total + ': ' + steps.label;
        barEl.setAttribute('aria-valuemin', '0');
        barEl.setAttribute('aria-valuemax', String(steps.total));
        barEl.setAttribute('aria-valuenow', String(done));
        barEl.setAttribute('aria-valuetext', text);
        setText(statusEl, text);
        tick();
      }

      function clearSteps() {
        steps = null;
        barEl.classList.remove('progress--steps');
        barEl.textContent = '';
        ['aria-valuemin', 'aria-valuemax', 'aria-valuenow', 'aria-valuetext'].forEach(function(a) { barEl.removeAttribute(a); });
        setText(hintEl, '');
      }

      // The form page stays alive while its validation request is pending, so
      // it can ask the server which step that request is on. Any failure just
      // leaves the plain busy indicator in place.
      function poll(run) {
        if (!busy || run !== pollRun) return;
        fetch(form.dataset.progressUrl + '?source=' + encodeURIComponent(source), { cache: 'no-store' })
          .then(function(r) { return r.ok ? r.json() : null; })
          .then(function(p) {
            if (!p || !busy || run !== pollRun) return;
            if (p.state === 'running') steps = { step: p.step, total: p.steps, label: p.label, finishing: false };
            else if (p.state === 'finishing') steps = { step: p.steps, total: p.steps, label: '', finishing: true };
            else return;  // not started on the server yet: keep what is shown
            renderSteps();
          })
          .catch(function() {})
          .then(function() {
            if (busy && run === pollRun && !(steps && steps.finishing)) pollTimer = setTimeout(function() { poll(run); }, 1000);
          });
      }

      // Same name the server tracks the job under: the typed URL or the file name.
      function currentSource() {
        if (!urlField.disabled) return urlField.value.trim();
        return fileField.files.length ? fileField.files[0].name : '';
      }

      function setBusy(on) {
        busy = on;
        form.classList.toggle('is-busy', on);
        pollRun++;
        clearTimeout(pollTimer);
        if (on) {
          form.setAttribute('aria-busy', 'true');
          submitBtn.setAttribute('aria-disabled', 'true');
          submitBtn.textContent = 'Checking\u2026';
          bodyEl.hidden = false;
          startedAt = Date.now();
          source = currentSource();
          tick();
          timer = setInterval(tick, 1000);
          if (window.fetch && form.dataset.progressUrl && source) {
            const run = pollRun;
            pollTimer = setTimeout(function() { poll(run); }, 700);
          }
        } else {
          clearInterval(timer);
          form.removeAttribute('aria-busy');
          submitBtn.removeAttribute('aria-disabled');
          submitBtn.textContent = idleLabel;
          bodyEl.hidden = true;
          clearSteps();
          statusEl.textContent = '';
          elapsedEl.textContent = '';
          lockable.forEach(function(el) { el.inert = false; });
        }
      }

      // The submit event (not a click handler) also covers Enter in the URL
      // field, and only fires once the browser's own validation has passed.
      form.addEventListener('submit', function(e) {
        if (busy) { e.preventDefault(); return; }
        setBusy(true);
        // Locked after the event so the form data is read before any control
        // is touched; the guard above is what actually blocks repeat submits.
        setTimeout(function() { if (busy) lockable.forEach(function(el) { el.inert = true; }); }, 0);
      });

      // Back/forward may restore this page, frozen mid-wait, from the
      // back/forward cache.
      window.addEventListener('pageshow', function() { if (busy) setBusy(false); });

      // Esc or the browser's Stop button fires no event on this page, so
      // offer a way out of the busy state.
      cancelBtn.addEventListener('click', function() {
        window.stop();
        setBusy(false);
        submitBtn.focus();
      });
    })();
  </script>

  <h2 id="what-do-you-get">What does Ask Wol check?</h2>
  <p>An interactive <strong>class diagram</strong> of your ontology, plus one
  HTML report (or JSON via the API) with a section per check. The checks are
  grouped into five areas, and each links to the matching entry in the
  <a href="guide">publishing guide</a>:</p>

  <!--CHECKS_OVERVIEW-->

  <p><strong>What you don&rsquo;t get:</strong> askwol checks syntax and
  structure, but not content or meaning, which is what ontologies are all
  about.</p>

  <h2 id="other-resources">Other resources</h2>
  <p><i>askwol</i> is a checker, not a full ontology engineering toolkit.
  A few other resources worth a look:</p>
  <ul>
    <li><a href="https://protege.stanford.edu/" target="_blank" rel="noopener">Prot&eacute;g&eacute;</a>: the standard free, open-source ontology editor.</li>
    <li><a href="https://www.michaeldebellis.com/post/new-protege-pizza-tutorial" target="_blank" rel="noopener">The Pizza Tutorial</a>: a revised Prot&eacute;g&eacute; 5 version of the classic hands-on OWL tutorial.</li>
    <li><a href="https://lov.linkeddata.es/dataset" target="_blank" rel="noopener">Linked Open Vocabularies (LOV)</a>: a catalogue of reusable RDF vocabularies.</li>
    <li><a href="https://ontochoice.github.io/choosing-terms-and-ontologies/" target="_blank" rel="noopener">OntoChoice</a>: an initiative on choosing ontologies and terms.</li>
    <li><a href="https://oops.linkeddata.es/" target="_blank" rel="noopener">OOPS!</a>: an online scanner for common ontology pitfalls.</li>
    <li><a href="https://w3id.org/foops/" target="_blank" rel="noopener">FOOPS!</a>: an online tool for assessing the FAIRness of ontologies and vocabularies.</li> 
    <li><a href="https://robot.obolibrary.org/" target="_blank" rel="noopener">ROBOT</a>: a command-line tool for automating ontology engineering workflows.</li>
  </ul>

  <div class="about">
    <img class="wollie" src="static/wollie-about.png" alt="Wollie, a hand-drawn owl" width="140" height="183">
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
      <a href="https://tdcc.nl/nes/ontology-engineers/">TDCC-NES Ontology Engineers</a>
      (<strong>Kathrin F&uuml;llenbach</strong> and <strong>Dani Metilli</strong>), funded by
      <a href="https://www.openscience.nl/en/">Open Science NL</a>. We help with ontology
      selection and reuse, co-development, knowledge graph design, and training.
    </p>
    <p>
      <i>askwol</i> is free and open source under the
      <a href="https://github.com/TDCC-NES/askwol/blob/main/LICENSE">MIT licence</a>.
      It is currently in <strong>beta</strong>: some checks may be incomplete
      or produce false positives. Found a bug or have an idea? Open an issue on
      <a href="https://github.com/TDCC-NES/askwol">GitHub</a> or reach us at
      <a href="mailto:nes@tdcc.nl">nes@tdcc.nl</a>.
    </p>
  </div>

  <p class="footer">
    <strong>External links:</strong>
    <a href="https://tdcc.nl/nes/ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot;
    <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot;
    <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a> &middot;
    <a href="https://www.w3.org/TR/owl2-syntax/" target="_blank" rel="noopener">OWL 2 Specification</a>
  </p>
</body>
</html>"""

# Single source of truth for the publishing guide. The order of this list IS
# the order of both the table of contents and the page body, so the two
# cannot drift apart. Sections in group="check" are linked from the
# validation report; their order and anchors must match the shared CHECKS catalogue.
# Sections in group="practice" are additional best practices with no
# automated check.
#
# Check-group sections are grouped into clusters via their "category" key.
# CHECK_CATEGORIES gives the cluster order and display labels, and is shared
# with report_html so the guide, the overview, and the results agree.
GUIDE_SECTIONS: list[dict[str, str]] = [
    {
        "group": "check",
        "category": "basics",
        "anchor": "metadata",
        "title": "Give the ontology itself good metadata",
        "toc_label": "Ontology metadata",
        "body": """\
  <p>Your ontology is itself a published research object. It should say
  what it is, who made it, which version it is, and under which licence
  it can be reused.</p>
  <p><span class="tag spec">Spec</span> <code>rdf:type owl:Ontology</code> and
  <code>owl:versionIRI</code>/<code>owl:versionInfo</code> come from OWL 2;
  <code>dcterms:title</code>, <code>dcterms:description</code>,
  <code>dcterms:creator</code>, <code>dcterms:created</code>,
  <code>dcterms:modified</code>, and <code>dcterms:publisher</code> are
  defined by the
  <a href="https://www.dublincore.org/specifications/dublin-core/dcmi-terms/" target="_blank" rel="noopener">DCMI Metadata Terms</a>
  vocabulary, not OWL itself. Licensing gets its own dedicated check; see
  <a href="#license">Open licence</a> below.</p>
  <p><span class="tag practice">TDCC guideline</span> Neither spec says any
  of these properties is mandatory on an ontology header. The
  <strong>core</strong> / <strong>additional</strong> grouping below is
  this guide&rsquo;s own editorial judgement of what a well-published
  ontology needs. askwol reports every missing property, in either group,
  as a <strong>recommendation</strong>.</p>
  <p>askwol evaluates <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/ontology_metadata.ttl" target="_blank" rel="noopener">SHACL shapes for the ontology header</a> and checks these properties:</p>
  <ul>
    <li><strong>Core:</strong> <code>rdf:type owl:Ontology</code>,
    <code>dcterms:title</code> (or <code>rdfs:label</code>, or the legacy
    <code>dc:title</code>), <code>dcterms:description</code> (or
    <code>rdfs:comment</code>, or the legacy <code>dc:description</code>),
    <code>dcterms:creator</code> (or <code>dc:creator</code>), and
    <code>owl:versionInfo</code> or <code>owl:versionIRI</code>.</li>
    <li><strong>Additional:</strong> <code>dcterms:created</code>
    (or <code>dcterms:issued</code>, or <code>dc:date</code>),
    <code>dcterms:modified</code> (or <code>dc:date</code>), and
    <code>dcterms:publisher</code> (or <code>dc:publisher</code>).</li>
  </ul>
  <p>Pre-2010 ontologies (e.g. FOAF, OWL-Time) often use the older
  <a href="https://www.dublincore.org/specifications/dublin-core/dces/" target="_blank" rel="noopener">Dublin Core Elements</a>
  (<code>dc:</code>) properties instead of DCMI Terms; askwol accepts
  either, since they carry the same meaning. One nuance: Elements 1.1&rsquo;s
  single, generic <code>dc:date</code> property doesn&rsquo;t distinguish created
  from modified, so askwol accepts it for either (or both) of the two
  additional date checks above.</p>
  <div class="tip">Fill in these metadata so that both humans and machines
  can understand the provenance and reuse conditions of your ontology.</div>
  
  <h4 id="versioning">Versioning</h4>
  <p>Version information is part of good ontology metadata.
  <span class="tag spec">Spec</span> OWL 2 defines
  <a href="https://www.w3.org/TR/owl2-syntax/#def_version_iri" target="_blank" rel="noopener"><code>owl:versionIRI</code></a>
  to give each release its own dereferenceable URL, and
  <a href="https://www.w3.org/TR/owl2-syntax/#a_versionInfo" target="_blank" rel="noopener"><code>owl:versionInfo</code></a>
  to hold &ldquo;a string that describes the IRI&rsquo;s version,&rdquo; with no
  format required.</p>
  <p><span class="tag practice">TDCC guideline</span> This guide recommends
  <a href="https://semver.org/" target="_blank" rel="noopener">Semantic Versioning</a>
  (<code>MAJOR.MINOR.PATCH</code>) as a practical convention, not an OWL
  requirement: bump <strong>major</strong> when you remove or redefine a
  term, <strong>minor</strong> when you add terms without breaking existing
  ones, and <strong>patch</strong> for fixes such as corrected labels or
  comments.</p>
  <pre>&lt;http://example.org/my-ontology&gt; a owl:Ontology ;
    owl:versionIRI &lt;http://example.org/my-ontology/2.0.0&gt; ;
    owl:versionInfo "2.0.0" .</pre>
  <p>Some ontologies version by <strong>date</strong> instead, especially W3C
  specifications on a fixed release schedule: PROV-O&rsquo;s
  <code>owl:versionIRI</code> is
  <code>http://www.w3.org/ns/prov-o-20130430</code>. A date is simpler than
  semver but only says <em>when</em> something changed, not whether it is
  safe to upgrade. Pick one scheme per ontology and stick to it.</p>
""",
    },
    {
        "group": "check",
        "category": "basics",
        "anchor": "imports",
        "title": "",
        "toc_label": "Resolving ontology imports",
        "body": """\
  <p><span class="tag spec">Spec</span> To include another ontology&rsquo;s
  axioms in yours, use
  <a href="https://www.w3.org/TR/owl2-syntax/#Imports" target="_blank" rel="noopener">OWL 2</a>
  <code>owl:imports</code> in the ontology header. Merely referencing a
  vocabulary&rsquo;s terms does not require an import:</p>
  <pre>&lt;https://example.org/my-ontology&gt; a owl:Ontology ;
    owl:imports &lt;http://xmlns.com/foaf/0.1/&gt; .</pre>
  <p>This tells reasoners and tools where your external terms are defined,
  so they can load the imported ontology and reason over it together with
  yours.</p>
  <p><span class="tag practice">TDCC guideline</span> Deciding <em>which</em>
  vocabularies deserve a formal import is a modelling judgement call askwol
  does not second-guess. What it does check is whether every
  <code>owl:imports</code> target you already declared is actually
  reachable: each IRI is fetched over HTTP and parsed as RDF, the same way a
  reasoner would follow it. This reachability check is askwol&rsquo;s own
  addition; OWL 2 does not require import targets to be checked at
  authoring time.</p>
  <div class="tip">A broken import (a dead link, a renamed URL, a server
  that no longer serves RDF) degrades reasoning for anyone who loads your
  ontology, with nothing reporting the failure unless a tool checks it
  explicitly. askwol reports an import that does not resolve as a
  <strong>warning</strong>.</div>
  <div class="tip">askwol only checks that declared imports resolve; it
  never merges their content into the checks that run on your ontology.
  Every other check, including the reasoner, runs on your ontology document
  alone.</div>
""",
    },
    {
        "group": "check",
        "category": "basics",
        "anchor": "iri-strategy",
        "title": "",
        "toc_label": "Choosing hash or slash IRIs",
        "body": """\
  <p><strong>What askwol checks:</strong> every term defined inside your
  ontology&rsquo;s own namespace is classified as either <em>hash style</em>
  (<code>http://example.org/ont#Person</code>) or <em>slash style</em>
  (<code>http://example.org/ont/Person</code>), per declared
  <code>owl:Ontology</code> base IRI. A base IRI whose defined terms all use
  the same pattern is fine; one that mixes both is reported as a
  <strong>warning</strong>. An ontology
  that legitimately bundles more than one base IRI (a rare pattern, e.g.
  the W3C PROV family) may use a different, consistent style for each
  without being flagged.</p>
  <div class="tip">Mixing hash and slash in the same vocabulary is almost
  always accidental. It breaks naive prefix-based namespace splitting and
  confuses consumers about whether <code>/Person</code> is the same term
  as <code>#Person</code>.</div>

  <h4 id="hash-vs-slash">Hash vs. slash, in plain terms</h4>
  <p><span class="tag practice">TDCC guideline</span> Neither RDF nor OWL
  requires hash or slash IRIs; both are valid (the W3C
  <a href="https://www.w3.org/TR/cooluris/" target="_blank" rel="noopener">&ldquo;Cool URIs for the
  Semantic Web&rdquo;</a> Interest Group Note describes both). They differ
  in how the identifier behaves over HTTP and how the vocabulary scales.</p>
  <ul>
    <li><strong>Hash</strong> &middot; <code>ont<strong>#</strong>Person</code>.
    The fragment is stripped before the HTTP request, so the server always
    returns the whole file in one request: zero server configuration, but a
    client asking about one term gets
    <em>every</em> term in the vocabulary. Fine for 50&nbsp;terms, painful
    for 50&thinsp;000. Used by OWL and RDF Schema.</li>
    <li><strong>Slash</strong> &middot; <code>ont<strong>/</strong>Person</code>.
    Each term is its own HTTP resource, typically served via a
    <code>303&nbsp;See&nbsp;Other</code> redirect per the W3C TAG&rsquo;s
    <a href="http://lists.w3.org/Archives/Public/www-tag/2005Jun/0039.html" target="_blank" rel="noopener">httpRange-14
    resolution</a> (2005). More flexible for large or growing vocabularies,
    at the cost of server-side redirect rules and content negotiation. Used
    by FOAF, Schema.org, Dublin Core, and DBpedia.</li>
  </ul>

  <h4 id="iri-strategy-recommendation">Recommendation</h4>
  <p><span class="tag practice">TDCC guideline</span> If in doubt, <strong>go
  with slash</strong>: it scales. Use hash only for a vocabulary you know
  will stay small. The Cool URIs note concludes:</p>
  <blockquote style="border-left:3px solid #ccc;padding-left:1em;color:#555;margin:1em 0;">
  &ldquo;Hash URIs should be preferred for rather <strong>small and stable</strong>
  sets of resources that evolve together. The ideal case are RDF Schema
  vocabularies and OWL ontologies. [&hellip;] 303&nbsp;URIs may also be
  used for [large] data sets, making neater-looking URIs.&rdquo;
  </blockquote>
  <p>Either way, <strong>pick one per base IRI</strong> and don&rsquo;t mix
  styles within it. Use a domain you control, or a persistent ID service
  like
  <a href="https://w3id.org/" target="_blank" rel="noopener">w3id.org</a> or
  <a href="https://purl.org/" target="_blank" rel="noopener">purl.org</a>, so
  your IRIs survive domain changes.</p>
""",
    },
    {
        "group": "check",
        "category": "basics",
        "anchor": "https-http",
        "title": "Use http or https, but be consistent per namespace",
        "toc_label": "IRI scheme (http vs https)",
        "body": """\
  <p><strong>What askwol checks:</strong> every IRI used in the ontology
  (in subject, predicate, or object position, plus every bound namespace)
  is grouped by namespace (the base IRI up to the last <code>/</code> or
  <code>#</code>), not just by host, so two unrelated vocabularies that
  happen to share a host are never compared to each other. A namespace
  that appears under exactly one URI scheme is fine; one referenced
  under both <code>http://</code> and <code>https://</code> is reported as a
  <strong>warning</strong>. The report
  lists the conflicting namespaces with examples of each scheme so you can
  pick one canonical form and migrate the others.</p>

  <p><span class="tag spec">Spec</span> <code>http://example.org/ont/Person</code>
  and <code>https://example.org/ont/Person</code> are
  <strong>different IRIs</strong>: RDF identifies resources by their exact
  IRI string, per
  <a href="https://www.rfc-editor.org/rfc/rfc3987" target="_blank" rel="noopener">RFC 3987</a>,
  and OWL never treats two IRIs as the same resource unless you assert
  <code>owl:sameAs</code> yourself. Mixing schemes breaks joins that rely on
  exact IRI matches, including SPARQL and any tool that does string
  comparison on URIs.</p>

  <h4 id="legacy-namespaces">The legacy problem</h4>
  <p>Most foundational vocabularies were minted before HTTPS was ubiquitous.
  OWL, RDFS, FOAF, Dublin Core, SKOS and PROV-O all use
  <code>http://</code>. Changing them would break billions of existing
  triples, so they stay on <code>http</code>.</p>
  <div class="warn"><strong>Do not</strong> &ldquo;fix&rdquo;
  <code>http://xmlns.com/foaf/0.1/name</code> to <code>https://</code>.
  You would be creating a <em>different</em> IRI that matches nothing in
  other people&rsquo;s data.</div>

  <h4 id="own-ontology-scheme">For your own ontology</h4>
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
        "category": "basics",
        "anchor": "license",
        "title": "Adopt an open licence",
        "toc_label": "Open licence",
        "body": """\
  <p><span class="tag practice">TDCC guideline</span> Your ontology should be released under an <strong>open licence</strong>; this guide recommends the DCMI property <code>dcterms:license</code>. To meet the Linked Open Data principles, the licence must satisfy the <a href="https://opendefinition.org" target="_blank" rel="noopener">Open Definition</a>: &ldquo;anyone can freely access, use, modify, and share [the ontology] for any purpose (subject, at most, to requirements that preserve provenance and openness).&rdquo;</p>
  <p>A licence is open if it&rsquo;s equivalent to the <strong>public domain</strong>, or at most adds <strong>attribution</strong> or <strong>share-alike</strong> restrictions; non-commercial or no-derivatives clauses are not open. For maximum reuse, this guide recommends one of the two <a href="https://creativecommons.org/cc-licenses/" target="_blank" rel="noopener">Creative Commons</a> licences below.</p>
  <ol>
    <li>
      <a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">Creative Commons Zero (CC0)</a> (public domain); IRI: <code>https://creativecommons.org/publicdomain/zero/1.0/</code>
    </li>
    <li>
      <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">Creative Commons Attribution (CC BY)</a> (requires attribution); IRI: <code>https://creativecommons.org/licenses/by/4.0/</code>
    </li>
  </ol>

  <p>askwol also recognises other licences that meet the Open Definition but are less suitable for ontologies, for the reasons below.</p>
  <ul>
    <li>
      <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">Creative Commons Attribution ShareAlike (CC BY-SA)</a> (requires attribution, share-alike); IRI: <code>https://creativecommons.org/licenses/by-sa/4.0/</code>; too restrictive due to the share-alike.
    </li>
    <li>
      <a href="http://opendatacommons.org/licenses/pddl/1.0/" target="_blank" rel="noopener">Open Data Commons Public Domain Dedication and License (PDDL)</a> (public domain); IRI: <code>http://opendatacommons.org/licenses/pddl/1.0/</code>; only covers data and not content.
    </li>
    <li>
      <a href="http://opendatacommons.org/licenses/by/1.0/" target="_blank" rel="noopener">Open Data Commons Attribution License (ODC-By)</a> (requires attribution); IRI: <code>http://opendatacommons.org/licenses/by/1.0/</code>; only covers data and not content.
    </li>
    <li>
      <a href="http://opendatacommons.org/licenses/odbl/1.0/" target="_blank" rel="noopener">Open Data Commons Open Database License (ODbL)</a> (requires attribution, share-alike); IRI: <code>http://opendatacommons.org/licenses/odbl/1.0/</code>; too restrictive due to the share-alike.
    </li>
    <li>
      <a href="https://opendefinition.org/licenses" target="_blank" rel="noopener">Other licences conformant with the Open Definition</a>; most of these are little used and incompatible with more widely adopted open licences.
    </li>
    <li>
      <a href="https://opensource.org/licenses" target="_blank" rel="noopener">Any licence approved by the Open Source Initiative</a>; these are primarily meant for open source software rather than ontologies.
    </li>
  </ul>

  <p>Declare it with <code>dcterms:license</code> in the ontology header:</p>
  <pre>&lt;https://example.org/my-ontology&gt; a owl:Ontology ;
    dcterms:license &lt;https://creativecommons.org/publicdomain/zero/1.0/&gt; .</pre>
  <div class="tip">askwol checks each declared licence against the Open Definition&rsquo;s <a href="https://opendefinition.org/licenses" target="_blank" rel="noopener">list of conformant licences</a>: a missing or non-open licence, an open but not-recommended licence, or more than one declared licence (even if each is fine on its own) is reported as a recommendation.</div>
""",
    },
    {
        "group": "check",
        "category": "reuse",
        "anchor": "resolvable",
        "title": "",
        "toc_label": "Making ontology namespaces resolvable",
        "body": """\
  <p>A <strong>namespace</strong> is the URI that a prefix expands to. In
  <code>@prefix foaf: &lt;http://xmlns.com/foaf/0.1/&gt;</code> the prefix is
  <code>foaf</code> and the namespace is
  <code>http://xmlns.com/foaf/0.1/</code>. This check looks at those namespace
  URIs; the short prefix aliases themselves are covered by
  <a href="#prefixes">Unused prefixes</a> below.</p>
  <p><span class="tag practice">TDCC guideline</span> Every namespace URI
  should return something useful when fetched with HTTP. Ideally it returns
  RDF (content-negotiated), so tools can discover term definitions
  automatically. Neither RDF nor OWL requires a namespace to be
  dereferenceable; this expectation comes from the
  <a href="https://www.w3.org/DesignIssues/LinkedData.html" target="_blank" rel="noopener">Linked Data principles</a>
  and the W3C Note linked below.</p>
  <div class="tip"><strong>Good:</strong>
  <code>http://xmlns.com/foaf/0.1/</code> returns RDF when asked with
  <code>Accept: application/rdf+xml</code>.</div>
  <div class="warn"><strong>Bad:</strong> A namespace that returns
  404 or a generic HTML page with no RDF link.</div>
  <p>If you host your own ontology, configure your server to support
  <a href="https://www.w3.org/TR/swbp-vocab-pub/" target="_blank" rel="noopener">content negotiation</a>,
  serving RDF to machines and HTML to browsers; see
  <a href="#server-config">Server configuration</a> below for the details.
  askwol reports a namespace that does not resolve as a
  <strong>warning</strong>.</p>
""",
    },
    {
        "group": "check",
        "category": "reuse",
        "anchor": "prefixes",
        "title": "Keep your prefixes clean",
        "toc_label": "Unused prefixes",
        "body": """\
  <p><span class="tag spec">Spec</span> Each
  <a href="https://www.w3.org/TR/turtle/" target="_blank" rel="noopener"><code>@prefix</code></a>
  line binds a short prefix to a <a href="#resolvable">namespace</a> URI.
  <span class="tag practice">TDCC guideline</span> Turtle itself does not
  forbid declaring a prefix you never use; this check is about good
  hygiene: only declare prefixes you actually use. Leftover
  <code>@prefix</code> declarations clutter the file and confuse readers;
  they suggest a dependency that doesn&rsquo;t exist.</p>
  <pre>@prefix dct: &lt;http://purl.org/dc/terms/&gt; .              # used below
@prefix geo: &lt;http://www.opengis.net/ont/geosparql#&gt; .  # unused, remove it</pre>
  <div class="tip">askwol reports every prefix that is declared
  but never appears in a triple as a <strong>recommendation</strong>, so you
  can clean them up.</div>
""",
    },
    {
        "group": "check",
        "category": "reuse",
        "anchor": "external-terms",
        "title": "Make sure reused terms actually exist",
        "toc_label": "External term definitions",
        "body": """\
  <p><span class="tag practice">TDCC guideline</span> Don&rsquo;t reinvent
  the wheel. Before defining a new term, check if an established vocabulary
  already covers it. No spec requires reuse, but the wider Semantic Web
  interoperates far better when ontologies share terms:</p>
  <ul>
    <li><a href="http://xmlns.com/foaf/0.1/">FOAF</a>: people and social networks</li>
    <li><a href="https://www.w3.org/ns/prov#">PROV-O</a>: provenance</li>
  </ul>
  <div class="warn">When reusing a term, use the <em>exact</em>
  IRI from the source vocabulary. A typo like <code>foaf:nme</code> instead
  of <code>foaf:name</code> breaks interoperability.</div>
  <div class="tip">askwol checks external terms used as subjects in your
  document against the retrieved vocabulary and reports terms not found there as
  <strong>warnings</strong>. This
  catches typos like <code>foaf:nme</code>, made-up terms like
  <code>owl:MadeUpClass</code>, and <strong>namespace hijacking</strong>
  (asserting a brand-new term such as <code>foaf:MadeUpConcept</code> under
  someone else&rsquo;s namespace instead of your own). Terms from your own
  namespace are checked separately (see
  <a href="#internal-terms">Internal term definitions</a>).</div>
  <div class="warn">A term can also exist but be deprecated by the
  vocabulary that defines it. <span class="tag spec">Spec</span>
  <code>owl:deprecated</code> is an
  <a href="https://www.w3.org/TR/owl2-syntax/#Annotation_Properties" target="_blank" rel="noopener">OWL 2</a>
  annotation property, and
  <code>owl:DeprecatedClass</code>/<code>owl:DeprecatedProperty</code> come
  from the
  <a href="https://www.w3.org/TR/owl-ref/#Deprecation" target="_blank" rel="noopener">OWL 1 Reference</a>
  (used by e.g. <a href="https://vivoweb.org/ontology/core" target="_blank" rel="noopener">VIVO</a>).
  <span class="tag practice">TDCC guideline</span> A
  <code>vs:term_status</code> of &ldquo;deprecated&rdquo;/&ldquo;archaic&rdquo;
  is a community convention from a non-normative
  (<a href="https://www.w3.org/2003/06/sw-vocab-status/note" target="_blank" rel="noopener">W3C Note</a>,
  used by e.g. <a href="http://xmlns.com/foaf/spec/index.rdf" target="_blank" rel="noopener">FOAF</a>),
  not a REC. askwol checks for all three and flags a deprecated reused term
  as a warning, so you don&rsquo;t quietly build on a term the source
  vocabulary is phasing out.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "internal-terms",
        "title": "Define every term you use in your own namespace",
        "toc_label": "Internal term definitions",
        "body": """\
  <p><span class="tag practice">TDCC guideline</span> Every term you use
  from your <em>own</em> namespace should also be defined there.
  Don&rsquo;t just <em>use</em> a term; <em>define</em> it. RDF&rsquo;s
  open-world assumption actually permits referencing an IRI with no triples
  about it at all; askwol still flags it, because within your <em>own</em>
  namespace an undefined term is almost always an authoring mistake, not an
  intentional stub.</p>
  <pre>&lt;#Person&gt; a owl:Class ;
    rdfs:label "Person"@en ;
    rdfs:comment "A human being."@en .</pre>
  <div class="warn">If you reference <code>ex:Persom</code> but
  never define it, that&rsquo;s probably a typo. askwol catches these.</div>
  <div class="tip">askwol treats a term as <strong>defined</strong> when it
  appears as the <strong>subject</strong> of at least one triple, and as
  <strong>referenced</strong> when it appears as a predicate or object. A term
  in your own namespace that is referenced but never defined is reported as
  a <strong>warning</strong>.
  External vocabulary terms are covered by the
  <a href="#external-terms">External term definitions</a> check instead.
  Some ontologies re-declare a reused term as boilerplate (e.g.
  <code>rdfs:label a owl:AnnotationProperty</code>, as PROV-O and FOAF do).
  askwol correctly recognises this as reuse of an existing term, keeping
  your own namespace scoped to what you actually define. New terms always
  belong in your own namespace: the
  <a href="#external-terms">External term definitions</a> check confirms
  that anything asserted under an external prefix, like
  <code>foaf:MadeUpConcept</code>, genuinely exists there already, catching
  <strong>namespace hijacking</strong> along the way.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "term-inventory",
        "title": "Categorise your terms and name them consistently",
        "toc_label": "Term inventory &amp; naming",
        "body": """\
  <p><span class="tag spec">Spec</span> Every term you define falls into a
  category OWL 2 itself defines: a <strong>class</strong>, an
  <strong>object property</strong>, a <strong>datatype property</strong>, an
  <strong>annotation property</strong>, a <strong>datatype</strong>, or a
  <strong>named individual</strong>. askwol lists each internal term with the
  category it detected, so you can spot a term that was never typed
  (<code>rdf:type</code> missing) or typed as the wrong kind of thing.</p>
  <pre>&lt;#Person&gt;   a owl:Class .
&lt;#hasParent&gt; a owl:ObjectProperty .
&lt;#birthDate&gt; a owl:DatatypeProperty .</pre>
  <h4 id="naming-conventions">Naming conventions</h4>
  <p><span class="tag practice">TDCC guideline</span> Capitalisation is a
  community convention, not an OWL or RDFS rule; nothing stops you from
  naming a class <code>person</code> or a property <code>HasName</code>.
  askwol checks it anyway, because consistent casing is one of the fastest
  ways to tell a class from a property at a glance. A mismatch is reported
  as a recommendation, not an error: it&rsquo;s worth fixing, but it won&rsquo;t
  block publication.</p>
  <ul>
    <li><strong>Classes start with an uppercase letter</strong> and are usually
    nouns: <code>Person</code>, <code>Dataset</code>, <code>Organisation</code>.</li>
    <li><strong>Properties start with a lowercase letter</strong>:
    <code>hasParent</code>, <code>birthDate</code>, <code>title</code>.</li>
  </ul>
  <p>Some vocabularies use stable, coded identifiers instead: CIDOC CRM&rsquo;s
  properties look like <code>P2_has_type</code> (the number is the permanent
  identifier; the wording after it can change between versions), and
  Wikidata&rsquo;s are fully opaque, like <code>P19</code>, deliberately avoiding
  any one language&rsquo;s naming bias. askwol recognises this pattern, an
  uppercase letter directly followed by a digit, and does not flag it.</p>
  <div class="tip">Object properties read best as verb phrases. A
  <code>has</code> or <code>is</code> prefix, or an <code>of</code>/<code>by</code>
  form, gives a single unambiguous reading: <code>hasWife</code>,
  <code>wifeOf</code>, <code>lovedBy</code>. This is a readability convention,
  not something askwol enforces; askwol only checks the case of the first
  letter, via <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/term_inventory.ttl" target="_blank" rel="noopener">SHACL shapes</a>.</div>
  <div class="warn">Mixing conventions (a lowercase class like
  <code>person</code>, or an uppercase property like <code>HasName</code>,
  with no digit following the capital) makes an ontology harder to read and
  to reuse.</div>
  <div class="tip">A term marked deprecated (see
  <a href="#external-terms">External term definitions</a>) is exempt from
  naming checks: an old term kept around for backward compatibility
  shouldn&rsquo;t need renaming on its way out.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "domains-ranges",
        "title": "Give properties a domain and a range",
        "toc_label": "Domains &amp; ranges",
        "body": """\
  <p><span class="tag spec">Spec</span> An
  <a href="https://www.w3.org/TR/rdf-schema/#ch_domain" target="_blank" rel="noopener"><code>rdfs:domain</code></a>
  says what kind of subject a property applies to; an
  <a href="https://www.w3.org/TR/rdf-schema/#ch_range" target="_blank" rel="noopener"><code>rdfs:range</code></a>
  says what kind of value it takes.
  <span class="tag practice">TDCC guideline</span> RDFS does not require
  either one; declaring both is this guide&rsquo;s recommendation because it
  makes a property self-documenting and lets tools reason about it.</p>
  <pre>&lt;#hasParent&gt; a owl:ObjectProperty ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range  &lt;#Person&gt; .  # a class

&lt;#birthDate&gt; a owl:DatatypeProperty ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range  xsd:date .   # a datatype</pre>
  <ul>
    <li>An <strong>object property</strong> should range over a
    <strong>class</strong>. A range that is a datatype means it should probably
    be a datatype property.</li>
    <li>A <strong>datatype property</strong> should range over a
    <strong>datatype</strong>. A range that is a class means it should probably
    be an object property.</li>
    <li>A <strong>domain</strong> should be a class for either kind.</li>
  </ul>
  <p><span class="tag spec">Spec</span> In OWL 2 DL, an object property
  ranges over classes and a datatype property over datatypes. Getting that
  wrong puts the ontology outside OWL 2 DL, so askwol reports it as an
  <strong>error</strong>. A domain or range that is simply missing is only a
  <strong>recommendation</strong>.</p>
  <div class="warn"><span class="tag spec">Spec</span> In OWL, a domain or
  range is not a constraint that rejects bad data; a reasoner instead
  <em>infers new facts</em> from it. Stating
  <code>rdfs:domain :Person</code> on <code>:birthDate</code> tells a reasoner
  that anything with a <code>:birthDate</code> is a <code>:Person</code>. Pick
  domains and ranges that are actually true of every use.</div>
  <div class="tip">askwol only looks at the <code>rdfs:domain</code> and
  <code>rdfs:range</code> declared directly on a property, not ones
  inherited from a super-property. A reasoner does follow that inheritance,
  so this check can occasionally flag something a reasoner would treat as
  fine. Checked against <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/term_inventory.ttl" target="_blank" rel="noopener">SHACL shapes</a>.
  Deprecated properties (see
  <a href="#external-terms">External term definitions</a>) are exempt.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "datatypes",
        "title": "",
        "toc_label": "Checking OWL datatypes",
        "body": """\
  <p><span class="tag spec">Spec</span> RDF typed literals use datatype
  IRIs, commonly from
  <a href="https://www.w3.org/TR/xmlschema11-2/" target="_blank" rel="noopener">XSD</a>
  built-ins (<code>xsd:string</code>, <code>xsd:integer</code>,
  <code>xsd:date</code>, <code>xsd:boolean</code>, &hellip;)
  or <code>rdf:langString</code>. A datatype property can range over
  <a href="https://www.w3.org/TR/rdf-schema/#ch_literal" target="_blank" rel="noopener"><code>rdfs:Literal</code></a>
  or a specific datatype. Custom datatypes can be declared with
  <a href="https://www.w3.org/TR/rdf-schema/#ch_datatype" target="_blank" rel="noopener"><code>rdfs:Datatype</code></a>.
  RDF itself places no closed list on datatype IRIs; any IRI is legal there.
  <span class="tag spec">Spec</span> OWL 2 has a specific
  <a href="https://www.w3.org/TR/owl2-syntax/#Datatype_Maps" target="_blank" rel="noopener">datatype map</a>
  and restrictions on datatype definitions; recognising an IRI or finding
  a declaration alone does not establish OWL 2 DL conformance.
  askwol checks datatype IRIs against its built-in list and local
  declarations, reporting unrecognised IRIs as <strong>errors</strong>.
  It does not perform a complete datatype or literal-value validation.</p>
  <pre>&lt;#age&gt; rdfs:range xsd:nonNegativeInteger .
&lt;#born&gt; rdfs:range xsd:date .
"42"^^xsd:integer</pre>
  <div class="warn">A misspelled datatype (<code>xsd:stirng</code>,
  <code>xsd:dateTiem</code>) is treated as a brand-new, unknown datatype.
  Filters and validators that expect the real datatype then skip your
  values. askwol lists every datatype it sees and flags the ones it does not
  recognise.</div>
""",
    },
    {
        "group": "check",
        "category": "structure",
        "anchor": "non-ontology-terms",
        "title": "Keep concept schemes separate from the schema",
        "toc_label": "Non-ontology terms",
        "body": """\
  <p><span class="tag practice">TDCC guideline</span> An OWL ontology is the
  <em>schema</em>: it defines classes, properties, and datatypes (the
  terminology). Named individuals are a different kind of thing, actual
  instances rather than schema, and most are fine to keep in the same
  file. <strong>SKOS concepts</strong>, the members of a controlled
  vocabulary or thesaurus, are the one case worth pulling out. A concept
  scheme is typically much larger than the schema and grows on its own
  schedule: new terms get added without ever touching a class or property
  definition. This guide recommends keeping SKOS concepts in their own
  <a href="https://www.w3.org/TR/skos-reference/#Concept" target="_blank" rel="noopener">SKOS</a>
  concept scheme, separate from the ontology file, so schema and data can
  each evolve and be reused independently.</p>
  <pre>&lt;#Dataset&gt; a owl:Class .     # schema, belongs here
&lt;#biology&gt; a skos:Concept .  # concept, belongs in a SKOS scheme
&lt;#Monday&gt; a &lt;#DayOfWeek&gt; .   # named individual, fine to keep here</pre>
  <div class="tip">askwol only reports <code>skos:Concept</code> instances defined
  in your own namespace, as <strong>recommendations</strong>; a full concept scheme has usually outgrown the schema
  file and is better managed on its own. Named individuals are left alone:
  many ontologies deliberately define a small, fixed set of them alongside
  their schema (days of week, units of measure, as OWL-Time does), a
  legitimate modelling pattern rather than accidental instance data. External
  terms are ignored either way. Checked against <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/non_ontology_terms.ttl" target="_blank" rel="noopener">SHACL shapes</a>.</div>
""",
    },
    {
        "group": "check",
        "category": "docs",
        "anchor": "labels",
        "title": "Give every class and property a human-readable label",
        "toc_label": "Labels",
        "body": """\
  <p><span class="tag practice">TDCC guideline</span> Every class and
  property you define should carry a human-readable
  <a href="https://www.w3.org/TR/rdf-schema/#ch_label" target="_blank" rel="noopener"><code>rdfs:label</code></a>:
  a short name a person can read. RDFS defines what the property means but
  does not require any resource to have one; this guide recommends adding
  one to everything you define.</p>
  <pre>&lt;#hasMother&gt; a owl:ObjectProperty ;
    rdfs:label "has mother"@en ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range &lt;#Person&gt; .</pre>
  <div class="tip">Use language tags (<code>@en</code>, <code>@de</code>)
  to support multilingual ontologies. Consider
  <code>skos:prefLabel</code> and <code>skos:altLabel</code> for richer
  labelling.</div>
  <div class="tip">askwol uses <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/definition_documentation.ttl" target="_blank" rel="noopener">SHACL shapes</a> to check that each
  <em>internally defined</em> class and property has an
  <code>rdfs:label</code>. Reused external vocabulary terms, and terms you
  have marked deprecated yourself, are ignored. A missing label is reported
  as a <strong>recommendation</strong>.</div>
""",
    },
    {
        "group": "check",
        "category": "docs",
        "anchor": "comments",
        "title": "Give every class and property a clear description",
        "toc_label": "Comments",
        "body": """\
  <p><span class="tag practice">TDCC guideline</span> Every class and
  property you define should also carry an
  <a href="https://www.w3.org/TR/rdf-schema/#ch_comment" target="_blank" rel="noopener"><code>rdfs:comment</code></a>:
  a brief description of what it means. As with labels, RDFS defines the
  property but does not require you to use it; this guide recommends it for
  every term you define.</p>
  <pre>&lt;#hasMother&gt; a owl:ObjectProperty ;
    rdfs:label "has mother"@en ;
    rdfs:comment "Relates a person to their biological mother."@en ;
    rdfs:domain &lt;#Person&gt; ;
    rdfs:range &lt;#Person&gt; .</pre>
  <div class="tip">A good comment states the intended meaning and, where
  helpful, how the term should (and should not) be used.</div>
  <div class="tip">askwol uses <a href="https://raw.githubusercontent.com/TDCC-NES/askwol/refs/heads/main/src/askwol/shapes/definition_documentation.ttl" target="_blank" rel="noopener">SHACL shapes</a> to check that each
  <em>internally defined</em> class and property has an
  <code>rdfs:comment</code>. Reused external vocabulary terms, and terms you
  have marked deprecated yourself, are ignored. A missing comment is reported
  as a <strong>recommendation</strong>.</div>
  <div class="tip">An <strong>inverse property</strong>
  (<code>owl:inverseOf</code>) doesn&rsquo;t need its own comment when its
  partner already has one: the relationship is documented either way.</div>
""",
    },
    {
        "group": "check",
        "category": "docs",
        "anchor": "lang-tags",
        "title": "Use language tags consistently",
        "toc_label": "Language tag consistency",
        "body": """\
  <p><span class="tag spec">Spec</span> If your ontology includes
  human-readable labels and descriptions, tag every literal that carries
  natural-language text with a
  <a href="https://www.rfc-editor.org/info/bcp47" target="_blank" rel="noopener">BCP 47 language tag</a>
  (<code>@en</code>, <code>@nl</code>, <code>@de</code>, &hellip;),
  producing an RDF 1.1
  <a href="https://www.w3.org/TR/rdf11-concepts/#dfn-language-tagged-string" target="_blank" rel="noopener">language-tagged string</a>.</p>
  <pre>:Person a owl:Class ;
    rdfs:label "person"@en ,
               "persoon"@nl ;
    rdfs:comment "A human being."@en ,
                    "Een menselijk wezen."@nl .</pre>
  <h4 id="language-consistency-rules">Consistency rules</h4>
  <p><span class="tag practice">TDCC guideline</span> Neither RDF nor BCP 47
  requires every subject to carry the same set of languages; askwol checks
  for it anyway, because an inconsistency here is usually a missed
  translation, not a deliberate choice:</p>
  <ul>
    <li><strong>No bare strings next to tagged ones.</strong> If
    <code>rdfs:label</code> uses <code>@en</code> on most subjects but one
    subject has a plain <code>"My label"</code> without a tag, that&rsquo;s
    inconsistent.</li>
    <li><strong>Same language set everywhere.</strong> If you provide
    <code>@en</code> and <code>@nl</code> labels on most classes, every
    class should have both. A missing <code>@nl</code> on one subject
    is probably an oversight.</li>
    <li><strong>No tags used anywhere.</strong> If your ontology has labels
    or comments but none carry a language tag, askwol reports that too, as
    a recommendation: plain
    strings are valid RDF, but untagged text is harder to localise or filter
    by language. An ontology with no labels or comments at all isn&rsquo;t
    flagged: there is nothing to tag.</li>
  </ul>
  <div class="warn">If a literal has no language tag, SPARQL filters like
  <code>FILTER(LANG(?label) = "en")</code> won&rsquo;t match it. The triple
  is still in your data, but any app or query that filters by language will
  skip it, as if it doesn&rsquo;t exist.</div>
  <div class="tip">askwol checks
  <code>rdfs:label</code>, <code>rdfs:comment</code>,
  <code>skos:prefLabel</code>, <code>skos:definition</code>, and other
  standard annotation properties for tag consistency on terms defined in
  your own namespace. Reused external vocabulary terms, and terms you have
  marked deprecated yourself, are ignored.</div>
""",
    },
    {
        "group": "check",
        "category": "logic",
        "anchor": "reasoner",
        "title": "Check logical consistency",
        "toc_label": "Reasoner checks",
        "body": """\
  <p><span class="tag spec">Spec</span> OWL is a logical language.
  <a href="https://www.w3.org/TR/owl2-direct-semantics/" target="_blank" rel="noopener">OWL 2 Direct Semantics</a>
  formally defines when an ontology is consistent and when a class is
  satisfiable; a reasoner can derive consequences from your axioms and
  detect contradictions you didn&rsquo;t intend. askwol displays a summary
  and two types of logical finding in the
  <strong>Reasoner checks</strong> section of the report:</p>
  <ul>
    <li><strong>Logical findings</strong>: a summary of the selected
    contradiction and class-satisfiability checks. No detected findings
    does not establish consistency of the ontology as a whole.</li>
    <li><strong>Inconsistent individuals</strong>: specific named
    individuals that violate a class restriction (e.g. a <code>Person</code>
    with membership in two
    <code>owl:disjointWith</code> classes). Each offending individual is
    listed by IRI so you can locate the contradiction.</li>
    <li><strong>Unsatisfiable classes</strong>: classes whose definition is
    logically empty. A class is unsatisfiable when its definition forces it
    to be equivalent to <code>owl:Nothing</code> (e.g. via disjoint
    superclasses). The class is syntactically valid but can never have
    instances. This does not make the ontology as a whole inconsistent.</li>
  </ul>
  <p>A functional object property with two object IRIs may imply that
  they name the same individual. It is a contradiction only if the
  objects must be different. For a functional datatype property, two
  unequal data values contradict functionality. askwol does not check
  all these cases.</p>
  <p>Each inconsistent individual and each unsatisfiable class is reported
  as an <strong>error</strong>.</p>
  <div class="tip"><span class="tag practice">TDCC guideline</span> askwol
  runs a lightweight
  <a href="https://www.w3.org/TR/owl2-profiles/#OWL_2_RL" target="_blank" rel="noopener">OWL 2 RL</a>
  reasoner on the <strong>current ontology only</strong>; it does
  <em>not</em> follow <code>owl:imports</code>. This is an implementation
  tradeoff askwol makes, not a spec requirement: it catches the obvious
  self-contained contradictions without the cost of loading every imported
  vocabulary. For deeper checks (against imports, with HermiT or Pellet), use
  a desktop tool like Prot&eacute;g&eacute;.</div>
  <div class="warn">This is the only check that reasons, and only over its own
  private copy of the graph. Every other check, including
  <a href="#domains-ranges">Domains &amp; ranges</a>, runs on the ontology
  <strong>as asserted</strong>; reasoning first could change some of those
  results.</div>
""",
    },
    {
        "group": "practice",
        "anchor": "validate",
        "title": "Run askwol during development, not just before release",
        "toc_label": "Validate early and often",
        "body": """\
  <p>Run <a href="./">askwol</a> on your ontology during development, not just
  before release.</p>
  <div class="tip">Integrate validation into your CI pipeline:
  <code>askwol check my-ontology.ttl</code></div>
""",
    },
    {
        "group": "practice",
        "anchor": "server-config",
        "title": "",
        "toc_label": "Serving ontology files with content negotiation",
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
  <strong>document URL</strong> consistent. In the
  <a href="https://lod-4tu.tudelft.nl/ontologies/sample.ttl" target="_blank" rel="noopener">askwol sample ontology</a>,
  terms live under <code>https://lod-4tu.tudelft.nl/dataset#</code>, and
  dereferencing <code>https://lod-4tu.tudelft.nl/dataset</code> (no fragment)
  returns the ontology itself, directly or via redirect.</div>
  <div class="warn">Static file servers often default to <code>text/plain</code>
  for <code>.ttl</code>. Set the MIME type explicitly in your web server or
  reverse proxy, otherwise namespace resolution (including askwol&rsquo;s) fails.</div>
""",
    },
    {
        "group": "practice",
        "anchor": "documentation",
        "title": "Generate human-readable documentation",
        "toc_label": "Documentation",
        "body": """\
  <p>Good <code>rdfs:label</code> and <code>rdfs:comment</code> annotations pay
  off once turned into a browsable HTML page: a documentation generator reads
  your Turtle file and produces one, ready to serve alongside the RDF via
  <a href="#server-config">content negotiation</a>.</p>
  <p><strong><a href="https://github.com/RDFLib/pyLODE" target="_blank" rel="noopener">pyLODE</a></strong>
  is a lightweight Python tool: a single command turns a Turtle file into one
  static HTML page that needs no server or JavaScript to view
  (<a href="https://lod-4tu.tudelft.nl/pylode/sample.html" target="_blank" rel="noopener">example output</a>).</p>
  <pre>python3 -m venv .venv &amp;&amp; source .venv/bin/activate
python -m pip install pylode
pylode my-ontology.ttl -o my-ontology.html</pre>
  <p><strong><a href="https://github.com/dgarijo/Widoco" target="_blank" rel="noopener">WIDOCO</a></strong>
  is a Java-based documentation generator that produces a multi-page bundle:
  metadata extraction, an optional WebVOWL diagram, and a ready-to-deploy
  <code>.htaccess</code> for content negotiation.</p>
  <pre>java -jar widoco.jar -ontFile my-ontology.ttl -outFolder docs \\
    -getOntologyMetadata -rewriteAll -uniteSections -webVowl -htaccess</pre>
  <div class="tip">WIDOCO&rsquo;s WebVOWL view needs a web server to load; open the
  page over HTTP (<code>python3 -m http.server 8080</code>) rather than from the
  file system.</div>
  <p>For W3C specification-style output,
  <a href="https://respec.org/" target="_blank" rel="noopener">ReSpec</a> renders
  technical documents in the browser, and
  <a href="https://github.com/floresbakker/OntoReSpec" target="_blank" rel="noopener">OntoReSpec</a>
  generates the markup it needs from an RDF ontology or data model
  (<a href="https://floresbakker.github.io/htmlvoc/" target="_blank" rel="noopener">example</a>).
  OntoReSpec is early-stage, with no stable release yet.</p>
""",
    },
]


_GUIDE_NUMBERS = {
    section["anchor"]: GUIDE_CHECK_NUMBERS.get(section["anchor"], "")
    for section in GUIDE_SECTIONS
}


# Enforce alignment between CHECKS and GUIDE_SECTIONS at import time. If they
# ever drift (someone renames an anchor, reorders a section, etc.) the module
# fails to load and the failure is caught by the test suite. This is the
# architectural guarantee that the report and the guide stay in sync.
_GUIDE_CHECK_ANCHORS = [s["anchor"] for s in GUIDE_SECTIONS if s["group"] == "check"]
_CHECK_GUIDE_ANCHORS = [c["guide_anchor"] for c in CHECKS]
assert _CHECK_GUIDE_ANCHORS == _GUIDE_CHECK_ANCHORS, (
    "CHECKS and GUIDE_SECTIONS (group=check) must list the same anchors in "
    f"the same order. CHECKS guide_anchors={_CHECK_GUIDE_ANCHORS}, "
    f"GUIDE check anchors={_GUIDE_CHECK_ANCHORS}"
)

# The category assigned to each check must match between the report registry
# and the guide, so the clusters stay identical across surfaces.
_GUIDE_CHECK_CATEGORIES = [s.get("category") for s in GUIDE_SECTIONS if s["group"] == "check"]
_CHECK_CATEGORIES_LIST = [c["category"] for c in CHECKS]
assert _CHECK_CATEGORIES_LIST == _GUIDE_CHECK_CATEGORIES, (
    "CHECKS and GUIDE_SECTIONS (group=check) must assign the same category to "
    f"each check. CHECKS categories={_CHECK_CATEGORIES_LIST}, "
    f"GUIDE categories={_GUIDE_CHECK_CATEGORIES}"
)


def _md_to_html(text: str) -> str:
    """Render a tiny Markdown subset (`code` spans and *emphasis*) as HTML,
    escaping everything else. Lets a single CHECKS description double as
    Markdown (README.md, API docs) and HTML (the landing page)."""
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"`([^`]+)`|\*([^*]+)\*", text):
        out.append(escape(text[pos:m.start()], quote=False))
        if m.group(1) is not None:
            out.append(f"<code>{escape(m.group(1), quote=False)}</code>")
        else:
            out.append(f"<em>{escape(m.group(2), quote=False)}</em>")
        pos = m.end()
    out.append(escape(text[pos:], quote=False))
    return "".join(out)


def _render_checks_overview() -> str:
    """Render the landing page's "What do you get?" checks list from CHECKS.

    Single source with the report and the guide: grouping, numbering, and
    per-check text all come from CHECKS, so this list cannot drift from what
    askwol actually checks."""
    parts: list[str] = []
    current_cat = None
    for check in CHECKS:
        cat = check["category"]
        if cat != current_cat:
            if current_cat is not None:
                parts.append("  </ul>")
            label = next(c["label"] for c in CHECK_CATEGORIES if c["key"] == cat)
            parts.append(f'  <h3 class="cluster-h">{CLUSTER_NUMBERS[cat]}. {label}</h3>')
            parts.append('  <ul class="checks-list">')
            current_cat = cat
        num = _GUIDE_NUMBERS[check["guide_anchor"]]
        title = escape(check["title"], quote=False)
        desc = _md_to_html(check["description"])
        parts.append(
            f'    <li><span class="num">{num}</span> '
            f'<strong><a href="guide#{check["guide_anchor"]}">{title}</a></strong>: {desc}</li>'
        )
    parts.append("  </ul>")
    return "\n".join(parts)


UPLOAD_HTML = UPLOAD_HTML.replace("<!--CHECKS_OVERVIEW-->", _render_checks_overview())
UPLOAD_HTML = UPLOAD_HTML.replace("<!--ICONS-->", PAGE_ICON_LINKS)


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
        cnum = CLUSTER_NUMBERS[cat["key"]]
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
                    cnum = CLUSTER_NUMBERS[cat]
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

    def _permalink(match: re.Match) -> str:
        level, attrs, anchor, label = match.groups()
        accessible_label = escape(f"Link to {unescape(label)}", quote=True)
        return (
            f'<{level}{attrs}>{label} '
            f'<a class="heading-anchor" href="#{anchor}" aria-label="{accessible_label}">#</a>'
            f'</{level}>'
        )

    return re.sub(
        r'<(h[234])([^>]*\bid="([^"]+)"[^>]*)>(.*?)</\1>',
        _permalink,
        "\n".join(blocks),
    )


# Update only after reviewing the guide's technical content.
GUIDE_LAST_REVIEWED = date(2026, 10, 14)


GUIDE_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How to Publish an OWL Ontology | Ask Wol</title>
<link rel="canonical" href="https://lod-4tu.tudelft.nl/askwol/guide">
<meta name="description" content="A practical guide to publishing OWL ontologies: IRI strategy, http vs https, resolvable namespaces, external and internal term definitions, labels and comments, language tags, reasoner checks, and prefix hygiene.">
<meta name="keywords" content="OWL, ontology, RDF, Semantic Web, publishing guide, IRI strategy, SHACL, namespaces, language tags, OWL reasoner, best practices">
<meta name="author" content="TDCC-NES Ontology Engineers">
<meta name="robots" content="index, follow">
<meta name="theme-color" content="#4a7c59">
<meta property="og:type" content="article">
<meta property="og:site_name" content="askwol">
<meta property="og:title" content="Ask Wol: OWL publishing guide">
<meta property="og:description" content="A practical guide to publishing OWL ontologies: IRI strategy, resolvable namespaces, vocabulary reuse, documentation, language tags, and reasoner checks.">
<meta property="og:image" content="https://lod-4tu.tudelft.nl/askwol/static/wollie-og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Wollie, a hand-drawn owl">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Ask Wol: OWL publishing guide">
<meta name="twitter:description" content="A practical guide to publishing OWL ontologies: IRI strategy, resolvable namespaces, vocabulary reuse, documentation, language tags, and reasoner checks.">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "TechArticle",
  "headline": "How to Publish an OWL Ontology",
  "url": "https://lod-4tu.tudelft.nl/askwol/guide",
  "mainEntityOfPage": "https://lod-4tu.tudelft.nl/askwol/guide",
  "description": "A practical guide to publishing OWL ontologies: IRI strategy, http vs https, resolvable namespaces, external and internal term definitions, labels and comments, language tags, reasoner checks, and prefix hygiene.",
  "author": {{"@type": "Organization", "name": "TDCC-NES Ontology Engineers", "url": "https://tdcc.nl/nes/ontology-engineers/"}},
  "publisher": {{"@type": "Organization", "name": "TDCC-NES Ontology Engineers"}},
  "isPartOf": {{"@type": "WebApplication", "name": "askwol"}}
}}
</script>
{PAGE_ICON_LINKS}
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 50px auto; padding: 0 20px; color: #333; line-height: 1.7; }}
  h1 {{ margin: 0.4em 0 0.1em; display: flex; align-items: center; gap: 0.9rem; font-size: 1.9rem; font-weight: 600; letter-spacing: -0.01em; line-height: 1.2; }}
  h1 .logo {{ height: 3rem; width: auto; flex: none; }}
  h2 {{ color: #555; margin-top: 2em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }}
  h3, h4 {{ color: #666; margin-top: 1.5em; }}
  .cluster-band {{ color: #4a7c59; font-size: 0.82em; font-weight: 700; margin: 2.2em 0 0; padding-bottom: 0.2em; border-bottom: 2px solid #cfe0d5; letter-spacing: 0.06em; text-transform: uppercase; }}
  .check-heading {{ color: #333; font-size: 1.25em; font-weight: 600; margin-top: 1.8em; border: none; padding: 0; }}
  .heading-anchor {{ opacity: 0; margin-left: 0.3em; font-size: 0.85em; font-weight: 400; text-decoration: none; }}
  h2:hover .heading-anchor, h3:hover .heading-anchor, h4:hover .heading-anchor,
  h2:focus-within .heading-anchor, h3:focus-within .heading-anchor, h4:focus-within .heading-anchor {{ opacity: 1; }}
  .heading-anchor:focus-visible {{ outline: 2px solid currentColor; outline-offset: 2px; }}
  @media (hover: none) {{ .heading-anchor {{ opacity: 1; }} }}
  .section-lead {{ color: #555; font-size: 1.05em; font-style: italic; margin: 0.4em 0 1.1em; }}
  .byline {{ color: #555; font-size: 0.9em; }}
  a {{ color: #4a7c59; }}
  code {{ background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }}
  pre {{ background: #f7f7f7; padding: 1em; border-radius: 6px; overflow-x: auto; font-size: 0.88em; line-height: 1.5; }}
  .tip {{ background: #f0f7f2; border-left: 4px solid #4a7c59; padding: 0.8em 1em; margin: 1em 0; border-radius: 0 6px 6px 0; }}
  .warn {{ background: #fef9f0; border-left: 4px solid #d4a017; padding: 0.8em 1em; margin: 1em 0; border-radius: 0 6px 6px 0; }}
  .tag {{ display: inline-block; font-size: 0.72em; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; padding: 0.15em 0.5em; border-radius: 4px; margin-right: 0.4em; white-space: nowrap; }}
  .tag.spec {{ background: #e0e7ff; color: #3730a3; }}
  .tag.practice {{ background: #f3e8ff; color: #7e22ce; }}
  .legend {{ background: #f9fafb; border: 1px solid #eee; border-radius: 8px; padding: 0.8em 1.1em; margin: 1.2em 0; font-size: 0.92em; }}
  .legend p {{ margin: 0.6em 0; }}
  .legend .tip, .legend .warn {{ margin: 0.6em 0; }}
  .footer {{ margin-top: 2.5em; font-size: 0.85em; color: #aaa; text-align: center; }}
  .topnav {{ margin-bottom: 1em; font-size: 0.95em; color: #555; background: #f7f7f7; border: 1px solid #eee; border-radius: 8px; padding: 0.6em 0.9em; }}
  .toc {{ background: #f9f9f9; padding: 1em 1.5em; border-radius: 8px; margin: 1.5em 0; }}
  .toc ul {{ list-style: none; margin: 0.3em 0 0 0; padding-left: 0; }}
  .toc li {{ margin: 0.2em 0; }}
  .toc .group-label {{ display: block; margin-top: 0.8em; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.04em; color: #6b7280; font-weight: 600; }}
  .toc .group-label:first-child {{ margin-top: 0; }}
  .toc .cluster-label {{ display: block; margin: 0.7em 0 0.15em 0.2em; font-size: 0.98em; color: #4a7c59; font-weight: 700; }}
</style>
</head>
<body>
  <p class="topnav">
    <strong>Navigation:</strong>
    <a href="./">OWL ontology checker</a> &middot;
    <a href="guide">OWL ontology publishing guide</a> &middot;
    <a href="docs">API docs</a>
  </p>
  <h1><img class="logo" src="static/wollie-h1.png" alt="" width="43" height="56"><span>How to Publish an OWL Ontology</span></h1>
  <p>A practical checklist for building OWL ontologies that are
  interoperable, resolvable, and maintainable. These are the things
  <a href="./">askwol</a> checks, and why they matter.</p>
  <p class="byline">By the <a href="https://tdcc.nl/nes/ontology-engineers/">TDCC-NES Ontology Engineers</a>
  (Kathrin F&uuml;llenbach and Dani Metilli). Last reviewed:
  <time datetime="{GUIDE_LAST_REVIEWED.isoformat()}">{GUIDE_LAST_REVIEWED.day} {GUIDE_LAST_REVIEWED:%B %Y}</time>.</p>

  <div class="toc">
    <strong>Contents</strong>
{_render_guide_toc()}
  </div>

  <div class="tip">Want a worked example? The
  <a href="https://lod-4tu.tudelft.nl/ontologies/sample.ttl" target="_blank" rel="noopener">askwol sample ontology</a>
  applies every convention below and passes all checks. Load it from the
  <a href="./">home page</a> (the <strong>sample ontology</strong> button) to see a clean report.</div>

  <div class="legend">
  <p>Two tags mark where a rule comes from, and two colored boxes flag extra context:</p>
  <p><span class="tag spec">Spec</span> what an OWL, RDF, RDFS, or other
  W3C/IETF specification actually defines or requires.</p>
  <p><span class="tag practice">TDCC guideline</span> a recommendation from
  the TDCC ontology engineers that askwol checks for, but that goes beyond
  what any specification mandates. A W3C Note (such as Cool URIs, cited
  below) is informative, not normative, so guidance drawn from one counts as
  a TDCC guideline here too.</p>
  <div class="tip">A green box like this one is a tip or extra detail.</div>
  <div class="warn">An amber box like this one is a warning or common
  pitfall to watch out for.</div>
  <p>Every finding in an askwol report also carries one of three
  <strong>severity levels</strong>, so you can tell a logically broken
  ontology from an ontology that could be published better. The report
  counts individual findings, not checks: ten classes without a label are
  ten recommendations.</p>
  <p><strong>&#x2717; Error</strong> a formal logic or OWL 2 DL problem (for
  example an inconsistent individual, an unsatisfiable class, an
  unrecognised datatype, or a property whose domain or range is of the
  wrong kind). An unsatisfiable class does not make the ontology as a whole
  inconsistent, but nothing can be an instance of it.</p>
  <p><strong>&#x26A0; Warning</strong> a likely mistake or a serious
  interoperability problem (for example a namespace or import that does not
  resolve, a reused term that does not exist in its vocabulary, mixed
  <code>http</code>/<code>https</code> IRIs, or a term that is used but
  never defined).</p>
  <p><strong>&#x1F4A1; Recommendation</strong> ontology publishing best
  practice (for example ontology metadata, an open licence, labels and
  comments, or naming conventions).</p>
  </div>

{_render_guide_body()}

  <p class="footer">
    <strong>External links:</strong>
    <a href="https://tdcc.nl/nes/ontology-engineers/" target="_blank" rel="noopener">TDCC-NES ontology engineers</a> &middot;
    <a href="https://www.w3.org/OWL/" target="_blank" rel="noopener">W3C OWL</a> &middot;
    <a href="https://www.w3.org/TR/owl2-primer/" target="_blank" rel="noopener">OWL 2 Primer</a> &middot;
    <a href="https://www.w3.org/TR/owl2-syntax/" target="_blank" rel="noopener">OWL 2 Specification</a>
  </p>
</body>
</html>"""
