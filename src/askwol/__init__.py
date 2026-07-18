"""askwol  -  OWL ontology checker for namespace resolution and term existence."""

import xml.sax

import defusedxml
import defusedxml.expatreader

# Ontology files are untrusted input (uploaded or fetched from arbitrary
# URLs) and rdflib's RDF/XML parser uses Python's stdlib xml.sax without
# hardening it against XML entity-expansion ("billion laughs") denial of
# service. Defuse the stdlib XML parsers globally, once, before any RDF
# parsing can happen.
defusedxml.defuse_stdlib()

# defuse_stdlib()'s default also forbids *any* <!ENTITY> declaration, even
# harmless internal ones used purely as string macros for long namespace
# URIs - a common, legitimate pattern in real-world RDF/XML ontologies (e.g.
# the W3C Wine ontology). That's not itself a vulnerability: expat >= 2.4.0
# already refuses runaway entity expansion ("billion laughs") via its own
# built-in amplification-factor limit, regardless of this flag. Re-patch
# make_parser to allow entity declarations while still forbidding external
# entity resolution (forbid_external=True), which is the actual XXE vector.
def _make_parser(*_args, **_kwargs):
    return defusedxml.expatreader.create_parser(forbid_entities=False)


xml.sax.make_parser = _make_parser
