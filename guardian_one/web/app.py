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
    print(f"\n  Guardian One Dev Panel")
    print(f"  http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    run_devpanel(debug=True)
