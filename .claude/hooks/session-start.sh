#!/bin/bash
set -euo pipefail

# Only run in remote (web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PIP_FLAGS="--break-system-packages --quiet"

# Fix cffi/cryptography (system cryptography may have broken cffi binding)
pip install cffi $PIP_FLAGS 2>/dev/null || true
pip install cryptography --ignore-installed $PIP_FLAGS 2>/dev/null || true

# Install core dependencies (--ignore-installed avoids debian RECORD issues)
pip install --ignore-installed pyyaml python-dotenv schedule rich openpyxl \
  flask pytest pytest-asyncio ollama anthropic httpx mcp fpdf2 \
  $PIP_FLAGS 2>/dev/null || true

# Install the project in editable mode so imports resolve
pip install -e "$CLAUDE_PROJECT_DIR" --no-deps $PIP_FLAGS 2>/dev/null || true

# Ensure PYTHONPATH includes the project root (idempotent)
env_line="export PYTHONPATH=\"$CLAUDE_PROJECT_DIR:\${PYTHONPATH:-}\""
if ! grep -Fqx "$env_line" "$CLAUDE_ENV_FILE" 2>/dev/null; then
  echo "$env_line" >> "$CLAUDE_ENV_FILE"
fi
