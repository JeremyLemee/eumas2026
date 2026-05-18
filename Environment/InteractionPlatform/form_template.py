from typing import Callable, Dict, Any

#from form import Form


class FormTemplate:
    def __init__(self, name: str, template: Dict[str, Callable[[Any, Any], str]], initial_step: str):
        self._name = name
        self._template = template
        self._initial_step = initial_step

    @property
    def name(self) -> str:
        return self._name

    @property
    def template(self) -> Dict[str, Callable[[Any, Any], str]]:
        return self._template

    @property
    def initial_step(self) -> str:
        return self._initial_step

    def get_operation(self, step: str) -> Callable[[Any, Any], str]:
        if step not in self._template:
            raise ValueError(f"Step '{step}' is not defined in the template")
        return self._template[step]