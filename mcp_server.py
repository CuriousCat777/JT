"""Guardian One MCP Server — expose Guardian One capabilities via MCP.

Run with:
    python mcp_server.py                    # stdio transport (default)
    python mcp_server.py --transport sse    # SSE transport on port 8080

Inspect with:
    npx @modelcontextprotocol/inspector python mcp_server.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Bootstrap Guardian One (best-effort — tools degrade gracefully if it fails)
# ---------------------------------------------------------------------------

_guardian = None
_boot_error: str | None = None


def _boot_guardian():
    """Attempt to boot Guardian One.  Returns (guardian, error_string | None)."""
    global _guardian, _boot_error
    if _guardian is not None:
        return
    try:
        # Ensure project root is importable
        project_root = str(Path(__file__).resolve().parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from dotenv import load_dotenv
        load_dotenv()

        from guardian_one.core.config import AgentConfig, load_config
        from guardian_one.core.guardian import GuardianOne
        from guardian_one.agents.chronos import Chronos
        from guardian_one.agents.archivist import Archivist
        from guardian_one.agents.cfo import CFO
        from guardian_one.agents.doordash import DoorDashAgent
        from guardian_one.agents.gmail_agent import GmailAgent
        from guardian_one.agents.web_architect import WebArchitect

        g = GuardianOne()
        cfg = g.config

        for AgentCls, key, extra_kw in [
            (Chronos, "chronos", {}),
            (Archivist, "archivist", {}),
            (CFO, "cfo", {"data_dir": cfg.data_dir}),
            (DoorDashAgent, "doordash", {}),
            (GmailAgent, "gmail", {"data_dir": cfg.data_dir}),
            (WebArchitect, "web_architect", {}),
        ]:
            agent_cfg = cfg.agents.get(key, AgentConfig(name=key))
            g.register_agent(AgentCls(config=agent_cfg, audit=g.audit, **extra_kw))

        _guardian = g
    except Exception as exc:
        _boot_error = f"Guardian One boot failed: {exc}"


_boot_guardian()

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Guardian One",
    instructions=(
        "Guardian One — multi-agent AI orchestration platform for personal "
        "life management. Provides tools for agent management, financial "
        "intelligence, scheduling, security auditing, and device control."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def system_status() -> dict[str, Any]:
    """Get Guardian One system status including registered agents, AI engine,
    H.O.M.E. L.I.N.K. services, and vault health."""
    if _guardian is None:
        return {"error": _boot_error or "Guardian One not initialized"}

    agents_info = {}
    for name, agent in _guardian._agents.items():
        agents_info[name] = {
            "enabled": agent.config.enabled,
            "status": agent.status.value,
        }

    ai_status = _guardian.ai_engine.status()
    vault_health = _guardian.vault.health_report()

    return {
        "owner": _guardian.config.owner,
        "agents": agents_info,
        "ai_engine": {
            "active_provider": ai_status["active_provider"] or "offline",
            "ollama_available": ai_status["ollama"]["available"],
            "anthropic_available": ai_status["anthropic"]["available"],
            "total_requests": ai_status["total_requests"],
        },
        "vault": {
            "total_credentials": vault_health["total_credentials"],
            "due_for_rotation": vault_health["due_for_rotation"],
        },
        "gateway_services": _guardian.gateway.list_services(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def list_agents() -> list[dict[str, Any]]:
    """List all registered Guardian One agents with their current status."""
    if _guardian is None:
        return [{"error": _boot_error or "Guardian One not initialized"}]

    result = []
    for name, agent in _guardian._agents.items():
        result.append({
            "name": name,
            "enabled": agent.config.enabled,
            "status": agent.status.value,
            "allowed_resources": agent.config.allowed_resources,
            "ai_enabled": agent.ai_enabled,
        })
    return result


@mcp.tool()
def run_agent(agent_name: str) -> dict[str, Any]:
    """Run a specific Guardian One agent and return its report.

    Args:
        agent_name: Name of the agent to run (e.g. 'chronos', 'cfo', 'archivist')
    """
    if _guardian is None:
        return {"error": _boot_error or "Guardian One not initialized"}

    try:
        report = _guardian.run_agent(agent_name)
        return {
            "agent_name": report.agent_name,
            "status": report.status,
            "summary": report.summary,
            "actions_taken": report.actions_taken,
            "recommendations": report.recommendations,
            "alerts": report.alerts,
            "timestamp": report.timestamp,
        }
    except KeyError as exc:
        return {"error": str(exc)}


@mcp.tool()
def daily_summary() -> str:
    """Generate the Guardian One daily summary report for the owner."""
    if _guardian is None:
        return _boot_error or "Guardian One not initialized"
    return _guardian.daily_summary()


@mcp.tool()
def audit_log(limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve recent entries from the immutable audit log.

    Args:
        limit: Maximum number of entries to return (default 20)
    """
    if _guardian is None:
        return [{"error": _boot_error or "Guardian One not initialized"}]

    entries = _guardian.audit.recent(limit)
    return [
        {
            "timestamp": e.timestamp,
            "agent": e.agent,
            "action": e.action,
            "severity": e.severity.value if hasattr(e.severity, "value") else str(e.severity),
            "details": e.details,
        }
        for e in entries
    ]


@mcp.tool()
def pending_reviews() -> list[dict[str, Any]]:
    """Get audit entries that require the owner's review."""
    if _guardian is None:
        return [{"error": _boot_error or "Guardian One not initialized"}]

    pending = _guardian.audit.pending_reviews()
    return [
        {
            "timestamp": e.timestamp,
            "agent": e.agent,
            "action": e.action,
            "severity": e.severity.value if hasattr(e.severity, "value") else str(e.severity),
            "details": e.details,
        }
        for e in pending
    ]


@mcp.tool()
def security_audit() -> dict[str, Any]:
    """Run a security audit of Claude connector/MCP attack surface."""
    if _guardian is None:
        return {"error": _boot_error or "Guardian One not initialized"}

    return _guardian.registry.audit()


@mcp.tool()
def vault_health() -> dict[str, Any]:
    """Check the encrypted credential vault health and rotation status."""
    if _guardian is None:
        return {"error": _boot_error or "Guardian One not initialized"}

    return _guardian.vault.health_report()


@mcp.tool()
def gateway_status(service_name: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    """Get H.O.M.E. L.I.N.K. gateway service status.

    Args:
        service_name: Specific service name, or omit for all services.
    """
    if _guardian is None:
        return {"error": _boot_error or "Guardian One not initialized"}

    if service_name:
        return _guardian.gateway.service_status(service_name)

    services = _guardian.gateway.list_services()
    return [
        {"name": svc, **_guardian.gateway.service_status(svc)}
        for svc in services
    ]


@mcp.tool()
def monitor_health() -> dict[str, Any]:
    """Run a full H.O.M.E. L.I.N.K. system health assessment."""
    if _guardian is None:
        return {"error": _boot_error or "Guardian One not initialized"}

    return _guardian.monitor.full_report()


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("guardian://config")
def get_config() -> str:
    """Guardian One system configuration."""
    config_path = Path(__file__).resolve().parent / "config" / "guardian_config.yaml"
    if config_path.exists():
        return config_path.read_text()
    return "Configuration file not found."


@mcp.resource("guardian://agents")
def get_agents_resource() -> str:
    """JSON list of all registered agents and their status."""
    return json.dumps(list_agents(), indent=2)


@mcp.resource("guardian://audit/recent")
def get_recent_audit() -> str:
    """JSON list of the 50 most recent audit log entries."""
    return json.dumps(audit_log(limit=50), indent=2, default=str)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


@mcp.prompt()
def morning_briefing() -> str:
    """Generate a morning briefing prompt for the owner."""
    return (
        "You are Guardian One, Jeremy's personal AI coordinator. "
        "Generate a concise morning briefing covering:\n"
        "1. System status — which agents are running, any alerts\n"
        "2. Today's schedule highlights (from Chronos)\n"
        "3. Financial summary — any bills due, spending alerts\n"
        "4. Security posture — any pending reviews or audit items\n"
        "5. Recommendations for the day\n\n"
        "Use the available tools to gather real-time data before responding."
    )


@mcp.prompt()
def security_review() -> str:
    """Generate a security review prompt."""
    return (
        "You are Guardian One's security analyst. "
        "Run a comprehensive security review covering:\n"
        "1. Connector/MCP attack surface audit\n"
        "2. Vault credential rotation status\n"
        "3. Gateway circuit breaker states\n"
        "4. Any pending security-related audit entries\n\n"
        "Use the security_audit, vault_health, gateway_status, and "
        "pending_reviews tools to gather data."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Guardian One MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport type (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
