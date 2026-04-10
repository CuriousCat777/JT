"""GOOS Flask Blueprint — web routes for the Guardian One Operating System.

Provides:
- Health check endpoints (/health, /goos/status)
- Registration and authentication API
- Onboarding flow API
- Client management API
- Varys node registration
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from guardian_one.goos.api import GOOSAPI
from guardian_one.goos.database import GOOSDatabase

goos_bp = Blueprint("goos", __name__, url_prefix="/goos")

_api: GOOSAPI | None = None
_db: GOOSDatabase | None = None
_start_time: float = time.monotonic()


def init_goos(api: GOOSAPI | None = None, db: GOOSDatabase | None = None) -> GOOSAPI:
    """Initialize the GOOS API and database. Called once at app startup."""
    global _api, _db
    _db = db or GOOSDatabase()
    _api = api or GOOSAPI(audit=None)
    # Load persisted clients into the in-memory registry
    _db.load_into_registry(_api.registry)
    return _api


def _get_api() -> GOOSAPI:
    global _api
    if _api is None:
        init_goos()
    assert _api is not None
    return _api


def _get_db() -> GOOSDatabase:
    global _db
    if _db is None:
        init_goos()
    assert _db is not None
    return _db


def _persist_after(fn):
    """Decorator: save registry to SQLite after modifying operations."""
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        api = _get_api()
        db = _get_db()
        db.save_from_registry(api.registry)
        return result
    wrapper.__name__ = fn.__name__
    return wrapper


# ------------------------------------------------------------------
# Health checks (no auth required)
# ------------------------------------------------------------------

@goos_bp.route("/health")
def health():
    """GET /goos/health — basic liveness check."""
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@goos_bp.route("/status")
def platform_status():
    """GET /goos/status — platform status with uptime."""
    api = _get_api()
    uptime = time.monotonic() - _start_time
    status = api.platform_status()
    status["uptime_seconds"] = round(uptime, 1)
    status["database"] = "sqlite"
    status["database_clients"] = _get_db().client_count()
    return jsonify(status)


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------

@goos_bp.route("/register", methods=["POST"])
@_persist_after
def register():
    """POST /goos/register — create a new GOOS account."""
    data = request.get_json(silent=True) or {}
    api = _get_api()
    result = api.register(
        email=data.get("email", ""),
        display_name=data.get("display_name", ""),
        password=data.get("password", ""),
        captcha_token=data.get("captcha_token", ""),
        ip_address=request.remote_addr or "",
        tier=data.get("tier", "free"),
    )
    if result.get("success"):
        return jsonify(result), 201
    return jsonify(result), 400


@goos_bp.route("/verify", methods=["GET"])
@_persist_after
def verify_email():
    """GET /goos/verify?client_id=...&token=... — verify email."""
    client_id = request.args.get("client_id", "")
    token = request.args.get("token", "")
    api = _get_api()
    result = api.verify_email(client_id, token)
    if result.get("success"):
        return jsonify({"message": "Email verified. Welcome to GOOS."})
    return jsonify({"error": "Invalid verification link."}), 400


@goos_bp.route("/login", methods=["POST"])
def login():
    """POST /goos/login — authenticate and get session token."""
    data = request.get_json(silent=True) or {}
    api = _get_api()
    result = api.login(
        email=data.get("email", ""),
        password=data.get("password", ""),
    )
    if result.get("success"):
        # Persist session to database
        db = _get_db()
        db.create_session(
            client_id=result["client_id"],
            session_token=result["session_token"],
            ip_address=request.remote_addr or "",
        )
        return jsonify(result)
    return jsonify(result), 401


# ------------------------------------------------------------------
# Onboarding
# ------------------------------------------------------------------

@goos_bp.route("/onboarding/<client_id>", methods=["GET"])
def get_onboarding(client_id: str):
    """GET /goos/onboarding/:client_id — get current onboarding step."""
    api = _get_api()
    result = api.get_onboarding_step(client_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@goos_bp.route("/onboarding/<client_id>/advance", methods=["POST"])
@_persist_after
def advance_onboarding(client_id: str):
    """POST /goos/onboarding/:client_id/advance — advance to next step."""
    data = request.get_json(silent=True) or {}
    api = _get_api()
    result = api.advance_onboarding(client_id, data=data)
    return jsonify(result)


# ------------------------------------------------------------------
# Client management
# ------------------------------------------------------------------

@goos_bp.route("/client/<client_id>", methods=["GET"])
def get_client(client_id: str):
    """GET /goos/client/:client_id — get client profile."""
    api = _get_api()
    result = api.get_client(client_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@goos_bp.route("/client/<client_id>/varys", methods=["POST"])
@_persist_after
def register_varys(client_id: str):
    """POST /goos/client/:client_id/varys — register a Varys node."""
    data = request.get_json(silent=True) or {}
    api = _get_api()
    result = api.register_varys_node(
        client_id=client_id,
        hostname=data.get("hostname", ""),
        os_type=data.get("os_type", "linux"),
        ip_local=data.get("ip_local", ""),
    )
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 201


@goos_bp.route("/client/<client_id>/offline", methods=["POST"])
@_persist_after
def go_offline(client_id: str):
    """POST /goos/client/:client_id/offline — switch to Varys-only mode."""
    api = _get_api()
    return jsonify(api.set_offline(client_id))


@goos_bp.route("/client/<client_id>/reconnect", methods=["POST"])
@_persist_after
def reconnect(client_id: str):
    """POST /goos/client/:client_id/reconnect — reconnect to Guardian."""
    api = _get_api()
    return jsonify(api.reconnect(client_id))
