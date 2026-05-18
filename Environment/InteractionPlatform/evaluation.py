from __future__ import annotations

import contextlib
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, Response
import requests
from rdflib import BNode, Graph, Literal, RDF, URIRef
from rdflib.collection import Collection
from werkzeug.serving import make_server

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

import transformation_creation
from annotation_creation import add_text_action, create_llm_annotation
from components.annotation import Annotation
from components.profile import Profile
from llm import load_llm
from ontologies import BDIOnt, HMAS
from transformation_creation import (
    create_llm_bdi_ability_transformation,
    create_llm_goal_to_bdi_transformation,
    create_llm_env_to_bdi_transformation
)
from utils import _normalize_uri_node, generate_id


PROFILE_BASE_URL = "http://localhost:8082"
PROFILE_URL = f"{PROFILE_BASE_URL}/profile"
PROFILE_AGENT_URL = URIRef(f"{PROFILE_URL}#agent")
EVALUATION_LOG_PATH = BASE_DIR / "evaluation_logs.md"
ATOM_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_\-.]*\Z")
_ONTOLOGY_ACCEPT_HEADER = "application/ld+json, text/turtle"
_ONTOLOGY_FORMATS = {
    "application/ld+json": "json-ld",
    "text/turtle": "turtle",
    "application/x-turtle": "turtle",
}
_EXCLUDED_ONTOLOGY_NAMESPACES = (
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/2001/XMLSchema#",
    "https://purl.org/hmas/",
)
SHARED_BDI_ONTOLOGY_PATH = BASE_DIR.parent.parent / "ontologies" / "bdi.ttl"


@dataclass(frozen=True)
class GoalCase:
    name: str
    sentence: str
    belief: str
    follows_pattern: bool


@dataclass(frozen=True)
class LlmSpec:
    provider: str
    model: str
    thinking: bool | str | None = None
    reasoning: bool | str | None = None
    temperature: int = 0

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class TransformationSpec:
    name: str
    function: Any
    use_llm: bool


@dataclass
class EvaluationResult:
    goal_name: str
    sentence: str
    expected_belief: str
    function_name: str
    llm_label: str
    iteration: int
    success: bool
    status: str
    annotation_url: str | None = None
    transformed_belief: str | None = None
    detail: str | None = None
    transformation_duration_seconds: float | None = None
    
LLMS = [
    LlmSpec(
        provider="ollama",
        model="gemma4:e2b",
        thinking=False,
        temperature=0
    ),
LlmSpec(
        provider="ollama",
        model="gemma4:e4b",
        thinking=False,
        temperature=0
    ),
LlmSpec(
        provider="ollama",
        model="gemma4:26b",
        thinking=False,
        temperature=0
    )
]

GOALS = [
    GoalCase(
        name="goal_1_1",
        sentence="Zone 1 should have light level 1. Zone 2 light level 2. Callback URL: http://localhost:8991/profile.",
        belief='set_env(1, 2, "http://localhost:8991/profile")',
        follows_pattern=True,
    ),
    GoalCase(
        name="goal_1_2",
        sentence="1 should be the light level of zone 1. Zone 2 light level 2. Callback URL: http://localhost:8991/profile.",
        belief='set_env(1, 2, "http://localhost:8991/profile")',
        follows_pattern=False,
    ),
    GoalCase(
        name="goal_2_1",
        sentence="Zone 1 should have light level 3. Zone 2 should have light level 2. A human will be in zone 1. Callback URL: http://localhost:8991/profile.",
        belief='set_env(3, 2, "http://localhost:8991/profile", human(1))',
        follows_pattern=True,
    ),
    GoalCase(
        name="goal_2_2",
        sentence="Zone 1 should have light level 3. 2 is the light level of zone 2. In zone 1, there will be a human. The callback URL is http://localhost:8991/profile.",
        belief='set_env(3, 2, "http://localhost:8991/profile", human(1))',
        follows_pattern=False,
    ),
    GoalCase(
        name="goal_3_1",
        sentence="Zone 1 should have light level 3. Zone 2 should have light level 1. A human will be in zone 1. A human will be in zone 2. Callback URL: http://localhost:8991/profile.",
        belief='set_env(3, 1, "http://localhost:8991/profile", human(1,2))',
        follows_pattern=True,
    ),
    GoalCase(
        name="goal_3_2",
        sentence="1 is the light level of zone 2. Zone 1 should have light level 3. There will be a human in both zones. The profile URL is http://localhost:8991/profile.",
        belief='set_env(3, 1, "http://localhost:8991/profile", human(1,2))',
        follows_pattern=False,
    )
]

GOALS_BY_NAME = {goal.name: goal for goal in GOALS}

REPETITIONS = 30

TRANSFORMATION_FUNCTIONS = [
    TransformationSpec(
        name="create_llm_env_to_bdi_transformation",
        function=create_llm_env_to_bdi_transformation().get_function(),
        use_llm=False,
    ),
    TransformationSpec(
        name="create_llm_goal_to_bdi_transformation",
        function=create_llm_goal_to_bdi_transformation().get_function(),
        use_llm=True,
    ),
    TransformationSpec(
        name="create_llm_bdi_ability_transformation",
        function=create_llm_bdi_ability_transformation().get_function(),
        use_llm=True,
    ),
]


class ProfileServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8082) -> None:
        self.host = host
        self.port = port
        self.base_url = PROFILE_BASE_URL
        self.profile_url = PROFILE_URL
        self._app = Flask("evaluation_profile_server")
        self._server = None
        self._thread: threading.Thread | None = None
        self._profile_graph = self._build_profile_graph()
        self._ontologies = {"bdi": self._load_bdi_ontology_graph()}
        self._register_routes()

    def _register_routes(self) -> None:
        @self._app.get("/profile")
        def get_profile() -> Response:
            return Response(
                self._profile_graph.serialize(format="turtle"),
                200,
                content_type="text/turtle; charset=utf-8",
            )

        @self._app.get("/ontologies/<ontology_name>")
        def get_ontology(ontology_name: str) -> Response:
            graph = self._ontologies.get(ontology_name)
            if graph is None:
                return Response("", 404)
            return Response(
                graph.serialize(format="turtle"),
                200,
                content_type="text/turtle; charset=utf-8",
            )

    def _build_profile_graph(self) -> Graph:
        graph = Graph()
        profile_document = URIRef(self.profile_url)
        bdi_namespace = URIRef(f"{self.base_url}/ontologies/bdi#")

        graph.bind("hmas", HMAS.HMAS)
        graph.bind("bdi", f"{self.base_url}/ontologies/bdi#")

        graph.add((profile_document, HMAS.HMAS.isProfileOf, PROFILE_AGENT_URL))
        graph.add((PROFILE_AGENT_URL, RDF.type, HMAS.Agent))

        for ability_type in (
            URIRef(str(bdi_namespace) + "predicate_ability"),
            URIRef(str(bdi_namespace) + "set_env"),
        ):
            ability_node = BNode()
            graph.add((PROFILE_AGENT_URL, HMAS.hasAbility, ability_node))
            graph.add((ability_node, RDF.type, ability_type))

        return graph

    def _load_bdi_ontology_graph(self) -> Graph:
        graph = Graph()
        graph.parse(SHARED_BDI_ONTOLOGY_PATH, format="turtle")
        return graph

    def start(self) -> None:
        try:
            self._server = make_server(self.host, self.port, self._app)
        except OSError as exc:
            raise RuntimeError(
                f"Could not start the evaluation profile server on {self.base_url}. "
                "Port 8082 must be free because the BDI transformation code uses "
                "http://localhost:8082/ontologies/bdi# as a fixed namespace."
            ) from exc
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> "ProfileServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


@contextlib.contextmanager
def configured_transformation_llm(llm_spec: LlmSpec):
    original_loader = transformation_creation._load_transformation_llm

    def loader():
        llm_kwargs: dict[str, Any] = {
            "provider": llm_spec.provider,
            "name": llm_spec.model,
            "temperature": llm_spec.temperature,
        }
        if llm_spec.thinking is not None:
            llm_kwargs["thinking"] = llm_spec.thinking
        if llm_spec.reasoning is not None:
            llm_kwargs["reasoning"] = llm_spec.reasoning
        return load_llm(**llm_kwargs)

    transformation_creation._load_transformation_llm = loader
    try:
        yield
    finally:
        transformation_creation._load_transformation_llm = original_loader


def _get_supported_rdf_format(content_type: str) -> str | None:
    mime_type = content_type.split(";", 1)[0].strip().lower()
    return _ONTOLOGY_FORMATS.get(mime_type)


def _parse_supported_rdf_response(graph: Graph, response: requests.Response) -> bool:
    rdf_format = _get_supported_rdf_format(response.headers.get("Content-Type", ""))
    if rdf_format is None:
        return False

    graph.parse(
        data=response.text,
        format=rdf_format,
        publicID=getattr(response, "url", None) or "",
    )
    return True


def _is_excluded_ontology_namespace(uri: str) -> bool:
    return any(uri.startswith(namespace) for namespace in _EXCLUDED_ONTOLOGY_NAMESPACES)


def _term_to_ontology_url(uri: str) -> str | None:
    if not uri.startswith(("http://", "https://")) or _is_excluded_ontology_namespace(uri):
        return None
    if "#" in uri:
        document_url, _ = uri.split("#", 1)
        return document_url or None
    if uri.endswith("/"):
        return uri
    if "/" in uri:
        return uri.rsplit("/", 1)[0] + "/"
    return None


def _iter_candidate_ontology_urls(graph: Graph) -> set[str]:
    candidates: set[str] = set()
    for _, predicate, obj in graph:
        for term in (predicate, obj):
            if not isinstance(term, URIRef):
                continue
            ontology_url = _term_to_ontology_url(str(term))
            if ontology_url is not None:
                candidates.add(ontology_url)
    return candidates


def _load_ontology_documents(graph: Graph, ontology_urls: set[str], visited: set[str] | None = None) -> None:
    if visited is None:
        visited = set()

    for ontology_url in sorted(ontology_urls):
        if ontology_url in visited:
            continue
        visited.add(ontology_url)
        try:
            response = requests.get(
                ontology_url,
                headers={"Accept": _ONTOLOGY_ACCEPT_HEADER},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue

        if not _parse_supported_rdf_response(graph, response):
            continue


def _expand_graph_with_imported_ontologies(graph: Graph) -> None:
    first_order_ontology_urls = _iter_candidate_ontology_urls(graph)
    import_predicates = (
        URIRef("http://www.w3.org/2002/07/owl#imports"),
        URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#seeAlso"),
    )
    for predicate_ref in import_predicates:
        for obj in graph.objects(predicate=predicate_ref):
            if isinstance(obj, URIRef):
                obj_str = str(obj)
                if not _is_excluded_ontology_namespace(obj_str):
                    first_order_ontology_urls.add(obj_str)
    _load_ontology_documents(graph, first_order_ontology_urls)


def create_natural_language_annotation(sentence: str) -> Annotation:
    annotation_id = generate_id()
    annotation = create_llm_annotation(annotation_id)
    add_text_action(annotation, sentence)

    creator_uri = _normalize_uri_node(str(PROFILE_AGENT_URL))
    if creator_uri is None:
        raise RuntimeError("Could not normalize the evaluation profile creator URI")
    annotation.add_triple(annotation.url, HMAS.hasCreator, creator_uri)
    return annotation


def load_agent_profile() -> Profile:
    profile = _load_profile_from_url(PROFILE_URL)
    if profile is None:
        raise RuntimeError(f"Could not load the agent profile from {PROFILE_URL}")
    return profile


def _load_profile_from_url(profile_url: str) -> Profile | None:
    try:
        response = requests.get(profile_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return None

    graph = Graph()
    for rdf_format in ("json-ld", "turtle", "xml"):
        try:
            graph.parse(data=response.text, format=rdf_format, publicID=profile_url)
            _expand_graph_with_imported_ontologies(graph)
            profile = Profile.parse_profile(graph)
            if profile is not None:
                return profile
        except Exception:
            continue

    return None


def annotation_to_belief(annotation: Annotation) -> str | None:
    content_node = annotation.model.value(annotation.url, HMAS.conveys)
    if content_node is None:
        content_node = annotation.model.value(annotation.url, HMAS.signifies)
    if content_node is None:
        return None

    literal_spec = rdf_statement_to_literal_spec(annotation.model, content_node)
    if literal_spec is None:
        return None
    return literal_spec_to_agentspeak(literal_spec)


def rdf_statement_to_literal_spec(graph: Graph, node: Any) -> dict[str, Any] | None:
    predicate = graph.value(node, BDIOnt.hasPredicate)
    values_head = graph.value(node, BDIOnt.hasValues)
    if not isinstance(predicate, Literal) or values_head is None:
        return None

    values = []
    for item in Collection(graph, values_head):
        values.append(rdf_value_to_agentspeak_value(graph, item))
    return {"predicate": str(predicate), "values": values}


def rdf_value_to_agentspeak_value(graph: Graph, value: Any) -> Any:
    if isinstance(value, Literal):
        python_value = value.toPython()
        if isinstance(python_value, (bool, int, float)):
            if isinstance(python_value, float) and python_value.is_integer():
                return int(python_value)
            return python_value
        return str(python_value)

    nested_literal = rdf_statement_to_literal_spec(graph, value)
    if nested_literal is not None:
        return nested_literal
    return str(value)


def literal_spec_to_agentspeak(literal_spec: dict[str, Any]) -> str:
    predicate = literal_spec["predicate"]
    values = literal_spec.get("values", [])
    if not values:
        return predicate
    args = ", ".join(agentspeak_value_to_text(value) for value in values)
    return f"{predicate}({args})"


def agentspeak_value_to_text(value: Any) -> str:
    if isinstance(value, dict):
        return literal_spec_to_agentspeak(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "g")
    if isinstance(value, str) and ATOM_PATTERN.fullmatch(value):
        return value
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class _AgentSpeakLiteralParser:
    def __init__(self, text: str):
        self.text = text
        self.length = len(text)
        self.position = 0

    def parse(self) -> dict[str, Any]:
        self._skip_whitespace()
        literal = self._parse_literal()
        self._skip_whitespace()
        if self.position != self.length:
            raise ValueError("unexpected trailing content")
        return literal

    def _skip_whitespace(self) -> None:
        while self.position < self.length and self.text[self.position].isspace():
            self.position += 1

    def _peek(self) -> str | None:
        if self.position >= self.length:
            return None
        return self.text[self.position]

    def _consume(self, expected: str) -> None:
        if self._peek() != expected:
            raise ValueError(f"expected {expected!r}")
        self.position += 1

    def _parse_literal(self) -> dict[str, Any]:
        predicate = self._parse_identifier()
        arguments: list[Any] = []
        self._skip_whitespace()
        if self._peek() == "(":
            self.position += 1
            self._skip_whitespace()
            if self._peek() != ")":
                while True:
                    arguments.append(self._parse_term())
                    self._skip_whitespace()
                    next_char = self._peek()
                    if next_char == ",":
                        self.position += 1
                        self._skip_whitespace()
                        continue
                    if next_char == ")":
                        break
                    raise ValueError("expected ',' or ')'")
            self._consume(")")
        return {"predicate": predicate, "values": arguments}

    def _parse_term(self) -> Any:
        self._skip_whitespace()
        current = self._peek()
        if current is None:
            raise ValueError("unexpected end of input")
        if current in {'"', "'"}:
            return self._parse_string()
        if current.isdigit() or current in {"-", "+"}:
            return self._parse_number_or_atom()
        if current.isalpha() or current == "_":
            identifier = self._parse_identifier()
            self._skip_whitespace()
            if self._peek() == "(":
                self.position -= len(identifier)
                return self._parse_literal()
            lowered = identifier.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            return identifier
        raise ValueError(f"unsupported character {current!r}")

    def _parse_identifier(self) -> str:
        start = self.position
        current = self._peek()
        if current is None or not (current.isalpha() or current == "_"):
            raise ValueError("expected identifier")
        self.position += 1
        while self.position < self.length:
            current = self.text[self.position]
            if current.isalnum() or current == "_":
                self.position += 1
                continue
            break
        return self.text[start:self.position]

    def _parse_string(self) -> str:
        quote = self._peek()
        if quote is None:
            raise ValueError("expected quoted string")
        self.position += 1
        chars: list[str] = []
        while self.position < self.length:
            current = self.text[self.position]
            self.position += 1
            if current == "\\":
                if self.position >= self.length:
                    raise ValueError("unterminated escape sequence")
                chars.append(self.text[self.position])
                self.position += 1
                continue
            if current == quote:
                return "".join(chars)
            chars.append(current)
        raise ValueError("unterminated string")

    def _parse_number_or_atom(self) -> Any:
        start = self.position
        while self.position < self.length:
            current = self.text[self.position]
            if current.isalnum() or current in {".", "_", "-", "+"}:
                self.position += 1
                continue
            break
        token = self.text[start:self.position]
        if re.fullmatch(r"[+-]?\d+", token):
            return int(token)
        if re.fullmatch(r"[+-]?\d+\.\d+", token):
            return float(token)
        return token


def _extract_agentspeak_literal_response(text: str) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None
    if normalized.lower() in {"none", "null"}:
        return None

    fenced_match = re.search(r"```(?:[\w-]+)?\s*(.*?)\s*```", normalized, re.DOTALL)
    if fenced_match is not None:
        normalized = fenced_match.group(1).strip()

    if normalized.lower().startswith("literal:"):
        normalized = normalized.split(":", 1)[1].strip()

    return normalized or None


def normalize_belief(text: str) -> dict[str, Any] | None:
    normalized = _extract_agentspeak_literal_response(text)
    if normalized is None:
        return None
    try:
        return _AgentSpeakLiteralParser(normalized).parse()
    except ValueError:
        return None


def evaluate_single_run(
    goal: GoalCase,
    transformation: TransformationSpec,
    llm: LlmSpec | None,
    iteration: int,
) -> EvaluationResult:
    transformation_started_at: float | None = None
    try:
        annotation = create_natural_language_annotation(goal.sentence)
        profile = load_agent_profile()
        llm_context = (
            configured_transformation_llm(llm)
            if llm is not None and transformation.use_llm
            else contextlib.nullcontext()
        )
        with llm_context:
            transformation_started_at = time.perf_counter()
            transformed = transformation.function(profile, annotation)
    except Exception as exc:  # noqa: BLE001
        transformation_duration_seconds = None
        if transformation_started_at is not None:
            transformation_duration_seconds = time.perf_counter() - transformation_started_at
        return EvaluationResult(
            goal_name=goal.name,
            sentence=goal.sentence,
            expected_belief=goal.belief,
            function_name=transformation.name,
            llm_label=llm.label if llm is not None else "n/a",
            iteration=iteration,
            success=False,
            status="failure",
            detail=f"runtime error: {exc}",
            transformation_duration_seconds=transformation_duration_seconds,
        )

    transformation_duration_seconds = None
    if transformation_started_at is not None:
        transformation_duration_seconds = time.perf_counter() - transformation_started_at

    if transformed is None:
        return EvaluationResult(
            goal_name=goal.name,
            sentence=goal.sentence,
            expected_belief=goal.belief,
            function_name=transformation.name,
            llm_label=llm.label if llm is not None else "n/a",
            iteration=iteration,
            success=False,
            status="failure",
            annotation_url=str(annotation.url),
            detail="transformation returned no annotation",
            transformation_duration_seconds=transformation_duration_seconds,
        )

    transformed_belief = annotation_to_belief(transformed)
    if transformed_belief is None:
        return EvaluationResult(
            goal_name=goal.name,
            sentence=goal.sentence,
            expected_belief=goal.belief,
            function_name=transformation.name,
            llm_label=llm.label if llm is not None else "n/a",
            iteration=iteration,
            success=False,
            status="failure",
            annotation_url=str(transformed.url),
            detail="could not convert transformed annotation into an AgentSpeak belief",
            transformation_duration_seconds=transformation_duration_seconds,
        )

    expected_normalized = normalize_belief(goal.belief)
    transformed_normalized = normalize_belief(transformed_belief)
    success = (
        expected_normalized is not None
        and transformed_normalized is not None
        and transformed_normalized == expected_normalized
    )

    return EvaluationResult(
        goal_name=goal.name,
        sentence=goal.sentence,
        expected_belief=goal.belief,
        function_name=transformation.name,
        llm_label=llm.label if llm is not None else "n/a",
        iteration=iteration,
        success=success,
        status="success" if success else "failure",
        annotation_url=str(transformed.url),
        transformed_belief=transformed_belief,
        detail=None if success else "belief mismatch",
        transformation_duration_seconds=transformation_duration_seconds,
    )


def run_evaluation() -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    with ProfileServer():
        for goal in GOALS:
            for transformation in TRANSFORMATION_FUNCTIONS:
                if transformation.use_llm:
                    for llm in LLMS:
                        for iteration in range(1, REPETITIONS + 1):
                            results.append(evaluate_single_run(goal, transformation, llm, iteration))
                    continue

                results.append(evaluate_single_run(goal, transformation, None, 1))
    return results


def build_markdown_report(results: list[EvaluationResult]) -> str:
    llm_results = [result for result in results if result.llm_label != "n/a"]
    non_llm_results = [result for result in results if result.llm_label == "n/a"]
    lines = [
        "# Evaluation Results",
        "",
        f"- Repetitions: {REPETITIONS}",
        f"- Goals: {len(GOALS)}",
        f"- Transformations: {len(TRANSFORMATION_FUNCTIONS)}",
        f"- LLMs: {len(LLMS)}",
        "",
        "## LLM Per-Run Results",
        "",
        "| Goal | Function | LLM | Iteration | Status | Transform time (s) | Expected belief | Produced belief | Detail |",
        "| --- | --- | --- | ---: | --- | ---: | --- | --- | --- |",
    ]

    for result in llm_results:
        produced = result.transformed_belief or ""
        detail = result.detail or ""
        transformation_duration = ""
        if result.transformation_duration_seconds is not None:
            transformation_duration = f"{result.transformation_duration_seconds:.6f}"
        lines.append(
            f"| {result.goal_name} | {result.function_name} | {result.llm_label} | "
            f"{result.iteration} | {result.status} | {transformation_duration} | "
            f"`{result.expected_belief}` | `{produced}` | {detail} |"
        )

    lines.extend(
        [
            "",
            "## Non-LLM Results",
            "",
            "| Goal | Function | Iteration | Status | Transform time (s) | Expected belief | Produced belief | Detail |",
            "| --- | --- | ---: | --- | ---: | --- | --- | --- |",
        ]
    )

    for result in non_llm_results:
        produced = result.transformed_belief or ""
        detail = result.detail or ""
        transformation_duration = ""
        if result.transformation_duration_seconds is not None:
            transformation_duration = f"{result.transformation_duration_seconds:.6f}"
        lines.append(
            f"| {result.goal_name} | {result.function_name} | "
            f"{result.iteration} | {result.status} | {transformation_duration} | "
            f"`{result.expected_belief}` | `{produced}` | {detail} |"
        )

    lines.extend(
        [
            "",
            "## Pattern Success Rates By Model",
            "",
            "| Function | LLM | Follows pattern | Successes | Total | Success rate | Average time (s) |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )

    pattern_summary: dict[tuple[str, str, bool], list[EvaluationResult]] = {}
    for result in llm_results:
        goal = GOALS_BY_NAME.get(result.goal_name)
        if goal is None:
            continue
        pattern_summary.setdefault(
            (result.function_name, result.llm_label, goal.follows_pattern),
            [],
        ).append(result)

    for function_name, llm_label, follows_pattern in sorted(pattern_summary):
        grouped_results = pattern_summary[(function_name, llm_label, follows_pattern)]
        successes = sum(1 for item in grouped_results if item.success)
        total = len(grouped_results)
        rate = 0.0 if total == 0 else successes / total
        durations = [
            item.transformation_duration_seconds
            for item in grouped_results
            if item.transformation_duration_seconds is not None
        ]
        average_time = "" if not durations else f"{sum(durations) / len(durations):.6f}"
        lines.append(
            f"| {function_name} | {llm_label} | {'yes' if follows_pattern else 'no'} | "
            f"{successes} | {total} | {rate:.2%} | {average_time} |"
        )

    lines.extend(
        [
            "",
            "## Non-LLM Transformation Times By Goal",
            "",
            "| Goal | Function | Iteration | Transform time (s) | Status |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )

    for result in non_llm_results:
        transformation_duration = ""
        if result.transformation_duration_seconds is not None:
            transformation_duration = f"{result.transformation_duration_seconds:.6f}"
        lines.append(
            f"| {result.goal_name} | {result.function_name} | "
            f"{result.iteration} | {transformation_duration} | {result.status} |"
        )

    lines.extend(
        [
            "",
            "## Non-LLM Success Proportions",
            "",
            "| Goal | Function | Successes | Total | Success rate |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )

    non_llm_summary: dict[tuple[str, str], list[EvaluationResult]] = {}
    for result in non_llm_results:
        non_llm_summary.setdefault((result.goal_name, result.function_name), []).append(result)

    for goal_name, function_name in sorted(non_llm_summary):
        grouped_results = non_llm_summary[(goal_name, function_name)]
        successes = sum(1 for item in grouped_results if item.success)
        total = len(grouped_results)
        rate = 0.0 if total == 0 else successes / total
        lines.append(
            f"| {goal_name} | {function_name} | "
            f"{successes} | {total} | {rate:.2%} |"
        )

    lines.extend(
        [
            "",
            "## Goal Definitions",
            "",
            "| Goal | Follows pattern | Sentence | Expected belief |",
            "| --- | --- | --- | --- |",
        ]
    )
    for goal in GOALS:
        lines.append(
            f"| {goal.name} | {'yes' if goal.follows_pattern else 'no'} | "
            f"{goal.sentence} | `{goal.belief}` |"
        )

    lines.extend(
        [
            "",
            "## Success Proportions",
            "",
            "| Goal | Function | LLM | Successes | Total | Success rate | Average time (s) |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )

    summary: dict[tuple[str, str, str], list[EvaluationResult]] = {}
    for result in llm_results:
        summary.setdefault(
            (result.goal_name, result.function_name, result.llm_label),
            [],
        ).append(result)

    for goal_name, function_name, llm_label in sorted(summary):
        grouped_results = summary[(goal_name, function_name, llm_label)]
        successes = sum(1 for item in grouped_results if item.success)
        total = len(grouped_results)
        rate = 0.0 if total == 0 else successes / total
        durations = [
            item.transformation_duration_seconds
            for item in grouped_results
            if item.transformation_duration_seconds is not None
        ]
        average_time = "" if not durations else f"{sum(durations) / len(durations):.6f}"
        lines.append(
            f"| {goal_name} | {function_name} | {llm_label} | "
            f"{successes} | {total} | {rate:.2%} | {average_time} |"
        )

    return "\n".join(lines) + "\n"


def write_report(results: list[EvaluationResult]) -> None:
    EVALUATION_LOG_PATH.write_text(build_markdown_report(results), encoding="utf-8")


def main() -> None:
    results = run_evaluation()
    write_report(results)


if __name__ == "__main__":
    main()
