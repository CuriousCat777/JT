"""VARYS Flask Blueprint — REST API for security operations.

Endpoints:
    GET  /varys/health         — Liveness check
    GET  /varys/status         — Full VARYS engine status
    GET  /varys/alerts         — Recent alerts with filtering
    GET  /varys/incidents      — Open incidents
    GET  /varys/entities       — High-risk entity profiles
    POST /varys/events         — Ingest external events via webhook
    POST /varys/actions/{id}/approve — Approve a pending response action
    POST /varys/actions/{id}/deny    — Deny a pending response action
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy Flask import to match existing Guardian One web pattern
try:
    from flask import Blueprint, jsonify, request
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False


def create_varys_blueprint(engine: Any) -> Any:
    """Create a Flask Blueprint for VARYS API routes.

    Args:
        engine: A VarysEngine instance.

    Returns:
        Flask Blueprint with VARYS routes registered.
    """
    if not _HAS_FLASK:
        raise ImportError("Flask is required for the VARYS API")

    bp = Blueprint("varys", __name__, url_prefix="/varys")

    @bp.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "varys"})

    @bp.route("/status")
    def status():
        return jsonify(engine.status())

    @bp.route("/alerts")
    def alerts():
        severity = request.args.get("severity")
        limit = request.args.get("limit", 50, type=int)

        all_alerts = []
        for action in engine.response.executed_actions:
            if action.action_type.value == "alert":
                all_alerts.append(action.to_dict())

        # Get alerts from response engine tracking
        alert_list = []
        for incident in engine.response.incidents:
            for alert in incident.alerts:
                d = alert.to_dict()
                if severity and d["severity"] != severity:
                    continue
                alert_list.append(d)

        # Also include non-incident alerts from sigma matches
        # (alerts that didn't escalate to incidents)
        return jsonify({
            "alerts": alert_list[:limit],
            "total": len(alert_list),
        })

    @bp.route("/incidents")
    def incidents():
        status_filter = request.args.get("status")
        items = []
        for incident in engine.response.incidents:
            d = incident.to_dict()
            if status_filter and d["status"] != status_filter:
                continue
            items.append(d)
        return jsonify({"incidents": items, "total": len(items)})

    @bp.route("/entities")
    def entities():
        threshold = request.args.get("threshold", 0.6, type=float)
        high_risk = engine.scorer.get_high_risk_entities(threshold=threshold)
        return jsonify({
            "entities": [e.to_dict() for e in high_risk],
            "total": len(high_risk),
        })

    @bp.route("/events", methods=["POST"])
    def ingest_events():
        """Receive external events via webhook/API."""
        from guardian_one.varys.models import SecurityEvent

        data = request.get_json(silent=True)
        if not data or "events" not in data:
            return jsonify({"error": "Missing 'events' array in body"}), 400

        events = []
        for item in data["events"]:
            events.append(SecurityEvent(
                source=item.get("source", "api"),
                category=item.get("category", ""),
                action=item.get("action", ""),
                outcome=item.get("outcome", ""),
                source_ip=item.get("source_ip", ""),
                source_user=item.get("source_user", ""),
                host_name=item.get("host_name", ""),
                process_command_line=item.get("command_line", ""),
                raw=item,
            ))

        alerts = engine.ingest_events(events)
        return jsonify({
            "accepted": len(events),
            "alerts_generated": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
        })

    @bp.route("/actions/pending")
    def pending_actions():
        return jsonify({
            "actions": [a.to_dict() for a in engine.response.pending_actions],
            "total": len(engine.response.pending_actions),
        })

    @bp.route("/rules")
    def rules():
        return jsonify({
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "severity": r.severity.value,
                    "enabled": r.enabled,
                    "mitre_tactic": r.mitre_tactic,
                    "mitre_technique": r.mitre_technique,
                    "threshold": r.threshold,
                }
                for r in engine.sigma.rules
            ],
            "total": len(engine.sigma.rules),
        })

    return bp
