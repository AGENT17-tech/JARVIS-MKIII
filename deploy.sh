#!/usr/bin/env bash
# JARVIS-MKIII — deploy.sh
# Run from inside ~/JARVIS_MKIII/
# Usage: chmod +x deploy.sh && ./deploy.sh

set -e
GREEN="\033[0;32m"; CYAN="\033[0;36m"; BOLD="\033[1m"; RESET="\033[0m"
PYTHON=$(command -v python3 || command -v python)
BASE="$(cd "$(dirname "$0")" && pwd)"

echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║    JARVIS-MKIII  DEPLOY  SEQUENCE    ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${RESET}"

# ── 1. Install dependencies ──────────────────────────────────────────────────
echo -e "${GREEN}[1/5] Installing dependencies...${RESET}"
pip3 install --break-system-packages -r "$BASE/backend/requirements.txt"

# ── 2. Vault init ────────────────────────────────────────────────────────────
echo -e "${GREEN}[2/5] Checking vault...${RESET}"
if [ ! -f "$BASE/backend/config/.vault" ]; then
    echo "Initialising vault..."
    cd "$BASE/backend" && $PYTHON core/vault.py init
    echo "Store your Groq API key:"
    $PYTHON core/vault.py set GROQ_API_KEY
    echo "Store your OpenWeather API key:"
    $PYTHON core/vault.py set OPENWEATHER_API_KEY
else
    echo "  Vault exists — skipping."
fi

# ── 3. Install system services ───────────────────────────────────────────────
echo -e "${GREEN}[3/5] Installing systemd services...${RESET}"

# Backend (system service)
sudo cp "$BASE/jarvis-mkiii.service" /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/jarvis-mkiii.service.d/

# Inject API keys into service environment
GROQ_KEY=$(cd "$BASE/backend" && $PYTHON -c "from core.vault import Vault; print(Vault().get('GROQ_API_KEY'))")
OWM_KEY=$(cd "$BASE/backend" && $PYTHON -c "from core.vault import Vault; print(Vault().get('OPENWEATHER_API_KEY'))")

sudo tee /etc/systemd/system/jarvis-mkiii.service.d/override.conf > /dev/null << EOF
[Service]
Environment="GROQ_API_KEY=${GROQ_KEY}"
Environment="OPENWEATHER_API_KEY=${OWM_KEY}"
EOF

sudo systemctl daemon-reload
sudo systemctl enable jarvis-mkiii
sudo systemctl restart jarvis-mkiii

# Voice (user service)
mkdir -p ~/.config/systemd/user/
cp "$BASE/jarvis-voice.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable jarvis-voice
systemctl --user restart jarvis-voice

# ── 4. HUD autostart ─────────────────────────────────────────────────────────
echo -e "${GREEN}[4/5] Updating HUD autostart...${RESET}"
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/jarvis-hud.desktop << EOF
[Desktop Entry]
Type=Application
Name=JARVIS HUD
Exec=bash -c "cd $BASE/hud && npm run start"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

# ── 5. Verify ────────────────────────────────────────────────────────────────
echo -e "${GREEN}[5/5] Verifying...${RESET}"
sleep 4
curl -s http://localhost:8000/status | python3 -m json.tool

echo ""
echo -e "${BOLD}${GREEN}JARVIS-MKIII deployed successfully.${RESET}"
echo ""
echo -e "${BOLD}Start the HUD:${RESET}"
echo "  cd ~/JARVIS_MKIII/hud && npm run start"
