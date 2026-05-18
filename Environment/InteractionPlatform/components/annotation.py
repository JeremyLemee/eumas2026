import json
from typing import Union

from rdflib import Graph, URIRef, IdentifiedNode, RDF, BNode, Node

from ontologies import HMAS

class Annotation:

    def __init__(self, url: URIRef, model: Graph):
        self._url = url
        self._model = model
        self._model.add((self._url, RDF.type, HMAS.Annotation))



    @property
    def model(self):
        return self._model

    @property
    def url(self):
        return self._url

    @model.setter
    def model(self, value):
        self._model = value

    @url.setter
    def url(self, value):
        self._url = value

    def add_triple(self, subject: IdentifiedNode, predicate, value):
        self.model.add((subject, predicate, value))

    def add_model(self, m: Graph):
        self.model += m

    def add_graph(self, graph: Graph):
        self._model += graph

    def __str__(self):
        return str(self.model.serialize(format="turtle"))

    def to_json_ld_dict(self):
        return json.loads(self.model.serialize(format="json-ld"))

    def get_ability(self):
        ability = None
        ability_triples = self.model.triples((self.url, HMAS.recommendsAbility, None))
        for (s, p, o) in ability_triples:
            ability_r = o
            t = self.model.triples((ability_r, RDF.type, None))
            for (s1, p1, o1) in t:
                ability = o1
        return ability

    def get_abilities(self):
        abilities = []
        ability_triples = self.model.triples((self.url, HMAS.recommendsAbility, None))
        for (s, p, o) in ability_triples:
            ability_r = o
            t = self.model.triples((ability_r, RDF.type, None))
            for (s1, p1, o1) in t:
                abilities.append(o1)
        return abilities

    def add_ability(self, ability: URIRef):
        ability_node = BNode()
        self._model.add((self.url, HMAS.recommendsAbility, ability_node))
        self._model.add((ability_node, RDF.type, ability))

    def remove_abilities(self):
        for (s, p, o) in self._model.triples((self.url, HMAS.recommendsAbility, None)):
            for t in self._model.triples((o, RDF.type, None)):
                self._model.remove(t)
            self._model.remove((s, p, o))

    def has_shacl_context(self):
        print("check has shacl context for signifier: ", self)
        context_url = None
        for (s, p, o) in self._model.triples((self.url, HMAS.recommendsContext, None)):
            context_url = o
        if context_url is None:
            return False
        else:
            has_node_type = False
            for (s1, p1, o1) in self._model.triples((context_url, RDF.type, None)):
                if o1 == URIRef("http://www.w3.org/ns/shacl#NodeShape"):
                    has_node_type = True
            return has_node_type

    def get_context(self):
        context_node = None
        for (s, p, o) in self._model.triples((self.url, HMAS.recommendsContext, None)):
            context_node = o
        if context_node is not None:
            return context_node, self.extract_subgraph(context_node, self._model)
        else:
            return None

    def extract_subgraph(self, start: Union[str, URIRef, BNode, Node], source_graph: Graph) -> Graph:
        """
        Return a new Graph containing every triple reachable from `start`
        by following outgoing predicates recursively in `source_graph`.

        :param start:     The URI (as string or URIRef) to start from.
        :param source_graph: The rdflib.Graph to traverse.
        :return:          A new Graph with the extracted subgraph.
        """
        start_node = start
        result = Graph()
        visited = set()

        def recurse(node: Node):
            if node in visited:
                return
            visited.add(node)
            for s, p, o in source_graph.triples((node, None, None)):
                result.add((s, p, o))
                if isinstance(o, Node):
                    recurse(o)

        recurse(start_node)
        return result

    def information_node(self):
        b = self.model.value(self._url, HMAS.conveys, None)
        if b is None:
            b = self.model.value(self._url, HMAS.signifies, None)
        return b

    def information_types(self):
        info_types = []
        b = None
        b = self.information_node()
        if b is not None and (isinstance(b, URIRef) or isinstance(b, BNode)):
            for (s1, p1, o1) in self.model.triples((b, RDF.type, None)):
                info_types.append(o1)
        return info_types

    @staticmethod
    def parse_annotation(model: Graph):
        url = None
        for (s, p, o) in model.triples((None, RDF.type, HMAS.Annotation)):
            url = s
        if url is None:
            for (s, p, o) in model.triples((None, RDF.type, HMAS.Signifier)):
                url = s
        if url is not None and isinstance(url, URIRef):
            return Annotation(url, model)
        else:
            return None

    @staticmethod
    def parse_all_annotation(model: Graph):
        # Collect unique subject URIs that are either Annotation or Signifier
        subjects = set()

        for s in model.subjects(RDF.type, HMAS.Annotation):
            if isinstance(s, URIRef):
                subjects.add(s)

        for s in model.subjects(RDF.type, HMAS.Signifier):
            if isinstance(s, URIRef):
                subjects.add(s)

        # Create one Annotation per unique subject
        return [Annotation(s, model) for s in subjects]

