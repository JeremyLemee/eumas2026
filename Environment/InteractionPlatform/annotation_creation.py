import time

from rdflib import URIRef, Graph, BNode, RDF, Literal, XSD
from rdflib.collection import Collection
from rdflib.term import Node

from components.annotation import Annotation
from ontologies import HMAS, SoarOnt, LabOnt, LLMOnt, BDIOnt
from ontologies.HMAS import recommendsAbility, hasId
from ontologies.LLMOnt import llm_ability, text_action
from components.signifier import Signifier
from utils import generate_id, annotations_url_from_id


def create_llm_annotation(identifier: str) -> Annotation:
    url = annotations_url_from_id(identifier)
    a = Annotation(url, Graph())
    llm_ability_node = BNode()
    a.add_triple(a.url, recommendsAbility, llm_ability_node)
    a.add_triple(a.url, hasId, Literal(generate_id()))
    a.add_triple(llm_ability_node, RDF.type, llm_ability)
    return a


def add_text_action(annotation: Annotation, text: str):
    action = BNode()
    annotation.add_triple(annotation.url, HMAS.conveys, action)
    annotation.add_triple(action, RDF.type, LLMOnt.llm_action)
    annotation.add_triple(action, text_action , Literal(text))


def add_ability(s: Signifier, ability: URIRef):
    ability_node = BNode()
    s.add_triple(s.url, recommendsAbility, ability_node)
    s.add_triple(ability_node, RDF.type, ability)


def add_type(s: Signifier, sig_type: URIRef):
    s.add_triple(s.url, RDF.type, sig_type)


def convert_list_to_rdf_list(l):
    # Create a new RDF graph
    graph = Graph()

    # Create a blank node to represent the head of the RDF list
    list_node = BNode()

    # Create an RDF collection
    collection = Collection(graph, list_node)

    # Add each string as a Literal to the RDF list
    for e in l:
        collection.append(Literal(e))

    return graph, list_node


def create_predicate_signifier(identifier: str, predicate: str, params: list):
    predicate_ability = BNode()
    url = annotations_url_from_id(identifier)
    s = Annotation(url, Graph())
    s.add_triple(s.url, recommendsAbility, predicate_ability)
    s.add_triple(predicate_ability, RDF.type, BDIOnt.predicate_ability)
    action_id = BNode()
    s.add_triple(s.url, HMAS.conveys, action_id)
    s.add_triple(action_id, BDIOnt.hasPredicate, Literal(predicate))
    g, l_id = convert_list_to_rdf_list(params)
    s.add_triple(action_id, BDIOnt.hasValues, l_id)
    s.add_graph(g)
    return s


def create_schema(identifier: Node, schema: dict):
    g = Graph()
    g.add((identifier, RDF.type, URIRef("https://www.w3.org/2019/wot/json-schema#ObjectSchema")))
    for e in schema:
        p = BNode()
        g.add((identifier, URIRef("https://www.w3.org/2019/wot/json-schema#properties"), p))
        g.add((p, URIRef("https://www.w3.org/2019/wot/json-schema#propertyName"), Literal(e)))
        g.add((p, RDF.type, URIRef(schema[e])))
    return g


def create_form(identifier: Node, target_url: str, schema: dict):
    g = Graph()
    g.add((identifier, URIRef("https://www.w3.org/2019/wot/hypermedia#hasTarget"), URIRef(target_url)))
    g.add((identifier, URIRef("https://www.w3.org/2019/wot/hypermedia#forContentType"), Literal("application/json")))
    schema_id = BNode()
    g.add((identifier, HMAS.expects, schema_id))
    g += create_schema(schema_id, schema)
    return g


def create_action_specification(identifier: Node, target_url: str, schema: dict):
    g = Graph()
    g.add((identifier, RDF.type, HMAS.ActionSpecification))
    form_id = BNode()
    g.add((identifier, HMAS.hasForm, form_id))
    g += create_form(form_id, target_url, schema)
    return g


def create_http_json_signifier(identifier: str, target_url: str, schema: dict):
    url = annotations_url_from_id(identifier)
    s = Annotation(url, Graph())
    action = BNode()
    s.add_triple(s.url, HMAS.conveys, action)
    s.add_model(create_action_specification(action, target_url, schema))
    return s



def add_soar_element(s, b, idx, first, second):
    e = BNode()
    s.add_triple(b, SoarOnt.hasElement, e)
    s.add_triple(e, SoarOnt.idx, Literal(idx))
    s.add_triple(e, SoarOnt.first, Literal(first))
    s.add_triple(e, SoarOnt.second, Literal(second))








