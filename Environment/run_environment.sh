#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$SCRIPT_DIR/Lab"
INTERACTION_DIR="$SCRIPT_DIR/InteractionPlatform"
MCP_SERVER_DIR="$SCRIPT_DIR/mcp-server"

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

cleanup() {
    echo -e "\n${YELLOW}Stopping servers...${NC}"
    kill "$LAB_PID" 2>/dev/null || true
    kill "$MCP_SERVER_PID" 2>/dev/null || true
    kill "$INTERACTION_PID" 2>/dev/null || true
    wait "$LAB_PID" 2>/dev/null || true
    wait "$MCP_SERVER_PID" 2>/dev/null || true
    wait "$INTERACTION_PID" 2>/dev/null || true
    echo -e "${GREEN}Servers stopped${NC}"
    exit 0
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

trap cleanup SIGINT SIGTERM

echo -e "${GREEN}Starting Environment services...${NC}"

echo -e "${YELLOW}Starting Lab environment...${NC}"
bash "$LAB_DIR/run.sh" &
LAB_PID=$!

wait_for_port "127.0.0.1" "8081" "Lab proxy" "$LAB_PID"

echo -e "${YELLOW}Starting MCP server...${NC}"
(uv run --project "$MCP_SERVER_DIR" "$MCP_SERVER_DIR/main.py") &
MCP_SERVER_PID=$!

wait_for_port "127.0.0.1" "8204" "MCP server" "$MCP_SERVER_PID"

echo -e "${YELLOW}Starting Interaction Platform...${NC}"
(cd "$INTERACTION_DIR" && uv run app.py) &
INTERACTION_PID=$!

wait_for_port "127.0.0.1" "5001" "Interaction Platform" "$INTERACTION_PID"

echo -e "${GREEN}All servers are running${NC}"
echo -e "${YELLOW}Lab proxy: http://127.0.0.1:8081/kg${NC}"
echo -e "${YELLOW}Interaction Platform: http://127.0.0.1:5001/${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

wait
