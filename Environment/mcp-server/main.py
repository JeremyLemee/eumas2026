import json
import logging
import os
import sys
import threading
import time
from functools import wraps
from pathlib import Path
from string import Template
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastmcp import FastMCP
from flask import Flask, Response, jsonify, render_template_string, request
from pydantic import Field
from rdflib import BNode, Graph, Literal, RDF, URIRef
from werkzeug.serving import make_server

# Add the repo root to sys.path so direct execution from mcp/servers can import sem/.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ontologies import HMAS  # noqa: E402
from ontologies.HMAS import hasCreator  # noqa: E402
from ontologies.LLMOnt import llm_ability, llm_action, text_action  # noqa: E402


DEFAULT_APP_URL = os.environ.get("SETUP_APP_URL", "http://127.0.0.1:5001")
DEFAULT_GUI_URL = os.environ.get("SETUP_GUI_URL", "http://127.0.0.1:9966")
CREATOR_PROFILE_URL = os.environ.get(
    "SETUP_CREATOR_PROFILE_URL", "http://localhost:8991/profile#agent"
)
PROFILE_REGISTRATION_NAME = os.environ.get(
    "SETUP_PROFILE_REGISTRATION_NAME", "coala_profile"
)
DEFAULT_GUI_MESSAGE = "Zone 1 should have light level 1. Zone 2 light level 2."
REQUEST_TIMEOUT = 10
LOG_FILE = Path(__file__).resolve().parent / "setup_tools_log.txt"

mcp = FastMCP(name="Tools")

_LOGGER = logging.getLogger("tools")
if not _LOGGER.handlers:
    _LOGGER.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    _LOGGER.addHandler(file_handler)
    _LOGGER.propagate = False


def _app_url(path: str) -> str:
    return f"{DEFAULT_APP_URL.rstrip('/')}{path}"


def _gui_url(path: str) -> str:
    return f"{DEFAULT_GUI_URL.rstrip('/')}{path}"


GUI_HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Setup Tools GUI</title>
  <style>
    :root {
      --bg: #f3efe6;
      --panel: #fffdf8;
      --line: #d7cfbe;
      --ink: #1f241e;
      --muted: #66705f;
      --accent: #2f6f5e;
      --accent-2: #a14b2b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(47, 111, 94, 0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(161, 75, 43, 0.10), transparent 24%),
        linear-gradient(180deg, #f8f3e9 0%, #eee6d7 100%);
    }
    main { max-width: 1080px; margin: 0 auto; padding: 24px; }
    .grid { display: grid; gap: 18px; grid-template-columns: 1.05fr 0.95fr; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
    }
    h1, h2 { margin: 0 0 12px; }
    p { margin: 0 0 12px; color: var(--muted); }
    textarea, pre {
      width: 100%;
      min-height: 180px;
      margin: 0;
      padding: 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      font: 0.95rem "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    button {
      border: 0;
      border-radius: 12px;
      padding: 10px 14px;
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    .status {
      margin-top: 12px;
      min-height: 24px;
      color: var(--accent-2);
      white-space: pre-wrap;
    }
    ul {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
      max-height: 420px;
      overflow: auto;
    }
    li {
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      white-space: pre-wrap;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 0.9rem;
    }
    .meta {
      display: inline-block;
      margin-bottom: 14px;
      color: var(--accent);
      background: rgba(47, 111, 94, 0.1);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.9rem;
    }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <div class="meta">GUI server on {{ gui_url }}</div>
    <h1>Setup Tools GUI</h1>
    <p>Define the goal the agent should read and inspect messages sent through <code>send_user_message</code>.</p>
    <div class="grid">
      <section class="panel">
        <h2>Goal</h2>
        <p>The MCP tool <code>read_user_message</code> reads this value.</p>
        <textarea id="goal-input"></textarea>
        <div style="margin-top:12px;">
          <button id="save-goal">Save Goal</button>
        </div>
        <div class="status" id="goal-status"></div>
      </section>
      <section class="panel">
        <h2>Agent Messages</h2>
        <p>Messages posted through <code>send_user_message</code> appear here.</p>
        <ul id="message-list"></ul>
      </section>
    </div>
  </main>
  <script>
    let goalInitialized = false;

    async function fetchState() {
      const response = await fetch('/api/state');
      if (!response.ok) {
        throw new Error(`State request failed: ${response.status}`);
      }
      return response.json();
    }

    function renderMessages(messages) {
      const list = document.getElementById('message-list');
      if (!messages.length) {
        list.innerHTML = '<li>No agent messages yet.</li>';
        return;
      }
      list.innerHTML = messages.slice().reverse().map((entry) => {
        const stamp = new Date(entry.timestamp * 1000).toLocaleString();
        return `<li>[${stamp}]\\n${entry.message}</li>`;
      }).join('');
    }

    async function refresh() {
      const state = await fetchState();
      if (!goalInitialized) {
        document.getElementById('goal-input').value = state.goal;
        goalInitialized = true;
      }
      renderMessages(state.messages);
    }

    async function saveGoal() {
      const goal = document.getElementById('goal-input').value;
      const response = await fetch('/goal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal }),
      });
      const payload = await response.json();
      const status = document.getElementById('goal-status');
      status.textContent = response.ok ? 'Goal saved.' : (payload.error || 'Failed to save goal.');
      if (response.ok) {
        goalInitialized = true;
      }
    }

    document.getElementById('save-goal').addEventListener('click', () => {
      saveGoal().catch((error) => {
        document.getElementById('goal-status').textContent = error.message;
      });
    });

    refresh().catch((error) => {
      document.getElementById('goal-status').textContent = error.message;
    });
    setInterval(() => { refresh().catch(() => {}); }, 2000);
  </script>
</body>
</html>
"""


def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    data: str | dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    return requests.request(
        method,
        _app_url(path),
        json=json_body,
        data=data,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )


def _gui_request(
    method: str,
    path: str,
    *,
    data: str | None = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    return requests.request(
        method,
        _gui_url(path),
        data=data,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )


def _response_text(response: requests.Response) -> str:
    return response.text.strip() or f"HTTP {response.status_code}"


def _short_repr(value: Any, max_length: int = 500) -> str:
    text = repr(value)
    if len(text) > max_length:
        return f"{text[:max_length]}... [truncated]"
    return text


def _log_tool_call(tool_name: str, parameters: dict[str, Any]) -> None:
    _LOGGER.info(
        "tool_called=%s parameters=%s",
        tool_name,
        {key: _short_repr(value) for key, value in parameters.items()},
    )


def _log_tool_result(tool_name: str, result: Any) -> None:
    _LOGGER.info("tool_result=%s result=%s", tool_name, _short_repr(result))


def _log_tool_error(tool_name: str, error: BaseException) -> None:
    _LOGGER.exception("tool_error=%s error=%s", tool_name, error)


def _logged_tool(func):
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        parameters: dict[str, Any] = {}
        parameter_names = func.__code__.co_varnames[: func.__code__.co_argcount]
        parameters.update(dict(zip(parameter_names, args)))
        parameters.update(kwargs)

        _log_tool_call(func.__name__, parameters)
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            _log_tool_error(func.__name__, exc)
            raise

        _log_tool_result(func.__name__, result)
        return result

    return wrapper


def _build_annotation_payload(statement: str) -> dict[str, Any]:
    normalized_statement = statement.strip()
    if not normalized_statement:
        raise ValueError("Annotation statement must not be empty.")

    graph = Graph()
    annotation_id = URIRef(f"http://example.org/annotation/{uuid4()}")
    graph.add((annotation_id, RDF.type, HMAS.Annotation))
    graph.add((annotation_id, HMAS.conveys, Literal(normalized_statement)))
    graph.add((annotation_id, hasCreator, URIRef(CREATOR_PROFILE_URL)))

    ability = BNode()
    graph.add((annotation_id, HMAS.recommendsAbility, ability))
    graph.add((ability, RDF.type, llm_ability))

    serialized = graph.serialize(format="json-ld")
    return json.loads(serialized)


def _build_direct_annotation_payload(statement: str) -> dict[str, Any]:
    normalized_statement = statement.strip()
    if not normalized_statement:
        raise ValueError("Annotation statement must not be empty.")

    graph = Graph()
    annotation_id = URIRef(f"http://example.org/annotation/{uuid4()}")
    graph.add((annotation_id, RDF.type, HMAS.Annotation))
    graph.add((annotation_id, hasCreator, URIRef(CREATOR_PROFILE_URL)))

    conveyed_action = BNode()
    graph.add((annotation_id, HMAS.conveys, conveyed_action))
    graph.add((conveyed_action, RDF.type, llm_action))
    graph.add((conveyed_action, text_action, Literal(normalized_statement)))

    ability = BNode()
    graph.add((annotation_id, HMAS.recommendsAbility, ability))
    graph.add((ability, RDF.type, llm_ability))

    serialized = graph.serialize(format="json-ld")
    return json.loads(serialized)


def _escape_turtle_literal(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _build_natural_language_annotation_turtle(statement: str) -> str:
    normalized_statement = statement.strip()
    if not normalized_statement:
        raise ValueError("Annotation statement must not be empty.")

    annotation_uuid = uuid4()
    has_id_uuid = uuid4()
    escaped_statement = _escape_turtle_literal(normalized_statement)

    return Template(
        """@prefix ns1: <https://purl.org/hmas/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<http://localhost:5001/annotations/$annotation_uuid> rdf:type ns1:Annotation ;
ns1:conveys [
<http://example.org/llm#text_action> "$statement" ;
rdf:type <http://example.org/llm#llm_action>
] ;
ns1:hasCreator <http://localhost:8991/profile#agent> ;
ns1:hasId "$has_id_uuid" ;
ns1:recommendsAbility [
rdf:type <http://example.org/llm#llm_ability>
] .
"""
    ).substitute(
        annotation_uuid=annotation_uuid,
        statement=escaped_statement,
        has_id_uuid=has_id_uuid,
    )


def _extract_message_text(payload: Any) -> str | None:
    if isinstance(payload, str):
        normalized = payload.strip()
        return normalized or None
    if isinstance(payload, dict):
        for key in ("goal", "message", "annotation", "text", "content", "value"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _gui_binding() -> tuple[str, int]:
    parsed = urlparse(DEFAULT_GUI_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9966
    return host, port


class SetupToolsGuiServer:
    def __init__(self) -> None:
        self.host, self.port = _gui_binding()
        self.goal = os.environ.get("SETUP_GUI_INITIAL_GOAL", DEFAULT_GUI_MESSAGE)
        self.messages: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.app = Flask(f"{__name__}_gui")
        self._server = None
        self._thread: threading.Thread | None = None
        self._setup_routes()

    def _state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "goal": self.goal,
                "messages": list(self.messages),
                "message_count": len(self.messages),
            }

    def _append_message(self, message: str) -> None:
        with self.lock:
            self.messages.append({"timestamp": time.time(), "message": message})
            self.messages = self.messages[-200:]

    def _set_goal(self, goal: str) -> None:
        with self.lock:
            self.goal = goal

    def _setup_routes(self) -> None:
        @self.app.get("/")
        def index() -> str:
            return render_template_string(GUI_HTML_TEMPLATE, gui_url=DEFAULT_GUI_URL)

        @self.app.get("/api/state")
        def api_state() -> Response:
            return jsonify(self._state())

        @self.app.get("/goal")
        def get_goal() -> Response:
            return jsonify({"goal": self._state()["goal"]})

        @self.app.post("/goal")
        def set_goal() -> tuple[Response, int] | Response:
            payload = request.get_json(silent=True)
            if payload is None:
                payload = request.get_data(as_text=True)

            goal = _extract_message_text(payload)
            if goal is None:
                return jsonify({"error": "Goal must be a non-empty string"}), 400

            self._set_goal(goal)
            return jsonify({"status": "updated", "goal": goal})

        @self.app.get("/message")
        def get_message() -> Response:
            goal = self._state()["goal"]
            accept = request.headers.get("Accept", "")
            if "application/json" in accept:
                return jsonify({"message": goal})
            return Response(goal, mimetype="text/plain")

        @self.app.post("/message")
        def post_message() -> tuple[Response, int] | Response:
            payload = request.get_json(silent=True)
            if payload is None:
                payload = request.get_data(as_text=True)

            message = _extract_message_text(payload)
            if message is None:
                return jsonify({"error": "Message must be a non-empty string"}), 400

            self._append_message(message)
            return jsonify({"status": "queued", "message": message}), 202

        @self.app.get("/messages")
        def get_messages() -> Response:
            return jsonify({"messages": self._state()["messages"]})

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._server = make_server(self.host, self.port, self.app)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="setup-tools-gui-server",
            daemon=True,
        )
        self._thread.start()


_GUI_SERVER = SetupToolsGuiServer()


def _start_gui_server() -> None:
    try:
        _GUI_SERVER.start()
        _LOGGER.info(
            "gui_server_started host=%s port=%s url=%s",
            _GUI_SERVER.host,
            _GUI_SERVER.port,
            DEFAULT_GUI_URL,
        )
    except OSError as exc:
        _LOGGER.exception("gui_server_failed error=%s", exc)
        raise RuntimeError(
            f"Failed to start GUI HTTP server on {DEFAULT_GUI_URL}: {exc}"
        ) from exc


def _read_message_from_gui() -> str:
    try:
        response = _gui_request(
            "GET",
            "/message",
            headers={"Accept": "application/json, text/plain, */*"},
        )
        response.raise_for_status()
    except requests.RequestException:
        return DEFAULT_GUI_MESSAGE

    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            for key in ("message", "annotation", "text", "content", "value"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        elif isinstance(payload, str) and payload.strip():
            return payload.strip()

    body = response.text.strip()
    if body:
        try:
            parsed = json.loads(body)
        except ValueError:
            return body
        if isinstance(parsed, dict):
            for key in ("message", "annotation", "text", "content", "value"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        elif isinstance(parsed, str) and parsed.strip():
            return parsed.strip()
        return body

    return DEFAULT_GUI_MESSAGE


@mcp.tool
@_logged_tool
def register_profile(
    profile_url: Annotated[
        str,
        Field(description="Absolute URL of the profile to register with Setup 4."),
    ],
) -> str:
    """Register an external profile URL with the Setup 4 application."""
    normalized_profile_url = profile_url.strip()
    if not normalized_profile_url:
        return "Profile URL must not be empty."

    payload = {
        "name": PROFILE_REGISTRATION_NAME,
        "url": normalized_profile_url,
    }

    try:
        response = _request("POST", "/profiles/register", json_body=payload)
        response.raise_for_status()
        return _response_text(response)
    except requests.RequestException as exc:
        return f"Error registering profile: {exc}"


@mcp.tool
@_logged_tool
def read_user_message() -> str:
    """Read the current message exposed by the HTTP GUI interface."""
    return _read_message_from_gui()


@mcp.tool
@_logged_tool
def send_user_message(
    message: Annotated[
        str,
        Field(description="Message to display in the HTTP GUI interface."),
    ],
) -> str:
    """Send a message to the HTTP GUI interface via HTTP POST request."""
    normalized_message = message.strip()
    if not normalized_message:
        return "Message must not be empty."

    try:
        response = _gui_request(
            "POST",
            "/message",
            data=normalized_message,
            headers={"Content-Type": "text/plain"},
        )
        response.raise_for_status()
        return _response_text(response)
    except requests.RequestException as exc:
        return f"Error sending message: {exc}"


@mcp.tool
@_logged_tool
def send_http_request(
    url: Annotated[
        str,
        Field(description="Absolute URL that should receive the request."),
    ],
    method: Annotated[
        str,
        Field(description="HTTP method to use, for example GET, POST, or PUT."),
    ],
    headers: Annotated[
        dict[str, str],
        Field(description="HTTP headers to include in the request."),
    ] | None = None,
    body: Annotated[
        str,
        Field(description="Raw request body to send. Use an empty string when no body is needed."),
    ] = "",
) -> str:
    """Send an HTTP request to an arbitrary URL and return the response details."""
    normalized_url = url.strip()
    if not normalized_url:
        return "URL must be a non-empty string."

    normalized_method = method.strip().upper()
    if not normalized_method:
        return "Method must be a non-empty string."

    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        return "Headers must be a JSON object."

    normalized_headers = {str(key): str(value) for key, value in headers.items()}

    try:
        response = requests.request(
            normalized_method,
            normalized_url,
            data=body,
            headers=normalized_headers,
            timeout=REQUEST_TIMEOUT,
        )
        return json.dumps(
            {
                "status_code": response.status_code,
                "reason": response.reason,
                "content_type": response.headers.get("Content-Type", ""),
                "body": response.text,
            },
            indent=2,
        )
    except requests.RequestException as exc:
        return f"Error sending HTTP request: {exc}"


@mcp.tool
@_logged_tool
def get_annotations_for_profile(
    profile: Annotated[
        str,
        Field(description="Name of the profile whose annotations should be retrieved."),
    ],
) -> str:
    """Fetch annotations selected for the given profile name."""
    try:
        response = _request("GET", "/annotations/", params={"profile": profile})
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        return f"Error fetching annotations for profile {profile}: {exc}"


@mcp.tool
@_logged_tool
def add_natural_language_annotation(
    annotation: Annotated[
        str,
        Field(
            description="Natural-language statement that will be converted into an annotation."
        ),
    ],
) -> str:
    """Create and add an annotation from a natural-language statement."""
    if not isinstance(annotation, str):
        return "Annotation statement must be a string."

    normalized_annotation = annotation.strip()
    if not normalized_annotation:
        return "Annotation statement must not be empty."

    try:
        response = _request(
            "POST",
            "/annotations_nl/",
            data={
                "annotation": normalized_annotation,
                "creator": CREATOR_PROFILE_URL,
            },
        )
        response.raise_for_status()
        return _response_text(response)
    except requests.RequestException as exc:
        return f"Error adding natural-language annotation: {exc}"


@mcp.tool
@_logged_tool
def add_natural_language_direct_annotation(
    agent: Annotated[
        str,
        Field(
            description="URL of the target agent that should receive the direct annotation."
        ),
    ],
    annotation: Annotated[
        str,
        Field(
            description="Natural-language statement that will be converted into a direct annotation."
        ),
    ],
) -> str:
    """Create a direct annotation from a natural-language statement and send it to an agent."""
    if not isinstance(agent, str) or not agent.strip():
        return "Agent must be a non-empty string."

    if not isinstance(annotation, str):
        return "Annotation statement must be a string."

    normalized_annotation = annotation.strip()
    if not normalized_annotation:
        return "Annotation statement must not be empty."

    try:
        annotation_payload = _build_direct_annotation_payload(normalized_annotation)
        response = _request(
            "POST",
            "/annotation/direct",
            json_body={"agent": agent.strip(), "annotation": annotation_payload},
        )
        response.raise_for_status()
        return _response_text(response)
    except requests.RequestException as exc:
        return f"Error adding natural-language direct annotation: {exc}"


if __name__ == "__main__":
    _start_gui_server()
    mcp.run(transport="http", host="127.0.0.1", port=8204, path="/mcp")
