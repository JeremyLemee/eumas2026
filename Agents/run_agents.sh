#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
RUN_ID="$(date '+%Y%m%d-%H%M%S')"
RUN_LOG_DIR="$LOG_DIR/$RUN_ID"
declare -a CHILD_PIDS=()
declare -a CHILD_PGIDS=()
declare -a AGENT_ORDER=()
declare -A AGENT_PIDS=()
declare -A AGENT_LOG_FILES=()
declare -A AGENT_LOG_OFFSETS=()
cleanup_ran=0

gather_matching_pids() {
  local pattern="$1"
  ps -eo pid=,args= | awk -v pattern="$pattern" 'index($0, pattern) {print $1}'
}

stop_matching_processes() {
  local label="$1"
  local pattern="$2"
  local -a stale_pids=()
  local pid

  while IFS= read -r pid; do
    stale_pids+=("$pid")
  done < <(gather_matching_pids "$pattern")

  if ((${#stale_pids[@]} == 0)); then
    return
  fi

  printf 'Stopping stale %s process(es): %s\n' "$label" "${stale_pids[*]}"
  for pid in "${stale_pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done

  sleep 1

  for pid in "${stale_pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done

  for pid in "${stale_pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

stop_process_group() {
  local pgid="$1"
  local signal="${2:-TERM}"

  if [[ -z "$pgid" ]]; then
    return
  fi

  kill "-${signal}" -- "$pgid" 2>/dev/null || true
}

cleanup() {
  local pgid
  local pid

  if ((cleanup_ran)); then
    return
  fi
  cleanup_ran=1

  for pgid in "${CHILD_PGIDS[@]:-}"; do
    stop_process_group "$pgid" TERM
  done

  sleep 2

  for pgid in "${CHILD_PGIDS[@]:-}"; do
    stop_process_group "$pgid" KILL
  done

  for pid in "${CHILD_PIDS[@]:-}"; do
    wait "$pid" 2>/dev/null || true
  done
}

read_new_log_bytes() {
  local agent_name="$1"
  local file_path="${AGENT_LOG_FILES[$agent_name]}"
  local offset="${AGENT_LOG_OFFSETS[$agent_name]:-0}"
  local file_size

  file_size=$(wc -c < "$file_path")
  if ((file_size <= offset)); then
    return
  fi

  printf '\n========== %s ==========' "$agent_name"
  printf '\n'
  dd if="$file_path" bs=1 skip="$offset" count="$((file_size - offset))" status=none
  AGENT_LOG_OFFSETS["$agent_name"]="$file_size"
}

stream_agent_logs() {
  local has_running_children=1
  local agent_name
  local pid

  while ((has_running_children)); do
    has_running_children=0

    for agent_name in "${AGENT_ORDER[@]}"; do
      read_new_log_bytes "$agent_name"

      pid="${AGENT_PIDS[$agent_name]}"
      if kill -0 "$pid" 2>/dev/null; then
        has_running_children=1
      fi
    done

    sleep 1
  done

  for agent_name in "${AGENT_ORDER[@]}"; do
    read_new_log_bytes "$agent_name"
  done
}

stop_stale_agents() {
  stop_matching_processes     'CoALA agent wrapper'     "$ROOT_DIR/coala_agent/.venv/bin/python3 setup_agent.py"
  stop_matching_processes     'CoALA agent launcher'     'uv run setup_agent.py'
  stop_matching_processes     'Soar agent wrapper'     "$ROOT_DIR/soar_agent/gradle/wrapper/gradle-wrapper.jar run"
  stop_matching_processes     'Soar agent JVM'     "$ROOT_DIR/soar_agent/build/classes/java/main"
  stop_matching_processes     'Jason agent wrapper'     "$ROOT_DIR/jason_agent/gradle/wrapper/gradle-wrapper.jar run"
  stop_matching_processes     'Jason agent JVM'     "$ROOT_DIR/jason_agent/build/classes/java/main"
}

start_agent() {
  local agent_name="$1"
  local agent_dir="$2"
  shift 2
  local log_file="$RUN_LOG_DIR/${agent_name}.log"

  AGENT_ORDER+=("$agent_name")
  AGENT_LOG_FILES["$agent_name"]="$log_file"
  AGENT_LOG_OFFSETS["$agent_name"]=0

  {
    printf 'Working directory: %s\n' "$ROOT_DIR/$agent_dir"
    printf 'Command: %s\n' "$*"
    printf 'Log file: %s\n' "$log_file"
    printf '\n'
  } > "$log_file"

  (
    cd "$ROOT_DIR/$agent_dir"
    exec setsid "$@" >> "$log_file" 2>&1
  ) &

  CHILD_PIDS+=("$!")
  CHILD_PGIDS+=("$!")
  AGENT_PIDS["$agent_name"]="$!"
}

trap cleanup EXIT INT TERM

stop_stale_agents
mkdir -p "$RUN_LOG_DIR"

printf 'Agent logs are being written to %s\n' "$RUN_LOG_DIR"
printf 'Terminal output is streamed sequentially by agent to avoid interleaved logs.\n'

start_agent "coala_agent" "coala_agent" uv run setup_agent.py
start_agent "soar_agent" "soar_agent" ./gradlew run
start_agent "jason_agent" "jason_agent" ./gradlew run

stream_agent_logs
wait
