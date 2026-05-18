import re
import uuid
from typing import Union, Any

from rdflib import Graph, Namespace, RDF
from rdflib.term import Node, URIRef, BNode, Literal
from rdflib.collection import Collection

from config_loader import load_config
from ontologies import BDIOnt, HMAS, LabOnt, SoarOnt, LLMOnt
from components.signifier import Signifier

#devices = {"B1": True, "B2": True, "L1": True, "L2": True}

SPARQL_NAMESPACES = {
    "rdf": RDF,
    "hmas": HMAS.HMAS,
    "lab": LabOnt.LabN,
    "soar": SoarOnt.SoarN,
    "bdi": BDIOnt.BDI,
    "llm": LLMOnt.LLMN,
}


def common_bindings(graph: Graph):
    graph.bind("hmas", Namespace("https://ci.mines-stetienne.fr/hmas/core#"))
    graph.bind("hint", Namespace("https://ci.mines-stetienne.fr/hmas/interaction#"))
    return graph


def _normalize_uri_node(value: Any) -> URIRef | None:
    lexical = str(value).strip()
    if not lexical:
        return None
    return URIRef(lexical)

def _construct_graph(query: str, bindings=None) -> Graph:
    graph = Graph()
    for triple in Graph().query(query, initBindings=bindings or {}, initNs=SPARQL_NAMESPACES):
        graph.add(triple)
    return graph



def get_signifier_list(graph: Graph):
    signifier_list = []
    for s, p, o in graph.triples((None, RDF.type, HMAS.Signifier)):
        if isinstance(s, URIRef):
            subgraph = extract_subgraph(s, graph)
            signifier = Signifier(s, subgraph) #TODO: check, code has been updated here
            signifier_list.append(signifier)
    return signifier_list


def generate_id():
    return str(uuid.uuid4())


def generate_url():
    return annotations_url_from_id(generate_id())


def annotations_url_from_id(sig_id: str):
    config = load_config()
    sig_url = config["annotations_url"]
    return URIRef(sig_url+ sig_id)


def get_state_from_relations(blocks, relations):
    state = []
    for b in blocks:
        pos = 0
        for r in relations:
            r0 = str(r[0])
            r1 = str(r[1])
            if r0 == b and r1 != 'table':
                pos = 1 + blocks.index(r1)
        state.append(pos)
    return state


def collect_node_triples(source_graph: Graph, node, target_graph: Graph, visited=None):
    """
    Recursively collects all triples associated with a node in a graph.
    
    Args:
        source_graph: The source graph containing all triples
        node: The node to collect triples for
        target_graph: The graph to add the collected triples to
        visited: Set of already visited nodes to prevent infinite recursion
    """
    if visited is None:
        visited = set()
    
    if node in visited:
        return
    
    visited.add(node)
    
    # Add all triples where node is subject
    for s, p, o in source_graph.triples((node, None, None)):
        target_graph.add((s, p, o))
        if isinstance(o, (BNode, URIRef)):
            collect_node_triples(source_graph, o, target_graph, visited)
    
    # Add all triples where node is object
    for s, p, o in source_graph.triples((None, None, node)):
        target_graph.add((s, p, o))
        if isinstance(s, (BNode, URIRef)):
            collect_node_triples(source_graph, s, target_graph, visited)


def extract_subgraph(start: Union[Node], source_graph: Graph) -> Graph:
    """
    Return a new Graph containing every triple reachable from `start`
    by following outgoing predicates recursively in `source_graph`.

    :param start:     The URI (as string or URIRef) to start from.
    :param source_graph: The rdflib.Graph to traverse.
    :return:          A new Graph with the extracted subgraph.
    """
    print("extract subgraph")
    start_node = start
    result = Graph()
    visited = set()

    def recurse(node: Node):
        print("recurse")
        if node in visited:
            return
        visited.add(node)
        for s, p, o in source_graph.triples((node, None, None)):
            result.add((s, p, o))
            if isinstance(o, Node):
                recurse(o)

    recurse(start_node)
    return result


def create_rdf_list1(g, elements):
    """"Create an RDF list from a Python list of lists and add it into the graph `g`."""
    if not elements:
        return RDF.nil  # Empty list

    head = BNode()
    current = head

    for e in elements:
        subnode = BNode()
        g.add((current, RDF.first, Literal(e)))
        g.add((current, RDF.rest, subnode))
        current = subnode
    return head

def create_rdf_list(g, elements):
    head = BNode()
    # Map Python scalars to Literals once
    terms = [e if hasattr(e, 'n3') else Literal(e) for e in elements]
    Collection(g, head, terms)
    return head


def _build_predicate_statement(graph: Graph, predicate: str, values: list) -> BNode:
    statement_node = BNode()
    values_head = BNode()
    graph.add((statement_node, BDIOnt.hasPredicate, Literal(predicate)))
    Collection(graph, values_head, values)
    graph.add((statement_node, BDIOnt.hasValues, values_head))
    return statement_node
