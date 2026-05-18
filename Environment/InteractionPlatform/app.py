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
from generation_creation import (
    create_disable_blinds_generation
)
from utils import annotations_url_from_id, generate_id, generate_url, _normalize_uri_node
from rdflib import BNode, Literal, RDF, XSD
from annotation_creation import create_predicate_signifier, create_llm_annotation, add_text_action
from rdflib.collection import Collection
from config_loader import load_config
from llm import load_llm
from transformation_creation import (
    create_bdi_llm_transformation as imported_create_bdi_llm_transformation,
    create_llm_bdi_ability_transformation as imported_create_llm_bdi_ability_transformation,
    create_llm_env_to_bdi_transformation as imported_create_llm_env_to_bdi_transformation,
    create_llm_goal_to_bdi_transformation as imported_create_llm_goal_to_bdi_transformation,
    create_soar_done_to_bdi_transformation as imported_create_soar_done_to_bdi_transformation,
    create_soar_wme_to_bdi_transformation as imported_create_soar_wme_to_bdi_transformation,
    create_state_to_soar_light_processing_transformation as imported_create_state_to_soar_light_processing_transformation,
)


app = Flask(__name__)
DEFAULT_PROFILE_CHECK_INTERVAL = 10.0
annotation_registry = AnnotationRegistry()
profile_registry = ProfileRegistry()
config = load_config()
HMAS_MESSAGE = HMAS.HMAS.Message
HMAS_MESSAGE_POLICY = HMAS.HMAS.MessagePolicy
HMAS_HAS_INTERACTION_POLICY = HMAS.HMAS.hasInteractionPolicy
HMAS_HAS_MESSAGE_URL = HMAS.HMAS.hasMessageUrl
HMAS_HAS_SENDER = HMAS.HMAS.hasSender
HMAS_HAS_RECEIVER = HMAS.HMAS.hasReceiver

SPARQL_NAMESPACES = {
    "rdf": RDF,
    "hmas": HMAS.HMAS,
    "lab": LabOnt.LabN,
    "soar": SoarOnt.SoarN,
    "bdi": BDIOnt.BDI,
    "llm": LLMOnt.LLMN,
}

ordered_transformations: list = []
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


def _register_ordered_transformation(transformation_fn) -> None:
    ordered_transformations.append(transformation_fn)
    selection.add_transformation(transformation_fn)


def _profile_has_ability(profile: Profile, ability: URIRef) -> bool:
    return ability in profile.get_abilities()


def _profile_has_goal_type(profile: Profile, goal_type: URIRef) -> bool:
    for goal_node in profile.model.objects(profile.id, HMAS.hasGoal):
        if (goal_node, RDF.type, goal_type) in profile.model:
            return True
    return False





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
        document_url, _ = urldefrag(uri)
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





def _light_is_on(environment_knowledge_graph: Graph) -> bool | None:
    for _, predicate, value in environment_knowledge_graph:
        if predicate != LabOnt.hasLightState:
            continue
        if isinstance(value, Literal) and value.datatype == XSD.boolean:
            python_value = value.toPython()
            if isinstance(python_value, bool):
                return python_value
    return None








def _extract_json_object(text: str) -> str | None:
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match is not None:
        return fenced_match.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + 1]


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


def _normalize_set_env_mode(value: Any) -> str | None:
    normalized = str(value).strip().lower()
    if normalized in {"on", "open", "enable", "enabled", "true", "1", "high", "up"}:
        return "on"
    if normalized in {"off", "close", "closed", "disable", "disabled", "false", "0", "low", "down"}:
        return "off"
    if normalized in {"2", "3"}:
        return "on"
    return None

def _deduplicate_env_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    latest_by_device: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for action in actions:
        device = action["device"]
        if device not in latest_by_device:
            order.append(device)
        latest_by_device[device] = action
    return [latest_by_device[device] for device in order]


def _parse_text_env_actions(text: str) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    direct_patterns = [
        (
            r"\b(?:turn|switch|set)?\s*(?:the\s+)?(?:zone\s*([12])\s+)?(light|blinds)\s*(?:in\s+zone\s*([12]))?\s*(on|off|open|close)\b",
            False,
        ),
        (
            r"\b(?:turn|switch|set)\s*(on|off|open|close)\s*(?:the\s+)?(?:zone\s*([12])\s+)?(light|blinds)\b",
            True,
        ),
    ]

    for pattern, mode_first in direct_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if mode_first:
                raw_mode = match.group(1)
                zone = match.group(2)
                item_type = match.group(3)
            else:
                zone = match.group(1) or match.group(3)
                item_type = match.group(2)
                raw_mode = match.group(4)
            if zone is None:
                continue
            device = f"{'L' if item_type.lower() == 'light' else 'B'}{zone}"
            mode = _normalize_set_env_mode(raw_mode)
            if mode is not None:
                actions.append({"device": device, "mode": mode})

    for match in re.finditer(r"\bzone\s*([12])\b[^.!\n]*\blight level\b\s*([123])\b", text, re.IGNORECASE):
        zone = match.group(1)
        level = match.group(2)
        mode = _normalize_set_env_mode(level)
        if mode is not None:
            actions.append({"device": f"L{zone}", "mode": mode})

    return _deduplicate_env_actions(actions)


def _normalize_http_payload(raw_body: str | None) -> str:
    if raw_body is None:
        return ""

    body = str(raw_body).strip()
    if not body:
        return ""

    try:
        parsed = json.loads(body)
        return json.dumps(parsed, separators=(",", ":"))
    except json.JSONDecodeError:
        pass

    json_like = (
        body.replace("'", '"')
        .replace(": True", ": true")
        .replace(": False", ": false")
        .replace(": None", ": null")
    )
    try:
        parsed = json.loads(json_like)
        return json.dumps(parsed, separators=(",", ":"))
    except json.JSONDecodeError:
        pass

    import ast

    try:
        parsed = ast.literal_eval(body)
        return json.dumps(parsed, separators=(",", ":"))
    except Exception:
        return body


def _extract_bdi_predicate(annotation: Annotation) -> str | None:
    action_node = annotation.model.value(annotation.url, HMAS.conveys)
    if action_node is None:
        return None
    for _, _, pred in annotation.model.triples((action_node, BDIOnt.hasPredicate, None)):
        return str(pred)
    return None


def _extract_bdi_values(annotation: Annotation) -> list[str]:
    values: list[str] = []
    action_node = annotation.model.value(annotation.url, HMAS.conveys)
    if action_node is None:
        return values
    for _, _, value_head in annotation.model.triples((action_node, BDIOnt.hasValues, None)):
        for item in annotation.model.items(value_head):
            if isinstance(item, (URIRef, BNode)):
                nested_predicate = None
                nested_values: list[str] = []
                for _, _, pred in annotation.model.triples((item, BDIOnt.hasPredicate, None)):
                    nested_predicate = str(pred)
                    break
                for _, _, nested_head in annotation.model.triples((item, BDIOnt.hasValues, None)):
                    nested_values = [str(nested_item) for nested_item in annotation.model.items(nested_head)]
                    break
                if nested_predicate is not None:
                    values.append(" ".join([nested_predicate, *nested_values]).strip())
                    continue
            values.append(str(item))
        break
    return values


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


def _extract_goal_state_payload(annotation: Annotation) -> tuple[int, int, str] | None:
    action_node = annotation.model.value(annotation.url, HMAS.conveys)
    if action_node is None:
        return None

    predicate = annotation.model.value(action_node, BDIOnt.hasPredicate)
    if predicate is None or str(predicate) != "goal":
        return None

    values_head = annotation.model.value(action_node, BDIOnt.hasValues)
    if values_head is None:
        return None

    values = list(annotation.model.items(values_head))
    if len(values) != 2:
        return None

    state_node, profile_value = values
    if not isinstance(state_node, (URIRef, BNode)):
        return None

    state_predicate = annotation.model.value(state_node, BDIOnt.hasPredicate)
    if state_predicate is None or str(state_predicate) != "state":
        return None

    state_values_head = annotation.model.value(state_node, BDIOnt.hasValues)
    if state_values_head is None:
        return None

    state_values = list(annotation.model.items(state_values_head))
    if len(state_values) != 2:
        return None

    z1 = _coerce_numeric_literal_to_int(state_values[0])
    z2 = _coerce_numeric_literal_to_int(state_values[1])
    if z1 is None or z2 is None:
        return None

    goal_url = str(profile_value)
    if not goal_url:
        return None

    return z1, z2, goal_url


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


def _register_profile_from_payload(payload) -> tuple[str, int]:
    if not isinstance(payload, dict):
        return "Invalid JSON payload", 400

    name = payload.get("name")
    profile_type = payload.get("type")
    profile_received = payload.get("profile")

    if not isinstance(name, str) or not name:
        return "Profile name is required", 400

    if profile_type == "local":
        if profile_received is None:
            return "Profile payload is required", 400
        profile_graph = Graph()
        try:
            profile_graph.parse(data=json.dumps(profile_received), format="json-ld")
        except Exception:
            return "Profile payload is not valid JSON-LD", 400
        profile = Profile.parse_profile(profile_graph)
        if profile is None:
            return "The profile is not valid", 400
        if profile_registry.add_profile(name, profile):
            return "Profile added successfully", 200
        return "The profile is not valid", 400

    if profile_type == "external":
        if not isinstance(profile_received, str) or not profile_received:
            return "Profile URL is required", 400
        profile_registry.add_profile_from_url(name, profile_received)
        return "Profile added successfully from external URL", 200

    return "The type of the profile is not valid", 400


def _get_profile_recurrent_policies(profile: Profile):
    policies = []
    policy_nodes = set(profile.model.objects(profile.id, HMAS.hasAnnotationPolicy))
    policy_nodes.update(profile.model.objects(profile.id, HMAS.hasInteractionPolicy))
    policy_nodes.update(profile.model.objects(profile.id, HMAS.hasRecurrentPolicy))

    for policy_node in policy_nodes:
        if profile.model.value(policy_node, RDF.type) not in {None, HMAS.RecurrentPolicy}:
            continue

        repetition_time = profile.model.value(policy_node, HMAS.hasRepetitionTime)
        callback_url = profile.model.value(policy_node, HMAS.hasCallbackUrl)
        if callback_url is None:
            continue

        try:
            repetition_seconds = (
                DEFAULT_PROFILE_CHECK_INTERVAL
                if repetition_time is None
                else float(repetition_time.toPython())
            )
        except (AttributeError, TypeError, ValueError):
            continue

        callback_value = str(callback_url.toPython() if hasattr(callback_url, "toPython") else callback_url)
        if repetition_seconds <= 0 or not callback_value:
            continue

        policies.append(
            {
                "policy_node": policy_node,
                "repetition_time": repetition_seconds,
                "callback_url": callback_value,
            }
        )

    return policies


def _select_annotations_for_profile(profile: Profile):
    return selection.find(
        profile,
        selection.environment_kg,
        selection.annotations,
        list(selection.generations),
        list(selection.transformations),
    )


def _serialize_annotations_as_json_ld(annotations):
    graph = Graph()
    for annotation in annotations:
        graph += annotation.model
    return graph.serialize(format="json-ld")


def _post_annotations_to_callback(callback_url: str, annotations):
    payload = _serialize_annotations_as_json_ld(annotations)
    response = requests.post(
        callback_url,
        data=payload,
        headers={"Content-Type": "application/ld+json"},
        timeout=10,
    )
    response.raise_for_status()
    return response


def _resolve_registered_profile(profile_name: str) -> tuple[Profile | None, str]:
    profile_entry = profile_registry.profiles.get(profile_name)
    if not isinstance(profile_entry, dict):
        return None, ""

    if profile_entry.get("type") == "external":
        profile_url = str(profile_entry.get("profile", ""))
        if not profile_url:
            return None, ""
        return _load_profile_from_url(profile_url), profile_url

    profile = profile_entry.get("profile")
    if isinstance(profile, Profile):
        return profile, str(profile.id)

    return None, ""


def _dispatch_callback_annotations(profile_name: str, profile: Profile, profile_url: str, policy: dict) -> None:
    print(
        "Applying recurrent policy",
        policy["policy_node"],
        "to profile",
        profile_name,
        f"({profile_url})",
        "with callback",
        policy["callback_url"],
    )

    annotations = _select_annotations_for_profile(profile)
    print(
        "Recurrent policy selection results for profile",
        profile_name,
        ":",
        sorted(str(annotation.url) for annotation in annotations),
    )
    if not annotations:
        print("Recurrent policy skipped for profile", profile_name, "because no annotations were selected")
        return

    _post_annotations_to_callback(policy["callback_url"], annotations)
    print(
        "Recurrent policy delivered",
        len(annotations),
        "annotation(s) to profile",
        profile_name,
        "via",
        policy["callback_url"],
    )


def _run_recurrent_policy_selection():
    while True:
        _dispatch_registered_profile_callbacks()
        time.sleep(1.0)


def _dispatch_registered_profile_callbacks(now: float | None = None) -> None:
    dispatch_time = time.monotonic() if now is None else now
    profile_names = list(profile_registry.available_profiles())

    for profile_name in profile_names:
        next_check = _profile_recheck_state.get(profile_name, 0.0)
        if dispatch_time < next_check:
            continue

        try:
            profile, profile_url = _resolve_registered_profile(profile_name)
        except Exception as exc:
            print(f"Failed to resolve profile {profile_name}: {exc}")
            _profile_recheck_state[profile_name] = dispatch_time + DEFAULT_PROFILE_CHECK_INTERVAL
            continue

        if profile is None:
            print("Skipping recurrent policy check for profile", profile_name, "because the profile could not be loaded")
            _profile_recheck_state[profile_name] = dispatch_time + DEFAULT_PROFILE_CHECK_INTERVAL
            continue

        policies = _get_profile_recurrent_policies(profile)
        next_interval = DEFAULT_PROFILE_CHECK_INTERVAL
        if policies:
            next_interval = min(policy["repetition_time"] for policy in policies)
            print(
                "Found",
                len(policies),
                "recurrent policy/policies for profile",
                profile_name,
                f"({profile_url})",
                "with next interval",
                next_interval,
                "seconds",
            )
        else:
            print("No recurrent policy found for profile", profile_name, f"({profile_url})")

        for policy in policies:
            try:
                _dispatch_callback_annotations(profile_name, profile, profile_url, policy)
            except Exception as exc:
                print(
                    f"Recurrent policy execution failed for profile {profile_name} "
                    f"with callback {policy['callback_url']}: {exc}"
                )

        _profile_recheck_state[profile_name] = dispatch_time + next_interval
        print(
            "Next recurrent policy check for profile",
            profile_name,
            "scheduled in",
            next_interval,
            "seconds",
        )


def _start_recurrent_policy_worker():
    global _recurrent_policy_thread_started

    if _recurrent_policy_thread_started:
        return

    worker = threading.Thread(target=_run_recurrent_policy_selection, daemon=True)
    worker.start()
    _recurrent_policy_thread_started = True


def _get_direct_callback_url(profile: Profile) -> str | None:
    policy_nodes = set(profile.model.objects(profile.id, HMAS.hasAnnotationPolicy))
    policy_nodes.update(profile.model.objects(profile.id, HMAS.hasInteractionPolicy))
    policy_nodes.update(profile.model.objects(profile.id, HMAS.hasRecurrentPolicy))

    for policy_node in policy_nodes:
        if profile.model.value(policy_node, RDF.type) not in {None, HMAS.RecurrentPolicy}:
            continue
        callback_url = profile.model.value(policy_node, HMAS.hasCallbackUrl)
        if callback_url is None:
            continue
        callback_value = str(callback_url.toPython() if hasattr(callback_url, "toPython") else callback_url)
        if callback_value:
            return callback_value
    return None


def _get_direct_message_url(profile: Profile) -> str | None:
    for policy_node in profile.model.objects(profile.id, HMAS_HAS_INTERACTION_POLICY):
        if profile.model.value(policy_node, RDF.type) != HMAS_MESSAGE_POLICY:
            continue
        message_url = profile.model.value(policy_node, HMAS_HAS_MESSAGE_URL)
        if message_url is None:
            continue
        message_value = str(message_url.toPython() if hasattr(message_url, "toPython") else message_url)
        if message_value:
            return message_value
    return None


def _materialize_subject_by_type(graph: Graph, rdf_type: URIRef) -> tuple[URIRef, Graph] | None:
    for subject in graph.subjects(RDF.type, rdf_type):
        if isinstance(subject, URIRef):
            return subject, graph

    for subject in graph.subjects(RDF.type, rdf_type):
        if not isinstance(subject, BNode):
            continue

        materialized_subject = generate_url()
        rewritten_graph = Graph()
        for triple_subject, predicate, triple_object in graph:
            new_subject = materialized_subject if triple_subject == subject else triple_subject
            new_object = materialized_subject if triple_object == subject else triple_object
            rewritten_graph.add((new_subject, predicate, new_object))
        return materialized_subject, rewritten_graph

    return None


def _wrap_message(message_id: URIRef, graph: Graph) -> Annotation:
    message = Annotation(message_id, graph)
    message.model.remove((message.url, RDF.type, HMAS.Annotation))
    message.model.remove((message.url, RDF.type, HMAS.Signifier))
    message.model.add((message.url, RDF.type, HMAS_MESSAGE))
    return message


def _is_message(input_resource: TransformationInput) -> bool:
    return (input_resource.url, RDF.type, HMAS_MESSAGE) in input_resource.model


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


def _parse_message_payload(message_payload) -> Annotation | None:
    graph = Graph()
    try:
        graph.parse(data=json.dumps(message_payload), format="json-ld")
    except Exception:
        return None

    materialized = _materialize_subject_by_type(graph, HMAS_MESSAGE)
    if materialized is None:
        return None

    message_id, materialized_graph = materialized
    message = _wrap_message(message_id, materialized_graph)
    if (
        message.model.value(message.url, HMAS_HAS_SENDER) is None
        or message.model.value(message.url, HMAS_HAS_RECEIVER) is None
    ):
        return None

    return message


def _parse_annotation_payload(annotation_payload) -> Annotation | None:
    graph = Graph()
    try:
        graph.parse(data=json.dumps(annotation_payload), format="json-ld")
    except Exception:
        return None

    parsed_annotation = Annotation.parse_annotation(graph)
    if parsed_annotation is not None:
        return parsed_annotation

    for annotation_type in (HMAS.Annotation, HMAS.Signifier):
        for subject in graph.subjects(RDF.type, annotation_type):
            if not isinstance(subject, BNode):
                continue

            materialized_subject = generate_url()
            rewritten_graph = Graph()
            for triple_subject, predicate, triple_object in graph:
                new_subject = materialized_subject if triple_subject == subject else triple_subject
                new_object = materialized_subject if triple_object == subject else triple_object
                rewritten_graph.add((new_subject, predicate, new_object))

            return Annotation(materialized_subject, rewritten_graph)

    return None


def _annotation_fingerprint(annotation: Annotation) -> str:
    return annotation.model.serialize(format="nt")


def _transformed_message_preserves_transport_fields(
    source_message: Annotation,
    transformed: Annotation,
) -> bool:
    source_sender = source_message.model.value(source_message.url, HMAS_HAS_SENDER)
    source_receiver = source_message.model.value(source_message.url, HMAS_HAS_RECEIVER)
    transformed_sender = transformed.model.value(transformed.url, HMAS_HAS_SENDER)
    transformed_receiver = transformed.model.value(transformed.url, HMAS_HAS_RECEIVER)

    if transformed_sender is not None and transformed_sender != source_sender:
        return False
    if transformed_receiver is not None and transformed_receiver != source_receiver:
        return False
    return True


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
    for sender in source.model.objects(source.url, HMAS_HAS_SENDER):
        graph.add((message_id, HMAS_HAS_SENDER, sender))
    for receiver in source.model.objects(source.url, HMAS_HAS_RECEIVER):
        graph.add((message_id, HMAS_HAS_RECEIVER, receiver))

def _build_forward_message(source_message: Annotation, transformed: Annotation) -> Annotation | None:
    if not _transformed_message_preserves_transport_fields(source_message, transformed):
        return None

    graph = Graph()
    graph += transformed.model
    graph.remove((transformed.url, RDF.type, HMAS.Annotation))
    graph.remove((transformed.url, RDF.type, HMAS.Signifier))
    graph.add((transformed.url, RDF.type, HMAS_MESSAGE))
    _copy_message_transport_metadata(transformed.url, graph, source_message)
    return _wrap_message(URIRef(str(transformed.url)), graph)


def _resolve_direct_annotation(profile: Profile, annotation: Annotation) -> Annotation | None:
    transformations = list(selection.transformations)
    selection.add_runtime_transformations(transformations, profile, Graph())

    pending = [annotation]
    visited: set[str] = set()

    while pending:
        current = pending.pop(0)
        fingerprint = _annotation_fingerprint(current)
        if fingerprint in visited:
            continue
        visited.add(fingerprint)

        if selection.ability_match(profile, current):
            return current

        for transformation in transformations:
            transformed = transformation(profile, current)
            if transformed is None:
                continue
            transformed_fingerprint = _annotation_fingerprint(transformed)
            if transformed_fingerprint not in visited:
                pending.append(transformed)

    return None


def _resolve_direct_message(profile: Profile, message: Annotation) -> Annotation | None:
    direct_message = _build_forward_message(message, message)
    if direct_message is not None and selection.ability_match(profile, direct_message):
        return direct_message

    transformations = list(ordered_transformations)
    selection.add_runtime_transformations(transformations, profile, Graph())

    for transformation in transformations:
        transformed = transformation(profile, message)
        if transformed is None:
            continue

        resolved_message = _build_forward_message(message, transformed)
        if resolved_message is None:
            continue
        if selection.ability_match(profile, resolved_message):
            return resolved_message

    return None



environment = Environment(URIRef("http://localhost:8081/kg"))
selection = Selection(profile_registry, annotation_registry, environment)
_recurrent_policy_thread_started = False
_profile_recheck_state = {}

# Generation functions are imported from the proxy module.
selection.add_generation(create_disable_blinds_generation().get_function())

# Transformation functions are defined locally in this module so Setup has no
# runtime dependency on transformation factories from other files.
_register_ordered_transformation(imported_create_bdi_llm_transformation().get_function())
_register_ordered_transformation(imported_create_state_to_soar_light_processing_transformation().get_function())
_register_ordered_transformation(imported_create_soar_done_to_bdi_transformation().get_function())
#_register_ordered_transformation(imported_create_llm_env_to_bdi_transformation().get_function())
_register_ordered_transformation(imported_create_llm_goal_to_bdi_transformation().get_function())
#_register_ordered_transformation(imported_create_llm_bdi_ability_transformation().get_function())


@app.get("/kg")
def get_kg():
    return Response(environment.get_state().serialize(format="turtle"), 200, content_type="text/turtle")

@app.route("/annotations_nl/", methods=["POST"])
def add_annotation_nl():
    annotation_id = generate_id()
    value = request.form.get('annotation')
    if value is None:
        return Response("The annotation does not have a content", 400)
    s = create_llm_annotation(annotation_id)
    add_text_action(s, value)
    creator = request.form.get('creator')
    if creator is not None:
        creator_uri = _normalize_uri_node(creator)
        if creator_uri is None:
            return Response("The annotation creator must be a non-empty URI", 400)
        s.add_triple(s.url, HMAS.hasCreator, creator_uri)
    else:
        return Response("The annotation does not have a creator", 400)
    #s.add_type(URIRef("http://example.org/NLGoalSignifier"))
    #s.add_type(SigOnt.GoalSignifier)

    # Convert the "model" to an rdflib Graph
    # graph = Graph()
    # graph.add((annotation_id, URIRef("https://example.org/hasNLMessage"), Literal(req_data)))
    # s = Annotation(annotation_id, graph)
    annotation_registry.add_annotation(s)
    return Response(
        str(s.url),
        201,
        headers={
            "Content-Type": "text/uri-list; charset=utf-8",
            "Location": str(s.url),
        },
    )


@app.get("/annotations/<annotation_id>")
def get_annotation_from_id(annotation_id):
    annotation_url = annotations_url_from_id(annotation_id)
    annotation_found = annotation_registry.get_by_id(annotation_url)
    if annotation_found is None:
        return "", 404
    return Response(str(annotation_found), 200, mimetype="text/turtle")


@app.get("/profiles")
def get_all_profiles():
    g = Graph()
    for key in profile_registry.available_profiles():
        profile = profile_registry.get_profile(key)
        if profile is not None:
            g += profile.model
    return Response(g.serialize(format="turtle"), 200, content_type="text/turtle")


@app.post("/annotations/")
def add_annotation():
    if not request.is_json:
        return "Invalid JSON payload", 400

    req_data = request.get_json()
    graph = Graph()
    try:
        graph.parse(data=json.dumps(req_data), format="json-ld")
    except Exception:
        return "Annotation payload is not valid JSON-LD", 400

    ann_url = None
    for s, _, _ in graph.triples((None, RDF.type, HMAS.Annotation)):
        ann_url = s
        break

    if not isinstance(ann_url, URIRef):
        return "Annotation is not correct", 400

    annotation_registry.add_annotation(Annotation(ann_url, graph))
    return "Annotation successfully added", 200


@app.post("/messages")
def add_message_direct():
    print("receive message")
    if not request.is_json:
        print("invalid payload for message")
        return "Invalid payload: not JSON", 400

    req_data = request.get_json()
    if not isinstance(req_data, dict):
        print("invalid JSON payload for message")
        return "Invalid JSON payload", 400

    profile_url = req_data.get("agent")
    message_payload = req_data.get("message")

    if not isinstance(profile_url, str) or not profile_url:
        print("profile URL not valid for message")
        return "Agent profile URL is required", 400
    if message_payload is None:
        print("no message payload")
        return "Message payload is required", 400

    message = _parse_message_payload(message_payload)
    if message is None:
        print("message payload is not valid JSON-LD")
        return "Message payload is not a valid JSON-LD message", 400

    profile = _load_profile_from_url(profile_url)
    if profile is None:
        print("profile could not be retrieved for message")
        return "Profile could not be retrieved", 400

    message_url = _get_direct_message_url(profile)
    if message_url is None:
        print("no message policy URL found")
        return "No message policy URL found", 400

    resolved_message = _resolve_direct_message(profile, message)
    if resolved_message is None:
        print("no valid message for agent abilities")
        return "No valid message found for agent abilities", 500

    try:
        response = requests.post(
            message_url,
            data=resolved_message.model.serialize(format="json-ld"),
            headers={"Content-Type": "application/ld+json"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        print("message could not be forwarded")
        return "Message could not be forwarded", 400

    return Response("", 200)


@app.post("/profiles")
def register_profiles():
    if not request.is_json:
        return "Invalid JSON payload", 400
    message, status = _register_profile_from_payload(request.get_json())
    return message, status


@app.post("/profiles/register")
def register_profile_external():
    if not request.is_json:
        return "Invalid JSON payload", 400
    payload = request.get_json()
    if not isinstance(payload, dict):
        return "Invalid JSON payload", 400
    name = payload.get("name")
    url = payload.get("url")
    if not isinstance(name, str) or not name:
        return "Profile name is required", 400
    if not isinstance(url, str) or not url:
        return "Profile URL is required", 400
    profile_registry.add_profile_from_url(name, url)
    return "Profile added successfully", 200


@app.get("/annotations/")
def get_annotations():
    profile_url = request.args.get("profile")
    if not isinstance(profile_url, str) or not profile_url:
        return "Profile URL is required", 400
    response = requests.get(profile_url, timeout=10)
    if not response.ok:
        return "Profile could not be retrieved", 400
    graph = Graph()
    for rdf_format in ("json-ld", "turtle", "xml"):
        try:
            graph.parse(data=response.text, format=rdf_format, publicID=profile_url)
            profile = Profile.parse_profile(graph)
            if profile is not None:
                break
        except Exception:
            continue
    else:
        return "Profile could not be retrieved", 400
    annotations = selection.find(
        profile,
        environment.get_state(),
        selection.annotations,
        list(selection.generations),
        list(selection.transformations),
    )
    if not annotations:
        return "", 404
    out = Graph()
    for annotation in annotations:
        out += annotation.model
    return Response(out.serialize(format="turtle"), 200, content_type="text/turtle")

@app.get("/td")
def get_td():
    base_url = request.host_url.rstrip("/")
    return Response(
        json.dumps(
            {
                "@context": [
                    "https://www.w3.org/2022/wot/td/v1.1",
                    {"hmas": str(HMAS.HMAS)},
                ],
                "id": f"{base_url}/setup4",
                "title": "SEMpy Setup 4 Application",
                "description": "Application for profile registration, annotation access, and proxy-backed environment discovery.",
                "security": "nosec_sc",
                "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
                "properties": {
                    "environment": {
                        "description": "Proxy-backed environment knowledge graph.",
                        "forms": [
                            {
                                "href": f"{base_url}/kg",
                                "op": ["readproperty"],
                                "htv:methodName": "GET",
                                "contentType": "text/turtle",
                            }
                        ],
                    },
                    "profiles": {
                        "description": "Registered profiles known by the application.",
                        "forms": [
                            {
                                "href": f"{base_url}/profiles",
                                "op": ["readproperty"],
                                "htv:methodName": "GET",
                                "contentType": "text/turtle",
                            }
                        ],
                    },
                },
                "actions": {
                    "registerProfile": {
                        "@type": ["hmas:registerProfile"],
                        "description": "Register an external agent profile.",
                        "safe": False,
                        "idempotent": False,
                        "input": {
                            "type": "object",
                            "required": ["name", "url"],
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Identifier for this profile",
                                },
                                "url": {
                                    "type": "string",
                                    "format": "uri",
                                    "description": "URL of the external agent profile",
                                },
                            },
                        },
                        "forms": [
                            {
                                "href": f"{base_url}/profiles/register",
                                "op": ["invokeaction"],
                                "htv:methodName": "POST",
                                "contentType": "application/json",
                            }
                        ],
                    },
                    "queryAnnotations": {
                        "@type": ["hmas:queryAnnotations"],
                        "description": "Query annotations for a profile URL using the profile query parameter.",
                        "safe": True,
                        "idempotent": True,
                        "input": {
                            "type": "object",
                            "required": ["profile"],
                            "properties": {
                                "profile": {
                                    "type": "string",
                                    "format": "uri",
                                    "description": "URL of the agent profile used to select annotations.",
                                }
                            },
                        },
                        "forms": [
                            {
                                "href": f"{base_url}/annotations/",
                                "op": ["invokeaction"],
                                "htv:methodName": "GET",
                                "contentType": "text/turtle",
                            }
                        ],
                    },
                    "messages": {
                        "@type": ["hmas:MessagePolicy"],
                        "description": "Forward a single message directly to an agent message endpoint.",
                        "safe": False,
                        "idempotent": False,
                        "forms": [
                            {
                                "href": f"{base_url}/messages",
                                "op": ["invokeaction"],
                                "htv:methodName": "POST",
                                "contentType": "application/json",
                            }
                        ],
                    },
                },
                "links": [
                    {
                        "href": f"{base_url}/kg",
                        "type": "text/turtle",
                        "rel": "describedby",
                    },
                    {
                        "href": f"{base_url}/profiles",
                        "type": "text/turtle",
                        "rel": "collection",
                    },
                    {
                        "href": f"{base_url}/annotations/",
                        "type": "text/turtle",
                        "rel": "collection",
                    },
                ],
            },
            indent=2,
        ),
        200,
        content_type="application/td+json; charset=utf-8",
    )


if __name__ == "__main__":
    _start_recurrent_policy_worker()
    app.run(host="0.0.0.0", debug=True, port=5001, use_reloader=False)
