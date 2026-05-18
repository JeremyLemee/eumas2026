#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}Starting light-server environment...${NC}"

# Check if node-red is installed
if ! command -v node-red &> /dev/null; then
    echo -e "${RED}Error: node-red is not installed${NC}"
    echo "Please install node-red: npm install -g node-red"
    exit 1
fi

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed${NC}"
    echo "Please install uv: https://docs.astral.sh/uv/getting-started/"
    exit 1
fi

# Start node-red with simulator flow
echo -e "${YELLOW}Starting Node-RED simulator...${NC}"
node-red --flows simulator/simulator_flow.json &
NODE_RED_PID=$!
echo -e "${GREEN}Node-RED started (PID: $NODE_RED_PID)${NC}"

# Wait for node-red to initialize
sleep 3

# Start the proxy
echo -e "${YELLOW}Starting proxy server...${NC}"
uv run "$SCRIPT_DIR/proxy.py" &
PROXY_PID=$!
echo -e "${GREEN}Proxy started (PID: $PROXY_PID)${NC}"

echo -e "${GREEN}All services started successfully!${NC}"
echo -e "${YELLOW}Node-RED: http://localhost:1880${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

# Cleanup function
cleanup() {
    echo -e "\n${RED}Stopping services...${NC}"
    kill $NODE_RED_PID 2>/dev/null || true
    kill $PROXY_PID 2>/dev/null || true
    wait $NODE_RED_PID 2>/dev/null || true
    wait $PROXY_PID 2>/dev/null || true
    echo -e "${GREEN}Services stopped${NC}"
    exit 0
}

# Set up signal handlers for graceful shutdown
trap cleanup SIGINT SIGTERM

# Wait for both processes
wait
