#!/usr/bin/env bash
# ============================================================================
# Guardian One — TelePrompter Server Launcher
# Start the teleprompter web app for phone access on your local network.
# ============================================================================

set -euo pipefail

PORT=5200
TOKEN_FILE="$HOME/.guardian_teleprompter_token"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

cleanup() {
    echo ""
    echo -e "${CYAN}Shutting down TelePrompter server...${RESET}"
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    echo -e "${GREEN}Server stopped. Goodbye.${RESET}"
    exit 0
}

echo -e "${BOLD}========================================${RESET}"
echo -e "${BOLD}  Guardian One — TelePrompter Server${RESET}"
echo -e "${BOLD}========================================${RESET}"
echo ""

# --- Check Python 3 ---
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}ERROR: Python 3 is not installed.${RESET}"
    echo "Install it with:  brew install python3  (macOS)  or  sudo apt install python3 (Linux)"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo -e "${GREEN}Found: ${PYTHON_VERSION}${RESET}"

# --- Check Flask ---
if ! python3 -c "import flask" 2>/dev/null; then
    echo -e "${RED}ERROR: Flask is not installed.${RESET}"
    echo "Install it with:  pip3 install flask"
    exit 1
fi

echo -e "${GREEN}Found: Flask$(python3 -c "import flask; print(' ' + flask.__version__)")${RESET}"
echo ""

# --- Auto-detect local IP ---
LOCAL_IP=""

# Try macOS method first
if command -v ipconfig &>/dev/null; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
fi

# Try Linux method
if [ -z "$LOCAL_IP" ] && command -v hostname &>/dev/null; then
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
fi

# Try ip command
if [ -z "$LOCAL_IP" ] && command -v ip &>/dev/null; then
    LOCAL_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' || true)
fi

# Fallback
if [ -z "$LOCAL_IP" ]; then
    echo -e "${RED}WARNING: Could not detect local IP address.${RESET}"
    echo "You may need to find it manually (ifconfig / ip addr)."
    LOCAL_IP="YOUR_IP"
fi

# --- Generate or load API token ---
if [ -f "$TOKEN_FILE" ]; then
    TOKEN=$(cat "$TOKEN_FILE")
    echo -e "Using existing API token from ${TOKEN_FILE}"
else
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(24))")
    echo "$TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    echo -e "Generated new API token (saved to ${TOKEN_FILE})"
fi
echo ""

# --- Print access info ---
URL="http://${LOCAL_IP}:${PORT}"

echo -e "${BOLD}========================================${RESET}"
echo -e "${BOLD}  SERVER READY${RESET}"
echo -e "${BOLD}========================================${RESET}"
echo ""
echo -e "  ${CYAN}${BOLD}${URL}${RESET}"
echo ""
echo -e "  API Token: ${TOKEN}"
echo ""
echo -e "${BOLD}--- iPhone Setup ---${RESET}"
echo -e "  1. Make sure your phone is on the same Wi-Fi network"
echo -e "  2. Open Safari on your iPhone"
echo -e "  3. Type the URL above into the address bar"
echo -e "  4. Tap ${BOLD}Share${RESET} (box with arrow) -> ${BOLD}Add to Home Screen${RESET}"
echo -e "  5. Now you have a TelePrompter app on your home screen!"
echo ""
echo -e "${BOLD}========================================${RESET}"
echo -e "  Press Ctrl+C to stop the server"
echo -e "${BOLD}========================================${RESET}"
echo ""

# --- Start the server ---
trap cleanup INT TERM

cd "$PROJECT_DIR"
python3 -m guardian_one.web.teleprompter.server --port "$PORT" --token "$TOKEN" &
SERVER_PID=$!

# Wait for the server process
wait "$SERVER_PID"
