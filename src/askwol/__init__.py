"""askwol  -  OWL ontology checker for namespace resolution and term existence."""

import defusedxml

# Ontology files are untrusted input (uploaded or fetched from arbitrary
# URLs) and rdflib's RDF/XML parser uses Python's stdlib xml.sax without
# hardening it against XML entity-expansion ("billion laughs") denial of
# service. Defuse the stdlib XML parsers globally, once, before any RDF
# parsing can happen.
defusedxml.defuse_stdlib()
