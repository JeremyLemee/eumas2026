
from rdflib import Graph, URIRef, RDF, BNode

from components.annotation import Annotation
from ontologies import HMAS


class Signifier(Annotation):

    def __init__(self, url: URIRef, model: Graph):
        super().__init__(url, model)
        self._model.add((self._url, RDF.type, HMAS.Signifier))


    def behavior_node(self):
        b = self.model.value(self._url, HMAS.signifies, None)
        return b

    def behavior_types(self):
        behavior_types = []
        b = None
        for (s, p, o) in self.model.triples((None, HMAS.signifies, None)):
            b = o
        if b is not None and (isinstance(b, URIRef) or isinstance(b, BNode)):
            for (s1, p1, o1) in self.model.triples((b, RDF.type, None)):
                behavior_types.append(o1)
        return behavior_types


    @staticmethod
    def parse_signifier(model: Graph):
        url = None
        for (s, p, o) in model.triples((None, RDF.type, HMAS.Signifier)):
            url = s
        if isinstance(url, URIRef):
            return Signifier(url, model)
        else:
            return None

