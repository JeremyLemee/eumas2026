from form import Form


class FormRegistry:

    def __init__(self):
        self.forms = {}

    def add_form(self, form: Form):
        self.forms[form.name] = form

    def get_form_by_id(self, name):
        return self.forms[name]
