from components.profile import Profile
import requests
from rdflib import Graph



class ProfileRegistry:

    def __init__(self):
        self.profiles = {}

    def is_valid(self, profile):
        return True  # TODO: Update

    def add_profile(self, name, profile: Profile):
        if self.is_valid(profile):
            self.profiles[name] = {"type": "local", "profile": profile}
            return True
        else:
            return False

    def add_profile_from_url(self, name: str, profile_url: str):
        self.profiles[name] = {"type": "external", "profile": profile_url}

    def update_profile(self, name, p: Profile):
        self.profiles[name] = {"type": "local", "profile": p}

    def get_profile(self, name):
        j = self.profiles[name]
        if j["type"] == "external":
            g = Graph()
            response = requests.get(j["profile"], timeout=10)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            parse_formats = []
            if content_type == "application/ld+json":
                parse_formats.append("json-ld")
            elif content_type in {"text/turtle", "application/x-turtle"}:
                parse_formats.append("turtle")
            elif content_type in {"application/rdf+xml", "text/xml"}:
                parse_formats.append("xml")

            parse_formats.extend(["json-ld", "turtle", "xml"])
            attempted = set()
            for rdf_format in parse_formats:
                if rdf_format in attempted:
                    continue
                attempted.add(rdf_format)
                try:
                    g.parse(data=response.text, format=rdf_format, publicID=j["profile"])
                    p: Profile = Profile.parse_profile(g)
                    if p is not None:
                        return p
                except Exception:
                    continue
            return None
        else:
            return j["profile"]

    def __iter__(self):
        return iter(self.profiles.items())

    def available_profiles(self):
        return self.profiles.keys()
