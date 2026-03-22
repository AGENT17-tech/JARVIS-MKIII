#!/usr/bin/env bash
# JARVIS-MKIII — Launch Script
# Finds a free port and starts the server cleanly.

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RESET="\033[0m"

PYTHON=$(command -v python3 || command -v python)

# ── Find a free port ──────────────────────────────────────────────────────────
PORT=8000
while lsof -i:$PORT &>/dev/null 2>&1; do
    echo -e "${YELLOW}  Port $PORT in use — trying $((PORT+1))...${RESET}"
    PORT=$((PORT+1))
done

echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════╗"
echo "  ║        JARVIS-MKIII  ONLINE      ║"
echo "  ╚══════════════════════════════════╝"
echo -e "${RESET}"
echo -e "${GREEN}  API:      http://localhost:$PORT${RESET}"
echo -e "${GREEN}  Docs:     http://localhost:$PORT/docs${RESET}"
echo -e "${GREEN}  Status:   http://localhost:$PORT/status${RESET}"
echo -e "${GREEN}  WS:       ws://localhost:$PORT/ws/{session_id}${RESET}"
echo ""

# ── Ensure Ollama is running ──────────────────────────────────────────────────
if ! pgrep -x "ollama" > /dev/null; then
    echo "  Starting Ollama (local tier)..."
    ollama serve &>/dev/null &
    sleep 2
fi

# ── Launch ────────────────────────────────────────────────────────────────────
uvicorn api.main:app --host 0.0.0.0 --port $PORT --reload
