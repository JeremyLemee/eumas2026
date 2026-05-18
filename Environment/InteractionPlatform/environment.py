from rdflib import Graph
import requests


class Environment:

    def __init__(self, url):
        self._url = url

    @property
    def url(self):
        return self._url

    def get_state(self):
        kg = Graph()
        r = requests.get(str(self._url))
        print("status code from environment request: ", r.status_code)
        print("response from environment request: ", r.text)
        kg.parse(str(self._url)) #TODO: check
        return kg
