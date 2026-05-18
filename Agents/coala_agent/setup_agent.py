import asyncio
import json
import re
import socket
import sys
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from flask import Flask
from flask import Response, jsonify, request
from rdflib import Graph, Literal, RDF, URIRef
from werkzeug.serving import make_server

from coala.body import Body
from coala.coala import Coala
from config_loader import load_config
from llm import load_llm
from ontologies import HMAS
from ontologies.LLMOnt import llm_ability, text_action


_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config.json"
_SETUP_MCP_URL = "http://127.0.0.1:8204/mcp"

_PROFILE_HOST = "127.0.0.1"
_CALLBACK_PORT = 8086
_PUBLIC_BASE_URL = "http://localhost:8991"
_CALLBACK_BASE_URL = "http://localhost:8086"
_IGNORED_CREATOR_PROFILE_URL = "http://localhost:8993/profile"
_PROFILE_PATH = "/profile"
_PERCEPTS_PATH = "/percepts"
_ANNOTATION_PATH = "/annotation"
_MESSAGE_PATH = "/message"

_HMAS_REGISTER_PROFILE = "hmas:registerProfile"
_HMAS_REGISTER_PROFILE_IRI = "https://purl.org/hmas/registerProfile"
_HMAS_QUERY_ANNOTATIONS = "hmas:queryAnnotations"
_HMAS_QUERY_ANNOTATIONS_IRI = "https://purl.org/hmas/queryAnnotations"
_HMAS_HAS_ID = URIRef("https://purl.org/hmas/hasId")

_PROFILE_URL_PATTERN = re.compile(r"https?://[^\s,\]]+/profile\b")
_WAIT_FOR_REPLY_MS = 15000


def _http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    accept: str | None = None,
) -> tuple[int, str, str]:
    normalized_headers = dict(headers or {})
    if accept:
        normalized_headers["Accept"] = accept
    payload = body.encode("utf-8") if body is not None else None
    request_obj = Request(url, data=payload, method=method.upper(), headers=normalized_headers)
    with urlopen(request_obj, timeout=10) as response:
        content_type = response.headers.get_content_type() or response.headers.get(
            "Content-Type", ""
        )
        return response.status, response.read().decode("utf-8"), content_type


def _parse_rdf_document(document: str, content_type: str = "") -> Graph:
    graph = Graph()
    mime_type = content_type.split(";", 1)[0].strip().lower()
    parse_formats: list[str] = []
    if mime_type == "application/ld+json":
        parse_formats.append("json-ld")
    elif mime_type in {"text/turtle", "application/x-turtle"}:
        parse_formats.append("turtle")
    elif mime_type in {"application/rdf+xml", "text/xml"}:
        parse_formats.append("xml")

    parse_formats.extend(["json-ld", "turtle", "xml"])
    attempted: set[str] = set()
    for rdf_format in parse_formats:
        if rdf_format in attempted:
            continue
        attempted.add(rdf_format)
        try:
            graph.parse(data=document, format=rdf_format)
            return graph
        except Exception:
            continue
    raise ValueError("Could not parse RDF payload.")


def _is_supported_rdf_mimetype(content_type: str) -> bool:
    mime_type = content_type.split(";", 1)[0].strip().lower()
    return mime_type in {
        "application/ld+json",
        "text/turtle",
        "application/x-turtle",
        "application/rdf+xml",
        "text/xml",
    }


def _select_profile_response_format() -> tuple[str, str]:
    accepts = request.accept_mimetypes
    if accepts and accepts["application/ld+json"] > accepts["text/turtle"]:
        return "application/ld+json", "json-ld"
    return "text/turtle", "turtle"


def _profile_registration_name(profile_url: str) -> str:
    parsed = urlparse(profile_url)
    if parsed.fragment:
        return parsed.fragment
    path = parsed.path.rstrip("/")
    if path:
        return path.rsplit("/", 1)[-1]
    return "agent"


def _extract_annotations(graph: Graph) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for annotation in graph.subjects(RDF.type, HMAS.Annotation):
        content = next(graph.objects(annotation, HMAS.conveys), None)
        if content is None:
            content = next(graph.objects(annotation, HMAS.signifies), None)
        if content is None:
            continue

        text_literal = next(graph.objects(content, text_action), None)
        if not isinstance(text_literal, Literal):
            continue

        statement = str(text_literal).strip()
        if not statement:
            continue

        creator = next(graph.objects(annotation, HMAS.hasCreator), None)
        annotations.append(
            {
                "id": str(next(graph.objects(annotation, _HMAS_HAS_ID), "")),
                "creator": str(creator) if creator is not None else "",
                "text": statement,
            }
        )
    return annotations


def _extract_messages(graph: Graph) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for message in graph.subjects(RDF.type, HMAS.Message):
        content = next(graph.objects(message, HMAS.conveys), None)
        if content is None:
            content = next(graph.objects(message, HMAS.signifies), None)
        if content is None:
            continue

        text_literal = next(graph.objects(content, text_action), None)
        if not isinstance(text_literal, Literal):
            continue

        statement = str(text_literal).strip()
        if not statement:
            continue

        sender = next(graph.objects(message, HMAS.hasSender), None)
        messages.append(
            {
                "id": str(next(graph.objects(message, _HMAS_HAS_ID), "")),
                "sender": str(sender) if sender is not None else "",
                "text": statement,
            }
        )
    return messages


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def _format_user_reply_from_message(message_text: str, sender_profile_url: Optional[str] = None) -> str:
    normalized_text = _normalize_whitespace(message_text)
    lowered = normalized_text.lower()

    if lowered in {"done true", "done: true"}:
        sentence = "The external agent reported that the task is done."
    elif lowered in {"done false", "done: false"}:
        sentence = "The external agent reported that the task is not done."
    else:
        sentence_body = normalized_text
        if sentence_body and sentence_body[-1] not in ".!?":
            sentence_body = f"{sentence_body}."
        sentence = f"The external agent replied: {sentence_body}"

    if sender_profile_url:
        return f"{sentence} Sender: {sender_profile_url}."
    return sentence


def _read_json(url: str) -> dict[str, Any]:
    _, body, _ = _http_request("GET", url, accept="application/td+json, application/json")
    return json.loads(body)


def _resolve_typed_affordance_operation(
    thing_description_url: str,
    compact_type: str,
    iri_type: str,
) -> tuple[str, str]:
    td = _read_json(thing_description_url)
    actions = td.get("actions", {})
    if not isinstance(actions, dict):
        raise ValueError("Thing Description does not expose actions.")

    for action in actions.values():
        if not isinstance(action, dict):
            continue
        action_type = action.get("@type")
        action_types = action_type if isinstance(action_type, list) else [action_type]
        if compact_type not in action_types and iri_type not in action_types:
            continue
        forms = action.get("forms", [])
        if not forms:
            continue
        form = forms[0]
        href = form.get("href")
        if not isinstance(href, str) or not href:
            continue
        method = form.get("htv:methodName", "POST")
        return urljoin(thing_description_url, href), method

    raise ValueError(f"No affordance of type {compact_type} found in TD {thing_description_url}.")


def _query_annotations_from_td(
    thing_description_url: str,
    profile_url: str,
) -> list[dict[str, Any]]:
    target_url, method = _resolve_typed_affordance_operation(
        thing_description_url,
        _HMAS_QUERY_ANNOTATIONS,
        _HMAS_QUERY_ANNOTATIONS_IRI,
    )
    separator = "&" if "?" in target_url else "?"
    query_url = f"{target_url}{separator}profile={quote(profile_url, safe='')}"
    try:
        _, body, content_type = _http_request(
            method,
            query_url,
            accept="text/turtle, application/ld+json",
        )
    except HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    graph = _parse_rdf_document(body, content_type)
    return _extract_annotations(graph)


class SetupBody(Body):
    def __init__(
        self,
        host: str,
        port: int,
        public_base_url: str,
        callback_base_url: str,
        profile_path: str,
        percepts_path: str,
        annotation_path: str = "/annotation",
        message_path: str = "/message",
        repetition_time: int = 1,
    ) -> None:
        self.annotation_path = annotation_path
        self.message_path = message_path
        self.callback_base_url = callback_base_url.rstrip("/")
        self._profile_server = None
        self._profile_thread: Thread | None = None
        self._lock = Lock()
        self._received_annotations: list[dict[str, Any]] = []
        self._received_messages: list[dict[str, Any]] = []
        self._message_log_cursor = 0
        super().__init__(
            host=host,
            port=port,
            public_base_url=public_base_url,
            profile_path=profile_path,
            percepts_path=percepts_path,
            repetition_time=repetition_time,
        )

    def _build_profile_graph(self):
        profile_id = URIRef(self.profile_url)
        agent_id = URIRef(f"{self.profile_url}#agent")
        graph = Graph()

        graph.add((profile_id, RDF.type, HMAS.ResourceProfile))
        graph.add((profile_id, HMAS.isProfileOf, agent_id))
        graph.add((agent_id, RDF.type, HMAS.Agent))

        ability = URIRef(f"{self.profile_url}#ability")
        graph.add((agent_id, HMAS.hasAbility, ability))
        graph.add((ability, RDF.type, llm_ability))

        recurrent_policy = URIRef(f"{self.profile_url}#annotation-policy")
        graph.add((agent_id, HMAS.hasInteractionPolicy, recurrent_policy))
        graph.add((recurrent_policy, RDF.type, HMAS.RecurrentPolicy))
        graph.add((recurrent_policy, HMAS.hasCallbackUrl, URIRef(self.callback_url)))
        graph.add((recurrent_policy, HMAS.hasRepetitionTime, Literal(self.repetition_time)))

        message_policy = URIRef(f"{self.profile_url}#message-policy")
        graph.add((agent_id, HMAS.hasInteractionPolicy, message_policy))
        graph.add((message_policy, RDF.type, HMAS.MessagePolicy))
        graph.add((message_policy, HMAS.hasMessageUrl, URIRef(self.message_url)))
        return graph

    @property
    def callback_url(self) -> str:
        return f"{self.callback_base_url}{self.annotation_path}"

    @property
    def message_url(self) -> str:
        return f"{self.callback_base_url}{self.message_path}"

    def _profile_binding(self) -> tuple[str, int] | None:
        parsed = urlparse(self.public_base_url)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return None
        if host == self.host and port == self.port:
            return None
        return host, port

    def _build_profile_app(self) -> Flask:
        app = Flask(f"{__name__}_profile")
        body = self

        @app.get(self.profile_path)
        def get_profile_route() -> Response:
            mimetype, rdf_format = _select_profile_response_format()
            serialization = body._build_profile_graph().serialize(format=rdf_format)
            return Response(serialization, mimetype=mimetype)

        return app

    def _extract_text_action_from_annotation(
        self, annotation_document: str, content_type: str = ""
    ) -> str | None:
        graph = _parse_rdf_document(annotation_document, content_type)

        for annotation in graph.subjects(RDF.type, HMAS.Annotation):
            for conveyed in graph.objects(annotation, HMAS.conveys):
                nested_text_action = graph.value(conveyed, text_action)
                if isinstance(nested_text_action, Literal):
                    value = str(nested_text_action).strip()
                    if value:
                        return value

        return None

    def _extract_creator_profile_url(
        self, annotation_document: str, content_type: str = ""
    ) -> str | None:
        graph = _parse_rdf_document(annotation_document, content_type)

        for annotation in graph.subjects(RDF.type, HMAS.Annotation):
            creator = graph.value(annotation, HMAS.hasCreator)
            if creator:
                value = str(creator).strip()
                if value:
                    return value

        return None

    def _should_ignore_text_action(self, text_action_value: str) -> bool:
        normalized_text = text_action_value.strip().lower()
        return normalized_text.startswith("register_profile ")

    def _format_observed_annotation(
        self,
        text_action_value: str,
        creator_profile_url: str | None,
    ) -> str:
        metadata_parts = ["reply:true"]
        if creator_profile_url:
            metadata_parts.append(f"agent:{creator_profile_url}")
        metadata = " ".join(f"[{part}]" for part in metadata_parts)
        return f"{text_action_value} {metadata}\n"

    def _format_observed_message(
        self,
        text_action_value: str,
        sender_profile_url: str | None,
    ) -> str:
        normalized_text = _normalize_whitespace(text_action_value)
        message_prefix = "Observed external message"
        if sender_profile_url:
            message_prefix = f"{message_prefix} from {sender_profile_url}"
        return f"{message_prefix}: {normalized_text}\n"

    def snapshot_received_messages(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._received_messages)

    def consume_unlogged_received_messages(self) -> list[dict[str, Any]]:
        with self._lock:
            messages = self._received_messages[self._message_log_cursor :]
            self._message_log_cursor = len(self._received_messages)
            return list(messages)

    def latest_received_message(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._received_messages:
                return None
            return dict(self._received_messages[-1])

    def format_received_message_for_observation(self, message: dict[str, Any]) -> str:
        return self._format_observed_message(
            str(message.get("text", "")),
            str(message.get("sender", "")) or None,
        ).rstrip()

    def _has_ignored_creator(self, annotation_document: str, content_type: str = "") -> bool:
        graph = _parse_rdf_document(annotation_document, content_type)

        for annotation in graph.subjects(RDF.type, HMAS.Annotation):
            for creator in graph.objects(annotation, HMAS.hasCreator):
                if str(creator) == _IGNORED_CREATOR_PROFILE_URL:
                    return True
        return False

    def _setup_routes(self):
        super()._setup_routes()
        body = self

        @self.app.post(self.annotation_path)
        def add_annotation() -> tuple[Response, int] | Response:
            annotation_document = request.get_data(as_text=True)
            content_type = request.headers.get("Content-Type", "")

            if not _is_supported_rdf_mimetype(content_type):
                return (
                    jsonify(
                        {
                            "error": (
                                "Content-Type must be application/ld+json, "
                                "text/turtle, application/x-turtle, "
                                "application/rdf+xml, or text/xml"
                            )
                        }
                    ),
                    400,
                )

            if not annotation_document.strip():
                return jsonify({"error": "Request body must contain RDF content"}), 400

            try:
                if body._has_ignored_creator(annotation_document, content_type):
                    return jsonify({"status": "ignored"}), 200

                extracted_text_action = body._extract_text_action_from_annotation(
                    annotation_document, content_type
                )
                creator_profile_url = body._extract_creator_profile_url(
                    annotation_document, content_type
                )
            except Exception as exc:
                return jsonify({"error": f"Invalid RDF annotation: {exc}"}), 400

            if not extracted_text_action:
                return (
                    jsonify(
                        {
                            "error": (
                                "Annotation must contain an hmas:Annotation with "
                                "hmas:conveys/llm:text_action"
                            )
                        }
                    ),
                    400,
                )

            if body._should_ignore_text_action(extracted_text_action):
                return jsonify({"status": "ignored", "reason": "filtered_text_action"}), 200

            observed_annotation = body._format_observed_annotation(
                extracted_text_action,
                creator_profile_url,
            )
            body.add_percept(observed_annotation)
            with body._lock:
                body._received_annotations.append(
                    {
                        "text": extracted_text_action,
                        "creator": creator_profile_url or "",
                    }
                )
            return (
                jsonify(
                    {
                        "status": "queued",
                        "percept": observed_annotation,
                    }
                ),
                200,
            )

        @self.app.post(self.message_path)
        def add_message() -> tuple[Response, int] | Response:
            message_document = request.get_data(as_text=True)
            content_type = request.headers.get("Content-Type", "")
            sys.stdout.write(message_document)
            if message_document and not message_document.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()

            if not _is_supported_rdf_mimetype(content_type):
                sys.stdout.write("Message content type is not supported RDF.\n")
                sys.stdout.flush()
                return (
                    jsonify(
                        {
                            "error": (
                                "Content-Type must be application/ld+json, "
                                "text/turtle, application/x-turtle, "
                                "application/rdf+xml, or text/xml"
                            )
                        }
                    ),
                    400,
                )

            if not message_document.strip():
                sys.stdout.write("Message body is empty.\n")
                sys.stdout.flush()
                return jsonify({"error": "Request body must contain RDF content"}), 400

            try:
                graph = _parse_rdf_document(message_document, content_type)
                turtle_message = graph.serialize(format="turtle")
                sys.stdout.write(turtle_message)
                if turtle_message and not turtle_message.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.flush()
            except Exception as exc:
                sys.stdout.write(f"Message RDF parsing failed: {exc}\n")
                sys.stdout.flush()
                return jsonify({"error": f"Invalid RDF message: {exc}"}), 400

            try:
                messages = _extract_messages(graph)
            except Exception as exc:
                sys.stdout.write(f"Message RDF extraction failed: {exc}\n")
                sys.stdout.flush()
                return jsonify({"error": f"Could not extract message content: {exc}"}), 400

            if not messages:
                return (
                    jsonify(
                        {
                            "error": (
                                "Message must contain an hmas:Message with "
                                "hmas:conveys/llm:text_action"
                            )
                        }
                    ),
                    400,
                )

            queued_percepts: list[str] = []
            with body._lock:
                for message in messages:
                    if body._should_ignore_text_action(message["text"]):
                        continue
                    observed_message = body._format_observed_message(
                        message["text"],
                        message["sender"] or None,
                    )
                    body.add_percept(observed_message)
                    body._received_messages.append(
                        {
                            "id": message["id"],
                            "text": message["text"],
                            "sender": message["sender"],
                            "observed_message": observed_message.rstrip(),
                        }
                    )
                    queued_percepts.append(observed_message)

            if not queued_percepts:
                return jsonify({"status": "ignored", "reason": "filtered_text_action"}), 200

            return jsonify({"status": "queued", "percepts": queued_percepts}), 200

    def start(self) -> None:
        super().start()

        profile_binding = self._profile_binding()
        if profile_binding is None:
            return

        if self._profile_thread and self._profile_thread.is_alive():
            return

        profile_host, profile_port = profile_binding
        self._profile_server = make_server(profile_host, profile_port, self._build_profile_app())
        self._profile_thread = Thread(target=self._profile_server.serve_forever, daemon=True)
        self._profile_thread.start()

    def stop(self) -> None:
        if self._profile_server is not None:
            self._profile_server.shutdown()
        if self._profile_thread is not None:
            self._profile_thread.join()
            self._profile_thread = None
        self._profile_server = None
        super().stop()

    def snapshot_received_annotations(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._received_annotations)


class SetupAgent(Coala):
    def process_observations(self, observations):
        super().process_observations(observations)
        if not isinstance(self.sensor, SetupBody):
            return

        for message in self.sensor.consume_unlogged_received_messages():
            self._record_percept(
                self.sensor.format_received_message_for_observation(message),
                source="message",
            )

    async def _execute_single_decision(self, decision: dict[str, Any]) -> None:
        if decision.get("tool") == "send_user_message" and isinstance(self.sensor, SetupBody):
            latest_message = self.sensor.latest_received_message()
            if latest_message is None:
                self._record_action("send_user_message_blocked", {"reason": "no_external_message"})
                self._record_action_output("Blocked send_user_message because no external message was observed.")
                self.working_memory.chat_memory.add_ai_message(
                    "Blocked send_user_message because no external message was observed."
                )
                return

            rewritten_message = _format_user_reply_from_message(
                str(latest_message.get("text", "")),
                str(latest_message.get("sender", "")) or None,
            )
            tool_input = decision.get("tool_input")
            if not isinstance(tool_input, dict):
                tool_input = {}
                decision["tool_input"] = tool_input
            tool_input["message"] = rewritten_message

        await super()._execute_single_decision(decision)


def _build_prompt(profile_url: str) -> str:
    return f"""You are an agent that must complete one deterministic message-and-reply workflow using the available tools.

Fixed constants:
- your_profile_url: {profile_url}
- reply_wait_ms: {_WAIT_FOR_REPLY_MS}

Rules:
- Execute the workflow in order and do not skip or reorder steps.
- Use permanent memory to track progress.
- First register your own profile with the Setup 4 application.
- The message from the HTTP GUI must be read with read_message.
- The message must be published as a natural-language annotation with add_natural_language_annotation.
- When waiting for a reply, use the internal wait tool and inspect the observation context for lines starting with "Observed external message".
- Only an external callback message can trigger send_user_message.
- When replying to the user, formulate the perceived external message into one proper English sentence that preserves its meaning.
- Do not invent reply content beyond what the observed external message means.
- When the workflow is complete, stop immediately.

Workflow:
1. If permanent memory field "current_state" is missing, set it to "register_profile".
2. When current_state is "register_profile":
   - Call register_profile with:
     - profile_url: "{profile_url}"
   - Set permanent memory field "current_state" to "read_message".
3. When current_state is "read_message":
   - Call read_message.
   - Store the returned text in permanent memory field "source_message".
   - Set permanent memory field "current_state" to "create_annotation".
4. When current_state is "create_annotation":
   - Call add_natural_language_annotation with:
     - annotation: the exact value stored in permanent memory field "source_message"
   - Set permanent memory field "current_state" to "wait_for_reply".
5. When current_state is "wait_for_reply":
   - Call the internal wait tool with:
     - milliseconds: {_WAIT_FOR_REPLY_MS}
   - Set permanent memory field "current_state" to "inspect_reply".
6. When current_state is "inspect_reply":
   - Inspect the messages only.
   - Look for the most recent observed external message.
   - If no external message has been observed yet, call {{"tool": "noop"}} and keep the current state unchanged.
   - If an external message exists indicating whether the goal has been achieved, store only its perceived text in permanent memory field "reply_message".
   - If the reply content is not already in English, translate it to English before storing it.
   - Set permanent memory field "current_state" to "send_user_message".
7. When current_state is "send_user_message":
   - Only proceed if a real external message has been observed.
   - Call send_user_message with:
     - message: one proper English sentence that conveys the exact meaning of permanent memory field "reply_message"
   - Set permanent memory field "current_state" to "end".
8. When current_state is "end":
   - Stop execution by calling {{"tool": "stop"}}.
"""


def build_agent() -> Coala:
    config = load_config(str(_CONFIG_PATH))
    llm_config = config["llm_agent"]
    llm = load_llm(
        llm_config["provider"],
        llm_config["model"],
        reasoning=llm_config.get("reasoning"),
        thinking=llm_config.get("thinking"),
    )

    body = SetupBody(
        host=_PROFILE_HOST,
        port=_CALLBACK_PORT,
        public_base_url=_PUBLIC_BASE_URL,
        callback_base_url=_CALLBACK_BASE_URL,
        profile_path=_PROFILE_PATH,
        percepts_path=_PERCEPTS_PATH,
        annotation_path=_ANNOTATION_PATH,
        message_path=_MESSAGE_PATH,
        repetition_time=1,
    )

    return SetupAgent(
        llm=llm,
        initial_prompt=_build_prompt(body.profile_url),
        initial_memory={"current_state": "register_profile"},
        body=body,
        mcp_servers=[
            {
                "name": "setup_tools",
                "server_url": _SETUP_MCP_URL,
            }
        ],
        agent_name="setup_agent",
        tool_timeout_seconds=60,
    )


async def main() -> None:
    agent = build_agent()
    await agent.start()


def ensure_mcp_server_available() -> None:
    parsed = urlparse(_SETUP_MCP_URL)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        print(f"Error: invalid MCP server URL: {_SETUP_MCP_URL}", file=sys.stderr)
        raise SystemExit(1)

    try:
        with socket.create_connection((host, port), timeout=3):
            return
    except OSError as exc:
        print(
            (
                f"Error: MCP server is not running at {_SETUP_MCP_URL}. "
                f"Start mcp/servers/setup4_tools.py first. Details: {exc}"
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    ensure_mcp_server_available()
    asyncio.run(main())
