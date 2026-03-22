#!/usr/bin/env bash
# JARVIS-MKIII — Setup Script
# Tested on Ubuntu 24.04 with NVIDIA T1000
# Run: chmod +x setup.sh && ./setup.sh

set -e
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
RESET="\033[0m"

# Resolve python3 binary
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: python3 not found. Install it with: sudo apt install python3"
    exit 1
fi

echo -e "${BOLD}${CYAN}╔══════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║   JARVIS-MKIII  SETUP  SEQUENCE  ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════╝${RESET}"
echo ""

# ── Python dependencies ───────────────────────────────────────────────────────
echo -e "${GREEN}[1/5] Installing Python dependencies...${RESET}"
pip3 install --break-system-packages -r requirements.txt

# ── Vault initialisation ──────────────────────────────────────────────────────
echo -e "${GREEN}[2/5] Initialising secrets vault...${RESET}"
if [ ! -f "config/.vault" ]; then
    $PYTHON core/vault.py init
    echo ""
    echo "Now store your Anthropic API key:"
    $PYTHON core/vault.py set ANTHROPIC_API_KEY
else
    echo "  Vault already exists — skipping."
fi

# ── Ollama setup ───────────────────────────────────────────────────────────────
echo -e "${GREEN}[3/5] Setting up Ollama + DeepSeek-R1...${RESET}"
if ! command -v ollama &> /dev/null; then
    echo "  Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "  Ollama already installed."
fi

# Start ollama only if not already running
if ! pgrep -x "ollama" > /dev/null; then
    echo "  Starting Ollama service..."
    ollama serve &>/dev/null &
    sleep 3
else
    echo "  Ollama already running."
fi

echo "  Pulling DeepSeek-R1 (this may take a while — ~4.7GB)..."
ollama pull deepseek-r1

# ── Memory directory ───────────────────────────────────────────────────────────
echo -e "${GREEN}[4/5] Creating memory store directory...${RESET}"
mkdir -p memory

# ── Run tests ──────────────────────────────────────────────────────────────────
echo -e "${GREEN}[5/5] Running test suite...${RESET}"
pip3 install --break-system-packages pytest pytest-asyncio &>/dev/null
$PYTHON -m pytest tests/ -v --tb=short

echo ""
echo -e "${BOLD}${GREEN}Setup complete.${RESET}"
echo ""
echo -e "${BOLD}Launch JARVIS-MKIII:${RESET}"
echo "  # Find a free port first (default 8000, fallback 8001):"
echo "  PORT=8000"
echo "  while lsof -i:\$PORT &>/dev/null; do PORT=\$((PORT+1)); done"
echo "  uvicorn api.main:app --host 0.0.0.0 --port \$PORT --reload"
echo ""
echo -e "${BOLD}Or use the launch script:${RESET}"
echo "  ./launch.sh"
echo ""
echo -e "${BOLD}Test the stack:${RESET}"
echo "  curl -X POST http://localhost:8000/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"prompt\": \"JARVIS, status report.\"}'"
