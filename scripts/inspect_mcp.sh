#!/usr/bin/env bash
# Launch the MCP Inspector against the Guardian One MCP server.
# Usage: bash scripts/inspect_mcp.sh
set -euo pipefail
cd "$(dirname "$0")/.."
npx @modelcontextprotocol/inspector python mcp_server.py
