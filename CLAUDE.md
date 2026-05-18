# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-project workspace containing cognitive agent implementations and supporting infrastructure. The repository is divided into:

- **Agents/** — Three agent implementations with different architectures:
  - `coala_agent/` — LLM-based cognitive agent using Python (CoALA framework)
  - `jason_agent/` — BDI agent using JaCaMo (Java)
  - `soar_agent/` — Soar cognitive architecture agent (Java)

- **Environment/** — Supporting infrastructure:
  - `InteractionPlatform/` — Web-based platform for agent interaction (Python/Flask)
  - `Lab/` — Simulator and proxy environment (Python with Node-Red)
  - `mcp-server/` — MCP (Model Context Protocol) server providing tools and UI (Python)

- **ontologies/** — Shared RDF/Turtle ontology definitions used across projects

## Architecture & Design

The system uses a client-server architecture where:

1. **Lab (Simulator & Proxy)** — Provides HTTP-accessible knowledge graphs at `http://localhost:8081`. The proxy translates between agents and the simulator environment.

2. **Interaction Platform** — Web interface running on `http://localhost:5001` that manages agent interactions and state.

3. **MCP Server** — Exposes tools and UIs to agents via HTTP streamable transport at `http://localhost:8082/mcp`, with a user interface at `http://localhost:9966`.

4. **Agents** — Three independent agent implementations that communicate with the Lab proxy and MCP server:
   - CoALA agent uses LLM reasoning via LangChain with Ollama/OpenAI
   - Jason agent uses JaCaMo (Jason + CArtAgO + MOISE)
   - Soar agent uses JSoar (Java Soar) with reinforcement learning

The ontologies (shared belief models, BDI concepts, lab environment schemas) are defined in Turtle format and referenced across agents and the proxy.

## Build & Development Commands

### Python Projects

For any Python project (Agents/coala_agent, Environment/InteractionPlatform, Environment/Lab, Environment/mcp-server):

```bash
# Install dependencies
cd <project-dir>
uv sync

# Run the service/agent
uv run <script>  # e.g., uv run app.py, uv run setup_agent.py

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type-check
uv run pyright
```

### Java/JaCaMo Projects

For Agents/jason_agent and Agents/soar_agent:

```bash
# Run the agent
cd <agent-dir>
./gradlew run

# Run tests
./gradlew testJaCaMo  # JaCaMo tests (Jason agent)
# or for Soar, check the test task defined in build.gradle
```

### Running the Full Environment

Start all environment services (Lab, MCP server, Interaction Platform) with:

```bash
bash Environment/run_environment.sh
```

This script waits for each service to become available before starting the next. Press Ctrl+C to stop all services.

Start all three agents with:

```bash
bash Agents/run_agents.sh
```

## Configuration

Projects store configuration in `config.json` files:

- **Agents/coala_agent/config.json** — LLM API keys, service endpoints
- **Environment/Lab/config.json** — Lab simulator configuration
- **Environment/mcp-server/config.json** — MCP server settings

Do not commit secrets or machine-specific endpoints; use local overrides or environment variables.

## Testing & Validation

### Python Testing

From the project directory:
```bash
uv run pytest                        # Run all tests
uv run pytest tests/test_file.py    # Run a single test file
uv run pytest tests/test_file.py::test_function  # Run a single test
```

### JaCaMo Testing

From the agent directory:
```bash
./gradlew testJaCaMo  # Runs tests defined in src/test/tests.jcm
```

### Service Health Checks

After starting the environment, verify services are available:
- Lab proxy knowledge graph: `http://localhost:8081/kg` (Turtle format)
- Interaction Platform: `http://localhost:5001/`
- MCP server: `http://localhost:8082/mcp`

## Code Organization & Conventions

### Python Style

- 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes
- Use `ruff` for linting and `pyright` for type-checking (see tool.ruff and tool.pyright in pyproject.toml)
- Tests follow `test_*.py` naming

### Java/JaCaMo Style

- `PascalCase` for Java classes
- `.asl` agent files use lower-case names (e.g., `lab_agent.asl`)
- Follow Gradle conventions; see build.gradle for source and test layout

### Ontology Files

Ontologies in `ontologies/` use Turtle (.ttl) format:
- **bdi.ttl** — BDI (Belief-Desire-Intention) concepts shared across agents
- **lab.ttl** — Lab environment and simulator schemas
- **soar.ttl** — Soar-specific ontology extensions
- **hmas-extension.ttl** — HMAS hypermedia multi-agent systems extensions
- **llm.ttl** — LLM reasoning and memory models

Local copies of ontologies may exist in agent directories; keep them in sync with the root ontologies/ directory.

## Service Ports

- **5001** — Interaction Platform (Flask web UI)
- **1880** — Node-Red (Lab simulator editor, URL: `http://localhost:1880/was/rl`)
- **8081** — Lab proxy (REST API and knowledge graph at `/kg`)
- **8082** — MCP server (HTTP streamable transport)
- **9966** — MCP server user interface
- **8204** — MCP server health/status check (internal)

## Key Dependencies

### Python

- **Flask** — Web framework (Interaction Platform, MCP server)
- **RDFlib** — RDF triple store and Turtle parsing
- **LangChain / LangGraph** — LLM orchestration and reasoning (CoALA agent)
- **MCP SDK** — Model Context Protocol client/server
- **Pytest** — Testing framework

### Java

- **JaCaMo** — BDI agent development (Jason agent)
- **JSoar** — Soar cognitive architecture (Soar agent)
- **RDF4J** — RDF processing and storage
- **Apache HttpClient** — HTTP communication with Lab proxy

## Debugging & Troubleshooting

### Common Issues

1. **Service fails to start** — Check that required ports are not in use and all dependencies are installed (`uv sync` or `./gradlew build`).

2. **Lab proxy connection refused** — Ensure Node-Red is running and `run_environment.sh` has started the Lab environment.

3. **MCP server errors** — Check `setup_tools_log.txt` in Environment/mcp-server for tool definition issues.

4. **Agent connection errors** — Verify agents are pointing to correct service endpoints in config.json (typically localhost with the ports listed above).

5. **Ontology parsing failures** — Ensure Turtle files in ontologies/ are well-formed RDF (use `rdflib` for validation).

### Development Notes

- The project uses `uv` for Python dependency management; always use `uv run` instead of `python` directly.
- Java agents require Java 17+ (Jason) or Java 21+ (Soar); check `java.toolchain.languageVersion` in build.gradle.
- Changes to shared ontologies in `ontologies/` should be validated against all consuming projects before committing.
