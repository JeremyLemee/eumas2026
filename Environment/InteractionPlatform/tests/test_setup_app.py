import json

import app as setup_app
import requests
from rdflib import BNode, Graph, Literal, RDF, RDFS, URIRef, XSD
from rdflib.collection import Collection

from components.annotation import Annotation
from components.profile import Profile
from annotation_creation import add_text_action, create_llm_annotation
from ontologies import BDIOnt, HMAS, LabOnt, LLMOnt, SoarOnt
from registries.profile_registry import ProfileRegistry
from utils import annotations_url_from_id, generate_id


class _FakeLlmResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLlm:
    def __init__(self, replies: list[str], prompts: list[str] | None = None):
        self._replies = list(replies)
        self._prompts = prompts if prompts is not None else []

    def invoke(self, prompt: str):
        self._prompts.append(prompt)
        if not self._replies:
            raise AssertionError("No fake LLM replies left for invoke()")
        return _FakeLlmResponse(self._replies.pop(0))


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "application/ld+json", url: str = "http://example.org/resource"):
        self.text = text
        self.status_code = 200
        self.headers = {"Content-Type": content_type}
        self.url = url

    def raise_for_status(self) -> None:
        return None


def _create_goal_state_annotation(z1: int, z2: int, url: str) -> Annotation:
    annotation_id = URIRef("http://example.org/annotations/state-goal")
    graph = Graph()
    ability_node = BNode()
    action_node = BNode()
    values_head = BNode()
    state_node = BNode()
    state_values_head = BNode()

    graph.add((annotation_id, RDF.type, HMAS.Annotation))
    graph.add((annotation_id, HMAS.recommendsAbility, ability_node))
    graph.add((ability_node, RDF.type, BDIOnt.predicate_ability))
    graph.add((annotation_id, HMAS.conveys, action_node))
    graph.add((action_node, BDIOnt.hasPredicate, Literal("goal")))
    graph.add((state_node, BDIOnt.hasPredicate, Literal("state")))

    Collection(graph, state_values_head, [Literal(z1), Literal(z2)])
    graph.add((state_node, BDIOnt.hasValues, state_values_head))
    Collection(graph, values_head, [state_node, Literal(url)])
    graph.add((action_node, BDIOnt.hasValues, values_head))

    return Annotation(annotation_id, graph)


def _create_llm_text_annotation(text: str) -> Annotation:
    annotation = create_llm_annotation(generate_id())
    add_text_action(annotation, text)
    return annotation


def _create_goal_state_annotation_with_float_literals(z1: float, z2: float, url: str) -> Annotation:
    annotation_id = URIRef("http://example.org/annotations/state-goal-float")
    graph = Graph()
    ability_node = BNode()
    action_node = BNode()
    values_head = BNode()
    state_node = BNode()
    state_values_head = BNode()

    graph.add((annotation_id, RDF.type, HMAS.Annotation))
    graph.add((annotation_id, HMAS.recommendsAbility, ability_node))
    graph.add((ability_node, RDF.type, BDIOnt.predicate_ability))
    graph.add((annotation_id, HMAS.conveys, action_node))
    graph.add((action_node, BDIOnt.hasPredicate, Literal("goal")))
    graph.add((state_node, BDIOnt.hasPredicate, Literal("state")))

    Collection(graph, state_values_head, [
        Literal(z1, datatype=XSD.double),
        Literal(z2, datatype=XSD.double),
    ])
    graph.add((state_node, BDIOnt.hasValues, state_values_head))
    Collection(graph, values_head, [state_node, Literal(url)])
    graph.add((action_node, BDIOnt.hasValues, values_head))

    return Annotation(annotation_id, graph)


def _create_soar_done_annotation() -> Annotation:
    annotation_id = URIRef("http://example.org/annotations/soar-done")
    graph = Graph()
    ability_node = BNode()
    action_node = BNode()

    graph.add((annotation_id, RDF.type, HMAS.Annotation))
    graph.add((annotation_id, HMAS.recommendsAbility, ability_node))
    graph.add((ability_node, RDF.type, SoarOnt.soar_light_processing))
    graph.add((annotation_id, HMAS.conveys, action_node))
    graph.add((action_node, SoarOnt.done, Literal("true")))

    return Annotation(annotation_id, graph)


def _create_soar_done_message() -> dict:
    message_id = URIRef("http://example.org/messages/soar-done")
    sender = URIRef("http://example.org/agents/soar#agent")
    receiver = URIRef("http://example.org/agents/jason#agent")
    graph = Graph()
    ability_node = BNode()
    action_node = BNode()

    graph.add((message_id, RDF.type, HMAS.HMAS.Message))
    graph.add((message_id, HMAS.hasId, Literal("message-1")))
    graph.add((message_id, HMAS.HMAS.hasSender, sender))
    graph.add((message_id, HMAS.HMAS.hasReceiver, receiver))
    graph.add((message_id, HMAS.recommendsAbility, ability_node))
    graph.add((ability_node, RDF.type, SoarOnt.soar_light_processing))
    graph.add((message_id, HMAS.conveys, action_node))
    graph.add((action_node, SoarOnt.done, Literal("true")))

    return json.loads(graph.serialize(format="json-ld"))


def _create_soar_done_message_annotation() -> Annotation:
    parsed = setup_app._parse_message_payload(_create_soar_done_message())
    assert parsed is not None
    return parsed


def _create_bdi_message(predicate: str, values: list[str]) -> Annotation:
    message_id = URIRef("http://example.org/messages/bdi-action")
    sender = URIRef("http://example.org/agents/jason#agent")
    receiver = URIRef("http://example.org/agents/llm#agent")
    graph = Graph()
    ability_node = BNode()
    action_node = BNode()
    values_head = BNode()

    graph.add((message_id, RDF.type, HMAS.HMAS.Message))
    graph.add((message_id, HMAS.hasId, Literal("message-bdi-1")))
    graph.add((message_id, HMAS.HMAS.hasSender, sender))
    graph.add((message_id, HMAS.HMAS.hasReceiver, receiver))
    graph.add((message_id, HMAS.recommendsAbility, ability_node))
    graph.add((ability_node, RDF.type, BDIOnt.predicate_ability))
    graph.add((message_id, HMAS.conveys, action_node))
    graph.add((action_node, BDIOnt.hasPredicate, Literal(predicate)))
    Collection(graph, values_head, [Literal(value) for value in values])
    graph.add((action_node, BDIOnt.hasValues, values_head))

    return setup_app._wrap_message(message_id, graph)


def _create_env_state_goal_profile(z1: int, z2: int) -> Profile:
    profile = Profile(URIRef("http://example.org/profiles/jason"), Graph())
    profile.add_ability(BDIOnt.predicate_ability)
    goal_node = BNode()
    values_head = BNode()

    profile.model.add((profile.id, HMAS.hasGoal, goal_node))
    profile.model.add((goal_node, RDF.type, BDIOnt.set_goal))
    profile.model.add((goal_node, BDIOnt.hasPredicate, Literal("env_state")))
    Collection(profile.model, values_head, [Literal(z1), Literal(z2)])
    profile.model.add((goal_node, BDIOnt.hasValues, values_head))
    return profile


def _create_external_json_ld_profile() -> tuple[Profile, str]:
    profile = Profile(URIRef("http://example.org/profiles/external"), Graph())
    profile.add_ability(BDIOnt.predicate_ability)
    profile_json_ld = profile.model.serialize(format="json-ld")
    return profile, profile_json_ld


def _create_disable_blinds_goal_profile(goal_type) -> Profile:
    profile = Profile(URIRef("http://example.org/profiles/jason"), Graph())
    profile.add_ability(BDIOnt.predicate_ability)
    goal_node = BNode()
    profile.model.add((profile.id, HMAS.hasGoal, goal_node))
    profile.model.add((goal_node, RDF.type, goal_type))
    return profile


def _build_setup4_environment_with_logs(current_state: dict, log_states: list[dict]) -> Graph:
    graph = Graph()
    env = URIRef("http://example.org/lab")
    state = URIRef("http://example.org/lab/currentState")

    graph.add((env, HMAS.hasState, state))
    graph.add((state, LabOnt.hasSunshine, Literal(current_state["Sunshine"])))
    graph.add((state, LabOnt.hasZ1Light, Literal(current_state["Z1Light"])))
    graph.add((state, LabOnt.hasZ2Light, Literal(current_state["Z2Light"])))
    graph.add((state, LabOnt.hasZ1Blinds, Literal(current_state["Z1Blinds"])))
    graph.add((state, LabOnt.hasZ2Blinds, Literal(current_state["Z2Blinds"])))

    for index, log_state in enumerate(log_states, start=1):
        entry = URIRef(f"http://example.org/logs/{index}")
        after_state = BNode()
        graph.add((entry, RDF.type, LabOnt.actionLogEntry))
        graph.add((entry, LabOnt.logAfterState, after_state))
        graph.add((after_state, LabOnt.hasSunshine, Literal(log_state["Sunshine"])))
        graph.add((after_state, LabOnt.hasZ1Level, Literal(log_state["Z1Level"])))
        graph.add((after_state, LabOnt.hasZ2Level, Literal(log_state["Z2Level"])))
        graph.add((after_state, LabOnt.hasZ1Light, Literal(log_state["Z1Light"])))
        graph.add((after_state, LabOnt.hasZ2Light, Literal(log_state["Z2Light"])))
        graph.add((after_state, LabOnt.hasZ1Blinds, Literal(log_state["Z1Blinds"])))
        graph.add((after_state, LabOnt.hasZ2Blinds, Literal(log_state["Z2Blinds"])))

    return graph


def _build_setup4_environment_with_disable_procedure(sunshine: float, procedure_name: str, request_uri: str, body: str) -> Graph:
    graph = Graph()
    env = URIRef("http://example.org/lab")
    state = URIRef("http://example.org/lab/currentState")
    procedure = URIRef(f"http://example.org/procedures/{procedure_name.replace(' ', '_')}")
    operation = BNode()

    graph.add((env, HMAS.hasState, state))
    graph.add((state, LabOnt.hasSunshine, Literal(sunshine)))
    graph.add((env, HMAS.hasProcedure, procedure))
    graph.add((procedure, RDF.type, HMAS.ActionSpecification))
    graph.add((procedure, URIRef("http://schema.org/name"), Literal(procedure_name)))
    graph.add((procedure, HMAS.hasOperation, operation))
    graph.add((operation, RDF.type, URIRef("http://www.w3.org/2011/http#Request")))
    graph.add((operation, URIRef("http://www.w3.org/2011/http#methodName"), Literal("POST")))
    graph.add((operation, URIRef("http://www.w3.org/2011/http#requestURI"), URIRef(request_uri)))
    graph.add((operation, URIRef("http://www.w3.org/2011/http#body"), Literal(body)))
    return graph


def test_state_to_soar_light_processing_transformation_builds_goal_paths():
    profile = Profile(URIRef("http://example.org/profiles/soar-light"), Graph())
    profile.add_ability(SoarOnt.soar_light_processing)

    annotation = _create_goal_state_annotation(1, 2, "http://example.org/agents/jason/profile")
    transformation = setup_app.create_state_to_soar_light_processing_transformation()

    transformed = transformation.get_function()(profile, annotation)

    assert transformed is not None
    assert SoarOnt.soar_light_processing in transformed.get_abilities()

    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert action is not None
    assert (action, RDF.type, SoarOnt.AddWME) in transformed.model

    relations = list(transformed.model.objects(action, SoarOnt.hasRelation))
    extracted = {}
    for relation in relations:
        attribute_node = transformed.model.value(relation, SoarOnt.hasAttribute)
        value_node = transformed.model.value(relation, SoarOnt.hasValue)
        attribute = transformed.model.value(attribute_node, SoarOnt.hasLiteral)
        value = transformed.model.value(value_node, SoarOnt.hasLiteral)
        extracted[str(attribute)] = value.toPython() if value is not None else None

    assert extracted == {
        "goal.z1": 1,
        "goal.z2": 2,
        "goal.url": "http://example.org/agents/jason/profile",
    }


def test_llm_action_to_soar_transformation_uses_llm_condition_gate(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(
        setup_app,
        "_load_setup4_transformation_llm",
        lambda: _FakeLlm(["True"], prompts),
    )

    profile = Profile(URIRef("http://example.org/profiles/soar"), Graph())
    profile.add_ability(SoarOnt.soar_ability)
    annotation = _create_llm_text_annotation("Turn on the light in the room.")

    transformed = setup_app.create_llm_action_to_soar_transformation().get_function()(profile, annotation)

    assert transformed is not None
    assert prompts
    assert "Answer with only True or False." in prompts[0]
    assert SoarOnt.soar_ability in transformed.get_abilities()

    action = transformed.model.value(transformed.url, HMAS.conveys)
    relations = list(transformed.model.objects(action, SoarOnt.hasRelation))
    extracted = {}
    for relation in relations:
        attribute_node = transformed.model.value(relation, SoarOnt.hasAttribute)
        value_node = transformed.model.value(relation, SoarOnt.hasValue)
        attribute = transformed.model.value(attribute_node, SoarOnt.hasLiteral)
        value = transformed.model.value(value_node, SoarOnt.hasLiteral)
        extracted[str(attribute)] = value.toPython() if value is not None else None

    assert extracted["predicate"] == "light"
    assert extracted["value"] == "on"


def test_llm_env_to_bdi_transformation_requires_set_env_and_uses_zone_light_levels():
    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation(
        "Zone 1 should have light level 2. "
        "Zone 2 should have light level 3. "
        "When the task is done, call back http://example.org/callback. "
        "A human is present in zone 1."
    )

    transformed = setup_app.create_llm_env_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is not None
    assert BDIOnt.set_env in transformed.get_abilities()

    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert transformed.model.value(action, BDIOnt.hasPredicate).toPython() == "set_env"
    values_head = transformed.model.value(action, BDIOnt.hasValues)
    values = list(transformed.model.items(values_head))
    assert [values[0].toPython(), values[1].toPython(), values[2].toPython()] == [
        2,
        3,
        "http://example.org/callback",
    ]
    human_node = values[3]
    assert transformed.model.value(human_node, BDIOnt.hasPredicate).toPython() == "human"
    human_values_head = transformed.model.value(human_node, BDIOnt.hasValues)
    assert [value.toPython() for value in transformed.model.items(human_values_head)] == [1]


def test_profile_registry_loads_external_json_ld_profiles(monkeypatch):
    expected_profile, profile_json_ld = _create_external_json_ld_profile()

    def fake_get(url: str, timeout: int):
        assert url == "http://example.org/profile"
        assert timeout == 10
        return _FakeResponse(profile_json_ld)

    monkeypatch.setattr(requests, "get", fake_get)

    registry = ProfileRegistry()
    registry.add_profile_from_url("external_profile", "http://example.org/profile")

    loaded_profile = registry.get_profile("external_profile")

    assert loaded_profile is not None
    assert loaded_profile.id == expected_profile.id
    assert BDIOnt.predicate_ability in loaded_profile.get_abilities()


def test_load_profile_from_url_expands_imported_ontologies(monkeypatch):
    profile_turtle = """
        @prefix hmas: <https://purl.org/hmas/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .

        <http://example.org/profile#agent> a hmas:Agent ;
            hmas:hasAbility [ a <http://example.org/abilities/disable_z1_blinds> ] ;
            owl:imports <http://example.org/abilities/> .
    """
    ontology_turtle = """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

        <http://example.org/abilities/disable_z1_blinds>
            rdfs:comment "Disable the blinds in zone 1." .
    """

    def fake_get(url: str, **kwargs):
        if url == "http://example.org/profile":
            return _FakeResponse(profile_turtle, "text/turtle", url)
        if url == "http://example.org/abilities/":
            assert kwargs["headers"]["Accept"] == setup_app._ONTOLOGY_ACCEPT_HEADER
            return _FakeResponse(ontology_turtle, "text/turtle", url)
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(requests, "get", fake_get)

    loaded_profile = setup_app._load_profile_from_url("http://example.org/profile")

    assert loaded_profile is not None
    assert (
        URIRef("http://example.org/abilities/disable_z1_blinds"),
        RDFS.comment,
        Literal("Disable the blinds in zone 1."),
    ) in loaded_profile.model

def test_llm_env_to_bdi_transformation_places_human_statement_third_when_no_url():
    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation(
        "Zone 1 should have light level 1. "
        "Zone 2 should have light level 2. "
        "Humans are present in zone 1 and zone 2."
    )

    transformed = setup_app.create_llm_env_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is not None
    action = transformed.model.value(transformed.url, HMAS.conveys)
    values_head = transformed.model.value(action, BDIOnt.hasValues)
    values = list(transformed.model.items(values_head))
    assert [values[0].toPython(), values[1].toPython()] == [1, 2]
    human_node = values[2]
    assert transformed.model.value(human_node, BDIOnt.hasPredicate).toPython() == "human"
    human_values_head = transformed.model.value(human_node, BDIOnt.hasValues)
    assert [value.toPython() for value in transformed.model.items(human_values_head)] == [1, 2]


def test_llm_env_to_bdi_transformation_returns_none_for_incomplete_zone_light_levels():
    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation("Zone 1 should have light level 2.")

    transformed = setup_app.create_llm_env_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is None


def test_llm_env_to_bdi_transformation_uses_latest_zone_light_levels_from_text():
    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation(
        "Zone 1 should have light level 1. "
        "Zone 1 light level 2. "
        "Zone 2 should have light level 1. "
        "Zone 2 light level 3. "
        "Callback URL: http://localhost:8991/profile."
    )

    transformed = setup_app.create_llm_env_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is not None
    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert transformed.model.value(action, BDIOnt.hasPredicate).toPython() == "set_env"
    values = list(transformed.model.items(transformed.model.value(action, BDIOnt.hasValues)))
    assert [values[0].toPython(), values[1].toPython(), values[2].toPython()] == [
        2,
        3,
        "http://localhost:8991/profile",
    ]


def test_llm_env_to_bdi_transformation_returns_none_for_incomplete_zone_light_levels_with_latest_value():
    profile_graph = Graph().parse(
        data="""
            @prefix hmas: <https://purl.org/hmas/> .
            @prefix bdi: <http://localhost:8082/ontologies/bdi#> .

            <http://localhost:8082/profile> a hmas:Agent ;
                hmas:hasAbility [ a bdi:set_env ] .
        """,
        format="turtle",
    )
    profile = Profile.parse_profile(profile_graph)
    assert profile is not None

    annotation_graph = Graph().parse(
        data="""
            @prefix hmas: <https://purl.org/hmas/> .
            @prefix llm: <http://example.org/llm#> .

            <http://localhost:5001/annotations/test> a hmas:Annotation ;
                hmas:recommendsAbility [ a llm:llm_ability ] ;
                hmas:conveys [
                    a llm:llm_action ;
                    llm:text_action "Zone 1 should have light level 1. Zone 1 light level 2. Callback URL: http://localhost:8991/profile."
                ] .
        """,
        format="turtle",
    )
    annotation = Annotation(URIRef("http://localhost:5001/annotations/test"), annotation_graph)

    transformed = setup_app.create_llm_env_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is None


def test_llm_goal_to_bdi_transformation_uses_separate_llm_queries(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(
        setup_app,
        "_load_transformation_llm",
        lambda: _FakeLlm(
            ["2", "3", "True", "False", "http://example.org/callback"],
            prompts,
        ),
    )

    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation(
        "Zone 1 should have light level 2. "
        "Zone 2 should have light level 3. "
        "A human is present in zone 1. "
        "Call back http://example.org/callback."
    )

    transformed = setup_app.create_llm_goal_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is not None
    assert len(prompts) == 5
    assert "desired light level for zone 1" in prompts[0]
    assert "desired light level for zone 2" in prompts[1]
    assert "human be present in zone 1" in prompts[2]
    assert "human be present in zone 2" in prompts[3]
    assert "callback URL" in prompts[4]
    assert BDIOnt.set_env in transformed.get_abilities()

    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert transformed.model.value(action, BDIOnt.hasPredicate).toPython() == "set_env"
    values_head = transformed.model.value(action, BDIOnt.hasValues)
    values = list(transformed.model.items(values_head))
    assert [values[0].toPython(), values[1].toPython(), values[2].toPython()] == [
        2,
        3,
        "http://example.org/callback",
    ]
    human_node = values[3]
    assert transformed.model.value(human_node, BDIOnt.hasPredicate).toPython() == "human"
    human_values_head = transformed.model.value(human_node, BDIOnt.hasValues)
    assert [value.toPython() for value in transformed.model.items(human_values_head)] == [1]


def test_llm_goal_to_bdi_transformation_returns_none_without_light_levels(monkeypatch):
    monkeypatch.setattr(
        setup_app,
        "_load_transformation_llm",
        lambda: _FakeLlm(
            ["null", "null", "False", "True", "http://example.org/callback"],
        ),
    )

    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation("There will be a human in zone 2. Call back http://example.org/callback.")

    transformed = setup_app.create_llm_goal_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is None


def test_llm_goal_to_bdi_transformation_returns_none_for_incomplete_zone_light_levels(monkeypatch):
    monkeypatch.setattr(
        setup_app,
        "_load_transformation_llm",
        lambda: _FakeLlm(
            ["2", "null", "False", "False", "http://example.org/callback"],
        ),
    )

    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation(
        "Zone 1 should have light level 2. Call back http://example.org/callback."
    )

    transformed = setup_app.create_llm_goal_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is None


def test_llm_bdi_ability_transformation_builds_agentspeak_literal(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(
        setup_app,
        "_load_transformation_llm",
        lambda: _FakeLlm(
            ['set_env(2, 3, "http://example.org/callback", human(1))'],
            prompts,
        ),
    )

    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.predicate_ability)
    custom_ability_node = BNode()
    profile.model.add((profile.id, HMAS.hasAbility, custom_ability_node))
    profile.model.add((custom_ability_node, RDF.type, BDIOnt.set_env))
    profile.model.add((BDIOnt.set_env, RDFS.comment, Literal("Set environment state for both zones.")))
    annotation = _create_llm_text_annotation(
        "Set zone 1 to light level 2, zone 2 to light level 3, and call back http://example.org/callback. "
        "A human is in zone 1."
    )

    transformed = setup_app.create_llm_bdi_ability_transformation().get_function()(profile, annotation)

    assert transformed is not None
    assert len(prompts) == 1
    assert "Set environment state for both zones." in prompts[0]
    assert "Relevant ability IRIs" in prompts[0]
    assert BDIOnt.predicate_ability in transformed.get_abilities()

    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert transformed.model.value(action, BDIOnt.hasPredicate).toPython() == "set_env"
    values_head = transformed.model.value(action, BDIOnt.hasValues)
    values = list(transformed.model.items(values_head))
    assert [values[0].toPython(), values[1].toPython(), values[2].toPython()] == [
        2,
        3,
        "http://example.org/callback",
    ]
    nested_action = values[3]
    assert transformed.model.value(nested_action, BDIOnt.hasPredicate).toPython() == "human"
    nested_values_head = transformed.model.value(nested_action, BDIOnt.hasValues)
    assert [value.toPython() for value in transformed.model.items(nested_values_head)] == [1]


def test_llm_bdi_ability_transformation_returns_none_for_invalid_literal(monkeypatch):
    monkeypatch.setattr(
        setup_app,
        "_load_transformation_llm",
        lambda: _FakeLlm(["This cannot be represented as an AgentSpeak literal."]),
    )

    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.predicate_ability)
    annotation = _create_llm_text_annotation("Do something unsupported.")

    transformed = setup_app.create_llm_bdi_ability_transformation().get_function()(profile, annotation)

    assert transformed is None


def test_llm_goal_to_bdi_transformation_normalizes_copied_creator_uri(monkeypatch):
    monkeypatch.setattr(
        setup_app,
        "_load_transformation_llm",
        lambda: _FakeLlm(
            ["1", "2", "False", "False", "null"],
        ),
    )

    profile = Profile(URIRef("http://example.org/profiles/bdi"), Graph())
    profile.add_ability(BDIOnt.set_env)
    annotation = _create_llm_text_annotation(
        "Zone 1 should have light level 1. Zone 2 should have light level 2."
    )
    annotation.add_triple(
        annotation.url,
        HMAS.hasCreator,
        URIRef("  http://localhost:8991/profile#agent\n  "),
    )

    transformed = setup_app.create_llm_goal_to_bdi_transformation().get_function()(profile, annotation)

    assert transformed is not None
    assert transformed.model.value(transformed.url, HMAS.hasCreator) == URIRef(
        "http://localhost:8991/profile#agent"
    )


def test_state_to_soar_light_processing_transformation_accepts_float_encoded_state_values():
    profile = Profile(URIRef("http://localhost:8083/profile"), Graph())
    profile.add_ability(SoarOnt.soar_light_processing)

    annotation = _create_goal_state_annotation_with_float_literals(
        1.0,
        2.0,
        "http://localhost:8082/profile",
    )
    transformation = setup_app.create_state_to_soar_light_processing_transformation()

    transformed = transformation.get_function()(profile, annotation)

    assert transformed is not None
    assert BDIOnt.predicate_ability not in profile.get_abilities()
    assert SoarOnt.soar_light_processing in transformed.get_abilities()

    action = transformed.model.value(transformed.url, HMAS.conveys)
    relations = list(transformed.model.objects(action, SoarOnt.hasRelation))
    extracted = {}
    for relation in relations:
        attribute_node = transformed.model.value(relation, SoarOnt.hasAttribute)
        value_node = transformed.model.value(relation, SoarOnt.hasValue)
        attribute = transformed.model.value(attribute_node, SoarOnt.hasLiteral)
        value = transformed.model.value(value_node, SoarOnt.hasLiteral)
        extracted[str(attribute)] = value.toPython() if value is not None else None

    assert extracted == {
        "goal.z1": 1,
        "goal.z2": 2,
        "goal.url": "http://localhost:8082/profile",
    }


def test_soar_done_to_bdi_transformation_builds_done_predicate():
    profile = Profile(URIRef("http://example.org/profiles/jason"), Graph())
    profile.add_ability(BDIOnt.predicate_ability)

    annotation = _create_soar_done_annotation()
    transformation = setup_app.create_soar_done_to_bdi_transformation()

    transformed = transformation.get_function()(profile, annotation)

    assert transformed is not None
    assert BDIOnt.predicate_ability in transformed.get_abilities()

    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert action is not None
    assert transformed.model.value(action, BDIOnt.hasPredicate).toPython() == "done"

    values_head = transformed.model.value(action, BDIOnt.hasValues)
    values = list(transformed.model.items(values_head))
    assert [value.toPython() for value in values] == ["true"]


def test_soar_done_to_bdi_transformation_accepts_message_input():
    profile = Profile(URIRef("http://example.org/profiles/jason"), Graph())
    profile.add_ability(BDIOnt.predicate_ability)

    message = _create_soar_done_message_annotation()
    transformation = setup_app.create_soar_done_to_bdi_transformation()

    transformed = transformation.get_function()(profile, message)

    assert transformed is not None
    assert (transformed.url, RDF.type, HMAS.HMAS.Message) in transformed.model
    assert (transformed.url, RDF.type, HMAS.Annotation) not in transformed.model
    assert transformed.model.value(transformed.url, HMAS.HMAS.hasSender) == URIRef("http://example.org/agents/soar#agent")
    assert transformed.model.value(transformed.url, HMAS.HMAS.hasReceiver) == URIRef("http://example.org/agents/jason#agent")

    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert transformed.model.value(action, BDIOnt.hasPredicate).toPython() == "done"


def test_bdi_llm_transformation_accepts_message_input():
    profile = Profile(URIRef("http://example.org/profiles/llm"), Graph())
    profile.add_ability(LLMOnt.llm_ability)

    message = _create_bdi_message("set_b1_open", ["b1", "open"])
    transformation = setup_app.create_bdi_llm_transformation()

    transformed = transformation.get_function()(profile, message)

    assert transformed is not None
    assert (transformed.url, RDF.type, HMAS.HMAS.Message) in transformed.model
    assert (transformed.url, RDF.type, HMAS.Annotation) not in transformed.model
    assert transformed.model.value(transformed.url, HMAS.HMAS.hasSender) == URIRef("http://example.org/agents/jason#agent")
    assert transformed.model.value(transformed.url, HMAS.HMAS.hasReceiver) == URIRef("http://example.org/agents/llm#agent")

    action = transformed.model.value(transformed.url, HMAS.conveys)
    assert transformed.model.value(action, LLMOnt.text_action).toPython() == "set_b1_open b1 open"


def test_post_annotations_adds_json_ld_annotation():
    original_annotations = setup_app.annotation_registry.annotations
    setup_app.annotation_registry.annotations = {}

    try:
        client = setup_app.app.test_client()
        annotation = _create_goal_state_annotation(3, 4, "http://example.org/agents/jason/profile")

        response = client.post(
            "/annotations/",
            json=json.loads(annotation.model.serialize(format="json-ld")),
        )

        stored_annotations = dict(setup_app.annotation_registry.annotations)
    finally:
        setup_app.annotation_registry.annotations = original_annotations

    assert response.status_code == 200
    assert annotation.url in stored_annotations


def test_post_annotations_nl_returns_created_uri_and_annotation_is_retrievable():
    original_annotations = setup_app.annotation_registry.annotations
    setup_app.annotation_registry.annotations = {}

    try:
        client = setup_app.app.test_client()
        response = client.post(
            "/annotations_nl/",
            data={
                "annotation": (
                    "Zone 1 should have light level 1. Zone 1 light level 2. "
                    "Callback URL: http://localhost:8991/profile."
                ),
                "creator": "http://localhost:8991/profile",
            },
        )

        created_url = response.get_data(as_text=True).strip()
        annotation_id = created_url.rsplit("/", 1)[-1]
        stored_annotations = dict(setup_app.annotation_registry.annotations)
        get_response = client.get(f"/annotations/{annotation_id}")
    finally:
        setup_app.annotation_registry.annotations = original_annotations

    assert response.status_code == 201
    assert response.headers["Location"] == created_url
    assert response.headers["Content-Type"].startswith("text/uri-list")
    assert created_url.startswith("http://localhost:5001/annotations/")
    assert annotations_url_from_id(annotation_id) in stored_annotations
    assert get_response.status_code == 200
    assert get_response.mimetype == "text/turtle"
    body = get_response.get_data(as_text=True)
    assert created_url in body


def test_post_annotations_nl_strips_creator_uri_whitespace():
    original_annotations = setup_app.annotation_registry.annotations
    setup_app.annotation_registry.annotations = {}

    try:
        client = setup_app.app.test_client()
        response = client.post(
            "/annotations_nl/",
            data={
                "annotation": "Zone 1 should have light level 1.",
                "creator": "  http://localhost:8991/profile#agent\n  ",
            },
        )

        created_url = response.get_data(as_text=True).strip()
        stored_annotation = setup_app.annotation_registry.annotations[URIRef(created_url)]
    finally:
        setup_app.annotation_registry.annotations = original_annotations

    assert response.status_code == 201
    assert stored_annotation.model.value(stored_annotation.url, HMAS.hasCreator) == URIRef(
        "http://localhost:8991/profile#agent"
    )


def test_post_messages_resolves_soar_done_to_bdi_and_preserves_transport_fields(monkeypatch):
    client = setup_app.app.test_client()
    target_profile_url = "http://example.org/agents/jason/profile"
    target_agent_url = URIRef(target_profile_url + "#agent")
    message_url = "http://example.org/agents/jason/messages"
    profile_graph = Graph()
    profile_id = target_agent_url
    policy_node = BNode()

    profile_graph.add((target_agent_url, RDF.type, HMAS.Agent))
    profile_graph.add((target_agent_url, HMAS.HMAS.hasInteractionPolicy, policy_node))
    profile_graph.add((policy_node, RDF.type, HMAS.HMAS.MessagePolicy))
    profile_graph.add((policy_node, HMAS.HMAS.hasMessageUrl, URIRef(message_url)))
    ability_node = BNode()
    profile_graph.add((target_agent_url, HMAS.hasAbility, ability_node))
    profile_graph.add((ability_node, RDF.type, BDIOnt.predicate_ability))
    target_profile = Profile(profile_id, profile_graph)

    forwarded = {}

    class _Response:
        def __init__(self, text="", ok=True):
            self.text = text
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError("request failed")

    def fake_post(url, data, headers, timeout):
        forwarded["url"] = url
        forwarded["data"] = data
        forwarded["headers"] = headers
        return _Response()

    monkeypatch.setattr(setup_app, "_load_profile_from_url", lambda url: target_profile if url == target_profile_url else None)
    monkeypatch.setattr(setup_app.requests, "post", fake_post)

    response = client.post(
        "/messages",
        json={
            "agent": target_profile_url,
            "message": _create_soar_done_message(),
        },
    )

    assert response.status_code == 200
    assert forwarded["url"] == message_url
    assert forwarded["headers"] == {"Content-Type": "application/ld+json"}

    forwarded_graph = Graph()
    forwarded_graph.parse(data=forwarded["data"], format="json-ld")
    forwarded_message = next(forwarded_graph.subjects(RDF.type, HMAS.HMAS.Message), None)
    assert forwarded_message is not None
    assert (forwarded_message, RDF.type, HMAS.Annotation) not in forwarded_graph
    assert forwarded_graph.value(forwarded_message, HMAS.HMAS.hasSender) == URIRef("http://example.org/agents/soar#agent")
    assert forwarded_graph.value(forwarded_message, HMAS.HMAS.hasReceiver) == URIRef("http://example.org/agents/jason#agent")

    action = forwarded_graph.value(forwarded_message, HMAS.conveys)
    assert forwarded_graph.value(action, BDIOnt.hasPredicate).toPython() == "done"


def test_recurrent_policy_dispatch_sends_selected_annotations_to_registered_profile(monkeypatch, capsys):
    original_profiles = setup_app.profile_registry.profiles
    original_annotations = setup_app.annotation_registry.annotations
    original_recheck_state = dict(setup_app._profile_recheck_state)

    setup_app.profile_registry.profiles = {}
    setup_app.annotation_registry.annotations = {}
    setup_app._profile_recheck_state.clear()

    try:
        profile_graph = Graph()
        profile_id = URIRef("http://localhost:9001/profile")
        profile = Profile(profile_id, profile_graph)
        predicate_ability = BNode()
        policy = BNode()

        profile.add_triple(profile_id, HMAS.hasAbility, predicate_ability)
        profile.add_triple(predicate_ability, RDF.type, BDIOnt.predicate_ability)
        profile.add_triple(profile_id, HMAS.hasAnnotationPolicy, policy)
        profile.add_triple(policy, RDF.type, HMAS.RecurrentPolicy)
        profile.add_triple(policy, HMAS.hasRepetitionTime, Literal(2.5, datatype=XSD.double))
        profile.add_triple(policy, HMAS.hasCallbackUrl, URIRef("http://localhost:8871/annotation"))

        annotation = _create_soar_done_annotation()
        setup_app.annotation_registry.add_annotation(annotation)
        setup_app.profile_registry.add_profile_from_url("jason_agent", "http://localhost:9001/profile")

        posted = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

        def fake_load_profile(url: str):
            assert url == "http://localhost:9001/profile"
            return profile

        def fake_post(url, data, headers, timeout):
            posted["url"] = url
            posted["data"] = data
            posted["headers"] = headers
            posted["timeout"] = timeout
            return FakeResponse()

        monkeypatch.setattr(setup_app, "_load_profile_from_url", fake_load_profile)
        monkeypatch.setattr(setup_app, "_select_annotations_for_profile", lambda _: {annotation})
        monkeypatch.setattr(setup_app.requests, "post", fake_post)

        setup_app._dispatch_registered_profile_callbacks(now=0.0)

        assert posted["url"] == "http://localhost:8871/annotation"
        assert posted["headers"] == {"Content-Type": "application/ld+json"}
        assert posted["timeout"] == 10
        posted_graph = Graph()
        posted_graph.parse(data=posted["data"], format="json-ld")
        assert (annotation.url, RDF.type, HMAS.Annotation) in posted_graph
        conveyed_action = posted_graph.value(annotation.url, HMAS.conveys)
        assert posted_graph.value(conveyed_action, SoarOnt.done).toPython() == "true"
        assert setup_app._profile_recheck_state["jason_agent"] == 2.5

        output = capsys.readouterr().out
        assert "Applying recurrent policy" in output
        assert "Recurrent policy selection results for profile jason_agent" in output
        assert "Recurrent policy delivered" in output
        assert "to profile jason_agent via http://localhost:8871/annotation" in output
    finally:
        setup_app.profile_registry.profiles = original_profiles
        setup_app.annotation_registry.annotations = original_annotations
        setup_app._profile_recheck_state.clear()


def test_recurrent_policy_dispatch_supports_interaction_policy_links(monkeypatch, capsys):
    original_profiles = setup_app.profile_registry.profiles
    original_annotations = setup_app.annotation_registry.annotations
    original_recheck_state = dict(setup_app._profile_recheck_state)

    setup_app.profile_registry.profiles = {}
    setup_app.annotation_registry.annotations = {}
    setup_app._profile_recheck_state.clear()

    try:
        profile_graph = Graph()
        profile_id = URIRef("http://localhost:9001/profile")
        profile = Profile(profile_id, profile_graph)
        predicate_ability = BNode()
        policy = BNode()

        profile.add_triple(profile_id, HMAS.hasAbility, predicate_ability)
        profile.add_triple(predicate_ability, RDF.type, BDIOnt.predicate_ability)
        profile.add_triple(profile_id, HMAS.hasInteractionPolicy, policy)
        profile.add_triple(policy, RDF.type, HMAS.RecurrentPolicy)
        profile.add_triple(policy, HMAS.hasRepetitionTime, Literal(2.5, datatype=XSD.double))
        profile.add_triple(policy, HMAS.hasCallbackUrl, URIRef("http://localhost:8871/annotation"))

        annotation = _create_soar_done_annotation()
        setup_app.annotation_registry.add_annotation(annotation)
        setup_app.profile_registry.add_profile_from_url("jason_agent", "http://localhost:9001/profile")

        posted = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

        def fake_load_profile(url: str):
            assert url == "http://localhost:9001/profile"
            return profile

        def fake_post(url, data, headers, timeout):
            posted["url"] = url
            posted["data"] = data
            posted["headers"] = headers
            posted["timeout"] = timeout
            return FakeResponse()

        monkeypatch.setattr(setup_app, "_load_profile_from_url", fake_load_profile)
        monkeypatch.setattr(setup_app, "_select_annotations_for_profile", lambda _: {annotation})
        monkeypatch.setattr(setup_app.requests, "post", fake_post)

        setup_app._dispatch_registered_profile_callbacks(now=0.0)

        assert posted["url"] == "http://localhost:8871/annotation"
        assert posted["headers"] == {"Content-Type": "application/ld+json"}
        assert posted["timeout"] == 10
        assert setup_app._profile_recheck_state["jason_agent"] == 2.5

        output = capsys.readouterr().out
        assert "Applying recurrent policy" in output
        assert "Found 1 recurrent policy/policies for profile jason_agent" in output
    finally:
        setup_app.profile_registry.profiles = original_profiles
        setup_app.annotation_registry.annotations = original_annotations
        setup_app._profile_recheck_state.clear()
        setup_app._profile_recheck_state.update(original_recheck_state)


def test_bdi_env_state_generation_builds_action_list_from_best_matching_log():
    profile = _create_env_state_goal_profile(1, 2)
    environment_kg = _build_setup4_environment_with_logs(
        current_state={
            "Sunshine": 610.0,
            "Z1Light": False,
            "Z2Light": False,
            "Z1Blinds": False,
            "Z2Blinds": False,
        },
        log_states=[
            {
                "Sunshine": 645.0,
                "Z1Level": 120.0,
                "Z2Level": 650.0,
                "Z1Light": True,
                "Z2Light": False,
                "Z1Blinds": False,
                "Z2Blinds": True,
            },
            {
                "Sunshine": 620.0,
                "Z1Level": 110.0,
                "Z2Level": 500.0,
                "Z1Light": True,
                "Z2Light": False,
                "Z1Blinds": False,
                "Z2Blinds": True,
            },
            {
                "Sunshine": 618.0,
                "Z1Level": 20.0,
                "Z2Level": 900.0,
                "Z1Light": True,
                "Z2Light": True,
                "Z1Blinds": True,
                "Z2Blinds": True,
            },
        ],
    )

    generation = setup_app.create_bdi_env_state_generation(lambda: "http://localhost:8081")
    generated = generation.get_function()(profile, environment_kg)

    assert len(generated) == 1
    annotation = next(iter(generated))
    action = annotation.model.value(annotation.url, HMAS.conveys)
    assert annotation.model.value(action, BDIOnt.hasPredicate).toPython() == "action_list"

    values_head = annotation.model.value(action, BDIOnt.hasValues)
    actions = list(annotation.model.items(values_head))
    assert len(actions) == 2

    decoded = []
    for nested_action in actions:
        assert annotation.model.value(nested_action, BDIOnt.hasPredicate).toPython() == "http_action"
        nested_values_head = annotation.model.value(nested_action, BDIOnt.hasValues)
        nested_values = [value.toPython() for value in annotation.model.items(nested_values_head)]
        decoded.append(nested_values)

    assert decoded == [
        [
            "l1",
            "on",
            "POST",
            "http://localhost:8081/action",
            '{"Content-Type":"application/json"}',
            '{"L1":true}',
        ],
        [
            "b2",
            "open",
            "POST",
            "http://localhost:8081/action",
            '{"Content-Type":"application/json"}',
            '{"B2":true}',
        ],
    ]


def test_bdi_env_state_generation_skips_logs_outside_sunshine_tolerance():
    profile = _create_env_state_goal_profile(1, 2)
    environment_kg = _build_setup4_environment_with_logs(
        current_state={
            "Sunshine": 610.0,
            "Z1Light": False,
            "Z2Light": False,
            "Z1Blinds": False,
            "Z2Blinds": False,
        },
        log_states=[
            {
                "Sunshine": 641.0,
                "Z1Level": 120.0,
                "Z2Level": 500.0,
                "Z1Light": True,
                "Z2Light": False,
                "Z1Blinds": False,
                "Z2Blinds": True,
            }
        ],
    )

    generation = setup_app.create_bdi_env_state_generation(lambda: "http://localhost:8081")
    generated = generation.get_function()(profile, environment_kg)

    assert generated == set()


def test_disable_blinds_generation_builds_disable_goal_annotation():
    profile = _create_disable_blinds_goal_profile(BDIOnt.disable_z1_blinds)
    environment_kg = _build_setup4_environment_with_disable_procedure(
        sunshine=850.0,
        procedure_name="Disable B1",
        request_uri="http://localhost:8081/action",
        body="{'B1': false}",
    )

    generation = setup_app.create_disable_blinds_generation()
    generated = generation.get_function()(profile, environment_kg)

    assert len(generated) == 1
    annotation = next(iter(generated))
    action = annotation.model.value(annotation.url, HMAS.conveys)
    assert annotation.model.value(action, BDIOnt.hasPredicate).toPython() == "disable_z1_blinds"

    values_head = annotation.model.value(action, BDIOnt.hasValues)
    values = list(annotation.model.items(values_head))
    assert values[0].toPython() == 850.0

    nested_action = values[1]
    assert annotation.model.value(nested_action, BDIOnt.hasPredicate).toPython() == "http_action"
    nested_values_head = annotation.model.value(nested_action, BDIOnt.hasValues)
    assert [value.toPython() for value in annotation.model.items(nested_values_head)] == [
        "POST",
        "http://localhost:8081/action",
        '{"Content-Type":"application/json"}',
        '{"B1":false}',
    ]
