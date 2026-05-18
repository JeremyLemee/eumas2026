import asyncio
import json
import socket
import threading
import time
from typing import Any
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, render_template_string, request
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from rdflib import BNode, Graph, Literal, RDF, URIRef
from rdflib.collection import Collection

from ontologies import HMAS
from ontologies.LLMOnt import llm_ability, text_action


_SETUP_MCP_URL = "http://127.0.0.1:8204/mcp"
_HOST = "127.0.0.1"
_PORT = 8991
_PUBLIC_BASE_URL = f"http://localhost:{_PORT}"
_PROFILE_PATH = "/profile"
_PERCEPTS_PATH = "/percepts"
_ANNOTATION_PATH = "/annotation"
_MESSAGE_PATH = "/message"
_LIGHT_TD_URL = "http://localhost:8082/td"

_BDI_NS = "http://example.org/bdi#"
_BDI_PREDICATE_ABILITY = URIRef(f"{_BDI_NS}predicate_ability")
_BDI_TURN_ON_LIGHT = URIRef(f"{_BDI_NS}turn_on_light")
_BDI_HAS_PREDICATE = URIRef(f"{_BDI_NS}hasPredicate")
_BDI_HAS_VALUES = URIRef(f"{_BDI_NS}hasValues")
_HMAS_HAS_ID = URIRef("https://purl.org/hmas/hasId")


HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Setup 3 Human Control</title>
  <style>
    :root {
      --bg: #f5f1e8;
      --panel: #fffaf1;
      --ink: #1e1f1c;
      --muted: #6c675e;
      --line: #d4cab8;
      --accent: #0e5a53;
      --accent-2: #b54f2d;
      --shadow: rgba(40, 32, 19, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(181, 79, 45, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(14, 90, 83, 0.12), transparent 24%),
        linear-gradient(180deg, #f8f4ec 0%, #eee6d7 100%);
    }
    main {
      max-width: 1380px;
      margin: 0 auto;
      padding: 24px;
    }
    h1, h2, h3 {
      margin: 0 0 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    h1 { font-size: 2.1rem; }
    h2 { font-size: 1.1rem; }
    h3 { font-size: 1rem; }
    p { margin: 0; }
    .hero {
      display: grid;
      gap: 14px;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(255,250,241,0.96), rgba(249,242,229,0.96));
      box-shadow: 0 18px 50px var(--shadow);
    }
    .hero-grid, .content-grid {
      display: grid;
      gap: 18px;
      margin-top: 18px;
    }
    .hero-grid { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
    .content-grid { grid-template-columns: 1.2fr 0.9fr; align-items: start; }
    .panel {
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--panel);
      box-shadow: 0 8px 30px var(--shadow);
    }
    .panel-stack {
      display: grid;
      gap: 18px;
    }
    .meta {
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(14, 90, 83, 0.10);
      color: var(--accent);
      font-size: 0.9rem;
    }
    .muted { color: var(--muted); }
    .status {
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(14, 90, 83, 0.08);
      white-space: pre-wrap;
    }
    .status.error {
      background: rgba(181, 79, 45, 0.10);
      color: #7d3018;
    }
    .row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .row.spread { justify-content: space-between; }
    .kv {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .kv code, .pill, pre, textarea, input {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }
    .pill {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(181, 79, 45, 0.10);
      color: var(--accent-2);
      font-size: 0.85rem;
    }
    textarea, input {
      width: 100%;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fffdf9;
      color: var(--ink);
      font-size: 0.95rem;
    }
    textarea { min-height: 110px; resize: vertical; }
    button {
      border: 0;
      border-radius: 12px;
      padding: 10px 14px;
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    button.secondary { background: #8f816a; }
    button.warn { background: var(--accent-2); }
    button:disabled { opacity: 0.55; cursor: default; }
    ul.log, ul.percepts {
      list-style: none;
      padding: 0;
      margin: 12px 0 0;
      display: grid;
      gap: 10px;
      max-height: 360px;
      overflow: auto;
    }
    li.entry {
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: rgba(255,255,255,0.68);
      white-space: pre-wrap;
    }
    .tool-card {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      background: rgba(255,255,255,0.7);
    }
    .tool-card + .tool-card { margin-top: 12px; }
    pre {
      margin: 8px 0 0;
      padding: 10px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fffdf9;
      font-size: 0.85rem;
      overflow: auto;
    }
    @media (max-width: 980px) {
      .content-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="row spread">
        <div>
          <h1>Setup 3 Human Control Surface</h1>
          <p class="muted">Manual replacement for <code>setup_agent.py</code> with the same body endpoints and MCP tool access.</p>
        </div>
        <div class="meta" id="run-status">Loading state...</div>
      </div>
      <div class="hero-grid">
        <div class="panel">
          <h2>Goal Prompt</h2>
          <pre id="goal-prompt"></pre>
        </div>
        <div class="panel">
          <h2>Body Interface</h2>
          <div class="kv">
            <div><span class="pill">Profile URL</span> <code id="profile-url"></code></div>
            <div><span class="pill">Callback URL</span> <code id="callback-url"></code></div>
            <div><span class="pill">Message URL</span> <code id="message-url"></code></div>
            <div><span class="pill">Light TD URL</span> <code id="light-td-url"></code></div>
          </div>
        </div>
      </div>
    </section>

    <section class="content-grid">
      <div class="panel-stack">
        <section class="panel">
          <div class="row spread">
            <h2>Observations</h2>
            <div class="row">
              <button id="consume-percepts">Consume Pending Percepts</button>
              <button class="secondary" id="refresh-state">Refresh</button>
            </div>
          </div>
          <p class="muted">External agents can still POST to <code>/percepts</code>, <code>/annotation</code>, or <code>/message</code>. Consume them here when you want them added to your current observation context.</p>
          <div class="kv" style="margin-top:14px;">
            <div>
              <h3>Current Observation Context</h3>
              <pre id="observation-context"></pre>
            </div>
            <div>
              <h3>Pending Percepts</h3>
              <ul class="percepts" id="pending-percepts"></ul>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="row spread">
            <h2>Permanent Memory</h2>
            <span class="muted">Manual state management</span>
          </div>
          <pre id="memory-json"></pre>
          <div class="row" style="margin-top:12px;">
            <input id="memory-field" placeholder="field name">
            <input id="memory-value" placeholder="value">
            <button id="save-memory">Update Field</button>
          </div>
        </section>

        <section class="panel">
          <h2>Decision Log</h2>
          <p class="muted">Record your next action before or after using tools.</p>
          <textarea id="decision-note" placeholder="Example: query the light TD annotations and inspect the returned values for turn_on."></textarea>
          <div class="row" style="margin-top:12px;">
            <button id="save-decision">Record Decision</button>
            <button class="warn" id="stop-session">Mark Session Stopped</button>
          </div>
        </section>

        <section class="panel">
          <h2>Activity</h2>
          <ul class="log" id="activity-log"></ul>
        </section>
      </div>

      <div class="panel-stack">
        <section class="panel">
          <div class="row spread">
            <h2>MCP Tools</h2>
            <span class="muted" id="tool-count"></span>
          </div>
          <p class="muted">Each card is backed by the <code>setup_tools</code> MCP server. Submit JSON arguments exactly as the tool expects.</p>
          <div id="tool-list"></div>
        </section>

        <section class="panel">
          <h2>Latest Tool Result</h2>
          <pre id="latest-result">No tool calls yet.</pre>
        </section>
      </div>
    </section>
  </main>

  <script>
    async function fetchJson(url, options = {}) {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Request failed');
      }
      return data;
    }

    function formatTimestamp(value) {
      if (!value) return 'never';
      return new Date(value * 1000).toLocaleString();
    }

    function setStatus(message, isError = false) {
      const node = document.getElementById('run-status');
      node.textContent = message;
      node.className = isError ? 'meta status error' : 'meta';
    }

    function renderState(state) {
      document.getElementById('run-status').textContent = state.stopped ? 'Session marked stopped' : 'Session active';
      document.getElementById('goal-prompt').textContent = state.goal_prompt;
      document.getElementById('profile-url').textContent = state.profile_url;
      document.getElementById('callback-url').textContent = state.callback_url;
      document.getElementById('message-url').textContent = state.message_url;
      document.getElementById('light-td-url').textContent = state.light_td_url;
      document.getElementById('observation-context').textContent =
        state.observation_context_display || 'No observations consumed yet.';
      document.getElementById('memory-json').textContent = JSON.stringify(state.memory, null, 2);

      const pending = document.getElementById('pending-percepts');
      pending.innerHTML = '';
      if (!state.pending_percepts.length) {
        const li = document.createElement('li');
        li.className = 'entry';
        li.textContent = 'No pending percepts.';
        pending.appendChild(li);
      } else {
        state.pending_percepts.forEach((percept) => {
          const li = document.createElement('li');
          li.className = 'entry';
          li.textContent = percept;
          pending.appendChild(li);
        });
      }

      const log = document.getElementById('activity-log');
      log.innerHTML = '';
      [...state.activity_log].reverse().forEach((entry) => {
        const li = document.createElement('li');
        li.className = 'entry';
        li.textContent = `[${formatTimestamp(entry.timestamp)}] ${entry.kind}\\n${entry.message}`;
        log.appendChild(li);
      });

      document.getElementById('latest-result').textContent = state.latest_tool_result || 'No tool calls yet.';
    }

    function makeToolCard(tool) {
      const wrapper = document.createElement('div');
      wrapper.className = 'tool-card';

      const schema = tool.input_schema || {};
      const example = {};
      const required = schema.required || [];
      required.forEach((field) => { example[field] = ''; });

      wrapper.innerHTML = `
        <div class="row spread">
          <h3>${tool.name}</h3>
          <span class="pill">${required.length} required</span>
        </div>
        <p class="muted">${tool.description || 'No description provided.'}</p>
        <pre>${JSON.stringify(schema, null, 2)}</pre>
        <textarea data-tool-input="${tool.name}">${JSON.stringify(example, null, 2)}</textarea>
        <div class="row" style="margin-top:12px;">
          <button data-tool-run="${tool.name}">Run Tool</button>
        </div>
      `;
      return wrapper;
    }

    async function loadState() {
      const state = await fetchJson('/api/state');
      renderState(state);
      return state;
    }

    async function loadTools() {
      const data = await fetchJson('/api/tools');
      document.getElementById('tool-count').textContent = `${data.tools.length} tools`;
      const list = document.getElementById('tool-list');
      list.innerHTML = '';
      data.tools.forEach((tool) => list.appendChild(makeToolCard(tool)));

      document.querySelectorAll('[data-tool-run]').forEach((button) => {
        button.addEventListener('click', async () => {
          const toolName = button.getAttribute('data-tool-run');
          const textarea = document.querySelector(`[data-tool-input="${toolName}"]`);
          let payload = {};
          try {
            payload = textarea.value.trim() ? JSON.parse(textarea.value) : {};
          } catch (error) {
            setStatus(`Invalid JSON for ${toolName}: ${error.message}`, true);
            return;
          }

          button.disabled = true;
          setStatus(`Running ${toolName}...`);
          try {
            const result = await fetchJson(`/api/tools/${toolName}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ tool_input: payload }),
            });
            document.getElementById('latest-result').textContent = result.result;
            await loadState();
            setStatus(`Completed ${toolName}`);
          } catch (error) {
            setStatus(error.message, true);
          } finally {
            button.disabled = false;
          }
        });
      });
    }

    document.getElementById('refresh-state').addEventListener('click', async () => {
      try {
        setStatus('Refreshing...');
        await loadState();
        setStatus('State refreshed');
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById('consume-percepts').addEventListener('click', async () => {
      try {
        setStatus('Consuming percepts...');
        await fetchJson('/api/percepts/consume', { method: 'POST' });
        await loadState();
        setStatus('Percepts consumed');
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById('save-memory').addEventListener('click', async () => {
      const field = document.getElementById('memory-field').value.trim();
      const value = document.getElementById('memory-value').value;
      try {
        setStatus(`Updating memory field ${field}...`);
        await fetchJson('/api/permanent-memory', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ field, value }),
        });
        document.getElementById('memory-field').value = '';
        document.getElementById('memory-value').value = '';
        await loadState();
        setStatus(`Updated ${field}`);
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById('save-decision').addEventListener('click', async () => {
      const note = document.getElementById('decision-note').value.trim();
      try {
        setStatus('Recording decision...');
        await fetchJson('/api/decisions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note }),
        });
        document.getElementById('decision-note').value = '';
        await loadState();
        setStatus('Decision recorded');
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    document.getElementById('stop-session').addEventListener('click', async () => {
      try {
        setStatus('Marking session stopped...');
        await fetchJson('/api/stop', { method: 'POST' });
        await loadState();
        setStatus('Session stopped');
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    async function boot() {
      try {
        await Promise.all([loadState(), loadTools()]);
        setStatus('Ready');
      } catch (error) {
        setStatus(error.message, true);
      }
    }

    boot();
    setInterval(() => { loadState().catch(() => {}); }, 4000);
  </script>
</body>
</html>
"""


def _normalize_literal_value(value: Any) -> Any:
    if isinstance(value, Literal):
        python_value = value.toPython()
        if isinstance(python_value, (str, bool, int, float)):
            return python_value
        return str(python_value)
    return str(value)


def _parse_annotation_value(graph: Graph, value: Any) -> Any:
    if isinstance(value, Literal):
        return _normalize_literal_value(value)

    if isinstance(value, (URIRef, BNode)):
        nested_predicate = next(graph.objects(value, _BDI_HAS_PREDICATE), None)
        nested_values_head = next(graph.objects(value, _BDI_HAS_VALUES), None)
        if isinstance(nested_predicate, Literal) and nested_values_head is not None:
            nested_values = [
                _parse_annotation_value(graph, item)
                for item in Collection(graph, nested_values_head)
            ]
            return {"predicate": str(nested_predicate), "values": nested_values}
        return str(value)

    return str(value)


def _extract_annotations(graph: Graph) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for annotation in graph.subjects(RDF.type, HMAS.Annotation):
        content = next(graph.objects(annotation, HMAS.conveys), None)
        if content is None:
            content = next(graph.objects(annotation, HMAS.signifies), None)
        if content is None:
            continue

        text_literal = next(graph.objects(content, text_action), None)
        if isinstance(text_literal, Literal):
            annotations.append(
                {
                    "id": str(next(graph.objects(annotation, _HMAS_HAS_ID), "")),
                    "predicate": "text_action",
                    "values": [_normalize_literal_value(text_literal)],
                }
            )
            continue

        predicate_literal = next(graph.objects(content, _BDI_HAS_PREDICATE), None)
        if not isinstance(predicate_literal, Literal):
            continue

        values_head = next(graph.objects(content, _BDI_HAS_VALUES), None)
        values = []
        if values_head is not None:
            values = [
                _parse_annotation_value(graph, item) for item in Collection(graph, values_head)
            ]

        annotations.append(
            {
                "id": str(next(graph.objects(annotation, _HMAS_HAS_ID), "")),
                "predicate": str(predicate_literal),
                "values": values,
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
        if isinstance(text_literal, Literal):
            messages.append(
                {
                    "id": str(next(graph.objects(message, _HMAS_HAS_ID), "")),
                    "predicate": "text_action",
                    "values": [_normalize_literal_value(text_literal)],
                    "sender": str(next(graph.objects(message, HMAS.hasSender), "")),
                    "receiver": str(next(graph.objects(message, HMAS.hasReceiver), "")),
                }
            )
            continue

        predicate_literal = next(graph.objects(content, _BDI_HAS_PREDICATE), None)
        if not isinstance(predicate_literal, Literal):
            continue

        values_head = next(graph.objects(content, _BDI_HAS_VALUES), None)
        values = []
        if values_head is not None:
            values = [_parse_annotation_value(graph, item) for item in Collection(graph, values_head)]

        messages.append(
            {
                "id": str(next(graph.objects(message, _HMAS_HAS_ID), "")),
                "predicate": str(predicate_literal),
                "values": values,
                "sender": str(next(graph.objects(message, HMAS.hasSender), "")),
                "receiver": str(next(graph.objects(message, HMAS.hasReceiver), "")),
            }
        )
    return messages


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


def _select_profile_response_format() -> tuple[str, str]:
    accepts = request.accept_mimetypes
    if accepts and accepts["application/ld+json"] > accepts["text/turtle"]:
        return "application/ld+json", "json-ld"
    return "text/turtle", "turtle"


def _build_prompt(profile_url: str) -> str:
    return f"""You are an agent that must execute the same workflow as the Jason setup-3 light agent.

Fixed constants:
- your_profile_url: {profile_url}
- light_td_url: {_LIGHT_TD_URL}

Rules:
- Follow the workflow exactly and keep progress in permanent memory.
- Use the local helper tools only for querying the light TD, parsing RDF annotations, and executing discovered HTTP actions.
- Never invent URLs, methods, headers, payloads, predicates, or values. Always reuse exact values returned by tools.
- The discovery step must find a `turn_on` annotation with exactly four values: method, url, headers JSON string, payload.
- If a required annotation is missing, store a precise error message in permanent memory field `error` and stop.
- When the workflow is complete, stop immediately.

Workflow:
1. If permanent memory field `current_state` is missing, set it to `discover_turn_on`.
2. When `current_state` is `discover_turn_on`:
   - Call `query_light_annotations` with:
     - thing_description_url: "{_LIGHT_TD_URL}"
   - Store the returned JSON in permanent memory field `light_annotations`.
   - Set `current_state` to `execute_turn_on`.
3. When `current_state` is `execute_turn_on`:
   - Read `light_annotations`.
   - Find the `turn_on` annotation.
   - Call `execute_http_action` with the exact four values from that annotation.
   - Set `current_state` to `end`.
   - If the annotation is missing, set permanent memory field `error` and stop.
4. When `current_state` is `end`:
   - Stop by calling {{"tool": "stop"}}.
"""


class HumanControlPanel:
    def __init__(self) -> None:
        self.app = Flask(__name__)
        self.lock = threading.Lock()
        self.pending_percepts: list[str] = []
        self.pending_annotation_payloads: list[str] = []
        self.pending_message_payloads: list[str] = []
        self.observation_context = ""
        self.observation_annotations = ""
        self.observation_messages = ""
        self.goal_prompt = _build_prompt(f"{_PUBLIC_BASE_URL}{_PROFILE_PATH}")
        self.memory: dict[str, str] = {"current_state": "discover_turn_on"}
        self.activity_log: list[dict[str, Any]] = []
        self.latest_tool_result = ""
        self.stopped = False
        self._setup_routes()

    @property
    def profile_url(self) -> str:
        return f"{_PUBLIC_BASE_URL}{_PROFILE_PATH}"

    @property
    def callback_url(self) -> str:
        return f"{_PUBLIC_BASE_URL}{_ANNOTATION_PATH}"

    @property
    def message_url(self) -> str:
        return f"{_PUBLIC_BASE_URL}{_MESSAGE_PATH}"

    def _record(self, kind: str, message: str) -> None:
        with self.lock:
            self.activity_log.append(
                {
                    "timestamp": time.time(),
                    "kind": kind,
                    "message": message,
                }
            )
            self.activity_log = self.activity_log[-200:]

    def _build_observation_context_display(self) -> str:
        sections: list[str] = []
        if self.observation_context:
            sections.append(f"Observed percepts:\n{self.observation_context}")
        if self.observation_annotations:
            sections.append(
                "Observed callback annotations:\n"
                f"{self.observation_annotations}"
            )
        if self.observation_messages:
            sections.append(
                "Observed callback messages:\n"
                f"{self.observation_messages}"
            )
        return "\n\n".join(sections)

    def _build_profile_graph(self) -> Graph:
        graph = Graph()
        profile_id = URIRef(self.profile_url)
        agent_id = URIRef(f"{self.profile_url}#agent")
        graph.add((profile_id, RDF.type, HMAS.ResourceProfile))
        graph.add((profile_id, HMAS.isProfileOf, agent_id))
        graph.add((agent_id, RDF.type, HMAS.Agent))

        ability = BNode()
        graph.add((agent_id, HMAS.hasAbility, ability))
        graph.add((ability, RDF.type, llm_ability))

        recurrent_policy = BNode()
        graph.add((agent_id, HMAS.hasInteractionPolicy, recurrent_policy))
        graph.add((recurrent_policy, RDF.type, HMAS.RecurrentPolicy))
        graph.add((recurrent_policy, HMAS.hasCallbackUrl, URIRef(self.callback_url)))
        graph.add((recurrent_policy, HMAS.hasRepetitionTime, Literal(10)))

        message_policy = BNode()
        graph.add((agent_id, HMAS.hasInteractionPolicy, message_policy))
        graph.add((message_policy, RDF.type, HMAS.MessagePolicy))
        graph.add((message_policy, HMAS.hasMessageUrl, URIRef(self.message_url)))
        return graph

    async def _list_tools(self) -> list[dict[str, Any]]:
        async with streamable_http_client(_SETUP_MCP_URL) as (read_stream, write_stream, _sid):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()

        tools: list[dict[str, Any]] = []
        for tool in getattr(tools_result, "tools", []) or []:
            input_schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
            tools.append(
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "input_schema": input_schema or {},
                }
            )
        return tools

    async def _call_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        async with streamable_http_client(_SETUP_MCP_URL) as (read_stream, write_stream, _sid):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=tool_input)

        parts: list[str] = []
        for content in getattr(result, "content", None) or []:
            text = getattr(content, "text", None)
            if text is None and isinstance(content, dict):
                text = content.get("text")
            parts.append(text if text is not None else str(content))
        return "\n".join(parts).strip()

    def _state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "goal_prompt": self.goal_prompt,
                "profile_url": self.profile_url,
                "callback_url": self.callback_url,
                "message_url": self.message_url,
                "light_td_url": _LIGHT_TD_URL,
                "memory": dict(self.memory),
                "pending_percepts": list(self.pending_percepts),
                "observation_context": self.observation_context,
                "observation_context_display": self._build_observation_context_display(),
                "observation_annotations": self.observation_annotations,
                "observation_messages": self.observation_messages,
                "activity_log": list(self.activity_log),
                "latest_tool_result": self.latest_tool_result,
                "stopped": self.stopped,
            }

    def _setup_routes(self) -> None:
        @self.app.get("/")
        def index() -> str:
            return render_template_string(HTML_TEMPLATE)

        @self.app.get(_PROFILE_PATH)
        def profile() -> Response:
            mimetype, rdf_format = _select_profile_response_format()
            serialization = self._build_profile_graph().serialize(format=rdf_format)
            return Response(serialization, mimetype=mimetype)

        @self.app.post(_PERCEPTS_PATH)
        def add_percept() -> tuple[Response, int] | Response:
            data = request.get_json(silent=True) or {}
            percept = data.get("percept")
            if not isinstance(percept, str) or not percept.strip():
                return jsonify({"error": "Field 'percept' must be a non-empty string"}), 400

            formatted = percept.strip()
            with self.lock:
                self.pending_percepts.append(formatted)
            self._record("percept_received", formatted)
            return jsonify({"status": "queued"}), 201

        @self.app.post(_ANNOTATION_PATH)
        def add_annotation() -> tuple[Response, int] | Response:
            annotation_document = request.get_data(as_text=True)

            if request.mimetype != "application/ld+json":
                return jsonify({"error": "Content-Type must be application/ld+json"}), 400

            if not annotation_document.strip():
                return jsonify({"error": "Request body must contain JSON-LD"}), 400

            try:
                graph = _parse_rdf_document(annotation_document, "application/ld+json")
                annotations = _extract_annotations(graph)
            except Exception as exc:
                return jsonify({"error": f"Invalid annotation payload: {exc}"}), 400

            if not annotations:
                return jsonify({"error": "No HMAS annotations found in payload"}), 400

            compact_annotations = [
                json.dumps(annotation, separators=(",", ":"), ensure_ascii=True)
                for annotation in annotations
            ]

            with self.lock:
                self.pending_annotation_payloads.extend(compact_annotations)
                self.pending_percepts.extend(
                    [f"callback_annotation={annotation}" for annotation in compact_annotations]
                )

            for annotation in compact_annotations:
                self._record("annotation_received", annotation)

            return jsonify({"status": "queued", "annotations": annotations}), 202

        @self.app.post(_MESSAGE_PATH)
        def add_message() -> tuple[Response, int] | Response:
            message_document = request.get_data(as_text=True)

            if request.mimetype != "application/ld+json":
                return jsonify({"error": "Content-Type must be application/ld+json"}), 400

            if not message_document.strip():
                return jsonify({"error": "Request body must contain JSON-LD"}), 400

            try:
                graph = _parse_rdf_document(message_document, "application/ld+json")
                messages = _extract_messages(graph)
            except Exception as exc:
                return jsonify({"error": f"Invalid message payload: {exc}"}), 400

            if not messages:
                return jsonify({"error": "No HMAS messages found in payload"}), 400

            compact_messages = [
                json.dumps(message, separators=(",", ":"), ensure_ascii=True)
                for message in messages
            ]

            with self.lock:
                self.pending_message_payloads.extend(compact_messages)
                self.pending_percepts.extend(
                    [f"callback_message={message}" for message in compact_messages]
                )

            for message in compact_messages:
                self._record("message_received", message)

            return jsonify({"status": "queued", "messages": messages}), 202

        @self.app.get("/api/state")
        def api_state() -> Response:
            return jsonify(self._state())

        @self.app.get("/api/tools")
        def api_tools() -> tuple[Response, int] | Response:
            try:
                tools = asyncio.run(self._list_tools())
            except Exception as exc:
                return jsonify({"error": f"Failed to load MCP tools: {exc}"}), 502
            return jsonify({"tools": tools})

        @self.app.post("/api/tools/<tool_name>")
        def api_call_tool(tool_name: str) -> tuple[Response, int] | Response:
            data = request.get_json(silent=True) or {}
            tool_input = data.get("tool_input", {})
            if not isinstance(tool_input, dict):
                return jsonify({"error": "tool_input must be a JSON object"}), 400

            try:
                result = asyncio.run(self._call_tool(tool_name, tool_input))
            except Exception as exc:
                self._record("tool_error", f"{tool_name}: {exc}")
                return jsonify({"error": f"Tool call failed: {exc}"}), 502

            with self.lock:
                self.latest_tool_result = result
            self._record("tool_call", f"{tool_name}({json.dumps(tool_input, ensure_ascii=True)})")
            self._record("tool_result", result or "<empty result>")
            return jsonify({"tool": tool_name, "result": result})

        @self.app.post("/api/percepts/consume")
        def api_consume_percepts() -> Response:
            with self.lock:
                consumed = "\n".join(self.pending_percepts)
                consumed_annotations = "\n".join(self.pending_annotation_payloads)
                consumed_messages = "\n".join(self.pending_message_payloads)
                self.pending_percepts = []
                self.pending_annotation_payloads = []
                self.pending_message_payloads = []
                self.observation_context = consumed
                self.observation_annotations = consumed_annotations
                self.observation_messages = consumed_messages
            self._record("observation_context", consumed or "<no new percepts>")
            return jsonify({"observation_context": consumed})

        @self.app.post("/api/permanent-memory")
        def api_permanent_memory() -> tuple[Response, int] | Response:
            data = request.get_json(silent=True) or {}
            field = data.get("field")
            value = data.get("value")
            if not isinstance(field, str) or not field.strip():
                return jsonify({"error": "field must be a non-empty string"}), 400

            with self.lock:
                self.memory[field.strip()] = "" if value is None else str(value)
            self._record("memory_update", f"{field.strip()} = {value!r}")
            return jsonify({"memory": self.memory})

        @self.app.post("/api/decisions")
        def api_decisions() -> tuple[Response, int] | Response:
            data = request.get_json(silent=True) or {}
            note = data.get("note")
            if not isinstance(note, str) or not note.strip():
                return jsonify({"error": "note must be a non-empty string"}), 400
            self._record("decision", note.strip())
            return jsonify({"status": "recorded"})

        @self.app.post("/api/stop")
        def api_stop() -> Response:
            with self.lock:
                self.stopped = True
            self._record("session", "Marked stopped by human operator.")
            return jsonify({"stopped": True})


def ensure_mcp_server_available() -> None:
    parsed = urlparse(_SETUP_MCP_URL)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        raise SystemExit(f"Error: invalid MCP server URL: {_SETUP_MCP_URL}")

    try:
        with socket.create_connection((host, port), timeout=3):
            return
    except OSError as exc:
        raise SystemExit(
            f"Error: MCP server is not running at {_SETUP_MCP_URL}. "
            f"Start mcp/servers/setup_tools.py first. Details: {exc}"
        ) from exc


def main() -> None:
    ensure_mcp_server_available()
    app = HumanControlPanel()
    app._record("session", f"Human control panel started on {_PUBLIC_BASE_URL}")
    app.app.run(host=_HOST, port=_PORT, debug=False)


if __name__ == "__main__":
    main()
