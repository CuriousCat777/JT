#!/bin/bash
set -euo pipefail

# Only run on Claude Code web (remote) sessions
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Install main project dependencies (allow partial failures for packages with build issues)
pip install -r "$CLAUDE_PROJECT_DIR/requirements.txt" || pip install --ignore-installed pyyaml cryptography python-dotenv schedule rich openpyxl flask pytest pytest-asyncio ollama anthropic httpx python-kasa whoosh

# Install search subsystem dependencies
pip install whoosh pyyaml 2>/dev/null || true
pip install -r "$CLAUDE_PROJECT_DIR/search/requirements.txt" 2>/dev/null || true

# Set PYTHONPATH so guardian_one package is importable
echo "export PYTHONPATH=\"$CLAUDE_PROJECT_DIR\"" >> "$CLAUDE_ENV_FILE"
