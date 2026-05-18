# EUMAS 2026

## Prerequisites

1) Install [`uv`](https://docs.astral.sh/uv/)

2) Install [`Node-Red`](https://nodered.org/docs/getting-started/local)

## Ontologies

The ontologies are available [`here`](ontologies).


## Environment

Run the environment servers with [`run_environment.sh`](Environment/run_environment.sh).

### Interaction Platform

The code for the Interaction Platform is available [`here`](Environment/InteractionPlatform).

The Interaction Platform is running on port 5001: http://localhost:5001/.

### Lab

The code for the Lab (simulator and proxy) is available [`here`](Environment/Lab).

The simulator is available at the URL: http://localhost:1880/was/rl.

The proxy is available at the URL: http://localhost:8081. Its knowledge graph is available in Turtle at http://localhost:8081/kg.

### MCP server

The MCP server provides tools for the CoALA agent. Its code is available [`here`](Environment/mcp-server).

The MCP server relies on the streamable HTTP transport and is available at: http://localhost:8082/mcp.

The MCP server also runs the user interface at: http://localhost:9966.


## Agents

Run all the agents [`run_agents.sh`](Agents/run_agents.sh).

## Jason agent

The code for the Jason agent is available [`here`](Agents/jason_agent).

## Soar agent

The code for the Soar agent is available [`here`](Agents/soar_agent).

## CoALA agent

The code for the CoALA agent is available [`here`](Agents/coala_agent).

## Scenario

The API keys for OpenAI models need to be configured at [`API_KEY.txt`](Environment/InteractionPlatform/API_KEY.txt) for the Interaction Platform and [`API_KEY.txt`](Agents/coala_agent/API_KEY.txt) for the CoALA agent.

First, run the environment using [`run_environment.sh`](Environment/run_environment.sh).

Then, set the user goal using the GUI provided at: http://localhost:9966/ (or use the default goal).

Then, run the agents with [`run_agents.sh`](Agents/run_agents.sh).

For creating different variations, select the transformation and generation functions available in [`app.py`](Environment/InteractionPlatform/app.py).


## Generative AI use

Made using Codex and Claude Code.



