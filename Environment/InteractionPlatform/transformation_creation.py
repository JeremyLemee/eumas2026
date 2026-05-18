import json
import re
import threading
import time
from typing import Any
from urllib.parse import urldefrag

from flask import Flask, Response, request
from rdflib import Graph, URIRef
import requests

from components.profile import Profile
from components.selection import Selection
from environment import Environment
from registries.annotation_registry import AnnotationRegistry
from registries.profile_registry import ProfileRegistry
from ontologies import HMAS, BDIOnt, LabOnt, LLMOnt, SoarOnt
from components.annotation import Annotation
from components.generation import Generation
from components.transformation import Transformation, TransformationInput
from utils import _build_predicate_statement, annotations_url_from_id, generate_id, generate_url, _normalize_uri_node, \
    _construct_graph
from rdflib import BNode, Literal, RDF, XSD
from annotation_creation import create_predicate_signifier, create_llm_annotation, add_text_action
from rdflib.collection import Collection
from config_loader import load_config
from llm import load_llm

SPARQL_NAMESPACES = {
    "rdf": RDF,
    "hmas": HMAS.HMAS,
    "lab": LabOnt.LabN,
    "soar": SoarOnt.SoarN,
    "bdi": BDIOnt.BDI,
    "llm": LLMOnt.LLMN,
}

def _extract_callback_url_from_text(text: str) -> str | None:
    match = re.search(r"https?://[^\s<>\"]+", text)
    if match is None:
        return None
    return match.group(0).rstrip(".,);]")

def _combined_graph(profile: Profile, input_resource: TransformationInput) -> Graph:
    graph = Graph()
    graph += profile.model
    graph += input_resource.model
    return graph


def _select_information(
    profile: Profile,
    input_resource: TransformationInput,
    query: str,
    extra_bindings=None,
):
    bindings = {
        "profile": profile.id,
        "annotation": input_resource.url,
    }
    if extra_bindings:
        bindings.update(extra_bindings)
    rows = _combined_graph(profile, input_resource).query(
        query,
        initBindings=bindings,
        initNs=SPARQL_NAMESPACES,
    )
    return [row.asdict() for row in rows]


def _load_transformation_llm():
    transformation_llm_config = load_config().get("transformation_llm", {})
    thinking = transformation_llm_config.get("thinking")
    llm_kwargs = {
        "provider": transformation_llm_config["provider"],
        "name": transformation_llm_config["model"],
    }
    if thinking is not None:
        llm_kwargs["thinking"] = thinking
    return load_llm(**llm_kwargs)


def _parse_llm_zone_light_level_response(response_text: str) -> int | None:
    match = re.search(r"\b([1-3])\b", response_text)
    if match is None:
        return None
    return int(match.group(1))


def _parse_llm_human_presence_response(response_text: str) -> bool | None:
    normalized = response_text.strip().lower()
    if normalized in {"true", "yes", "present", "1"}:
        return True
    if normalized in {"false", "no", "absent", "0"}:
        return False
    return None


def _parse_llm_callback_url_response(response_text: str) -> str | None:
    normalized = response_text.strip()
    if not normalized or normalized.lower() == "null":
        return None
    match = re.search(r"https?://[^\s<>\"]+", normalized)
    if match is None:
        return None
    return match.group(0).rstrip(".,);]")


def _coerce_numeric_literal_to_int(value) -> int | None:
    if not isinstance(value, Literal):
        return None

    python_value = value.toPython()
    if isinstance(python_value, bool):
        return None
    if isinstance(python_value, int):
        return python_value
    if isinstance(python_value, float):
        return int(python_value) if python_value.is_integer() else None

    try:
        numeric_value = float(str(python_value))
    except (TypeError, ValueError):
        return None
    return int(numeric_value) if numeric_value.is_integer() else None


def _is_message(input_resource: TransformationInput) -> bool:
    return (input_resource.url, RDF.type, HMAS.HMAS.Message) in input_resource.model


def _wrap_message(message_id: URIRef, graph: Graph) -> Annotation:
    message = Annotation(message_id, graph)
    message.model.remove((message.url, RDF.type, HMAS.Annotation))
    message.model.remove((message.url, RDF.type, HMAS.Signifier))
    message.model.add((message.url, RDF.type, HMAS.HMAS.Message))
    return message


def _copy_annotation_metadata(annotation_id: URIRef, graph: Graph, source: TransformationInput | None) -> None:
    if source is None:
        return
    for identifier in source.model.objects(source.url, HMAS.hasId):
        graph.add((annotation_id, HMAS.hasId, identifier))
    for creator in source.model.objects(source.url, HMAS.hasCreator):
        normalized_creator = _normalize_uri_node(creator)
        if normalized_creator is not None:
            graph.add((annotation_id, HMAS.hasCreator, normalized_creator))


def _copy_message_transport_metadata(message_id: URIRef, graph: Graph, source: TransformationInput | None) -> None:
    _copy_annotation_metadata(message_id, graph, source)
    if source is None:
        return
    for sender in source.model.objects(source.url, HMAS.HMAS.hasSender):
        graph.add((message_id, HMAS.HMAS.hasSender, sender))
    for receiver in source.model.objects(source.url, HMAS.HMAS.hasReceiver):
        graph.add((message_id, HMAS.HMAS.hasReceiver, receiver))


def _build_output_resource(
    resource_id: URIRef,
    graph: Graph,
    source: TransformationInput | None = None,
) -> Annotation:
    if source is not None and _is_message(source):
        _copy_message_transport_metadata(resource_id, graph, source)
        return _wrap_message(resource_id, graph)

    _copy_annotation_metadata(resource_id, graph, source)
    return Annotation(resource_id, graph)


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


def _extract_llm_agentspeak_literal_response(response_text: str) -> str | None:
    normalized = response_text.strip()
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


def _parse_agentspeak_literal(text: str) -> dict[str, Any] | None:
    normalized = _extract_llm_agentspeak_literal_response(text)
    if normalized is None:
        return None
    try:
        return _AgentSpeakLiteralParser(normalized).parse()
    except ValueError:
        return None


def _agentspeak_value_to_rdf(graph: Graph, value: Any):
    if isinstance(value, dict):
        return _agentspeak_literal_to_rdf(graph, value)
    return Literal(value)


def _agentspeak_literal_to_rdf(graph: Graph, literal_spec: dict[str, Any]) -> BNode:
    return _build_predicate_statement(
        graph,
        literal_spec["predicate"],
        [_agentspeak_value_to_rdf(graph, value) for value in literal_spec.get("values", [])],
    )


def _select_bdi_recommended_ability(profile: Profile, predicate: str) -> URIRef | None:
    abilities = [
        ability
        for ability in profile.get_abilities()
        if isinstance(ability, URIRef) and ability != LLMOnt.llm_ability
    ]
    if not abilities:
        return None
    if BDIOnt.predicate_ability in abilities:
        return BDIOnt.predicate_ability

    for ability in abilities:
        lexical = str(ability)
        local_name = lexical.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        if local_name == predicate:
            return ability

    return abilities[0]


def _build_bdi_ability_prompt(profile: Profile, text: str) -> str:
    ability_terms = sorted(
        {
            str(ability)
            for ability in profile.get_abilities()
            if isinstance(ability, URIRef) and ability != LLMOnt.llm_ability
        }
    )
    turtle_representation = profile.model.serialize(format="turtle")
    return f"""
You translate free-text requests into one exact ground AgentSpeak literal for a BDI agent.
Use only predicates, argument structures, and concepts supported by the profile and ontology context below.
Return exactly one AgentSpeak literal and nothing else.
If the text cannot be converted into a literal the BDI agent will understand, return exactly:
None

Profile and ontology context (Turtle):
{turtle_representation}

Relevant ability IRIs:
{ability_terms}

Input text:
\"\"\"{text}\"\"\"
""".strip()


def _create_llm_text_annotation(
    annotation_id: URIRef,
    text_action: str,
    source: TransformationInput | None = None,
) -> Annotation:
    graph = Graph()
    ability_node = BNode()
    action_node = BNode()
    graph.add((annotation_id, RDF.type, HMAS.Annotation))
    graph.add((annotation_id, HMAS.recommendsAbility, ability_node))
    graph.add((ability_node, RDF.type, LLMOnt.llm_ability))
    graph.add((annotation_id, HMAS.conveys, action_node))
    graph.add((action_node, RDF.type, LLMOnt.llm_action))
    graph.add((action_node, LLMOnt.text_action, Literal(text_action)))
    return _build_output_resource(annotation_id, graph, source)


def create_bdi_llm_transformation():
    def transformation(profile: Profile, message: TransformationInput):
        select_query = """SELECT ?predicate ?value
WHERE {
  FILTER(EXISTS {
    ?profile hmas:hasAbility/rdf:type llm:llm_ability
  })

  ?annotation hmas:conveys ?action .
  ?action bdi:hasPredicate ?predicate .

  OPTIONAL {
    ?action bdi:hasValues ?valuesHead .
    ?valuesHead rdf:rest*/rdf:first ?valueNode .

    OPTIONAL {
      ?valueNode rdf:value ?unwrappedValue .
    }

    BIND(COALESCE(?unwrappedValue, ?valueNode) AS ?value)
  }
}
        """
        information = _select_information(profile, message, select_query)
        if not information:
            return None

        predicate = str(information[0]["predicate"])
        values = [str(row["value"]) for row in information if row.get("value") is not None]
        text = f"{predicate} {' '.join(values)}".strip()
        print("text for LLM agent: ", text)
        return _create_llm_text_annotation(URIRef(str(message.url)), text, message)

    return Transformation(transformation)


def create_soar_wme_to_bdi_transformation():
    def transformation(profile: Profile, message: TransformationInput):
        select_query = """
            SELECT ?predicate ?value
            WHERE {
                FILTER(EXISTS { ?profile hmas:hasAbility/rdf:type bdi:predicate_ability })
                ?annotation hmas:conveys ?action .
                ?action soar:predicate ?predicate .
                ?action soar:hasValue ?value .
            }
        """
        information = _select_information(profile, message, select_query)
        if not information:
            return None

        predicate = str(information[0]["predicate"])
        value = str(information[0]["value"])
        message_id = URIRef(str(message.url))
        construct_query = """
            CONSTRUCT {
                ?annotationId rdf:type hmas:Annotation .
                ?annotationId hmas:recommendsAbility ?abilityNode .
                ?abilityNode rdf:type bdi:predicate_ability .
                ?annotationId hmas:conveys ?actionNode .
                ?actionNode bdi:hasPredicate ?predicate .
                ?actionNode bdi:hasValues ?valuesHead .
                ?valuesHead rdf:first ?value .
                ?valuesHead rdf:rest rdf:nil .
            }
            WHERE {
                BIND(?annotationNode AS ?annotationId)
                BIND(BNODE() AS ?abilityNode)
                BIND(BNODE() AS ?actionNode)
                BIND(BNODE() AS ?valuesHead)
            }
        """
        graph = _construct_graph(
            construct_query,
            {
                "annotationNode": message_id,
                "predicate": Literal(predicate),
                "value": Literal(value),
            },
        )
        return _build_output_resource(message_id, graph, message)

    return Transformation(transformation)



def create_state_to_soar_light_processing_transformation():
    def transformation(profile: Profile, annotation: Annotation):
        select_query = """
            SELECT ?predicate ?statePredicate ?z1 ?z2 ?goalUrl
            WHERE {
                FILTER(EXISTS { ?profile hmas:hasAbility/rdf:type soar:soar_light_processing })
                ?annotation hmas:conveys ?action .
                ?action bdi:hasPredicate ?predicate .
                FILTER(STR(?predicate) = "goal")
                ?action bdi:hasValues ?rootValues .
                ?rootValues rdf:first ?stateNode .
                ?rootValues rdf:rest ?tail .
                ?tail rdf:first ?goalUrl .
                ?stateNode bdi:hasPredicate ?statePredicate .
                FILTER(STR(?statePredicate) = "state")
                ?stateNode bdi:hasValues ?stateValues .
                ?stateValues rdf:first ?z1 .
                ?stateValues rdf:rest ?stateTail .
                ?stateTail rdf:first ?z2 .
            }
        """
        information = _select_information(profile, annotation, select_query)
        if not information:
            return None

        z1 = _coerce_numeric_literal_to_int(information[0]["z1"])
        z2 = _coerce_numeric_literal_to_int(information[0]["z2"])
        goal_url = str(information[0]["goalUrl"])
        if z1 is None or z2 is None or not goal_url:
            return None

        annotation_id = URIRef(str(annotation.url))
        construct_query = """
            CONSTRUCT {
                ?annotationId rdf:type hmas:Annotation .
                ?annotationId hmas:recommendsAbility ?abilityNode .
                ?abilityNode rdf:type soar:soar_light_processing .
                ?annotationId hmas:conveys ?actionNode .
                ?actionNode rdf:type soar:AddWME .
                ?actionNode soar:hasInputLink ?inputLink .
                ?actionNode soar:hasRelation ?z1Relation .
                ?z1Relation soar:hasIdentifier ?inputLink .
                ?z1Relation soar:hasAttribute ?z1Attr .
                ?z1Relation soar:hasValue ?z1ValueNode .
                ?z1Attr soar:hasLiteral "goal.z1" .
                ?z1ValueNode soar:hasLiteral ?z1Value .
                ?actionNode soar:hasRelation ?z2Relation .
                ?z2Relation soar:hasIdentifier ?inputLink .
                ?z2Relation soar:hasAttribute ?z2Attr .
                ?z2Relation soar:hasValue ?z2ValueNode .
                ?z2Attr soar:hasLiteral "goal.z2" .
                ?z2ValueNode soar:hasLiteral ?z2Value .
                ?actionNode soar:hasRelation ?urlRelation .
                ?urlRelation soar:hasIdentifier ?inputLink .
                ?urlRelation soar:hasAttribute ?urlAttr .
                ?urlRelation soar:hasValue ?urlValueNode .
                ?urlAttr soar:hasLiteral "goal.url" .
                ?urlValueNode soar:hasLiteral ?goalUrlValue .
            }
            WHERE {
                BIND(?annotationNode AS ?annotationId)
                BIND(BNODE() AS ?abilityNode)
                BIND(BNODE() AS ?actionNode)
                BIND(BNODE() AS ?inputLink)
                BIND(BNODE() AS ?z1Relation)
                BIND(BNODE() AS ?z1Attr)
                BIND(BNODE() AS ?z1ValueNode)
                BIND(BNODE() AS ?z2Relation)
                BIND(BNODE() AS ?z2Attr)
                BIND(BNODE() AS ?z2ValueNode)
                BIND(BNODE() AS ?urlRelation)
                BIND(BNODE() AS ?urlAttr)
                BIND(BNODE() AS ?urlValueNode)
            }
        """
        graph = _construct_graph(
            construct_query,
            {
                "annotationNode": annotation_id,
                "z1Value": Literal(z1),
                "z2Value": Literal(z2),
                "goalUrlValue": Literal(goal_url),
            },
        )

        _copy_annotation_metadata(annotation_id, graph, annotation)
        return Annotation(annotation_id, graph)

    return Transformation(transformation)


def create_soar_done_to_bdi_transformation():
    def transformation(profile: Profile, message: TransformationInput):
        select_query = """
            SELECT ?doneValue
            WHERE {
                FILTER(EXISTS { ?profile hmas:hasAbility/rdf:type bdi:predicate_ability })
                ?annotation hmas:conveys ?action .
                ?action soar:done ?doneValue .
            }
        """
        information = _select_information(profile, message, select_query)
        if not information:
            return None

        done_value = str(information[0]["doneValue"]).lower()
        message_id = URIRef(str(message.url))
        construct_query = """
            CONSTRUCT {
                ?annotationId rdf:type hmas:Annotation .
                ?annotationId hmas:recommendsAbility ?abilityNode .
                ?abilityNode rdf:type bdi:predicate_ability .
                ?annotationId hmas:conveys ?actionOut .
                ?actionOut bdi:hasPredicate "done" .
                ?actionOut bdi:hasValues ?valuesHead .
                ?valuesHead rdf:first ?doneValueLiteral .
                ?valuesHead rdf:rest rdf:nil .
            }
            WHERE {
                BIND(?annotationNode AS ?annotationId)
                BIND(BNODE() AS ?abilityNode)
                BIND(BNODE() AS ?actionOut)
                BIND(BNODE() AS ?valuesHead)
                BIND(?doneValue AS ?doneValueLiteral)
            }
        """
        graph = _construct_graph(
            construct_query,
            {
                "annotationNode": message_id,
                "doneValue": Literal(done_value),
            },
        )
        return _build_output_resource(message_id, graph, message)

    return Transformation(transformation)

def _extract_zone_light_levels_map_from_text(text: str) -> dict[int, int]:
    extracted: dict[int, int] = {}
    clause_patterns = (
        re.compile(r"\b(?:zone|z)\s*([12])\D{0,40}?(?:light level|level)\D*([1-3])\b"),
        re.compile(r"\b(?:light level|level)\D*([1-3])\D{0,40}?(?:zone|z)\s*([12])\b"),
        re.compile(r"\bz([12])\s*[:=,-]?\s*([1-3])\b"),
    )

    for clause in re.split(r"[.!?;\n]+", text.lower()):
        for pattern in clause_patterns:
            for match in pattern.finditer(clause):
                if pattern.pattern.startswith(r"\b(?:light level|level)"):
                    zone = int(match.group(2))
                    level = int(match.group(1))
                else:
                    zone = int(match.group(1))
                    level = int(match.group(2))
                extracted[zone] = level

    return extracted



def _extract_human_zones_from_text(text: str) -> list[int]:
    zones: list[int] = []
    seen: set[int] = set()

    for clause in re.split(r"[.!?;\n]+", text):
        lowered = clause.lower()
        if "human" not in lowered:
            continue

        for zone_match in re.finditer(r"\b(?:zone|zones|z)\s*([12])\b", lowered):
            zone = int(zone_match.group(1))
            if zone not in seen:
                seen.add(zone)
                zones.append(zone)

        for human_match in re.finditer(r"\bhuman\s*[:=,-]?\s*([12])\b", lowered):
            zone = int(human_match.group(1))
            if zone not in seen:
                seen.add(zone)
                zones.append(zone)

    return zones


def create_llm_env_to_bdi_transformation():
    def transformation(profile: Profile, annotation: Annotation):
        print(f"[create_llm_env_to_bdi_transformation] Start for profile={profile.id} annotation={annotation.url}")
        select_query = """
            PREFIX hmas: <https://purl.org/hmas/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX bdi:  <http://localhost:8082/ontologies/bdi#>
            PREFIX llm:  <http://example.org/llm#>

            SELECT ?text
            WHERE {
                FILTER(EXISTS { ?profile hmas:hasAbility/rdf:type bdi:set_env })
                FILTER(EXISTS { ?annotation hmas:recommendsAbility/rdf:type llm:llm_ability })
                ?annotation hmas:conveys ?action .
                ?action llm:text_action ?text .
            }
        """
        information = _select_information(profile, annotation, select_query)
        print(f"[create_llm_env_to_bdi_transformation] SELECT rows={len(information)}")
        if not information:
            print("[create_llm_env_to_bdi_transformation] No matching profile/annotation information found.")
            return None
        text = str(information[0]["text"])
        print(f"[create_llm_env_to_bdi_transformation] Extracted text={text!r}")
        zone_light_levels = _extract_zone_light_levels_map_from_text(text)
        print(f"[create_llm_env_to_bdi_transformation] Parsed zone light levels={zone_light_levels}")
        if set(zone_light_levels) != {1, 2}:
            print(
                "[create_llm_env_to_bdi_transformation] Incomplete zone light levels; both zone 1 and zone 2 are required."
            )
            return None

        callback_url = _extract_callback_url_from_text(text)
        human_zones = _extract_human_zones_from_text(text)
        print(f"[create_llm_env_to_bdi_transformation] Parsed callback_url={callback_url!r}")
        print(f"[create_llm_env_to_bdi_transformation] Parsed human_zones={human_zones}")

        annotation_id = URIRef(str(annotation.url))
        graph = Graph()
        ability_node = BNode()
        action_node = BNode()

        values: list[Any] = [Literal(zone_light_levels[zone]) for zone in sorted(zone_light_levels)]
        if callback_url:
            values.append(Literal(callback_url))
        if human_zones:
            values.append(_build_predicate_statement(graph, "human", [Literal(zone) for zone in human_zones]))
        print(f"[create_llm_env_to_bdi_transformation] Constructed values={values}")

        values_head = BNode()
        Collection(graph, values_head, values)
        print(f"[create_llm_env_to_bdi_transformation] Built RDF collection head={values_head}")

        construct_query = """
            PREFIX hmas: <https://purl.org/hmas/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX bdi:  <http://localhost:8082/ontologies/bdi#>

            CONSTRUCT {
                ?annotationId rdf:type hmas:Annotation .
                ?annotationId hmas:recommendsAbility ?abilityNode .
                ?abilityNode rdf:type bdi:set_env .
                ?annotationId hmas:conveys ?actionNode .
                ?actionNode bdi:hasPredicate "set_env" .
                ?actionNode bdi:hasValues ?valuesHead .
            }
            WHERE {
                BIND(?annotationNode AS ?annotationId)
                BIND(?abilityBinding AS ?abilityNode)
                BIND(?actionBinding AS ?actionNode)
                BIND(?valuesBinding AS ?valuesHead)
            }
        """
        graph += _construct_graph(
            construct_query,
            {
                "annotationNode": annotation_id,
                "abilityBinding": ability_node,
                "actionBinding": action_node,
                "valuesBinding": values_head,
            },
        )
        _copy_annotation_metadata(annotation_id, graph, annotation)
        print(f"[create_llm_env_to_bdi_transformation] Finished transformation for annotation={annotation_id}")
        return Annotation(annotation_id, graph)

    return Transformation(transformation)

def _extract_text_response_content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(content).strip()


def create_llm_goal_to_bdi_transformation():
    def transformation(profile: Profile, annotation: Annotation):
        print(f"[create_llm_goal_to_bdi_transformation] Start for profile={profile.id} annotation={annotation.url}")
        select_query = """
            PREFIX hmas: <https://purl.org/hmas/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX bdi:  <http://localhost:8082/ontologies/bdi#>
            PREFIX llm:  <http://example.org/llm#>

            SELECT ?text
            WHERE {
                FILTER(EXISTS { ?profile hmas:hasAbility/rdf:type bdi:set_env })
                FILTER(EXISTS { ?annotation hmas:recommendsAbility/rdf:type llm:llm_ability })
                ?annotation hmas:conveys ?action .
                ?action llm:text_action ?text .
            }
        """
        information = _select_information(profile, annotation, select_query)
        print(f"[create_llm_goal_to_bdi_transformation] SELECT rows={len(information)}")
        if not information:
            print("[create_llm_goal_to_bdi_transformation] No matching profile/annotation information found.")
            return None

        text = str(information[0]["text"])
        print(f"[create_llm_goal_to_bdi_transformation] Extracted text={text!r}")

        llm = _load_transformation_llm()
        def invoke(prompt: str) -> str:
            response = llm.invoke(prompt)
            response_text = _extract_text_response_content(response)
            print(f"[create_llm_goal_to_bdi_transformation] LLM response={response_text!r}")
            return response_text

        zone_light_levels: dict[int, int] = {}
        zone_1_level = _parse_llm_zone_light_level_response(
            invoke(
                f"""
What is the desired light level for zone 1 in the text below?
Answer with only one of: 1, 2, 3, or null.
If multiple values are given for zone 1, use the latest one.

Text:
\"\"\"{text}\"\"\"
                """.strip()
            )
        )
        if zone_1_level is not None:
            zone_light_levels[1] = zone_1_level

        zone_2_level = _parse_llm_zone_light_level_response(
            invoke(
                f"""
What is the desired light level for zone 2 in the text below?
Answer with only one of: 1, 2, 3, or null.
If multiple values are given for zone 2, use the latest one.

Text:
\"\"\"{text}\"\"\"
                """.strip()
            )
        )
        if zone_2_level is not None:
            zone_light_levels[2] = zone_2_level

        human_zone_1 = _parse_llm_human_presence_response(
            invoke(
                f"""
Will a human be present in zone 1 according to the text below?
Answer with only True or False.

Text:
\"\"\"{text}\"\"\"
                """.strip()
            )
        )
        human_zone_2 = _parse_llm_human_presence_response(
            invoke(
                f"""
Will a human be present in zone 2 according to the text below?
Answer with only True or False.

Text:
\"\"\"{text}\"\"\"
                """.strip()
            )
        )
        human_zones = [
            zone for zone, present in ((1, human_zone_1), (2, human_zone_2)) if present is True
        ]
        callback_url = _parse_llm_callback_url_response(
            invoke(
                f"""
What is the callback URL in the text below?
Answer with only the URL, or null if no callback URL is present.

Text:
\"\"\"{text}\"\"\"
                """.strip()
            )
        )
        print(f"[create_llm_goal_to_bdi_transformation] Parsed zone light levels={zone_light_levels}")
        print(f"[create_llm_goal_to_bdi_transformation] Parsed callback_url={callback_url!r}")
        print(f"[create_llm_goal_to_bdi_transformation] Parsed human_zones={human_zones}")
        if set(zone_light_levels) != {1, 2}:
            print(
                "[create_llm_goal_to_bdi_transformation] Incomplete zone light levels; both zone 1 and zone 2 are required."
            )
            return None

        annotation_id = URIRef(str(annotation.url))
        graph = Graph()
        ability_node = BNode()
        action_node = BNode()

        values: list[Any] = [Literal(zone_light_levels[zone]) for zone in sorted(zone_light_levels)]
        if callback_url:
            values.append(Literal(callback_url))
        if human_zones:
            values.append(_build_predicate_statement(graph, "human", [Literal(zone) for zone in human_zones]))
        print(f"[create_llm_goal_to_bdi_transformation] Constructed values={values}")

        values_head = BNode()
        Collection(graph, values_head, values)
        print(f"[create_llm_goal_to_bdi_transformation] Built RDF collection head={values_head}")

        construct_query = """
            PREFIX hmas: <https://purl.org/hmas/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX bdi:  <http://localhost:8082/ontologies/bdi#>

            CONSTRUCT {
                ?annotationId rdf:type hmas:Annotation .
                ?annotationId hmas:recommendsAbility ?abilityNode .
                ?abilityNode rdf:type bdi:set_env .
                ?annotationId hmas:conveys ?actionNode .
                ?actionNode bdi:hasPredicate "set_env" .
                ?actionNode bdi:hasValues ?valuesHead .
            }
            WHERE {
                BIND(?annotationNode AS ?annotationId)
                BIND(?abilityBinding AS ?abilityNode)
                BIND(?actionBinding AS ?actionNode)
                BIND(?valuesBinding AS ?valuesHead)
            }
        """
        graph += _construct_graph(
            construct_query,
            {
                "annotationNode": annotation_id,
                "abilityBinding": ability_node,
                "actionBinding": action_node,
                "valuesBinding": values_head,
            },
        )
        _copy_annotation_metadata(annotation_id, graph, annotation)
        print(f"[create_llm_goal_to_bdi_transformation] Finished transformation for annotation={annotation_id}")
        return Annotation(annotation_id, graph)

    return Transformation(transformation)


def create_llm_bdi_ability_transformation():
    def transformation(profile: Profile, annotation: Annotation):
        print("apply llm bdi ability transformation")
        print(f"[create_llm_bdi_ability_transformation] Start for profile={profile.id} annotation={annotation.url}")
        select_query = """
            PREFIX hmas: <https://purl.org/hmas/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX llm:  <http://example.org/llm#>

            SELECT ?text
            WHERE {
                FILTER(EXISTS { ?profile hmas:hasAbility ?profileAbility })
                FILTER(EXISTS { ?annotation hmas:recommendsAbility/rdf:type llm:llm_ability })
                ?annotation hmas:conveys ?action .
                ?action llm:text_action ?text .
            }
        """
        information = _select_information(profile, annotation, select_query)
        print(f"[create_llm_bdi_ability_transformation] SELECT rows={len(information)}")
        if not information:
            print("[create_llm_bdi_ability_transformation] No matching profile/annotation information found.")
            return None

        text = str(information[0]["text"])
        print(f"[create_llm_bdi_ability_transformation] Extracted text={text!r}")

        llm = _load_transformation_llm()
        prompt = _build_bdi_ability_prompt(profile, text)
        response = llm.invoke(prompt)
        response_text = _extract_text_response_content(response)
        print(f"[create_llm_bdi_ability_transformation] LLM response={response_text!r}")

        literal_spec = _parse_agentspeak_literal(response_text)
        if literal_spec is None:
            print("[create_llm_bdi_ability_transformation] LLM response could not be parsed as an AgentSpeak literal.")
            return None

        recommended_ability = _select_bdi_recommended_ability(profile, literal_spec["predicate"])
        if recommended_ability is None:
            print("[create_llm_bdi_ability_transformation] No compatible BDI ability found in the target profile.")
            return None

        annotation_id = URIRef(str(annotation.url))
        graph = Graph()
        ability_node = BNode()
        graph.add((annotation_id, RDF.type, HMAS.Annotation))
        graph.add((annotation_id, HMAS.recommendsAbility, ability_node))
        graph.add((ability_node, RDF.type, recommended_ability))

        action_node = _agentspeak_literal_to_rdf(graph, literal_spec)
        graph.add((annotation_id, HMAS.conveys, action_node))
        _copy_annotation_metadata(annotation_id, graph, annotation)
        print(f"[create_llm_bdi_ability_transformation] Finished transformation for annotation={annotation_id}")
        return Annotation(annotation_id, graph)

    return Transformation(transformation)
