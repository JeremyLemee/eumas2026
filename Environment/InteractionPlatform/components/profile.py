from rdflib import IdentifiedNode, URIRef, Graph, RDF, BNode

from ontologies import HMAS


class Profile:

    def __init__(self, identifier: URIRef, model: Graph):
        self._id = identifier
        self._model = model
        self._model.add((self._id, RDF.type, HMAS.Agent)) #TODO: check

    @property
    def id(self):
        return self._id

    @property
    def model(self):
        return self._model

    def add_triple(self, subject: IdentifiedNode, predicate, value):
        self.model.add((subject, predicate, value))

    def __str__(self):
        return str(self.model.serialize(format="turtle"))

    def get_ability(self):
        ability = None
        ability_triples = self.model.triples((self.id, HMAS.hasAbility, None))
        for (s, p, o) in ability_triples:
            ability_r = o
            t = self.model.triples((ability_r, RDF.type, None))
            for (s1, p1, o1) in t:
                ability = o1
        return ability

    def get_abilities(self):
        ability_list = []
        ability_triples = self.model.triples((self.id, HMAS.hasAbility, None))
        for (s, p, o) in ability_triples:
            ability_r = o
            t = self.model.triples((ability_r, RDF.type, None))
            for (s1, p1, o1) in t:
                ability_list.append(o1)
        return ability_list

    def add_ability(self, ability):
        ability_id = BNode()
        self.add_triple(self.id, HMAS.hasAbility, ability_id)
        self.add_triple(ability_id, RDF.type, ability)

    def contains_ability(self, ability):
        b = False
        print("abilities: ", self.get_abilities())
        if ability in self.get_abilities():
            b = True
        return b

    def get_goal_id(self):
        goal_id = None
        for (s, p, o) in self.model.triples((self.id, HMAS.hasGoal, None)):
            goal_id = o
        return goal_id

    def has_goal(self):
        return any(self._model.triples((self.id, HMAS.hasGoal, None)))

    def remove_goal(self):  # TODO: improve with recursivity
        for (s, p, o) in self._model.triples((self.id, HMAS.hasGoal, None)):
            self._model.remove((s, p, o))

    def get_policy_per_type(self, policy_type):
        policies = []
        policy_nodes = set(self.model.objects(self.id, HMAS.hasAnnotationPolicy))
        policy_nodes.update(self.model.objects(self.id, HMAS.hasInteractionPolicy))
        policy_nodes.update(self.model.objects(self.id, HMAS.hasRecurrentPolicy))

        for o in policy_nodes:
            if isinstance(o, URIRef) or isinstance(o, BNode):
                for (s2, p2, o2) in self.model.triples((o, RDF.type, None)):
                    if o2 == policy_type:
                        policies.append(o)
        return policies

    def add_policy(self, policy_type):
        p = BNode()
        self.model.add((self.id, HMAS.hasAnnotationPolicy, p))
        self.model.add((p, RDF.type, policy_type))
        return p


    @staticmethod
    def parse_profile(g: Graph):
        p_id = None
        for (s, p, o) in g.triples((None, RDF.type, HMAS.Agent)):  # TODO: check or update
            p_id = s
        if p_id is not None and isinstance(p_id, URIRef):
            profile = Profile(p_id, g)
            return profile
        else:
            return None
