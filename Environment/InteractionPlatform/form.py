from typing import Callable, Dict, Any

from form_template import FormTemplate


class Form:
    def __init__(self, name: str, agent_type: str, form_type: str, form_template: FormTemplate, form: Dict[str, Any] = None):
        self.name = name
        self.agent_type = agent_type
        self.form_type = form_type
        self.form_template = form_template
        self.form = form if form is not None else {}
        self.forms = {"main": {}}
        self.current_step = form_template.initial_step

    def add_key_value_to_form(self, key: str, value: Any):
        self.form[key] = value

    def add_key_value_to_forms(self, form: str, key: str, value: Any):
        if form not in self.forms:
            self.forms[form] = {}
        self.forms[form][key] = value

    def add_form_as_value(self, form1: str, key: str, form2: Dict[str, Any]):
        if form1 not in self.forms:
            self.forms[form1] = {}
        self.forms[form1][key] = form2

    def add_value_to_list(self, list_form: str, value: Any):
        if list_form not in self.forms:
            self.forms[list_form] = []
        if isinstance(self.forms[list_form], list):
            self.forms[list_form].append(value)

    def add_form_to_list(self, list_form: str, form: str):
        if list_form not in self.forms:
            self.forms[list_form] = []
        if isinstance(self.forms[list_form], list):
            self.forms[list_form].append(self.forms[form])

    def fill_form(self, user_input: Any) -> str:
        operation = self.form_template.get_operation(self.current_step)
        next_step = operation(self, user_input)
        return next_step
