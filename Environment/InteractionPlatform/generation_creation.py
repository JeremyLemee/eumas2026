import json
import time

from rdflib import BNode, Graph, Literal, RDF, URIRef, XSD
from rdflib.collection import Collection

from annotation_creation import add_text_action, create_llm_annotation, create_predicate_signifier
from components.annotation import Annotation
from components.generation import Generation
from components.profile import Profile
from ontologies import BDIOnt, HMAS, LabOnt, LLMOnt
from utils import _build_predicate_statement, generate_id, generate_url


def _device_state(env_kg, state_prop):
    """Read device state from environment KG."""
    for _, pred, value in env_kg:
        if pred == state_prop and isinstance(value, Literal):
            return bool(value.toPython())
    return None


def _get_profile_goal_types(agent_profile: Profile):
    goals = []
    for goal_node in agent_profile.model.objects(agent_profile.id, HMAS.hasGoal):
        goal_type = agent_profile.model.value(goal_node, RDF.type)
        if goal_type is not None:
            goals.append(goal_type)
    return goals


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

def create_disable_blinds_generation():
    goal_specs = {
        BDIOnt.disable_z1_blinds: {
            "predicate": "disable_z1_blinds",
            "status_path": LabOnt.B1Status,
        },
        BDIOnt.disable_z2_blinds: {
            "predicate": "disable_z2_blinds",
            "status_path": LabOnt.B2Status,
        },
    }

    def _select_goal_spec(agent_profile: Profile):
        for goal_node in agent_profile.model.objects(agent_profile.id, HMAS.hasGoal):
            goal_type = agent_profile.model.value(goal_node, RDF.type)
            if goal_type in goal_specs:
                return goal_specs[goal_type]
        return None

    def _literal_bool(value: Literal) -> bool | None:
        if not isinstance(value, Literal):
            return None

        python_value = value.toPython()
        if isinstance(python_value, bool):
            return python_value

        lexical = str(value).strip().lower()
        if lexical == "true":
            return True
        if lexical == "false":
            return False

        return None

    def _literal_equivalent(left, right) -> bool:
        if isinstance(left, Literal) and isinstance(right, Literal):
            left_bool = _literal_bool(left)
            right_bool = _literal_bool(right)
            if left_bool is not None and right_bool is not None:
                return left_bool == right_bool
            return left.toPython() == right.toPython()

        return left == right

    def _state_has_value(environment_kg: Graph, target_node, path, expected_value) -> bool:
        for value in environment_kg.objects(target_node, path):
            if _literal_equivalent(value, expected_value):
                return True
        return False

    def _extract_status_literal(environment_kg: Graph, target_node, status_path: URIRef) -> Literal | None:
        for value in environment_kg.objects(target_node, status_path):
            if isinstance(value, Literal) and _literal_bool(value) is not None:
                return value
        return None

    def _copy_node_subgraph(source_graph: Graph, source_node, target_graph: Graph, node_map=None, expanded=None):
        if source_node is None or isinstance(source_node, Literal):
            return source_node

        if node_map is None:
            node_map = {}
        if expanded is None:
            expanded = set()

        if source_node in node_map:
            target_node = node_map[source_node]
            if source_node in expanded:
                return target_node
        elif isinstance(source_node, BNode):
            target_node = BNode()
            node_map[source_node] = target_node
        else:
            target_node = source_node
            node_map[source_node] = target_node

        expanded.add(source_node)
        for predicate, obj in source_graph.predicate_objects(source_node):
            copied_obj = _copy_node_subgraph(source_graph, obj, target_graph, node_map, expanded)
            target_graph.add((target_node, predicate, copied_obj))

        return target_node

    def _select_action_information(environment_kg: Graph, status_path: URIRef):
        query = """
        PREFIX hmas:  <https://purl.org/hmas/>
        PREFIX hctl:  <https://www.w3.org/2019/wot/hypermedia#>
        PREFIX http:  <http://www.w3.org/2011/http#>
        PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX lab:   <http://example.org/lab#>
        PREFIX sh:    <http://www.w3.org/ns/shacl#>

        SELECT ?state ?procedure ?precondition ?sunshine ?method ?requestURI ?body ?contentType ?preTarget ?prePath ?preValue
        WHERE {
            ?env hmas:hasState ?state ;
                 hmas:hasProcedure ?procedure .
            ?state lab:hasSunshine ?sunshine .
            ?procedure
                       hmas:hasPostcondition ?postcondition ;
                       hmas:hasOperation ?operation .
            ?postcondition sh:targetNode ?postTarget ;
                           sh:property ?postProperty .
            ?postProperty sh:path ?postPath ;
                          sh:hasValue false .
            FILTER(?postPath = ?statusPath)
            ?operation rdf:type http:Request ;
                       http:methodName ?method ;
                       http:requestURI ?requestURI .
            OPTIONAL { ?operation http:body ?body . }
            OPTIONAL {
                ?procedure hmas:hasForm ?form .
                ?form hctl:forContentType ?contentType .
            }
            OPTIONAL {
                ?procedure hmas:hasPrecondition ?precondition .
                ?precondition sh:targetNode ?preTarget ;
                              sh:property ?preProperty .
                ?preProperty sh:path ?prePath ;
                             sh:hasValue ?preValue .
            }
        }
        """

        rows = list(
            environment_kg.query(
                query,
                initBindings={"statusPath": status_path},
            )
        )
        if not rows:
            return None

        row = rows[0]
        status_literal = _extract_status_literal(environment_kg, row.state, status_path)
        if status_literal is None:
            return None

        preconditions = []
        for candidate_row in rows:
            if (
                candidate_row.preTarget is not None
                and candidate_row.prePath is not None
                and candidate_row.preValue is not None
            ):
                precondition_tuple = (
                    candidate_row.preTarget,
                    candidate_row.prePath,
                    candidate_row.preValue,
                )
                if precondition_tuple not in preconditions:
                    preconditions.append(precondition_tuple)

        precondition_satisfied = all(
            _state_has_value(environment_kg, target_node, path, expected_value)
            for target_node, path, expected_value in preconditions
        )

        return {
            "sunshine": row.sunshine,
            "method": row.method,
            "request_uri": row.requestURI,
            "body": row.body,
            "content_type": row.contentType,
            "precondition": row.precondition,
            "status_literal": status_literal,
            "precondition_satisfied": precondition_satisfied,
        }

    def generation(agent_profile: Profile, environment_kg: Graph):
        print("create disable blinds generation")
        if BDIOnt.predicate_ability not in agent_profile.get_abilities():
            return set()

        goal_spec = _select_goal_spec(agent_profile)
        if goal_spec is None:
            return set()

        action_info = _select_action_information(environment_kg, goal_spec["status_path"])
        if action_info is None:
            return set()

        annotation = Annotation(generate_url(), Graph())
        ability_node = BNode()
        action_node = BNode()

        annotation.add_triple(annotation.url, RDF.type, HMAS.Annotation)
        annotation.add_triple(annotation.url, HMAS.recommendsAbility, ability_node)
        annotation.add_triple(ability_node, RDF.type, BDIOnt.predicate_ability)
        annotation.add_triple(annotation.url, HMAS.conveys, action_node)
        annotation.add_triple(action_node, BDIOnt.hasPredicate, Literal(goal_spec["predicate"]))

        if action_info["precondition"] is not None and action_info["precondition_satisfied"]:
            copied_precondition = _copy_node_subgraph(
                environment_kg,
                action_info["precondition"],
                annotation.model,
            )
            annotation.add_triple(annotation.url, HMAS.recommendsContext, copied_precondition)

        sunshine_value = (
            action_info["sunshine"]
            if isinstance(action_info["sunshine"], Literal)
            else Literal(str(action_info["sunshine"]))
        )
        values = [sunshine_value, action_info["status_literal"]]

        if action_info["precondition_satisfied"]:
            content_type = (
                str(action_info["content_type"])
                if action_info["content_type"] is not None
                else "application/json"
            )
            http_action = _build_predicate_statement(
                annotation.model,
                "http_action",
                [
                    Literal(str(action_info["method"])),
                    Literal(str(action_info["request_uri"])),
                    Literal(json.dumps({"Content-Type": content_type}, separators=(",", ":"))),
                    Literal(_normalize_http_payload(action_info["body"])),
                ],
            )
            values.append(http_action)

        values_head = BNode()
        Collection(annotation.model, values_head, values)
        annotation.add_triple(action_node, BDIOnt.hasValues, values_head)
        print("annotation created to disable blinds: ",annotation.model.serialize(format="turtle"))
        return {annotation}

    return Generation(generation)
