from rdflib import URIRef

from components.annotation import Annotation
from environment import Environment
from components.profile import Profile
from ontologies import HMAS
from registries.profile_registry import ProfileRegistry
from registries.annotation_registry import AnnotationRegistry

from pyshacl import validate


class Selection:

    def __init__(self, profile_registry: ProfileRegistry,
                 annotations_registry: AnnotationRegistry, env: Environment):
        self.profile_registry = profile_registry
        self.annotation_registry = annotations_registry
        self.env = env
        self._transformations = set()
        self._generations = set()

    @property
    def annotations(self):
        return set(self.annotation_registry.get_annotation_list()) #TODO: update

    @property
    def transformations(self):
        return self._transformations

    @property
    def generations(self):
        return self._generations

    @property
    def environment_kg(self):
        return self.env.get_state()

    def add_transformation(self, transformation):
        self._transformations.add(transformation)

    def add_generation(self, generation):
        self._generations.add(generation)

    def add_runtime_transformations(self, transformations, profile, environment_kg):
        """
        Preserve the runtime hook expected by app.py.

        Direct annotation/message resolution now passes an already prepared
        transformation list, so there is nothing to mutate here. Keeping this
        method avoids crashing those code paths with AttributeError.
        """
        return transformations

    def find(self, profile, environment_kg, annotations: set, generations, transformations): #TODO: check whether to use sets
        print("profile: ", profile)
        print("initial generations: ", generations)
        print("generations: ", generations)
        annotations.update(self.generate_annotations(profile, environment_kg, generations))
        annotations = self.filter_self_created(profile, annotations)
        annotation_list = list(annotations)
        for a in annotation_list:
            for t in transformations:
                annotation_t = t(profile, a)
                if annotation_t is not None and not self.is_self_created(profile, annotation_t):
                    print("annotation found")
                    annotations.add(annotation_t)
                    break
        print("number of annotations before environment filtering: ", len(annotations))
        annotations = self.filter_env(environment_kg, annotations)
        print("number of annotations after environment filtering: ", len(annotations))
        annotations = self.filter_ag(profile, annotations)
        annotations = self.filter_ag_env(profile, annotations)
        print("final number of annotations: ", len(annotations))
        return annotations

    def is_self_created(self, profile: Profile, annotation: Annotation) -> bool:
        profile_id = str(profile.id)
        creator_predicates = (HMAS.hasCreator, HMAS.HMAS.hasCreatorId)
        for predicate in creator_predicates:
            for creator in annotation.model.objects(annotation.url, predicate):
                if str(creator) == profile_id:
                    return True
        return False

    def filter_self_created(self, profile: Profile, annotations: set):
        return {a for a in annotations if not self.is_self_created(profile, a)}

    def filter_env(self, env_state, annotations: set):
        def _conforms(s):
            if not s.has_shacl_context():
                print("no SHACL context")
                return True
            print("check SHACL context")
            shacl_context_node, shacl_context = s.get_context()
            print("SHACL context: ", shacl_context.serialize(format="turtle"))
            conforms, results_graph, results_text = validate(env_state, shacl_graph=shacl_context)
            print("result graph: ", results_graph.serialize(format="turtle"))
            print("result of SHACL validation: ", results_text)
            return bool(conforms)

        return {a for a in annotations if _conforms(a)}

    def filter_ag(self, profile, annotations: set):
        new_annotations = {s for s in annotations if self.ability_match(profile, s)}
        new_annotations2 = {s for s in new_annotations if self.check_policy(profile, s)}
        return new_annotations2

    def filter_ag_env(self, profile, annotations: set):
        return annotations

    def check_context(self, env_state, annotation_list: list):
        for s in annotation_list:
            if s.has_shacl_context():
                shacl_context = s.get_context().model
                print("SHACL context: ", shacl_context.serialize(format="turtle"))
                #print("env state: ", self.env.get_state().serialize(format="turtle"))
                conforms, results_graph, results_text = validate(env_state, shacl_graph=shacl_context)
                print("result graph: ", results_graph.serialize(format="turtle"))
                print("result of SHACL validation: ", results_text)
                if not conforms:
                    annotation_list.remove(s)
        return annotation_list

    def check_ability(self, profile: Profile, annotation_list: list):
        for s in annotation_list:
            if self.ability_match(profile, s):
                    annotation_list.remove(s)
        return annotation_list

    def ability_filtering(self, profile: Profile, annotation_list: list):
        for s in annotation_list:
            if not self.ability_match(profile, s):
                annotation_list.remove(s)
        return annotation_list

    def check_policy(self, profile: Profile, annotation: Annotation):
        policies = profile.get_policy_per_type(HMAS.NoKnownAnnotation)
        if len(policies)==0:
            return True
        known_annotations = set()
        for po in policies:
            for (s, p, o) in profile.model.triples((po, HMAS.hasKnownAnnotation, None)):
                if isinstance(o, URIRef):
                    known_annotations.add(o)
        if annotation.url in known_annotations:
            return False
        else:
            return True





    def ability_match(self, profile: Profile, annotation: Annotation):
        b = True
        print("annotation: ", annotation)
        profile_abilities = profile.get_abilities()
        print("profile abilities: ", profile_abilities)
        annotation_abilities = annotation.get_abilities()
        print("annotation abilities: ", annotation_abilities)
        if len(profile_abilities) > 0 and len(annotation_abilities) > 0:
            for a in annotation_abilities:
                if a not in profile_abilities:
                    print("no ability match")
                    b = False
        elif len(profile_abilities)==0 and len(annotation_abilities)>0:
            print("profile has no ability but annotation requires ability")
            b = False
        return b



    def generate_annotations(self, profile: Profile, environment_kg, generations: list):
        s = set()
        for g in generations:
            print("type of generation: ", type(g))
            generated_s = g(profile, environment_kg)
            s.add(frozenset(generated_s))
        return_s = set().union(*s)
        return return_s



    @transformations.setter
    def transformations(self, value):
        self._transformations = value

    @generations.setter
    def generations(self, value):
        self._generations = value
