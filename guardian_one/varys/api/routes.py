"""VARYS API — Flask blueprint for security dashboard endpoints."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from flask import Blueprint, Response, jsonify, request

from guardian_one.varys.api.chat_ui import get_chat_html

if TYPE_CHECKING:
    from guardian_one.varys.agent import VarysAgent

varys_bp = Blueprint("varys", __name__, url_prefix="/api/varys")

# Standalone chat page (no /api prefix)
varys_pages_bp = Blueprint("varys_pages", __name__)


@varys_pages_bp.route("/varys/chat")
def chat_page():
    """Serve the VARYS chatbot UI."""
    return Response(get_chat_html(), content_type="text/html")

# The agent instance is set after app creation
_agent: VarysAgent | None = None


def set_agent(agent: Any) -> None:
    """Inject the VarysAgent instance."""
    global _agent
    _agent = agent


def _require_agent():
    if _agent is None:
        return jsonify({"error": "VARYS agent not initialized"}), 503
    return None


# ── Alerts ────────────────────────────────────────────────────

@varys_bp.route("/alerts")
def list_alerts():
    err = _require_agent()
    if err:
        return err
    severity = request.args.get("severity")
    status = request.args.get("status")
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    alerts = _agent.get_alerts(severity=severity, status=status, page=page, limit=limit)
    return jsonify({"alerts": alerts, "page": page, "limit": limit})


@varys_bp.route("/alerts/<alert_id>")
def get_alert(alert_id: str):
    err = _require_agent()
    if err:
        return err
    alerts = _agent.get_alerts()
    for a in alerts:
        if a["id"] == alert_id:
            return jsonify(a)
    return jsonify({"error": "Alert not found"}), 404


@varys_bp.route("/alerts/<alert_id>/acknowledge", methods=["POST"])
def acknowledge_alert(alert_id: str):
    err = _require_agent()
    if err:
        return err
    if _agent.acknowledge_alert(alert_id):
        return jsonify({"status": "acknowledged"})
    return jsonify({"error": "Alert not found"}), 404


@varys_bp.route("/alerts/<alert_id>/escalate", methods=["POST"])
def escalate_alert(alert_id: str):
    err = _require_agent()
    if err:
        return err
    if _agent.escalate_alert(alert_id):
        return jsonify({"status": "escalated"})
    return jsonify({"error": "Alert not found"}), 404


@varys_bp.route("/alerts/<alert_id>/dismiss", methods=["POST"])
def dismiss_alert(alert_id: str):
    err = _require_agent()
    if err:
        return err
    if _agent.dismiss_alert(alert_id):
        return jsonify({"status": "dismissed"})
    return jsonify({"error": "Alert not found"}), 404


# ── Metrics ───────────────────────────────────────────────────

@varys_bp.route("/metrics/risk-score")
def risk_score():
    err = _require_agent()
    if err:
        return err
    report = _agent.report()
    return jsonify(report.data.get("risk_score", {}))


@varys_bp.route("/metrics/detection-stats")
def detection_stats():
    err = _require_agent()
    if err:
        return err
    report = _agent.report()
    return jsonify({
        "total_alerts": report.data.get("total_alerts", 0),
        "active_alerts": report.data.get("active_alerts", 0),
        "events_processed": report.data.get("events_processed", 0),
    })


# ── Rules ─────────────────────────────────────────────────────

@varys_bp.route("/rules")
def list_rules():
    err = _require_agent()
    if err:
        return err
    return jsonify({"rules": _agent._sigma.get_rules()})


# ── Chat ──────────────────────────────────────────────────────

@varys_bp.route("/chat", methods=["POST"])
def chat():
    """Chat with VARYS — ask security questions, get triage advice."""
    err = _require_agent()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    if not _agent.ai_enabled:
        return jsonify({
            "response": "[VARYS is running in deterministic mode — AI not available]",
            "ai_available": False,
        })

    # Build context from current state
    report = _agent.report()
    context = {
        "active_alerts": report.data.get("active_alerts", 0),
        "risk_score": report.data.get("risk_score", {}),
        "events_processed": report.data.get("events_processed", 0),
    }

    response = _agent.think_quick(
        f"User asks: {message}\n\nCurrent security state: {json.dumps(context)}",
        context=context,
    )

    return jsonify({
        "response": response or "Unable to process request.",
        "ai_available": True,
        "context": context,
    })
