#!/bin/bash
set -euo pipefail

RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
NC='[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$SCRIPT_DIR/Lab"
INTERACTION_DIR="$SCRIPT_DIR/InteractionPlatform"
MCP_SERVER_DIR="$SCRIPT_DIR/mcp-server"
declare -a CHILD_PIDS=()
declare -a CHILD_PGIDS=()
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

    echo -e "${YELLOW}Stopping stale ${label} process(es): ${stale_pids[*]}${NC}"
    for pid in "${stale_pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done

    sleep 1

    for pid in "${stale_pids[@]}"; do
        if kill -0 "$pid" >/dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    done

    for pid in "${stale_pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}

wait_for_port() {
    local host="$1"
    local port="$2"
    local label="$3"
    local pid="$4"

    while true; do
        if (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
            return 0
        fi

        if ! kill -0 "$pid" >/dev/null 2>&1; then
            echo -e "${RED}Error: ${label} exited before ${host}:${port} became available${NC}"
            exit 1
        fi

        sleep 1
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

    echo -e "\n${YELLOW}Stopping servers...${NC}"
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
    echo -e "${GREEN}Servers stopped${NC}"
}

start_component() {
    setsid "$@" &
    CHILD_PIDS+=("$!")
    CHILD_PGIDS+=("$!")
}

stop_stale_environment() {
    stop_matching_processes         'environment wrapper'         "$SCRIPT_DIR/run_environment.sh"
    stop_matching_processes         'Lab wrapper'         "$LAB_DIR/run.sh"
    stop_matching_processes         'Node-RED simulator'         "node-red --flows $LAB_DIR/simulator/simulator_flow.json"
    stop_matching_processes         'Lab proxy launcher'         "uv run $LAB_DIR/proxy.py"
    stop_matching_processes         'Lab proxy server'         "$LAB_DIR/.venv/bin/python3 $LAB_DIR/proxy.py"
    stop_matching_processes         'MCP server launcher'         "uv run --project $MCP_SERVER_DIR $MCP_SERVER_DIR/main.py"
    stop_matching_processes         'MCP server'         "$MCP_SERVER_DIR/.venv/bin/python3 $MCP_SERVER_DIR/main.py"
    stop_matching_processes         'Interaction Platform launcher'         'uv run app.py'
    stop_matching_processes         'Interaction Platform server'         "$INTERACTION_DIR/.venv/bin/python3 app.py"
}

if ! command -v uv >/dev/null 2>&1; then
    echo -e "${RED}Error: uv is not installed${NC}"
    echo "Please install uv: https://docs.astral.sh/uv/getting-started/"
    exit 1
fi

if ! command -v node-red >/dev/null 2>&1; then
    echo -e "${RED}Error: node-red is not installed${NC}"
    echo "Please install node-red: npm install -g node-red"
    exit 1
fi

trap cleanup EXIT INT TERM

stop_stale_environment

echo -e "${GREEN}Starting Environment services...${NC}"

echo -e "${YELLOW}Starting Lab environment...${NC}"
start_component bash "$LAB_DIR/run.sh"
LAB_PID="${CHILD_PIDS[-1]}"

wait_for_port "127.0.0.1" "8081" "Lab proxy" "$LAB_PID"

echo -e "${YELLOW}Starting MCP server...${NC}"
start_component uv run --project "$MCP_SERVER_DIR" "$MCP_SERVER_DIR/main.py"
MCP_SERVER_PID="${CHILD_PIDS[-1]}"

wait_for_port "127.0.0.1" "8204" "MCP server" "$MCP_SERVER_PID"

echo -e "${YELLOW}Starting Interaction Platform...${NC}"
(
    cd "$INTERACTION_DIR"
    exec setsid uv run app.py
) &
INTERACTION_PID=$!
CHILD_PIDS+=("$INTERACTION_PID")
CHILD_PGIDS+=("$INTERACTION_PID")

wait_for_port "127.0.0.1" "5001" "Interaction Platform" "$INTERACTION_PID"

echo -e "${GREEN}All servers are running${NC}"
echo -e "${YELLOW}Lab proxy: http://127.0.0.1:8081/kg${NC}"
echo -e "${YELLOW}Interaction Platform: http://127.0.0.1:5001/${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

wait
