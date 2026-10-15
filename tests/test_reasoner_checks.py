import pytest
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS

from askwol.models import Status, ValidationReport
from askwol.reasoner_checks import run_reasoner_checks
from askwol.report import report_as_markdown

EX = Namespace("https://example.org/ont#")


def test_no_findings_do_not_establish_consistency():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Person, RDF.type, OWL.Class))
    g.add((EX.Person, RDFS.label, Literal("Person", lang="en")))

    report = run_reasoner_checks(g)

    assert report.consistent is None
    assert report.unsatisfiable_classes == []
    assert any(c.key == "ontology_consistency" and c.status == Status.OK for c in report.checks)

    keys = [c.key for c in report.checks]
    assert keys == ["ontology_consistency", "inconsistent_individuals", "unsatisfiable_classes"]
    assert all(c.status == Status.OK for c in report.checks)
    assert report.inconsistent_individuals == []


def test_all_three_facets_always_present_when_unsatisfiable_class_only():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Cat, RDF.type, OWL.Class))
    g.add((EX.Dog, RDF.type, OWL.Class))
    g.add((EX.Cat, OWL.disjointWith, EX.Dog))
    g.add((EX.ImpossiblePet, RDF.type, OWL.Class))
    g.add((EX.ImpossiblePet, RDFS.subClassOf, EX.Cat))
    g.add((EX.ImpossiblePet, RDFS.subClassOf, EX.Dog))

    report = run_reasoner_checks(g)

    keys = {c.key: c.status for c in report.checks}
    assert {"ontology_consistency", "inconsistent_individuals", "unsatisfiable_classes"} <= set(keys)
    assert keys["inconsistent_individuals"] == Status.OK
    assert keys["unsatisfiable_classes"] == Status.WARN
    assert keys["ontology_consistency"] == Status.WARN

    assert "https://example.org/ont#ImpossiblePet" in report.unsatisfiable_classes
    assert any(c.key.startswith("unsatisfiable_class") and c.status == Status.WARN for c in report.checks)
    assert report.consistent is None


def test_disjoint_types_make_individual_inconsistent():
    g = Graph()
    g.add((EX.ontology, RDF.type, OWL.Ontology))
    g.add((EX.Cat, RDF.type, OWL.Class))
    g.add((EX.Dog, RDF.type, OWL.Class))
    g.add((EX.Cat, OWL.disjointWith, EX.Dog))
    g.add((EX.Fido, RDF.type, EX.Cat))
    g.add((EX.Fido, RDF.type, EX.Dog))

    report = run_reasoner_checks(g)

    assert report.consistent is False
    assert any("Fido" in item for item in report.inconsistent_individuals)
    assert any(c.key.startswith("inconsistent_individual") and c.status == Status.FAIL for c in report.checks)

    full = ValidationReport(file="example.ttl")
    full.reasoner = report

    md = report_as_markdown(full)
    assert "## Reasoner checks" in md
    assert "Logical findings" in md


def _graph(axioms: str) -> Graph:
    return Graph().parse(
        data="""
            @prefix : <https://example.org/ont#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            : a owl:Ontology .
        """ + axioms,
        format="turtle",
    )


def test_self_disjoint_classes_and_their_subclasses_are_unsatisfiable():
    graph = _graph("""
        :A a owl:Class ; owl:disjointWith :A .
        :B a owl:Class ; rdfs:subClassOf :A .
        :C a owl:Class ; rdfs:subClassOf :B .
    """)
    original_triples = set(graph)

    report = run_reasoner_checks(graph)

    assert report.unsatisfiable_classes == [str(EX.A), str(EX.B), str(EX.C)]
    assert report.inconsistent_individuals == []
    assert report.consistent is None
    assert set(graph) == original_triples


def test_self_disjoint_membership_includes_inherited_types():
    report = run_reasoner_checks(_graph("""
        :A a owl:Class ; owl:disjointWith :A .
        :B a owl:Class ; rdfs:subClassOf :A .
        :direct a :A .
        :inherited a :B .
    """))

    assert report.inconsistent_individuals == [str(EX.direct), str(EX.inherited)]
    assert report.consistent is False


@pytest.mark.parametrize("axioms", [
    ":x a owl:Nothing .",
    ":A a owl:Class ; rdfs:subClassOf owl:Nothing . :x a :A .",
    """
        :A a owl:Class ; rdfs:subClassOf :B .
        :B a owl:Class ; rdfs:subClassOf owl:Nothing .
        :x a :A .
    """,
])
def test_named_membership_in_nothing_is_a_contradiction(axioms):
    report = run_reasoner_checks(_graph(axioms))

    assert report.inconsistent_individuals == [str(EX.x)]
    assert report.consistent is False
    assert str(OWL.Nothing) not in report.unsatisfiable_classes


@pytest.mark.parametrize(("individual", "declaration"), [
    ("<https://external.example/person>", ""),
    (":punnedClass", ":punnedClass a owl:Class ."),
    (":punnedProperty", ":punnedProperty a owl:ObjectProperty ."),
])
def test_named_disjoint_memberships_are_not_hidden_by_iri_or_schema_role(individual, declaration):
    report = run_reasoner_checks(_graph(f"""
        :A a owl:Class ; owl:disjointWith :B .
        :B a owl:Class .
        {declaration}
        {individual} a :A, :B .
    """))
    iri = individual.strip("<>") if individual.startswith("<") else str(EX[individual[1:]])

    assert report.inconsistent_individuals == [iri]
    assert report.consistent is False


def test_separate_disjoint_branches_and_schema_declarations_are_not_contradictions():
    report = run_reasoner_checks(_graph("""
        :A a owl:Class ; owl:disjointWith :B .
        :B a owl:Class .
        :C a owl:Class ; rdfs:subClassOf :A .
        :D a owl:Class ; rdfs:subClassOf :B .
        :p a owl:ObjectProperty ; rdfs:domain :C ; rdfs:range :D .
        :x :p :y .
        :punned a owl:Class, :C .
    """))

    assert report.inconsistent_individuals == []
    assert report.unsatisfiable_classes == []
    assert report.consistent is None


def test_unchecked_contradictions_do_not_expand_the_selected_reasoning_checks():
    report = run_reasoner_checks(_graph(":x owl:sameAs :y ; owl:differentFrom :y ."))

    assert report.inconsistent_individuals == []
    assert report.unsatisfiable_classes == []
    assert report.consistent is None
