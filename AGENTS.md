# Repository Guidelines

## Project Structure & Module Organization
This repository is a multi-project workspace for agents and lab infrastructure.
`Agents/` contains the agent implementations: `Agents/coala_agent/` and `Environment/InteractionPlatform/` are Python projects, while `Agents/jason_agent/` and `Agents/soar_agent/` are Gradle-based Java/JaCaMo projects.
Shared ontology files live in `ontologies/`, and lab support code is under `Environment/Lab/`.
Keep tests close to the project they exercise, for example `Environment/InteractionPlatform/tests/` or `Agents/jason_agent/src/test/`.

## Build, Test, and Development Commands
There is no single root build command; run commands from the relevant subproject.
For Python projects, use:
`uv sync` to install dependencies, `uv run pytest` to run tests, `uv run ruff check .` to lint, and `uv run pyright` to type-check.
For `Environment/InteractionPlatform/`, `uv run app.py` starts the service.
For Java/JaCaMo projects, use `./gradlew run` to launch the agent and `./gradlew test` to run the project test task.
`Environment/Lab/run.sh` starts the local lab environment and requires both `node-red` and `uv`.

## Coding Style & Naming Conventions
Follow the local language conventions already used in the repo.
Python code uses 4-space indentation, `snake_case` for functions and modules, and `PascalCase` for classes.
Java classes use `PascalCase`, while agent files and ASL artifacts use lower-case names such as `lab_agent.asl`.
Prefer ASCII-only text unless a file already contains non-ASCII content.
Use the existing formatters and linters in each project: `ruff` and `pyright` for Python, Gradle conventions for Java.

## Testing Guidelines
Python tests follow `test_*.py` naming, with reusable fixtures or fakes defined near the test body when helpful.
JaCaMo tests live under `src/test/` and are wired through the Gradle `test` task.
Add tests for behavior changes, especially around ontology handling, environment setup, and HTTP integration.
If a change affects multiple subprojects, run the relevant test suite in each one instead of relying on a repo-wide command.

## Commit & Pull Request Guidelines
The Git history currently contains only an initial commit, so no strict commit convention is established yet.
Use short, imperative commit messages that describe the change, such as `fix lab proxy startup`.
Pull requests should summarize the affected subproject(s), list validation steps, and include screenshots or logs when UI or runtime behavior changes.
Call out any required runtime configuration, such as `LAB_SERVER_URL` or local service endpoints.

## Security & Configuration Tips
Do not commit secrets, API keys, or machine-specific endpoints.
Several projects assume local services are running at fixed URLs; verify `config.json` files and README instructions before changing defaults.
