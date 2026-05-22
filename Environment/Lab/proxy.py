import os
import json
import threading
import time
import argparse
from decimal import Decimal

from flask import Flask, request, jsonify, Response
import requests
from rdflib import Graph, URIRef, Literal, RDF, BNode, Namespace, XSD

from config_loader import load_config
from ontologies import HMAS, LabOnt

app = Flask(__name__)

# === Configuration ===
config = load_config()
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--real", action="store_true")
_args, _ = _parser.parse_known_args()

TARGET_BASE = (
    "https://api.interactions.unisg.ch/was/rl"
    if _args.real
    else "http://localhost:1880/was/rl/"
)
STATUS_PATH = "status"
ACTION_PATH = "action"

def _join_base(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


STATUS_URL = _join_base(TARGET_BASE, STATUS_PATH)
ACTION_URL = _join_base(TARGET_BASE, ACTION_PATH)

CONTROL_URL = config["control_url"]

# Administrative enable/disable state for each device.
device_enabled = {"B1": True, "B2": True, "L1": True, "L2": True}

HCTL = Namespace("https://www.w3.org/2019/wot/hypermedia#")
HTTP = Namespace("http://www.w3.org/2011/http#")
TD = Namespace("https://www.w3.org/2019/wot/td#")
SH = Namespace("http://www.w3.org/ns/shacl#")
SCHEMA = Namespace("http://schema.org/")


class _ProxyEnvironment:
    def get_state(self) -> Graph:
        return _build_env_kg()


# === Helpers ===
SESSION = requests.Session()
DEFAULT_TIMEOUT = 6


def fwd_response(r: requests.Response) -> Response:
    headers = {}
    ct = r.headers.get("Content-Type")
    if ct:
        headers["Content-Type"] = ct
    return Response(r.content, status=r.status_code, headers=headers)


def call_action(payload: dict) -> requests.Response:
    return requests.post(
        ACTION_URL,
        json=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )


def _local_base_url() -> str:
    return request.host_url.rstrip("/")


def _local_action_url() -> str:
    return f"{_local_base_url()}/action"


def _local_control_url() -> str:
    return f"{_local_base_url()}/control"


def _bind_common_namespaces(kg: Graph) -> None:
    kg.bind("lab", LabOnt.LabN)
    kg.bind("hmas", HMAS.HMAS)
    kg.bind("http", HTTP)
    kg.bind("hctl", HCTL)
    kg.bind("td", TD)
    kg.bind("sh", SH)
    kg.bind("schema", SCHEMA, override=True, replace=True)


def _current_state_iri() -> URIRef:
    return URIRef(f"{LabOnt.LabN}currentState")


def _decimal_literal(value):
    return Literal(str(Decimal(str(value))), datatype=XSD.decimal)


def _status_snapshot(statuses: dict | None = None) -> dict:
    base = dict(device_enabled)
    if statuses:
        base.update(statuses)
    return base


def _snapshot_with_statuses(snapshot: dict, statuses: dict | None = None) -> dict:
    enriched = dict(snapshot)
    status_snapshot = _status_snapshot(statuses)
    enriched.update(
        {
            "L1Status": status_snapshot["L1"],
            "L2Status": status_snapshot["L2"],
            "B1Status": status_snapshot["B1"],
            "B2Status": status_snapshot["B2"],
        }
    )
    _normalize_disabled_device_states(enriched)
    return enriched


def _normalize_disabled_device_states(snapshot: dict) -> None:
    """Disabled devices are always represented as off in the KG snapshot."""
    if not snapshot.get("L1Status", True):
        snapshot["Z1Light"] = False
    if not snapshot.get("L2Status", True):
        snapshot["Z2Light"] = False
    if not snapshot.get("B1Status", True):
        snapshot["Z1Blinds"] = False
    if not snapshot.get("B2Status", True):
        snapshot["Z2Blinds"] = False


def _add_state_triples(kg: Graph, node, snapshot: dict) -> None:
    kg.add((node, LabOnt.hasZ1Light, Literal(snapshot.get("Z1Light", False))))
    kg.add((node, LabOnt.hasZ2Light, Literal(snapshot.get("Z2Light", False))))
    kg.add((node, LabOnt.hasZ1Blinds, Literal(snapshot.get("Z1Blinds", False))))
    kg.add((node, LabOnt.hasZ2Blinds, Literal(snapshot.get("Z2Blinds", False))))
    kg.add((node, LabOnt.hasZ1Level, _decimal_literal(snapshot.get("Z1Level", 0))))
    kg.add((node, LabOnt.hasZ2Level, _decimal_literal(snapshot.get("Z2Level", 0))))
    kg.add((node, LabOnt.hasSunshine, _decimal_literal(snapshot.get("Sunshine", 0))))
    kg.add((node, LabOnt.L1Status, Literal(snapshot.get("L1Status", True))))
    kg.add((node, LabOnt.L2Status, Literal(snapshot.get("L2Status", True))))
    kg.add((node, LabOnt.B1Status, Literal(snapshot.get("B1Status", True))))
    kg.add((node, LabOnt.B2Status, Literal(snapshot.get("B2Status", True))))


def _add_http_procedure(
    kg: Graph,
    env,
    state,
    label: str,
    request_uri: str,
    payload: dict,
    preconditions: list[tuple[URIRef, bool]],
    postconditions: list[tuple[URIRef, bool]],
) -> None:
    proc = BNode()
    op = BNode()
    pre = BNode()
    post = BNode()

    kg.add((env, HMAS.hasProcedure, proc))
    kg.add((proc, RDF.type, HMAS.ActionSpecification))
    kg.add((proc, SCHEMA.name, Literal(label)))
    kg.add((proc, HMAS.hasOperation, op))
    kg.add((proc, HMAS.hasPrecondition, pre))
    kg.add((proc, HMAS.hasPostcondition, post))

    kg.add((pre, RDF.type, SH.NodeShape))
    kg.add((pre, SH.targetNode, state))
    for predicate, expected_value in preconditions:
        prop_shape = BNode()
        kg.add((pre, SH.property, prop_shape))
        kg.add((prop_shape, SH.path, predicate))
        kg.add((prop_shape, SH.hasValue, Literal(expected_value)))

    kg.add((post, RDF.type, SH.NodeShape))
    kg.add((post, SH.targetNode, state))
    for predicate, expected_value in postconditions:
        prop_shape = BNode()
        kg.add((post, SH.property, prop_shape))
        kg.add((prop_shape, SH.path, predicate))
        kg.add((prop_shape, SH.hasValue, Literal(expected_value)))

    kg.add((op, RDF.type, HTTP.Request))
    kg.add((op, HTTP.methodName, Literal("POST")))
    kg.add((op, HTTP.requestURI, URIRef(request_uri)))
    kg.add((op, HTTP.body, Literal(json.dumps(payload))))


def _build_env_kg() -> Graph:
    """Build the environment KG from current device state and upstream status."""
    values = _snapshot_with_statuses(_read_remote_state())

    kg = Graph()
    _bind_common_namespaces(kg)
    env = LabOnt.myLab
    kg.add((env, RDF.type, LabOnt.Lab))

    state = _current_state_iri()
    kg.add((env, HMAS.hasState, state))
    _add_state_triples(kg, state, values)

    return kg


def _device_state(env_kg, state_prop):
    """Read device state from environment KG."""
    for _, pred, value in env_kg:
        if pred == state_prop and isinstance(value, Literal):
            return bool(value.toPython())
    return None


def _device_enabled(status_prop):
    """Check if a device is administratively enabled."""
    if status_prop == LabOnt.L1Status:
        return device_enabled.get("L1", True)
    if status_prop == LabOnt.L2Status:
        return device_enabled.get("L2", True)
    if status_prop == LabOnt.B1Status:
        return device_enabled.get("B1", True)
    if status_prop == LabOnt.B2Status:
        return device_enabled.get("B2", True)
    return True


def _read_remote_state() -> dict:
    try:
        r = requests.get(STATUS_URL, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        values = r.json()
        if not isinstance(values, dict):
            raise ValueError("status payload is not an object")
        return values
    except Exception:
        return {
            "Z1Light": False,
            "Z2Light": False,
            "Z1Blinds": False,
            "Z2Blinds": False,
            "Z1Level": 0,
            "Z2Level": 0,
            "Sunshine": 0,
        }


def _invoke_upstream_action(payload: dict) -> requests.Response:
    return requests.post(
        ACTION_URL,
        json=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )


def _device_action_payload(device: str, value: bool) -> dict:
    return {device: value}


def _device_to_upstream_field(device: str) -> str | None:
    mapping = {
        "L1": "Z1Light",
        "L2": "Z2Light",
        "B1": "Z1Blinds",
        "B2": "Z2Blinds",
    }
    return mapping.get(device)


def _device_is_active(snapshot: dict, device: str) -> bool:
    upstream_field = _device_to_upstream_field(device)
    if upstream_field is None:
        return False
    return bool(snapshot.get(upstream_field, False))

# === Recurrent Policy Management ===
_profile_recheck_state = {}
_recurrent_policy_thread_started = False




# === Proxy Endpoints ===

@app.get("/status")
def proxy_status():
    try:
        r = requests.get(STATUS_URL, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        return fwd_response(r)
    except requests.RequestException as e:
        return jsonify({"error": "Upstream status fetch failed", "detail": str(e)}), 502


@app.get("/devices")
def get_devices_status():
    return Response(json.dumps(device_enabled), 200, content_type="application/json")


@app.post("/control")
def control():
    global device_enabled

    if not request.is_json:
        return Response("The request is not valid", 400)

    r = request.get_json()
    if not isinstance(r, dict):
        return Response("The request is not valid", 400)

    device = r.get("device")
    activate = r.get("activate")

    if not isinstance(activate, bool) or device not in device_enabled:
        return Response("The request is not valid", 400)

    if activate:
        device_enabled[device] = True
        return Response(
            f"The request was executed successfully for device {device} and activate status: {activate}",
            200,
        )

    if _device_is_active(_read_remote_state(), device):
        upstream_field = _device_to_upstream_field(device)
        if upstream_field is None:
            return Response("The request is not valid", 400)

        response = _invoke_upstream_action(_device_action_payload(upstream_field, False))
        if response.status_code != 200:
            return Response(
                f"An error occurred with status code: {response.status_code} and reason: {response.text}",
                400,
            )

    device_enabled[device] = False
    return Response(
        f"The request was executed successfully for device {device} and activate status: {activate}",
        200,
    )


@app.post("/action")
def action():
    global config

    if not request.is_json:
        return Response("The request is not valid", 400)

    d = request.get_json()
    if not isinstance(d, dict):
        return Response("The request is not valid", 400)

    if all(k in d for k in ["Z1Light", "Z2Light", "Z1Blinds", "Z2Blinds"]):
        if not all(isinstance(d[k], bool) for k in ["Z1Light", "Z2Light", "Z1Blinds", "Z2Blinds"]):
            return Response("The request is not valid", 400)

        r = _invoke_upstream_action(d)

        if r.status_code == 200:
            return Response("The request was executed successfully", 200)

        return Response(f"An error occurred with status code: {r.status_code} and reason: {r.text}", 400)

    if len(d) != 1:
        return Response("The request is not valid", 400)

    key = next(iter(d))
    value = d[key]

    if key not in ["L1", "L2", "B1", "B2"] or not isinstance(value, bool):
        return Response("The request is not valid", 400)

    upstream_field = _device_to_upstream_field(key)
    if upstream_field is None:
        return Response("The request is not valid", 400)

    if not device_enabled.get(key, True):
        return Response(f"Device {key} is disabled and cannot be changed", 409)

    payload = {upstream_field: value}

    r = _invoke_upstream_action(payload)

    if r.status_code == 200:
        return Response("The request was executed successfully", 200)

    return Response(f"An error occurred with status code: {r.status_code} and reason: {r.text}", 400)




# === Thing Description ===

def _thing_description() -> dict:
    base_url = request.host_url.rstrip("/")
    return {
        "@context": [
            "https://www.w3.org/2022/wot/td/v1.1",
            {
                "hmas": str(HMAS.HMAS),
            },
        ],
        "id": f"{base_url}/light-proxy",
        "title": "Light Lab Proxy",
        "description": "HTTP proxy for lab device control with HMAS profile registration and annotation-based discovery.",
        "security": "nosec_sc",
        "securityDefinitions": {
            "nosec_sc": {"scheme": "nosec"},
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
                        "name": {"type": "string", "description": "Identifier for this profile"},
                        "url": {"type": "string", "format": "uri", "description": "URL of the external agent profile"},
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
                "forms": [
                    {
                        "href": f"{base_url}/annotations/",
                        "op": ["invokeaction"],
                        "htv:methodName": "GET",
                        "contentType": "text/turtle",
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
        ],
    }


@app.get("/td")
def get_td():
    return Response(
        json.dumps(_thing_description(), indent=2),
        200,
        content_type="application/td+json; charset=utf-8",
    )


# === Knowledge Graph with Procedures ===

@app.get("/kg")
def get_kg():
    try:
        r = requests.get(STATUS_URL, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        values = _snapshot_with_statuses(r.json())

        kg = Graph()
        _bind_common_namespaces(kg)
        env = LabOnt.myLab
        kg.add((env, RDF.type, LabOnt.Lab))

        state = _current_state_iri()
        kg.add((env, HMAS.hasState, state))
        _add_state_triples(kg, state, values)

        action_url = _local_action_url()
        control_url = _local_control_url()

        def add_action_procedure(device_label, state_prop, status_prop, expected_state, payload):
            _add_http_procedure(
                kg=kg,
                env=env,
                state=state,
                label=device_label,
                request_uri=action_url,
                payload=payload,
                preconditions=[
                    (state_prop, not expected_state),
                    (status_prop, True),
                ],
                postconditions=[(state_prop, expected_state)],
            )

        def add_control_procedure(device_label, status_prop, expected_status, device):
            _add_http_procedure(
                kg=kg,
                env=env,
                state=state,
                label=device_label,
                request_uri=control_url,
                payload={"device": device, "activate": expected_status},
                preconditions=[(status_prop, not expected_status)],
                postconditions=[(status_prop, expected_status)],
            )

        add_action_procedure("Turn on L1", LabOnt.hasZ1Light, LabOnt.L1Status, True, {"L1": True})
        add_action_procedure("Turn off L1", LabOnt.hasZ1Light, LabOnt.L1Status, False, {"L1": False})
        add_action_procedure("Turn on L2", LabOnt.hasZ2Light, LabOnt.L2Status, True, {"L2": True})
        add_action_procedure("Turn off L2", LabOnt.hasZ2Light, LabOnt.L2Status, False, {"L2": False})

        add_action_procedure("Open B1", LabOnt.hasZ1Blinds, LabOnt.B1Status, True, {"B1": True})
        add_action_procedure("Close B1", LabOnt.hasZ1Blinds, LabOnt.B1Status, False, {"B1": False})
        add_action_procedure("Open B2", LabOnt.hasZ2Blinds, LabOnt.B2Status, True, {"B2": True})
        add_action_procedure("Close B2", LabOnt.hasZ2Blinds, LabOnt.B2Status, False, {"B2": False})

        add_control_procedure("Enable L1", LabOnt.L1Status, True, "L1")
        add_control_procedure("Disable L1", LabOnt.L1Status, False, "L1")
        add_control_procedure("Enable L2", LabOnt.L2Status, True, "L2")
        add_control_procedure("Disable L2", LabOnt.L2Status, False, "L2")
        add_control_procedure("Enable B1", LabOnt.B1Status, True, "B1")
        add_control_procedure("Disable B1", LabOnt.B1Status, False, "B1")
        add_control_procedure("Enable B2", LabOnt.B2Status, True, "B2")
        add_control_procedure("Disable B2", LabOnt.B2Status, False, "B2")

        return Response(kg.serialize(format="turtle"), mimetype="text/turtle")

    except requests.RequestException as e:
        return jsonify({"error": "Upstream status fetch failed", "detail": str(e)}), 502


# === Health & Root Endpoints ===

@app.get("/health")
def health():
    return jsonify({"status": "ok", "target_base": TARGET_BASE}), 200


@app.get("/")
def root():
    return jsonify(
        {
            "message": "Light Lab Proxy",
            "endpoints": {
                "GET /status": "Proxy to TD property",
                "POST /action": "Proxy to TD action",
                "GET /devices": "Get device enablement status",
                "POST /control": "Enable or disable device access (L1, L2, B1, B2)",
                "GET /profiles": "List registered profiles",
                "POST /profiles": "Register profile",
                "POST /profiles/register": "Register profile by URL",
                "GET /annotations/": "Query annotations for profile URL",
                "GET /td": "Thing Description",
                "GET /kg": "Knowledge Graph with procedures",
                "GET /health": "Health check",
            },
            "upstream": {
                "status_url": STATUS_URL,
                "action_url": ACTION_URL,
            },
        }
    ), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8081)), debug=False)
