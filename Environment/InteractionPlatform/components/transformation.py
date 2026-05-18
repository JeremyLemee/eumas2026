from typing import Protocol

from rdflib import Graph, URIRef

from components.profile import Profile


class TransformationInput(Protocol):
    @property
    def model(self) -> Graph: ...

    @property
    def url(self) -> URIRef: ...


class Transformation:

    def __init__(self, f=lambda x, y: y):
        self.function = f

    def is_applicable(self, profile: Profile, input_resource: TransformationInput):
        return self.function(profile, input_resource) is not None

    def transform(self, profile: Profile, input_resource: TransformationInput):
        return self.function(profile, input_resource)

    def get_function(self):
        return self.function
