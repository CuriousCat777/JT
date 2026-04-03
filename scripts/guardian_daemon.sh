#!/usr/bin/env bash
# Guardian One — Linux Daemon Startup Script
# Used by the guardian-one.service systemd unit.
#
# What it does:
#   1. Loads .env (secrets, API keys, GUARDIAN_MASTER_PASSPHRASE)
#   2. Activates the project virtualenv
#   3. Validates critical prerequisites
#   4. Launches Guardian One in daemon mode (headless scheduler)
#
# Manual usage:
#   ./scripts/guardian_daemon.sh
#
# The systemd unit calls this script automatically on boot / restart.

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"
LOG_DIR="$PROJECT_DIR/logs"
DATA_DIR="$PROJECT_DIR/data"

# ── Ensure directories ──────────────────────────────────────────────
mkdir -p "$LOG_DIR" "$DATA_DIR"

# ── Load environment (safe parser — never source/eval) ──────────────
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Strip leading whitespace
        trimmed="${line#"${line%%[![:space:]]*}"}"

        # Skip blank lines and comments
        case "$trimmed" in
            ""|\#*) continue ;;
        esac

        # Strip optional 'export ' prefix
        case "$trimmed" in
            export[[:space:]]*)
                trimmed="${trimmed#export }"
                trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"
                ;;
        esac

        # Must contain '='
        if [[ "$trimmed" != *=* ]]; then
            echo "[guardian-daemon] WARNING: skipping invalid line in $ENV_FILE: $line"
            continue
        fi

        key="${trimmed%%=*}"
        value="${trimmed#*=}"

        # Trim whitespace
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"

        # Validate variable name
        if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
            echo "[guardian-daemon] WARNING: skipping invalid var name in $ENV_FILE: $key"
            continue
        fi

        # Strip surrounding quotes
        if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
            value="${value:1:${#value}-2}"
        fi

        export "$key=$value"
    done < "$ENV_FILE"
else
    echo "[guardian-daemon] WARNING: $ENV_FILE not found — running with inherited env"
fi

# ── Activate virtualenv ─────────────────────────────────────────────
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[guardian-daemon] FATAL: virtualenv not found at $VENV_DIR"
    echo "[guardian-daemon] Run: python3 -m venv $VENV_DIR && $VENV_DIR/bin/pip install -r requirements.txt -e '.[dev]'"
    exit 1
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# ── Validate prerequisites ──────────────────────────────────────────
if [ -z "${GUARDIAN_MASTER_PASSPHRASE:-}" ]; then
    echo "[guardian-daemon] FATAL: GUARDIAN_MASTER_PASSPHRASE not set"
    echo "[guardian-daemon] Set it in $ENV_FILE or export it before running."
    exit 1
fi

# ── Launch ──────────────────────────────────────────────────────────
cd "$PROJECT_DIR"
echo "[guardian-daemon] Starting Guardian One daemon..."
echo "[guardian-daemon] Project: $PROJECT_DIR"
echo "[guardian-daemon] Python:  $(python --version)"
echo "[guardian-daemon] PID:     $$"
echo "[guardian-daemon] Time:    $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

exec python main.py --daemon
