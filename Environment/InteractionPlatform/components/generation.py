from collections.abc import Callable

from rdflib import Graph

from components.profile import Profile


class Generation:

    def __init__(
        self,
        f: Callable[[Profile, Graph], set]):
        self.function = f

    def get_function(self) -> Callable[[Profile, Graph], set]:
        return self.function
