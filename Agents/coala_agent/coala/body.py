from threading import Thread
from typing import Optional

from flask import Flask, Response, jsonify, request
from rdflib import BNode, Graph, Literal, RDF, URIRef
from werkzeug.serving import make_server

from coala.sensor import Sensor
from ontologies import HMAS
from ontologies.LLMOnt import llm_ability


class Body(Sensor):
    """
    Sensor implementation backed by a lightweight Flask REST API.

    Clients can submit percepts via POST /percepts with a JSON payload of the
    form {"agent_id": "...", "percept": "..."} and the percept will be queued
    for later aggregation via gather().
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        public_base_url: Optional[str] = None,
        profile_path: str = "/profile",
        percepts_path: str = "/percepts",
        repetition_time: int = 1,
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.profile_path = profile_path
        self.percepts_path = percepts_path
        self.public_base_url = (public_base_url or f"http://localhost:{port}").rstrip("/")
        self.repetition_time = repetition_time
        self.app = Flask(__name__)
        self._server = None
        self._thread: Optional[Thread] = None
        self._setup_routes()

    def _setup_routes(self):
        body = self

        @self.app.get(self.profile_path)
        def get_profile_route():
            profile_json_ld = body._build_profile_graph().serialize(format="json-ld", indent=2)
            return Response(profile_json_ld, mimetype="application/ld+json")

        @self.app.post(self.percepts_path)
        def add_percept_route():
            data = request.get_json(silent=True) or {}
            agent_id = data.get("agent_id")
            percept = data.get("percept")

            if not isinstance(percept, str) or not percept.strip():
                return jsonify({"error": "Field 'percept' must be a non-empty string"}), 400

            formatted = body._format_percept(agent_id, percept)
            body.add_percept(formatted)
            return jsonify({"status": "queued"}), 201

    def _format_percept(self, agent_id: Optional[str], percept: str) -> str:
        """Store both agent and message while keeping Sensor API text-based."""
        if agent_id and agent_id.strip():
            return f"[agent:{agent_id.strip()}] {percept}"
        return percept

    @property
    def profile_url(self) -> str:
        return f"{self.public_base_url}{self.profile_path}"

    @property
    def callback_url(self) -> str:
        return f"{self.public_base_url}{self.percepts_path}"

    def _build_profile_graph(self) -> Graph:
        graph = Graph()
        profile_id = URIRef(self.profile_url)

        graph.add((profile_id, RDF.type, HMAS.ResourceProfile))
        graph.add((profile_id, RDF.type, HMAS.Agent))

        ability = BNode()
        graph.add((profile_id, HMAS.hasAbility, ability))
        graph.add((ability, RDF.type, llm_ability))

        recurrent_policy = BNode()
        graph.add((profile_id, HMAS.hasRecurrentPolicy, recurrent_policy))
        graph.add((recurrent_policy, RDF.type, HMAS.RecurrentPolicy))
        graph.add((recurrent_policy, HMAS.hasCallbackUrl, URIRef(self.callback_url)))
        graph.add((recurrent_policy, HMAS.hasRepetitionTime, Literal(self.repetition_time)))
        return graph

    def start(self):
        """Start the Flask server in a background thread if not already running."""
        if self._thread and self._thread.is_alive():
            return

        self._server = make_server(self.host, self.port, self.app)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the Flask server and wait for the background thread to exit."""
        if not self._thread:
            return

        if self._server is not None:
            self._server.shutdown()
        self._thread.join()
        self._thread = None
        self._server = None
