#!/usr/bin/env bash
# Guardian One — Production deployment script
# Usage: sudo ./deploy/install.sh
set -euo pipefail

INSTALL_DIR="/opt/guardian-one"
SERVICE_USER="guardian"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Guardian One Production Install ==="

# 1. Create service user (no login shell)
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "[+] Creating service user: $SERVICE_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# 2. Set up install directory
echo "[+] Setting up $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"/{data,logs,config}
cp -r "$REPO_DIR"/guardian_one "$INSTALL_DIR/"
cp "$REPO_DIR"/main.py "$INSTALL_DIR/"
cp "$REPO_DIR"/requirements.txt "$INSTALL_DIR/"
cp "$REPO_DIR"/config/guardian_config.yaml "$INSTALL_DIR/config/"

# 3. Python virtual environment
echo "[+] Creating virtual environment"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 4. Set permissions
echo "[+] Setting permissions"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/data"
chmod 700 "$INSTALL_DIR/logs"

# 5. Install systemd service
echo "[+] Installing systemd service"
cp "$REPO_DIR/deploy/guardian-one.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable guardian-one

# 6. Prompt for .env
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo ""
    echo "[!] Create $INSTALL_DIR/.env with your secrets:"
    echo "    GUARDIAN_MASTER_PASSPHRASE=<your-passphrase>"
    echo "    NOTION_TOKEN=<optional>"
    echo "    ANTHROPIC_API_KEY=<optional>"
    echo ""
    echo "    Then start with: sudo systemctl start guardian-one"
else
    echo "[+] .env found — starting service"
    systemctl start guardian-one
    systemctl status guardian-one --no-pager
fi

echo ""
echo "=== Install complete ==="
echo "  Status:  sudo systemctl status guardian-one"
echo "  Logs:    sudo journalctl -u guardian-one -f"
echo "  Health:  curl http://localhost:8080/health"
