#!/usr/bin/env bash
# deploy/install.sh — one-time setup for Guardian One as a systemd service
#
# Usage:
#   sudo ./deploy/install.sh
#
# What it does:
#   1. Creates a 'guardian' system user (if needed)
#   2. Copies the project to /opt/guardian-one
#   3. Creates a Python venv and installs dependencies
#   4. Installs the systemd unit file
#   5. Enables the service (does NOT start it)

set -euo pipefail

INSTALL_DIR="/opt/guardian-one"
SERVICE_NAME="guardian-one"
SVC_USER="guardian"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Guardian One — Install ==="

# --- System user ---
if ! id "$SVC_USER" &>/dev/null; then
    echo "  Creating system user: $SVC_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
fi

# --- Copy project ---
echo "  Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
rsync -a --exclude='__pycache__' --exclude='.git' --exclude='venv' \
      "$SCRIPT_DIR/" "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
chown -R "$SVC_USER":"$SVC_USER" "$INSTALL_DIR"

# --- Python venv ---
echo "  Setting up Python virtual environment"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# --- systemd unit ---
echo "  Installing systemd service"
cp "$INSTALL_DIR/deploy/guardian-one.service" /etc/systemd/system/"$SERVICE_NAME".service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "  Done. To start the daemon:"
echo "    sudo systemctl start $SERVICE_NAME"
echo "    sudo systemctl status $SERVICE_NAME"
echo "    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "  To reload config (SIGHUP):"
echo "    sudo systemctl reload $SERVICE_NAME"
