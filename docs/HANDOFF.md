# SYSTEM HANDOFF: Guardian One + Ryzen MCP Infrastructure

**Role:** Systems Maintenance Managers (Varys/Guardian)
**Status:** Active
**Date:** 2026-04-02

## Context

- **Recent Activity:** Added MCP servers to both JT and Ryzen repos on branch `claude/add-mcp-inspector-YBhrL`. Fixed crash bug in JT MCP server (BaseException catch for cryptography Rust panic). Set permissions to bypassPermissions globally.
- **Technical Stack:** Python MCP SDK (mcp>=1.0.0), FastMCP, Guardian One multi-agent system (Chronos, Archivist, CFO, DoorDash, Gmail, WebArchitect), Node.js v22 for Inspector
- **Known Blockers:** `cryptography` Rust bindings broken in current env (pyo3 panic) — MCP server degrades gracefully. Remote scheduling service (CronCreate/RemoteTrigger) disconnected — `/loop` and `/schedule` unavailable.

## Instructions

1. Verify MCP servers import cleanly:
   ```bash
   cd ~/JT && GUARDIAN_MASTER_PASSPHRASE=test python -c "from mcp_server import mcp, _boot_error; print(len(mcp._tool_manager.list_tools()), _boot_error)"
   ```
2. Verify Ryzen MCP:
   ```bash
   cd ~/Ryzen && python -c "import mcp_server; print('OK')"
   ```
3. Confirm both branches pushed:
   ```bash
   git -C ~/JT log --oneline -3
   git -C ~/Ryzen log --oneline -3
   ```
4. Monitor Chronos agent health (first agent) — calendar sync, conflict detection, sleep analysis
5. Do not create PRs unless explicitly requested

## Validation Criteria

- **Success:** JT MCP server registers 10 tools, Ryzen registers 3 tools, both repos clean on `claude/add-mcp-inspector-YBhrL`
- **Fallback:** If MCP import fails, check `pip show mcp` and reinstall if needed

## Checkpoint State

| Variable | Value |
|----------|-------|
| Branch | `claude/add-mcp-inspector-YBhrL` (both repos) |
| JT_Commits | 2 (initial MCP server + BaseException fix) |
| Ryzen_Commits | 1 (initial MCP server) |
| JT_MCP_Tools | 10 (system_status, list_agents, run_agent, daily_summary, audit_log, pending_reviews, security_audit, vault_health, gateway_status, monitor_health) |
| Ryzen_MCP_Tools | 3 (ping, system_info, echo) |
| Permissions_Mode | bypassPermissions |
| BORIS_Daily_Check | NOT_SCHEDULED (remote service unavailable) |
| Chronos_Status | First agent reviewed, 424 lines, healthy |

## Agent Architecture Reference

```
guardian_one/agents/
├── chronos.py         # Time management (calendar, sleep, workflows, pre-charting)
├── archivist.py       # File & data sovereignty
├── cfo.py             # Financial intelligence (Plaid, Empower, Rocket Money)
├── cfo_dashboard.py   # Excel financial dashboards
├── doordash.py        # Meal delivery coordination
├── gmail_agent.py     # Email & inbox monitoring
├── web_architect.py   # Website security & n8n deployment
└── website_manager.py # Per-site build/deploy pipelines
```

## MCP Server Endpoints

### JT (Guardian One) — `mcp_server.py`
- **Tools (10):** system_status, list_agents, run_agent, daily_summary, audit_log, pending_reviews, security_audit, vault_health, gateway_status, monitor_health
- **Resources (3):** guardian://config, guardian://agents, guardian://audit/recent
- **Prompts (2):** morning_briefing, security_review
- **Inspect:** `npx @modelcontextprotocol/inspector python mcp_server.py`

### Ryzen — `mcp_server.py`
- **Tools (3):** ping, system_info, echo
- **Resources (1):** ryzen://status
- **Prompts (1):** get_started
- **Inspect:** `npx @modelcontextprotocol/inspector python mcp_server.py`

## Strategic Optimization Tips

- **Information Density:** Use action verbs (Analyze, Verify, Deploy) instead of passive requests
- **Structured Output:** Command agents to respond in JSON format for inter-agent data passing
- **Checkpointing:** Force hard checkpoints every few minutes to prevent context drift
- **Event-Driven Communication:** Treat agents as event producers, not direct state editors — emit structured events (e.g., TaskUpdated) into a log
- **A2A Standards:** Varys and Guardian should use established Agent Communication Protocols (ACP) for standardized messaging
