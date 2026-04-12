"""Teleprompter API Server — Guardian One integration layer.

Provides REST endpoints for the iOS teleprompter app:
  POST /api/generate-script   — AI script generation
  POST /api/coach              — Real-time advisory coaching
  POST /api/log-encounter      — Log practice/encounter data
  GET  /api/scripts            — List scripts
  GET  /api/scripts/<id>       — Get single script
  POST /api/scripts            — Create script
  PUT  /api/scripts/<id>       — Update script
  DELETE /api/scripts/<id>     — Delete script
  GET  /api/sessions           — Practice session history
  POST /api/sessions/start     — Start practice session
  POST /api/sessions/complete  — Complete practice session
  GET  /api/stats              — Practice statistics
  POST /api/advisory           — Get AI advisory tip
  GET  /api/tips               — Recent advisory tips
  GET  /api/health             — Health check

Auth: Static bearer token authentication using the configured API token.
CORS: Restricted to localhost + the PWA origin.

Run:
    python -m guardian_one.web.teleprompter.server --port 5200
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    teleprompter_agent: Any | None = None,
    api_token: str | None = None,
) -> Flask:
    """Create the Flask app with teleprompter endpoints.

    Args:
        teleprompter_agent: Initialized Teleprompter agent instance.
        api_token: Bearer token for API auth (falls back to env var).
    """
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # Auth token — from arg, env, or auto-generated
    token = api_token or os.environ.get("TELEPROMPTER_API_TOKEN") or secrets.token_urlsafe(32)
    if not api_token and not os.environ.get("TELEPROMPTER_API_TOKEN"):
        print(f"\n  Auto-generated API token: {token}")
        print(f"  Set TELEPROMPTER_API_TOKEN env var to use a persistent token.\n")

    agent = teleprompter_agent

    # ------------------------------------------------------------------
    # CORS middleware
    # ------------------------------------------------------------------
    from urllib.parse import urlparse

    _allowed_schemes = {"http", "https"}
    _allowed_hosts = {"localhost", "127.0.0.1", "[::1]"}

    @app.after_request
    def _cors(response: Response) -> Response:
        origin = request.headers.get("Origin", "")
        # Parse the Origin and match host exactly — a prefix check like
        # origin.startswith("http://localhost") would let "http://localhost.evil.com"
        # through, since attackers can point that DNS name anywhere.
        if origin:
            try:
                parsed = urlparse(origin)
                if (
                    parsed.scheme in _allowed_schemes
                    and parsed.hostname in _allowed_hosts
                ):
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Vary"] = "Origin"
            except ValueError:
                pass
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "3600"
        # Preflight requests get a 204 with no body
        if request.method == "OPTIONS" and response.status_code == 200:
            response.status_code = 204
        return response

    # ------------------------------------------------------------------
    # Auth decorator
    # ------------------------------------------------------------------
    def require_auth(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == "OPTIONS":
                return "", 200
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify({"error": "Missing authorization"}), 401
            provided = auth[7:]
            if not hmac.compare_digest(provided, token):
                return jsonify({"error": "Invalid token"}), 403
            return f(*args, **kwargs)
        return decorated

    def _ensure_agent():
        if agent is None:
            return jsonify({"error": "Teleprompter agent not initialized"}), 503
        return None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service": "teleprompter",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_ready": agent is not None,
        })

    # ------------------------------------------------------------------
    # Script generation (AI)
    # ------------------------------------------------------------------
    @app.route("/api/generate-script", methods=["POST", "OPTIONS"])
    @require_auth
    def generate_script():
        err = _ensure_agent()
        if err:
            return err

        data = request.get_json(silent=True) or {}
        scenario = data.get("scenario", "")
        category = data.get("category", "general")
        chief_complaint = data.get("chief_complaint", "")
        patient_profile = data.get("patient_profile", {})
        setting = data.get("setting", "")
        constraints = data.get("constraints", {})

        if not scenario and chief_complaint:
            # Build scenario from structured input
            age = patient_profile.get("age", "")
            acuity = patient_profile.get("acuity", "")
            complexity = patient_profile.get("complexity", "")
            scenario = f"{chief_complaint}"
            if age:
                scenario = f"{age}-year-old patient with {chief_complaint}"
            if acuity:
                scenario += f", acuity: {acuity}"
            if setting:
                scenario += f", setting: {setting}"
                category = setting if setting in (
                    "admission", "discharge", "consult", "handoff",
                    "bad_news", "informed_consent", "family",
                ) else category
            if constraints.get("time_pressure"):
                scenario += f", time constraint: {constraints['time_pressure']}"
            if constraints.get("language_barrier"):
                scenario += f", language barrier: {constraints['language_barrier']}"

        if not scenario:
            return jsonify({"error": "scenario or chief_complaint required"}), 400

        result = agent.generate_script(scenario=scenario, category=category)
        return jsonify(result)

    # ------------------------------------------------------------------
    # Real-time coaching
    # ------------------------------------------------------------------
    @app.route("/api/coach", methods=["POST", "OPTIONS"])
    @require_auth
    def coach():
        if request.method == "OPTIONS":
            return "", 204
        err = _ensure_agent()
        if err:
            return err

        data = request.get_json(silent=True) or {}
        current_section = data.get("current_section", "")
        transcript_snippet = data.get("transcript", "")
        patient_tone = data.get("patient_tone", "")
        physician_phrasing = data.get("physician_phrasing", "")

        context_parts = []
        if current_section:
            context_parts.append(f"Current script section: {current_section}")
        if patient_tone:
            context_parts.append(f"Patient emotional tone: {patient_tone}")
        if physician_phrasing:
            context_parts.append(f"Physician phrasing: {physician_phrasing}")

        scenario = transcript_snippet or " | ".join(context_parts) or "General telehealth coaching"

        result = agent.get_advisory(
            scenario=scenario,
            context="\n".join(context_parts),
        )

        return jsonify({
            "tip_id": result["tip_id"],
            "rephrase": "",  # Parsed from advice if structured
            "risk_flag": "",
            "optimization": "",
            "full_advice": result["advice"],
            "ai_provider": result.get("ai_provider", ""),
        })

    # ------------------------------------------------------------------
    # Encounter logging
    # ------------------------------------------------------------------
    @app.route("/api/log-encounter", methods=["POST", "OPTIONS"])
    @require_auth
    def log_encounter():
        if request.method == "OPTIONS":
            return "", 204
        err = _ensure_agent()
        if err:
            return err

        data = request.get_json(silent=True) or {}
        required = ["encounter_type", "script_id"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        # Start and immediately complete a practice session
        session = agent.start_practice(data["script_id"])
        if not session:
            return jsonify({"error": "Script not found"}), 404

        result = agent.complete_practice(
            session_id=session["session_id"],
            duration_seconds=data.get("duration_seconds", 0),
            self_rating=data.get("outcome_score", 3),
            notes=json.dumps({
                "encounter_type": data["encounter_type"],
                "complexity_score": data.get("complexity_score", 0),
                "ai_suggestions": data.get("ai_suggestions", ""),
                "notes": data.get("notes", ""),
            }),
        )

        return jsonify({"success": True, "session": result})

    # ------------------------------------------------------------------
    # Scripts CRUD
    # ------------------------------------------------------------------
    @app.route("/api/scripts", methods=["GET"])
    @require_auth
    def list_scripts():
        err = _ensure_agent()
        if err:
            return err
        category = request.args.get("category")
        return jsonify(agent.list_scripts(category=category))

    @app.route("/api/scripts/<script_id>", methods=["GET"])
    @require_auth
    def get_script(script_id: str):
        err = _ensure_agent()
        if err:
            return err
        script = agent.get_script(script_id)
        if not script:
            return jsonify({"error": "Not found"}), 404
        return jsonify(script)

    @app.route("/api/scripts", methods=["POST"])
    @require_auth
    def create_script():
        err = _ensure_agent()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        if not data.get("title") or not data.get("content"):
            return jsonify({"error": "title and content required"}), 400

        result = agent.create_script(
            title=data["title"],
            category=data.get("category", "general"),
            scenario=data.get("scenario", ""),
            content=data["content"],
            tags=data.get("tags", []),
            scroll_speed=data.get("scroll_speed", 3),
        )
        return jsonify(result), 201

    @app.route("/api/scripts/<script_id>", methods=["PUT"])
    @require_auth
    def update_script(script_id: str):
        err = _ensure_agent()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        result = agent.update_script(script_id, data)
        if not result:
            return jsonify({"error": "Not found"}), 404
        return jsonify(result)

    @app.route("/api/scripts/<script_id>", methods=["DELETE"])
    @require_auth
    def delete_script(script_id: str):
        err = _ensure_agent()
        if err:
            return err
        if agent.delete_script(script_id):
            return jsonify({"success": True})
        return jsonify({"error": "Not found"}), 404

    # ------------------------------------------------------------------
    # Practice sessions
    # ------------------------------------------------------------------
    @app.route("/api/sessions", methods=["GET"])
    @require_auth
    def list_sessions():
        err = _ensure_agent()
        if err:
            return err
        script_id = request.args.get("script_id")
        limit_raw = request.args.get("limit", "50")
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "limit must be a valid integer"}), 400
        return jsonify(agent.get_sessions(script_id=script_id, limit=limit))

    @app.route("/api/sessions/start", methods=["POST"])
    @require_auth
    def start_session():
        err = _ensure_agent()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        script_id = data.get("script_id", "")
        if not script_id:
            return jsonify({"error": "script_id required"}), 400
        result = agent.start_practice(script_id)
        if not result:
            return jsonify({"error": "Script not found"}), 404
        return jsonify(result), 201

    @app.route("/api/sessions/complete", methods=["POST"])
    @require_auth
    def complete_session():
        err = _ensure_agent()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id", "")
        if not session_id:
            return jsonify({"error": "session_id required"}), 400
        result = agent.complete_practice(
            session_id=session_id,
            duration_seconds=data.get("duration_seconds", 0),
            self_rating=data.get("self_rating", 3),
            notes=data.get("notes", ""),
        )
        if not result:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(result)

    # ------------------------------------------------------------------
    # Stats & advisory
    # ------------------------------------------------------------------
    @app.route("/api/stats", methods=["GET"])
    @require_auth
    def stats():
        err = _ensure_agent()
        if err:
            return err
        return jsonify(agent.practice_stats())

    @app.route("/api/advisory", methods=["POST"])
    @require_auth
    def advisory():
        err = _ensure_agent()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        scenario = data.get("scenario", "")
        if not scenario:
            return jsonify({"error": "scenario required"}), 400
        result = agent.get_advisory(
            scenario=scenario,
            context=data.get("context", ""),
        )
        return jsonify(result)

    @app.route("/api/tips", methods=["GET"])
    @require_auth
    def tips():
        err = _ensure_agent()
        if err:
            return err
        limit = int(request.args.get("limit", "20"))
        return jsonify(agent.get_tips(limit=limit))

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------
    @app.route("/api/activity", methods=["GET"])
    @require_auth
    def activity_log():
        err = _ensure_agent()
        if err:
            return err
        limit = int(request.args.get("limit", "100"))
        return jsonify(agent.get_activity_log(limit=limit))

    # ------------------------------------------------------------------
    # PWA static files
    # ------------------------------------------------------------------
    @app.route("/")
    def pwa_index():
        static_dir = Path(__file__).parent / "static"
        index = static_dir / "index.html"
        if index.exists():
            return Response(index.read_text(), mimetype="text/html")
        return "<h1>Teleprompter</h1><p>PWA not built yet.</p>"

    @app.route("/manifest.json")
    def manifest():
        static_dir = Path(__file__).parent / "static"
        f = static_dir / "manifest.json"
        if f.exists():
            return Response(f.read_text(), mimetype="application/json")
        return jsonify({"name": "Teleprompter", "short_name": "TelePrompter"})

    @app.route("/sw.js")
    def service_worker():
        static_dir = Path(__file__).parent / "static"
        f = static_dir / "sw.js"
        if f.exists():
            return Response(f.read_text(), mimetype="application/javascript")
        return Response("// no sw", mimetype="application/javascript")

    @app.route("/static/<path:filename>")
    def static_files(filename: str):
        static_dir = Path(__file__).parent / "static"
        filepath = (static_dir / filename).resolve()
        # Prevent path traversal — ensure resolved path stays inside static_dir.
        # Path.is_relative_to handles sibling-prefix bypasses that a bare
        # str.startswith("/a/b/static") would miss (e.g. "/a/b/static-other").
        try:
            filepath.relative_to(static_dir.resolve())
        except ValueError:
            return "Forbidden", 403
        if filepath.exists():
            mime = "text/css" if filename.endswith(".css") else \
                   "application/javascript" if filename.endswith(".js") else \
                   "application/json" if filename.endswith(".json") else \
                   "image/png" if filename.endswith(".png") else \
                   "text/html"
            is_binary = filename.endswith((".png", ".ico", ".jpg", ".gif", ".woff", ".woff2"))
            data = filepath.read_bytes() if is_binary else filepath.read_text()
            return Response(data, mimetype=mime)
        return "Not found", 404

    return app


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def run_teleprompter_server(
    guardian: Any | None = None,
    port: int = 5200,
    api_token: str | None = None,
    host: str = "127.0.0.1",
) -> None:
    """Start the teleprompter API server.

    If guardian is provided, extracts the teleprompter agent.
    Otherwise creates a standalone agent.

    Defaults to binding on 127.0.0.1 so the API is not exposed to the
    network. Pass host="0.0.0.0" (or use --allow-lan on the CLI) only
    when an iPhone PWA or other LAN client needs to reach the server —
    and only on trusted networks. The bearer token is the only line of
    defense once the port is exposed.
    """
    from guardian_one.core.audit import AuditLog
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.teleprompter import Teleprompter

    agent = None
    if guardian:
        agent = guardian.get_agent("teleprompter")

    if agent is None:
        # Standalone mode
        audit = AuditLog(log_dir=Path("logs"))
        cfg = AgentConfig(name="teleprompter", enabled=True,
                          allowed_resources=["scripts", "practice_sessions", "advisory"])
        agent = Teleprompter(config=cfg, audit=audit, data_dir="data")
        if guardian:
            agent.set_ai_engine(guardian.ai_engine)
        agent.initialize()

    app = create_app(teleprompter_agent=agent, api_token=api_token)

    print(f"\n  Teleprompter API Server")
    print(f"  " + "=" * 40)
    print(f"  URL:     http://{host}:{port}")
    print(f"  PWA:     http://localhost:{port}/")
    print(f"  Health:  http://localhost:{port}/api/health")
    print(f"  Scripts: {len(agent.list_scripts())} loaded")
    if host == "0.0.0.0":
        print(f"  WARNING: exposed on all interfaces — bearer token is the")
        print(f"           only gate. Use only on trusted LAN.")
    print(f"  " + "=" * 40)
    print()

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Teleprompter API Server")
    parser.add_argument("--port", type=int, default=5200)
    parser.add_argument("--token", type=str, default=None)
    parser.add_argument(
        "--allow-lan",
        action="store_true",
        help="Bind to 0.0.0.0 so iPhone PWA on the LAN can reach the server "
             "(default: 127.0.0.1 only).",
    )
    args = parser.parse_args()
    run_teleprompter_server(
        port=args.port,
        api_token=args.token,
        host="0.0.0.0" if args.allow_lan else "127.0.0.1",
    )
