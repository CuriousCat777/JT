"""Guardian One — Web-based Dev Panel.

Usage:
    python -m guardian_one.web.app          # Start on port 5100
    python main.py --devpanel               # Via CLI
    python main.py --devpanel --port 8080   # Custom port
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from guardian_one.core.config import AgentConfig, load_config
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.audit import Severity
from guardian_one.core.base_agent import AgentStatus

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_guardian: GuardianOne | None = None
_lock = threading.Lock()


def _get_guardian() -> GuardianOne:
    global _guardian
    if _guardian is None:
        with _lock:
            if _guardian is None:
                config = load_config()
                _guardian = GuardianOne(config=config)
                _build_agents(_guardian)
    return _guardian


def _build_agents(guardian: GuardianOne) -> None:
    """Register all agents (mirrors main.py)."""
    from guardian_one.agents.chronos import Chronos
    from guardian_one.agents.archivist import Archivist
    from guardian_one.agents.cfo import CFO
    from guardian_one.agents.doordash import DoorDashAgent
    from guardian_one.agents.gmail_agent import GmailAgent
    from guardian_one.agents.web_architect import WebArchitect
    from guardian_one.agents.device_agent import DeviceAgent
    from guardian_one.homelink.devices import DeviceRegistry
    from guardian_one.homelink.automations import AutomationEngine

    config = guardian.config
    for name, cls, kwargs in [
        ("chronos", Chronos, {}),
        ("archivist", Archivist, {}),
        ("cfo", CFO, {"data_dir": config.data_dir}),
        ("doordash", DoorDashAgent, {}),
        ("gmail", GmailAgent, {"data_dir": config.data_dir}),
        ("web_architect", WebArchitect, {}),
    ]:
        cfg = config.agents.get(name, AgentConfig(name=name))
        guardian.register_agent(cls(config=cfg, audit=guardian.audit, **kwargs))

    # DeviceAgent — smart home device management & automation
    dev_cfg = config.agents.get("device_agent", AgentConfig(
        name="device_agent", enabled=True,
        allowed_resources=["devices", "network"],
    ))
    dev_registry = DeviceRegistry()
    automation_engine = AutomationEngine(audit=guardian.audit)
    dev_agent = DeviceAgent(
        config=dev_cfg, audit=guardian.audit,
        device_registry=dev_registry,
        automation_engine=automation_engine,
    )
    guardian.register_agent(dev_agent)

    # Wire device + automation awareness into HOMELINK Monitor
    from guardian_one.homelink.monitor import Monitor
    guardian.monitor = Monitor(
        gateway=guardian.gateway,
        vault=guardian.vault,
        registry=guardian.registry,
        device_registry=dev_registry,
        automation_engine=automation_engine,
    )


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("panel.html")

    # ------------------------------------------------------------------
    # API — System
    # ------------------------------------------------------------------

    @app.route("/api/status")
    def api_status():
        g = _get_guardian()
        agents = []
        for name in g.list_agents():
            agent = g.get_agent(name)
            if agent is None:
                continue
            agents.append({
                "name": name,
                "status": agent.status.value,
                "enabled": agent.config.enabled,
                "interval_min": agent.config.schedule_interval_minutes,
                "allowed_resources": agent.config.allowed_resources,
            })
        return jsonify({
            "owner": g.config.owner,
            "timezone": g.config.timezone,
            "agents": agents,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ------------------------------------------------------------------
    # API — Agents
    # ------------------------------------------------------------------

    @app.route("/api/agents")
    def api_agents():
        g = _get_guardian()
        result = []
        for name in g.list_agents():
            agent = g.get_agent(name)
            if agent is None:
                continue
            try:
                report = agent.report()
                report_data = {
                    "agent_name": report.agent_name,
                    "status": report.status,
                    "summary": report.summary,
                    "alerts": report.alerts,
                    "recommendations": report.recommendations,
                    "timestamp": report.timestamp,
                }
            except Exception as exc:
                report_data = {"error": str(exc)}
            result.append({
                "name": name,
                "status": agent.status.value,
                "enabled": agent.config.enabled,
                "interval_min": agent.config.schedule_interval_minutes,
                "allowed_resources": agent.config.allowed_resources,
                "report": report_data,
            })
        return jsonify(result)

    @app.route("/api/agents/<name>/run", methods=["POST"])
    def api_run_agent(name: str):
        g = _get_guardian()
        try:
            report = g.run_agent(name)
            return jsonify({
                "agent_name": report.agent_name,
                "status": report.status,
                "summary": report.summary,
                "alerts": report.alerts,
                "recommendations": report.recommendations,
                "actions_taken": report.actions_taken,
                "timestamp": report.timestamp,
            })
        except KeyError:
            return jsonify({"error": f"Unknown agent: {name}"}), 404

    @app.route("/api/agents/run-all", methods=["POST"])
    def api_run_all():
        g = _get_guardian()
        reports = g.run_all()
        return jsonify([
            {
                "agent_name": r.agent_name,
                "status": r.status,
                "summary": r.summary,
                "alerts": r.alerts,
            }
            for r in reports
        ])

    # ------------------------------------------------------------------
    # API — Audit Log
    # ------------------------------------------------------------------

    @app.route("/api/audit")
    def api_audit():
        g = _get_guardian()
        agent_filter = request.args.get("agent")
        severity_filter = request.args.get("severity")
        limit = min(int(request.args.get("limit", 100)), 500)

        sev = None
        if severity_filter:
            try:
                sev = Severity(severity_filter)
            except ValueError:
                pass

        entries = g.audit.query(agent=agent_filter, severity=sev, limit=limit)
        return jsonify([e.to_dict() for e in entries])

    @app.route("/api/audit/pending")
    def api_audit_pending():
        g = _get_guardian()
        entries = g.audit.pending_reviews()
        return jsonify([e.to_dict() for e in entries])

    @app.route("/api/audit/summary")
    def api_audit_summary():
        g = _get_guardian()
        return jsonify({"summary": g.audit.summary(last_n=30)})

    # ------------------------------------------------------------------
    # API — H.O.M.E. L.I.N.K.
    # ------------------------------------------------------------------

    @app.route("/api/homelink/services")
    def api_services():
        g = _get_guardian()
        return jsonify(g.gateway.all_services_status())

    @app.route("/api/homelink/health")
    def api_health():
        g = _get_guardian()
        snapshots = g.monitor.all_health()
        return jsonify([
            {
                "service": s.service,
                "circuit_state": s.circuit_state,
                "success_rate": s.success_rate,
                "avg_latency_ms": s.avg_latency_ms,
                "rate_limit_remaining": s.rate_limit_remaining,
                "risk_score": s.risk_score,
            }
            for s in snapshots
        ])

    @app.route("/api/homelink/anomalies")
    def api_anomalies():
        g = _get_guardian()
        anomalies = g.monitor.detect_anomalies()
        return jsonify([
            {
                "service": a.service,
                "type": a.anomaly_type,
                "description": a.description,
                "severity": a.severity,
                "detected_at": a.detected_at,
            }
            for a in anomalies
        ])

    # ------------------------------------------------------------------
    # API — Vault (metadata only, NO secrets)
    # ------------------------------------------------------------------

    @app.route("/api/vault")
    def api_vault():
        g = _get_guardian()
        health = g.vault.health_report()
        keys = g.vault.list_keys()
        meta = []
        for k in keys:
            m = g.vault.get_meta(k)
            if m:
                meta.append({
                    "key_name": m.key_name,
                    "service": m.service,
                    "scope": m.scope,
                    "created_at": m.created_at,
                    "rotated_at": m.rotated_at,
                    "expires_at": m.expires_at,
                    "rotation_days": m.rotation_days,
                })
        return jsonify({
            "health": health,
            "credentials": meta,
        })

    # ------------------------------------------------------------------
    # API — Registry
    # ------------------------------------------------------------------

    @app.route("/api/registry")
    def api_registry():
        g = _get_guardian()
        integrations = []
        for name in g.registry.list_all():
            record = g.registry.get(name)
            if record is None:
                continue
            integrations.append({
                "name": record.name,
                "description": record.description,
                "base_url": record.base_url,
                "auth_method": record.auth_method,
                "owner_agent": record.owner_agent,
                "status": record.status,
                "threat_count": len(record.threat_model),
                "vault_keys": record.vault_keys,
            })
        return jsonify(integrations)

    @app.route("/api/registry/<name>/threats")
    def api_registry_threats(name: str):
        g = _get_guardian()
        record = g.registry.get(name)
        if record is None:
            return jsonify({"error": f"Unknown integration: {name}"}), 404
        return jsonify({
            "name": record.name,
            "threats": [
                {"risk": t.risk, "severity": t.severity, "mitigation": t.mitigation}
                for t in record.threat_model
            ],
            "failure_impact": record.failure_impact,
            "rollback_procedure": record.rollback_procedure,
        })

    # ------------------------------------------------------------------
    # API — Config (read-only view)
    # ------------------------------------------------------------------

    @app.route("/api/config")
    def api_config():
        g = _get_guardian()
        return jsonify({
            "owner": g.config.owner,
            "timezone": g.config.timezone,
            "daily_summary_hour": g.config.daily_summary_hour,
            "data_dir": g.config.data_dir,
            "log_dir": g.config.log_dir,
            "agents": {
                name: {
                    "enabled": cfg.enabled,
                    "schedule_interval_minutes": cfg.schedule_interval_minutes,
                    "allowed_resources": cfg.allowed_resources,
                }
                for name, cfg in g.config.agents.items()
            },
        })

    # ------------------------------------------------------------------
    # API — Daily Summary
    # ------------------------------------------------------------------

    @app.route("/api/summary")
    def api_summary():
        g = _get_guardian()
        return jsonify({"summary": g.daily_summary()})

    # ------------------------------------------------------------------
    # Chat page
    # ------------------------------------------------------------------

    @app.route("/chat")
    def chat_page():
        return render_template("chat.html")

    # ------------------------------------------------------------------
    # API — Guardian Chat
    # ------------------------------------------------------------------

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        g = _get_guardian()
        body = request.get_json(force=True)
        message = (body.get("message") or "").strip()
        use_ai = body.get("use_ai", False)

        if not message:
            return jsonify({"response": "Say something, Jeremy.", "type": "error"})

        lowered = message.lower()

        # Deterministic command routing
        try:
            if lowered in ("help", "?"):
                return jsonify({"response": _chat_help(), "type": "help"})

            elif lowered == "status":
                return jsonify({"response": g.daily_summary(), "type": "status"})

            elif lowered == "agents":
                lines = []
                for name in g.list_agents():
                    agent = g.get_agent(name)
                    if agent:
                        try:
                            report = agent.report()
                            lines.append(f"{name:20s} [{report.status}] {report.summary[:70]}")
                        except Exception as e:
                            lines.append(f"{name:20s} [error] {e}")
                return jsonify({"response": "\n".join(lines), "type": "agents"})

            elif lowered.startswith("agent "):
                agent_name = message[6:].strip()
                if agent_name in g.list_agents():
                    report = g.run_agent(agent_name)
                    lines = [f"[{report.status}] {report.summary}"]
                    for a in (report.alerts or [])[:5]:
                        lines.append(f"  [ALERT] {a}")
                    for r in (report.recommendations or [])[:5]:
                        lines.append(f"  [REC] {r}")
                    return jsonify({"response": "\n".join(lines), "type": "agent_run"})
                else:
                    return jsonify({
                        "response": f"Unknown agent: {agent_name}\nAvailable: {', '.join(g.list_agents())}",
                        "type": "error",
                    })

            elif lowered == "brief":
                return jsonify({"response": g.monitor.weekly_brief_text(), "type": "brief"})

            elif lowered == "devices":
                dev_agent = g.get_agent("device_agent")
                if dev_agent:
                    report = dev_agent.report()
                    lines = [report.summary]
                    for a in (report.alerts or [])[:10]:
                        lines.append(f"  [ALERT] {a}")
                    return jsonify({"response": "\n".join(lines), "type": "devices"})
                return jsonify({"response": "DeviceAgent not registered.", "type": "error"})

            elif lowered == "rooms":
                dev_agent = g.get_agent("device_agent")
                if dev_agent:
                    rooms = dev_agent.device_registry.room_summary()
                    lines = []
                    for room in rooms:
                        lines.append(f"{room['name']} ({room['type']}) — {room['device_count']} devices")
                        for did in room["device_ids"]:
                            d = dev_agent.device_registry.get(did)
                            if d:
                                lines.append(f"  {d.device_id}: {d.name} [{d.status.value}]")
                    return jsonify({"response": "\n".join(lines), "type": "rooms"})
                return jsonify({"response": "DeviceAgent not registered.", "type": "error"})

            elif lowered.startswith("scene "):
                scene_name = message[6:].strip()
                dev_agent = g.get_agent("device_agent")
                if dev_agent:
                    scene_id = f"scene-{scene_name}" if not scene_name.startswith("scene-") else scene_name
                    results = dev_agent.activate_scene(scene_id)
                    scene = dev_agent.automation.get_scene(scene_id)
                    if scene:
                        lines = [f"Scene activated: {scene.name}", scene.description]
                        for r in results:
                            target = r["device_id"] or r["room_id"]
                            lines.append(f"  -> {r['action']} on {target}")
                        return jsonify({"response": "\n".join(lines), "type": "scene"})
                    else:
                        available = ", ".join(s.scene_id.replace("scene-", "") for s in dev_agent.automation.all_scenes())
                        return jsonify({"response": f"Scene '{scene_name}' not found.\nAvailable: {available}", "type": "error"})
                return jsonify({"response": "DeviceAgent not registered.", "type": "error"})

            elif lowered.startswith("event "):
                event_name = message[6:].strip()
                dev_agent = g.get_agent("device_agent")
                if dev_agent:
                    if event_name in ("sunrise", "sunset"):
                        results = dev_agent.handle_solar_event(event_name)
                    else:
                        results = dev_agent.handle_schedule_event(event_name)
                    lines = [f"Event fired: {event_name}", f"Actions: {len(results)}"]
                    for r in results:
                        target = r["device_id"] or r["room_id"]
                        lines.append(f"  -> {r['action']} on {target}")
                    return jsonify({"response": "\n".join(lines), "type": "event"})
                return jsonify({"response": "DeviceAgent not registered.", "type": "error"})

            elif lowered == "audit":
                dev_agent = g.get_agent("device_agent")
                if dev_agent:
                    audit_result = dev_agent.device_registry.security_audit()
                    lines = [audit_result["summary"]]
                    for issue in audit_result["issues"][:15]:
                        lines.append(f"  [{issue['severity'].upper():8s}] {issue['device']}: {issue['issue']}")
                    return jsonify({"response": "\n".join(lines), "type": "audit"})
                return jsonify({"response": "DeviceAgent not registered.", "type": "error"})

            elif lowered == "homelink":
                services = g.gateway.list_services()
                lines = []
                for svc in services:
                    status = g.gateway.service_status(svc)
                    risk = g.monitor.assess_service(svc).risk_score
                    lines.append(f"{svc:25s} circuit={status['circuit_state']:10s} risk={risk}/5")
                vault_health = g.vault.health_report()
                lines.append(f"\nVault: {vault_health['total_credentials']} credentials")
                return jsonify({"response": "\n".join(lines), "type": "homelink"})

            elif lowered == "reviews":
                pending = g.audit.pending_reviews()
                if pending:
                    lines = [f"{len(pending)} items need your review:"]
                    for entry in pending[:10]:
                        lines.append(f"  [{entry.agent}] {entry.action}")
                    return jsonify({"response": "\n".join(lines), "type": "reviews"})
                return jsonify({"response": "No items pending review.", "type": "reviews"})

            elif lowered.startswith("cfo "):
                from guardian_one.core.command_router import CommandRouter
                router = CommandRouter(g)
                result = router.handle(message[4:].strip())
                text = result.text
                if result.ai_summary:
                    text += f"\n\n{result.ai_summary}"
                return jsonify({"response": text, "type": "cfo"})

            # AI mode — if toggle is on and message doesn't match a command
            elif use_ai:
                try:
                    answer = g.think(message)
                    return jsonify({"response": answer, "type": "ai"})
                except Exception as e:
                    return jsonify({
                        "response": f"AI engine offline: {e}\n\nTry a deterministic command instead. Type 'help' for options.",
                        "type": "error",
                    })

            else:
                # Try CFO router as fallback
                from guardian_one.core.command_router import CommandRouter
                router = CommandRouter(g)
                result = router.handle(message)
                if result.intent.name != "help":
                    text = result.text
                    if result.ai_summary:
                        text += f"\n\n{result.ai_summary}"
                    return jsonify({"response": text, "type": "cfo"})
                return jsonify({
                    "response": f"I don't understand '{message}'.\n\n{_chat_help()}",
                    "type": "help",
                })

        except Exception as exc:
            return jsonify({"response": f"Error: {exc}", "type": "error"})


    def _chat_help() -> str:
        return """Guardian One — Commands:

  status              Full system status
  agents              List all agents
  agent <name>        Run a specific agent
  brief               Weekly H.O.M.E. L.I.N.K. brief
  devices             Device inventory
  rooms               Room layout
  scene <name>        Activate scene (movie/work/away/goodnight)
  event <name>        Fire event (wake/sleep/leave/arrive)
  audit               Device security audit
  homelink            Service status
  reviews             Items needing review
  cfo <question>      Talk to CFO (finances)

With AI toggle ON, type anything and Guardian thinks with AI.
With AI toggle OFF, Guardian uses deterministic commands only."""

    return app


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def run_devpanel(guardian: GuardianOne | None = None, port: int = 5100, debug: bool = False) -> None:
    """Start the dev panel server."""
    global _guardian
    if guardian is not None:
        _guardian = guardian
    app = create_app()
    print(f"\n  Guardian One — Command Center")
    print(f"  http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    run_devpanel(debug=True)
