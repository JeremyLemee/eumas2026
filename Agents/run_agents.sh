#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

start_agent() {
  local agent_dir="$1"
  shift

  (
    cd "$ROOT_DIR/$agent_dir"
    "$@"
  ) &
}

start_agent "coala_agent" uv run setup_agent.py
start_agent "soar_agent" ./gradlew run
start_agent "jason_agent" ./gradlew run

wait
